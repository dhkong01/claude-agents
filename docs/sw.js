const CACHE = 'stock-pwa-v4';
// 아이콘·manifest만 캐시, HTML/JS는 항상 네트워크 우선
const PRECACHE = ['/claude-agents/icon-192.svg', '/claude-agents/icon-512.svg', '/claude-agents/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  const path = url.pathname;

  // data/ → 네트워크 우선 (항상 최신), 실패 시 캐시
  if (path.includes('/data/')) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // index.html / sw.js → 항상 네트워크 (캐시 사용 안 함)
  if (path.endsWith('.html') || path.endsWith('.js') || path === '/claude-agents/' || path === '/claude-agents') {
    e.respondWith(fetch(e.request));
    return;
  }

  // 아이콘·manifest → 캐시 우선
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
