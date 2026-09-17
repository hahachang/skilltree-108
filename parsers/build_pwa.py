"""web/ → docs/：產生可安裝到主畫面的獨立靜態網站（PWA）。

目錄名是 docs/ 而不是 dist/，因為 GitHub Pages 從分支發布時
**只接受根目錄或 /docs**，不吃其他資料夾。

為什麼要另外產生：`web/index.html` 是 artifact 的原始檔，發布時外層的
<!doctype>/<head> 由平台包上去，所以它本身不能有 head。但 PWA 需要
manifest、theme-color 與 service worker 註冊，那些都必須放在 head。
因此 dist/ 由本腳本從 web/ 包裝而成，不重複維護兩份內容。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB, DIST = os.path.join(BASE, "web"), os.path.join(BASE, "docs")
DATA_FILES = ["graph_math.json", "graph_natural.json", "graph_cross.json",
              "handbook_math.json"]
NAME, SHORT = "108課綱技能樹", "技能樹"
THEME_LIGHT, THEME_DARK = "#eef0f6", "#0d1017"

HEAD = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{name}</title>
<meta name="description" content="把 108 課綱的自然科學與數學重構成依賴關係圖，看得出每個技能真正需要先學什麼。">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="{light}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{dark}" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{short}">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="icon" href="icon-192.png">
<style>
:root{{color-scheme:light dark;padding-top:env(safe-area-inset-top,0);
  padding-bottom:env(safe-area-inset-bottom,0)}}
body{{margin:0;font-size:14px}}
img{{max-width:100%}}
[hidden]{{display:none!important}}
</style>
</head>
<body>
"""

TAIL = """
<script>
// 離線快取。網路優先，所以開起來一定是最新版；斷線時退回快取照常運作。
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("sw.js").catch(function () {
      /* 非 https 或不支援時安靜略過，不影響網頁本身 */
    });
  });
}
</script>
</body>
</html>
"""

SW = """// 由 parsers/build_pwa.py 產生，請勿手改。
var CACHE = "skilltree-%(ver)s";
var ASSETS = %(assets)s;

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
"""


def make_icons() -> list[str]:
    """畫一個三節點的依賴圖當圖示：上方一個已點亮的節點，往下連到兩個未完成的。"""
    from PIL import Image, ImageDraw

    out = []
    for size in (192, 512, 180):
        ss = 4                                   # 超取樣，讓圓邊不鋸齒
        img = Image.new("RGBA", (size * ss, size * ss), (13, 16, 23, 255))
        d = ImageDraw.Draw(img)
        s = size * ss

        def circle(cx, cy, r, fill=None, outline=None, w=0):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=w)

        top = (s * 0.5, s * 0.30)
        left = (s * 0.29, s * 0.70)
        right = (s * 0.71, s * 0.70)
        for pt in (left, right):
            d.line([top, pt], fill=(70, 86, 116, 255), width=int(s * 0.028))
        BG = (13, 16, 23, 255)
        circle(top[0], top[1], s * 0.135, fill=(224, 166, 58, 255))
        circle(left[0], left[1], s * 0.105, fill=BG,
               outline=(63, 201, 178, 255), w=int(s * 0.032))
        circle(right[0], right[1], s * 0.105, fill=BG,
               outline=(143, 151, 255, 255), w=int(s * 0.032))

        img = img.resize((size, size), Image.LANCZOS)
        name = f"icon-{size}.png"
        img.save(os.path.join(DIST, name))
        out.append(name)
    return out


def main() -> None:
    os.makedirs(DIST, exist_ok=True)
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        body = f.read()
    # web/index.html 是 artifact 原始檔，本身沒有 head；這裡補上完整外殼
    page = HEAD.format(name=NAME, short=SHORT, light=THEME_LIGHT, dark=THEME_DARK) + body + TAIL
    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    for name in DATA_FILES:
        shutil.copy(os.path.join(WEB, name), os.path.join(DIST, name))

    icons = make_icons()
    manifest = {
        "name": NAME, "short_name": SHORT,
        "description": "把 108 課綱的自然科學與數學重構成依賴關係圖。",
        "lang": "zh-Hant", "dir": "ltr",
        "start_url": "./", "scope": "./", "display": "standalone",
        "orientation": "any",
        "background_color": THEME_DARK, "theme_color": THEME_LIGHT,
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png",
             "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }
    with open(os.path.join(DIST, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    assets = ["./", "index.html", "manifest.webmanifest"] + DATA_FILES + icons
    h = hashlib.sha256()
    for name in ["index.html", "manifest.webmanifest"] + DATA_FILES:
        with open(os.path.join(DIST, name), "rb") as f:
            h.update(f.read())
    with open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8") as f:
        f.write(SW % {"ver": h.hexdigest()[:12], "assets": json.dumps(assets)})

    total = sum(os.path.getsize(os.path.join(DIST, n)) for n in os.listdir(DIST))
    print(f"✓ docs/：{len(os.listdir(DIST))} 個檔案，共 {total / 1024:.0f} KB")
    print(f"  快取版本 skilltree-{h.hexdigest()[:12]}（綁資產內容，改一個字就換新快取）")
    print("  本機驗證：python3 -m http.server --directory docs 8777")


if __name__ == "__main__":
    main()
