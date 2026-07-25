const CACHE_NAME = 'krashimitra-v3'; // v3: web push (mandi bhav alerts); v2: bell → KrashiBook
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './mandi.html',
  './weather.html',
  './shop.html',
  './chat.html',
  './sarkari_yojana.html',
  './krashi_bajar.html',
  './khoj.html',
  './about.html',
  './help.html',
  './privacy-policy.html',
  './assets/logo.png',
  './assets/krashimitra_logo.png',
  './assets/logo-192.png',
  './assets/logo-512.png',
  './assets/favicon.ico'
];

// Install Event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Pre-caching offline assets');
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

// Activate Event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('[Service Worker] Clearing old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Exclude external API requests (FastAPI backend and analytics)
  if (
    requestUrl.origin !== self.location.origin ||
    event.request.method !== 'GET' ||
    requestUrl.pathname.includes('/api') ||
    event.request.url.includes('google-analytics') ||
    event.request.url.includes('googletagmanager')
  ) {
    return;
  }

  // Network-First with Cache-Fallback for HTML pages (ensures dynamic data stays fresh, but works offline)
  if (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Clone response and save to cache
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
          return response;
        })
        .catch(() => {
          // If network fails, serve from cache
          return caches.match(event.request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Fallback for pages not in cache
            return caches.match('./index.html');
          });
        })
    );
  } else {
    // Cache-First / Network-Fallback for assets (CSS, JS, Images, Fonts)
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((response) => {
          // Cache new asset response
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
          return response;
        });
      })
    );
  }
});

// ══════════════════════════════════════════════════════════
// WEB PUSH — mandi bhav alerts (🔔 toggle on /bhav pages)
// The server sends {title, body, url, tag}; we render it and, on click,
// focus an already-open tab for that URL instead of opening a duplicate.
// ══════════════════════════════════════════════════════════
self.addEventListener('push', (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; }
  catch (e) { d = { body: event.data ? event.data.text() : '' }; }

  event.waitUntil(
    self.registration.showNotification(d.title || 'कृषि मित्र — मंडी भाव', {
      body:     d.body || '',
      icon:     d.icon  || '/assets/logo-192.png',
      badge:    d.badge || '/assets/logo-192.png',
      tag:      d.tag   || 'mandi-bhav',
      renotify: true,
      data:     { url: d.url || '/' }
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url === url && 'focus' in w) return w.focus();
      }
      return self.clients.openWindow ? self.clients.openWindow(url) : null;
    })
  );
});
