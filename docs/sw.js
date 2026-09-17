// 由 parsers/build_pwa.py 產生，請勿手改。
var CACHE = "skilltree-1a47fdbe6d9f";
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
  e.respondWith(
    Promise.race([
      fetch(e.request).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return res;
      }),
      new Promise(function (_, reject) {
        // 斷線時 fetch 會直接 reject；這道逾時是為了「連得上但拿不到資料」的情況
        setTimeout(reject, 3000, new Error("timeout"));
      })
    ]).catch(function () {
      return caches.match(e.request).then(function (hit) {
        return hit || caches.match("index.html");
      });
    })
  );
});
