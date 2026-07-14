const KEY = 'vkr_seen_comment';

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}'); }
  catch { return {}; }
}

export function markSeen(docId) {
  const map = load();
  map[docId] = new Date().toISOString();
  localStorage.setItem(KEY, JSON.stringify(map));
}

export function hasUnread(doc) {
  if (!doc?.last_comment_at) return false;
  const map = load();
  const seen = map[doc.id];
  if (!seen) return true;
  return new Date(doc.last_comment_at) > new Date(seen);
}
