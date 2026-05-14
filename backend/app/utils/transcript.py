import logging
import multiprocessing
import os
import signal
import ssl
import subprocess
import tempfile
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

WHISPER_MODEL_CACHE: dict[str, object] = {}

# Corporate environments often use self-signed certs / MITM proxies.
# Disable SSL verification globally for urllib (used by Whisper model downloads).
ssl._create_default_https_context = ssl._create_unverified_context


def download_audio(url: str, output_dir: str | None = None) -> str:
    """Download audio from a URL using yt-dlp. Returns path to downloaded file."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ainews_audio_")
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--no-playlist",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        # Fallback: direct HTTP download for MP3/audio URLs
        downloaded = _direct_download(url, output_dir)
        if downloaded:
            return downloaded
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:500]}")

    mp3_files = list(Path(output_dir).glob("*.mp3"))
    if not mp3_files:
        all_files = list(Path(output_dir).iterdir())
        if all_files:
            return str(all_files[0])
        raise RuntimeError("No audio file produced by yt-dlp")
    return str(mp3_files[0])


def _strip_tracking_prefixes(url: str) -> list[str]:
    """Extract the actual audio CDN URL by stripping tracking/redirect prefixes."""
    import re
    urls = [url]
    # Spotify prefix: https://prfx.byspotify.com/e/play.podtrac.com/xxx/actual-host.com/path
    # podtrac prefix: https://play.podtrac.com/xxx/actual-host.com/path
    for pattern in [
        r"(?:https?://)?(?:prfx\.byspotify\.com/e/)?(?:play\.podtrac\.com/[^/]+/)(.+)",
        r"(?:https?://)?(?:pdst\.fm/e/)(.+)",
        r"(?:https?://)?(?:traffic\.megaphone\.fm/)(.+)",
    ]:
        m = re.search(pattern, url)
        if m:
            inner = m.group(1)
            if not inner.startswith("http"):
                inner = "https://" + inner
            urls.insert(0, inner)
    return urls


def _direct_download(url: str, output_dir: str) -> str | None:
    """Fallback: download audio file directly via HTTP when yt-dlp fails."""
    import hashlib
    candidate_urls = _strip_tracking_prefixes(url)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for try_url in candidate_urls:
        try:
            req = urllib.request.Request(try_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "audio" not in content_type and "octet-stream" not in content_type:
                    continue
                fname = hashlib.md5(try_url.encode()).hexdigest()[:12] + ".mp3"
                out_path = os.path.join(output_dir, fname)
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                if os.path.getsize(out_path) > 1000:
                    logger.info("Direct download succeeded from %s", try_url[:80])
                    return out_path
        except Exception:
            logger.debug("Direct download failed for %s", try_url[:80])
    return None


def transcribe_audio(audio_path: str, language: str = "en") -> str:
    """Transcribe audio file using OpenAI Whisper. Returns transcript text."""
    import whisper

    model_size = "tiny" if language == "en" else "small"
    if model_size not in WHISPER_MODEL_CACHE:
        WHISPER_MODEL_CACHE[model_size] = whisper.load_model(model_size)
    model = WHISPER_MODEL_CACHE[model_size]

    result = model.transcribe(audio_path, language=language if language != "cn" else "zh")
    return result.get("text", "")


def _transcribe_in_process(audio_path: str, language: str, result_queue: multiprocessing.Queue):
    """Target function for child process. Runs Whisper and puts result in queue."""
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        text = transcribe_audio(audio_path, language=language)
        result_queue.put(("ok", text))
    except Exception as e:
        result_queue.put(("error", str(e)))


def transcribe_audio_with_timeout(audio_path: str, language: str = "en", timeout: int = 300) -> str:
    """Transcribe audio in a child process with a hard kill timeout.

    Unlike ThreadPoolExecutor, multiprocessing.Process.terminate() sends SIGTERM
    to the child, which actually kills native C/PyTorch Whisper code.

    Returns transcript text. Raises RuntimeError on timeout or failure.
    """
    result_queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_transcribe_in_process,
        args=(audio_path, language, result_queue),
    )
    proc.start()
    logger.info("Whisper process started (PID %d, timeout=%ds)", proc.pid, timeout)
    proc.join(timeout=timeout)

    if proc.is_alive():
        logger.error("Whisper process timed out after %ds — killing PID %d", timeout, proc.pid)
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()  # SIGKILL as last resort
            proc.join(timeout=5)
        raise RuntimeError(f"Whisper transcription timed out after {timeout}s")

    if proc.exitcode != 0:
        raise RuntimeError(f"Whisper process exited with code {proc.exitcode}")

    try:
        status, payload = result_queue.get_nowait()
    except Exception:
        raise RuntimeError("Whisper process completed but produced no result")

    if status == "error":
        raise RuntimeError(f"Whisper transcription failed: {payload}")

    return payload


def get_youtube_transcript(video_url: str) -> str | None:
    """Try to get a YouTube transcript via the transcript API. Returns None if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        import re

        match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", video_url)
        if not match:
            return None
        video_id = match.group(1)

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(["en", "zh-Hans", "zh-Hant", "zh"])
        except Exception:
            transcript = transcript_list.find_generated_transcript(["en", "zh-Hans", "zh-Hant", "zh"])

        parts = transcript.fetch()
        return " ".join(p.get("text", p) if isinstance(p, dict) else str(p) for p in parts)
    except Exception:
        logger.debug("YouTube transcript not available for %s", video_url)
        return None


def cleanup_audio(audio_path: str) -> None:
    """Remove a downloaded audio file and its parent temp dir if empty."""
    try:
        p = Path(audio_path)
        p.unlink(missing_ok=True)
        parent = p.parent
        if parent.name.startswith("ainews_audio_") and not list(parent.iterdir()):
            parent.rmdir()
    except Exception:
        pass
