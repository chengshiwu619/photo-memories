const preloadedThumbnails = new Set();

function preloadPageThumbnails(payload) {
  if (typeof Image === "undefined") return payload;
  if (preloadedThumbnails.size > 4096) preloadedThumbnails.clear();
  payload.items?.slice(0, 36).forEach((photo) => {
    if (preloadedThumbnails.has(photo.thumbnailUrl)) return;
    preloadedThumbnails.add(photo.thumbnailUrl);
    const image = new Image();
    image.decoding = "async";
    image.src = photo.thumbnailUrl;
  });
  return payload;
}

async function request(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
  return payload;
}

export function getStats() {
  return request("/api/stats");
}

export function getTimelineIndex(category, starredOnly = false) {
  const params = new URLSearchParams({
    category: category === 2 ? "sample" : "life",
    starred: starredOnly ? "1" : "0",
  });
  return request(`/api/timeline-index?${params}`);
}

export function getTimelineLocation(id, category, starredOnly = false) {
  const params = new URLSearchParams({
    id: String(id),
    category: category === 2 ? "sample" : "life",
    starred: starredOnly ? "1" : "0",
  });
  return request(`/api/timeline-location?${params}`);
}

export async function getPhotoPage({ category, mode, starredOnly, pageParam }) {
  const params = new URLSearchParams({
    category: category === 2 ? "sample" : "life",
    mode,
    limit: String(pageParam?.limit || 72),
    offset: String(pageParam?.offset || 0),
    starred: starredOnly ? "1" : "0",
  });
  if (pageParam?.exclude?.length) params.set("exclude", pageParam.exclude.join(","));
  const payload = await request(`/api/photos?${params}`);
  return preloadPageThumbnails(payload);
}

export async function refreshRandomPhotos(category, starredOnly = false) {
  const payload = await post("/api/photos/refresh", {
    category: category === 2 ? "sample" : "life",
    starred: Boolean(starredOnly),
    limit: 72,
  });
  return preloadPageThumbnails(payload);
}

export function getReviewPage({ pageParam }) {
  const params = new URLSearchParams({ limit: "240", offset: String(pageParam?.offset || 0) });
  return request(`/api/review?${params}`);
}

export function getAllReviewIds() {
  return request("/api/review/ids?limit=100000");
}

export function getDeletionPage({ pageParam }) {
  const params = new URLSearchParams({ limit: "240", offset: String(pageParam?.offset || 0) });
  return request(`/api/deletions?${params}`);
}

export function getAllDeletionIds() {
  return request("/api/deletions/ids?limit=100000");
}

export function getPhotoContext(id, category, starredOnly = false) {
  const params = new URLSearchParams({
    id: String(id),
    category: category === 2 ? "sample" : "life",
    before: "120",
    after: "120",
    starred: starredOnly ? "1" : "0",
  });
  return request(`/api/photo-context?${params}`);
}

function post(url, payload) {
  return request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function setCategory(ids, category) {
  return post("/api/category", { ids, category });
}

export function markReviewSample(ids) {
  return post("/api/review/sample", { ids });
}

export function dismissReview(ids) {
  return post("/api/review/dismiss", { ids });
}

export function setStarred(id, starred) {
  return post("/api/star", { id, starred });
}

export function setStarredMany(ids, starred) {
  return post("/api/star", { ids, starred });
}

export function queueDeletion(ids) {
  return post("/api/deletions/queue", { ids });
}

export function restoreDeletion(ids) {
  return post("/api/deletions/restore", { ids });
}

export function deleteOriginals(ids) {
  return post("/api/deletions/delete-originals", { ids, confirmation: "DELETE_ORIGINALS" });
}
