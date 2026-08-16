const CACHE = 'news-app-v1';
// 아이콘·manifest만 캐시, HTML/JS/data는 항상 네트워크 우선
const PRECACHE = ['/claude-agents/news-app/icon-192.svg', '/claude-agents/news-app/icon-512.svg', '/claude-agents/news-app/manifest.json'];

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

  // data/ → CDN 캐시 완전 우회 (cache: 'reload')
  if (path.includes('/data/')) {
    e.respondWith(
      fetch(e.request, { cache: 'reload' }).catch(() => caches.match(e.request))
    );
    return;
  }

  // index.html / JS → CDN 캐시 완전 우회 (cache: 'reload')
  if (path.endsWith('.html') || path.endsWith('.js') || path === '/claude-agents/news-app/' || path === '/claude-agents/news-app') {
    e.respondWith(fetch(new Request(e.request, { cache: 'reload' })));
    return;
  }

  // 아이콘·매니페스트 → 캐시 우선
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
