/* Service Worker：预缓存应用外壳，其余资源运行时缓存。
   数据集有 100KB 级，缓存后离线可用。 */

// 改版本号即令旧缓存失效：activate 会清掉非当前版本的 cache
const CACHE = "jieshu-demo-v6";

const SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./manifest.webmanifest",
  "./assets/ui/main.js",
  "./assets/engine/index.js",
  "./assets/data/dataset.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      // 逐条添加：任一资源缺失不应让整个安装失败
      await Promise.all(
        SHELL.map((url) => cache.add(url).catch(() => undefined)),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  event.respondWith(
    (async () => {
      const hit = await caches.match(req);
      if (hit !== undefined) return hit;
      try {
        const res = await fetch(req);
        if (res.ok && new URL(req.url).origin === self.location.origin) {
          const cache = await caches.open(CACHE);
          void cache.put(req, res.clone());
        }
        return res;
      } catch {
        return new Response("", { status: 504, statusText: "offline" });
      }
    })(),
  );
});
