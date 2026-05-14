import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export const fetchDigests = (skip = 0, limit = 20) =>
  api.get("/digests", { params: { skip, limit } }).then((r) => r.data);

export const fetchLatestDigest = () =>
  api.get("/digests/latest").then((r) => r.data);

export const fetchDigest = (id) =>
  api.get(`/digests/${id}`).then((r) => r.data);

export const fetchPodcasts = () =>
  api.get("/podcasts").then((r) => r.data);

export const fetchPodcastEpisodes = (name, skip = 0, limit = 20) =>
  api.get(`/podcasts/${encodeURIComponent(name)}/episodes`, { params: { skip, limit } }).then((r) => r.data);

export const fetchEpisode = (id) =>
  api.get(`/podcasts/episodes/${id}`).then((r) => r.data);

export const submitMedia = (url, title = "") =>
  api.post("/media/summarize", { url, title }).then((r) => r.data);

export const fetchMediaList = (skip = 0, limit = 20) =>
  api.get("/media", { params: { skip, limit } }).then((r) => r.data);

export const fetchMedia = (id) =>
  api.get(`/media/${id}`).then((r) => r.data);

export const deleteMedia = (id) =>
  api.delete(`/media/${id}`).then((r) => r.data);

export const fetchLivestreams = (account = "", skip = 0, limit = 20) =>
  api.get("/livestreams", { params: { account, skip, limit } }).then((r) => r.data);

export const fetchLivestream = (id) =>
  api.get(`/livestreams/${id}`).then((r) => r.data);

export const submitLivestream = (url, title = "") =>
  api.post("/livestreams/summarize", { url, title }).then((r) => r.data);

export const fetchLivestreamAccounts = () =>
  api.get("/livestreams/accounts").then((r) => r.data);

// Feedback
export const submitFeedback = (digestId, articleTitle, helpful) =>
  api.post("/feedback", { digest_id: digestId, article_title: articleTitle, helpful }).then((r) => r.data);

export const fetchFeedback = (digestId) =>
  api.get("/feedback", { params: { digest_id: digestId } }).then((r) => r.data);

// Predictions
export const fetchPredictions = (skip = 0, limit = 30) =>
  api.get("/predictions", { params: { skip, limit } }).then((r) => r.data);

export const fetchLatestPrediction = () =>
  api.get("/predictions/latest").then((r) => r.data);

export const fetchPredictionAccuracy = () =>
  api.get("/predictions/accuracy").then((r) => r.data);

// Speeches (Elon Musk, Jensen Huang)
export const fetchSpeeches = (personality = "", skip = 0, limit = 20) =>
  api.get("/speeches", { params: { personality, skip, limit } }).then((r) => r.data);

export const fetchPersonalities = () =>
  api.get("/speeches/personalities").then((r) => r.data);

export const deleteSpeech = (id) =>
  api.delete(`/speeches/${id}`).then((r) => r.data);

export const deleteEpisode = (id) =>
  api.delete(`/podcasts/episodes/${id}`).then((r) => r.data);

// Admin - digest generation
export const triggerDigest = (force = false) =>
  api.post(`/admin/run-digest?force=${force}`).then((r) => r.data);

export const fetchDigestStatus = () =>
  api.get("/admin/digest-status").then((r) => r.data);

export const cancelDigest = () =>
  api.post("/admin/cancel-digest").then((r) => r.data);

// Push
export const getVapidKey = () =>
  api.get("/push/vapid-public-key").then((r) => r.data.public_key);

export const subscribePush = (endpoint, keys) =>
  api.post("/push/subscribe", { endpoint, keys }).then((r) => r.data);

export const unsubscribePush = (endpoint, keys) =>
  api.delete("/push/subscribe", { data: { endpoint, keys } }).then((r) => r.data);

export default api;
