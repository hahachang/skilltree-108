// 由 parsers/build_pwa.py 產生，請勿手改。
var CACHE = "skilltree-7df21a9a38eb";
var ASSETS = ["./", "index.html", "manifest.webmanifest", "graph_math.json", "graph_natural.json", "graph_cross.json", "icon-192.png", "icon-512.png", "icon-180.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(ASSETS); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  // 版本號綁資產內容雜湊，內容一改就換新快取並清掉舊的
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  e.respondWith(caches.match(e.request).then(function (hit) {
    return hit || fetch(e.request);
  }));
});
