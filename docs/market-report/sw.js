/* 마켓리포트 서비스워커 (scope: /market-report/)
 * - 앱 셸·CDN 라이브러리: 네트워크 우선, 실패(오프라인) 시 캐시 — 배포 직후에도 항상 최신 코드를 받는다.
 * - 데이터 JSON: 네트워크 우선(HTTP 캐시 우회), 오프라인이면 마지막으로 받은 값 */
const CACHE = 'market-report-v1';
const SHELL = [
  './', 'index.html', 'manifest.webmanifest', 'css/style.css',
  'js/data.js', 'js/live.js', 'js/charts.js', 'js/globe.js', 'js/app.js',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png',
];
const CDN = ['cdn.jsdelivr.net'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function networkFirst(req, opts) {
  return fetch(req, opts).then(function (res) {
    if (res && res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then(function (c) { c.put(req, copy); });
    }
    return res;
  }).catch(function () {
    return caches.match(req, { ignoreSearch: true });
  });
}

self.addEventListener('fetch', function (e) {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  if (!sameOrigin && CDN.indexOf(url.hostname) < 0) return;

  // 데이터: CDN/HTTP 캐시를 우회해 항상 새 값을 시도
  if (sameOrigin && url.pathname.indexOf('/data/') >= 0) {
    e.respondWith(networkFirst(req, { cache: 'reload' }));
    return;
  }
  e.respondWith(networkFirst(req));
});
