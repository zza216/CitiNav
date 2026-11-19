// CitiNav service worker — cache the app shell so it installs and loads offline.
const CACHE = "citinav-v8";
const ASSETS = [
  "./",
  "./index.html",
  "./test.html",
  "./street.js",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;

  // The app's own files: network first, so a new version shows up on the next
  // load (no URL tricks or cache bumps needed). Fall back to the cache offline.
  if (new URL(e.request.url).origin === self.location.origin) {
    e.respondWith(
      // cache: "no-cache" makes the browser revalidate with the server instead
      // of trusting its HTTP cache (cheap 304 when nothing changed).
      fetch(e.request, { cache: "no-cache" })
        .then((resp) => {
          if (resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => caches.match(e.request, { ignoreSearch: true })
          .then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  // Third-party files (Leaflet, map tiles): cache first.
  e.respondWith(
    caches.match(e.request).then((hit) => {
      if (hit) return hit;
      return fetch(e.request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match("./index.html"));
    })
  );
});
