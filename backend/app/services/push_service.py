import json
import logging

from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import PushSubscription

logger = logging.getLogger(__name__)


def send_push_to_all(db: Session, title: str, body: str, url: str = "/") -> int:
    """Send a web push notification to all subscribers. Returns count of successful sends."""
    settings = get_settings()
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.warning("VAPID keys not configured, skipping push notifications")
        return 0

    subs = db.query(PushSubscription).all()
    success_count = 0

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/icon-192.png",
    })

    vapid_claims = {
        "sub": f"mailto:{settings.vapid_contact_email}",
    }

    for sub in subs:
        try:
            keys = json.loads(sub.keys_json)
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": keys,
            }
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=vapid_claims,
            )
            success_count += 1
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                logger.info("Removing stale subscription: %s", sub.endpoint[:50])
                db.delete(sub)
                db.commit()
            else:
                logger.warning("Push failed for %s: %s", sub.endpoint[:50], str(e)[:200])
        except Exception:
            logger.exception("Push error for %s", sub.endpoint[:50])

    return success_count
