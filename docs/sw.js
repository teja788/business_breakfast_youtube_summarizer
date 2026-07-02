/* Service worker: offline support for the static dashboard.
   - Pinned cross-origin CDN libs (immutable URLs): cache-first.
   - Same-origin shell + data: stale-while-revalidate (instant load, self-updating;
     data JSON is keyed by pathname so ?v= versions don't pile up in the cache). */
"use strict";

const VERSION = "bb-cache-v2";
const PRECACHE = [
  "./", "./index.html", "./app.js", "./styles.css", "./manifest.json",
  "https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js",
  "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js",
  "https://cdn.jsdelivr.net/npm/minisearch@7.1.0/dist/umd/index.min.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    (async () => {
      const c = await caches.open(VERSION);
      await Promise.allSettled(PRECACHE.map((u) => c.add(u))); // best-effort; never fail install
      self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) {
    e.respondWith(cacheFirst(req)); // pinned, immutable CDN libs
  } else if (url.pathname.endsWith(".json")) {
    // meta.json (the version pointer) + versioned data: ALWAYS fresh when online
    // so ?v= cache-busting isn't defeated; fall back to cache only offline.
    e.respondWith(networkFirst(req));
  } else {
    // app shell (html/js/css): instant from cache, self-updating next load.
    e.respondWith(staleWhileRevalidate(req));
  }
});

const pathKey = (req) => new Request(new URL(req.url).pathname); // ignore ?v= → one entry/file

// Last-resort offline fallback: index.html only for navigations; anything else
// gets a clean 503 JSON so res.ok checks fail instead of res.json() choking on HTML.
async function offlineFallback(req, c) {
  if (req.mode === "navigate" || req.destination === "document") {
    return (await c.match("./index.html")) || Response.error();
  }
  return new Response(JSON.stringify({ offline: true }), {
    status: 503,
    headers: { "Content-Type": "application/json" },
  });
}

async function cacheFirst(req) {
  const c = await caches.open(VERSION);
  const hit = await c.match(req, { ignoreSearch: true });
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && res.ok) c.put(req, res.clone());
    return res;
  } catch (err) {
    return hit || Response.error();
  }
}

async function networkFirst(req) {
  const c = await caches.open(VERSION);
  const key = pathKey(req);
  try {
    const res = await fetch(req);
    if (res && res.ok) c.put(key, res.clone());
    return res;
  } catch (err) {
    return (await c.match(key)) || (await offlineFallback(req, c));
  }
}

async function staleWhileRevalidate(req) {
  const c = await caches.open(VERSION);
  const key = pathKey(req);
  const hit = await c.match(key);
  const net = fetch(req)
    .then((res) => {
      if (res && res.ok) c.put(key, res.clone());
      return res;
    })
    .catch(() => null);
  return hit || (await net) || (await offlineFallback(req, c));
}
