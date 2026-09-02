/* Jarvis HUD service worker — caches only the static app shell so the page
 * launches instantly and shows a clean offline state. All live data (the
 * bridge API, the token config, the vault markdown, the voicemode logs) is
 * always fetched from the network and never cached. */

const CACHE = 'jarvis-shell-v1';
const SHELL = [
  './',
  'index.html',
  'manifest.webmanifest',
  'icon-192.png',
  'icon-512.png',
  'icon-maskable.png',
  'favicon-32.png',
];

// Never intercept/cache these — they must always hit the network.
const BYPASS = [
  /\/chat(\/|$|\?)/,
  /\/voice(\/|$|\?)/,
  /\/events/,
  /\/version/,
  /\/devices/,
  /\/register/,
  /jarvis-config\.js/,
  /\/vault\//,
  /voicemode-logs/,
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (BYPASS.some((re) => re.test(url.pathname + url.search))) return;

  // Navigation: network-first (so the version auto-reload always gets fresh
  // HTML), fall back to the cached shell when offline.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const clone = r.clone();
          caches.open(CACHE).then((c) => c.put('index.html', clone)).catch(() => {});
          return r;
        })
        .catch(() => caches.match('index.html').then((r) => r || caches.match('./')))
    );
    return;
  }

  // Static assets: cache-first, refreshed in the background.
  e.respondWith(
    caches.match(req).then((cached) => {
      const net = fetch(req)
        .then((r) => {
          if (r && r.ok && r.type === 'basic') {
            const clone = r.clone();
            caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
          }
          return r;
        })
        .catch(() => cached);
      return cached || net;
    })
  );
});
