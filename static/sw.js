const CACHE = "just2sale-shell-v3";
const SHELL = [
  "/caja/",
  "/static/css/app.css",
  "/static/js/money.js",
  "/static/js/offline.js",
  "/static/js/session.js",
  "/static/js/print.js",
  "/static/favicon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "wipe") return;
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key.indexOf("just2sale") === 0).map((key) => caches.delete(key))))
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;
  const shell = url.pathname.startsWith("/static/") || url.pathname === "/caja/" || url.pathname === "/sw.js";
  if (!shell) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/caja/")))
  );
});
