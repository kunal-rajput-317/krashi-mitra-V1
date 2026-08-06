// v6 is a forced purge, not just a version bump: v5 caches can hold one
// farmer's /profile response (see the fetch handler below), and the activate
// step deletes every cache that isn't the current name.
const CACHE_NAME = 'krashimitra-v6'; // v6: never cache authenticated API responses; v5: mandi.html retired, mandi data lives on /bhav; v4: shared analytics.js (GA4 + Clarity); v3: web push (mandi bhav alerts); v2: bell → KrashiBook
const ASSETS_TO_CACHE = [
  './',
  './analytics.js',
  './index.html',
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

// A page navigation — the only thing that gets the network-first HTML treatment.
function isPageRequest(request) {
  return request.mode === 'navigate' || request.destination === 'document';
}

// Is this a plain static file, safe to serve to anybody from a URL-keyed cache?
//
// This distinction is the whole point of the guard. The Render host serves the
// site AND the API from one origin (backend/main.py mounts frontend/ at "/"),
// and so does uvicorn on :8000 in development — so /profile, /alerts and every
// other per-user endpoint is a same-origin GET here, exactly like a stylesheet.
// The old rule ("not text/html → cache-first") therefore cached one farmer's
// /profile response under the URL alone, with no regard for the Authorization
// header that produced it, and replayed it to the next account signed in on the
// same phone. Logging into a second account showed the first account's name,
// village and crops, and no amount of re-fetching could shift it, because the
// re-fetch was answered by the cache too.
//
// `destination` is what separates them: a stylesheet is "style", an image is
// "image", and a fetch()/XHR call — every API call this app makes — is "".
function isStaticAsset(request) {
  // Anything carrying a session is per-user by definition, whatever it looks like.
  if (request.headers.get('Authorization')) return false;
  const d = request.destination;
  return d === 'style' || d === 'script' || d === 'image' ||
         d === 'font'  || d === 'manifest';
}

// Fetch Event
self.addEventListener('fetch', (event) => {
  const request    = event.request;
  const requestUrl = new URL(request.url);

  // Exclude other origins (incl. the cross-origin backend and analytics) and
  // anything that isn't a plain GET.
  if (
    requestUrl.origin !== self.location.origin ||
    request.method !== 'GET' ||
    requestUrl.pathname.includes('/api') ||
    request.url.includes('google-analytics') ||
    request.url.includes('googletagmanager')
  ) {
    return;
  }

  // Network-First with Cache-Fallback for pages (dynamic data stays fresh, still works offline)
  if (isPageRequest(request)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Clone response and save to cache
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
          return response;
        })
        .catch(() => {
          // If network fails, serve from cache
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Fallback for pages not in cache
            return caches.match('./index.html');
          });
        })
    );
    return;
  }

  // Cache-First / Network-Fallback for assets (CSS, JS, Images, Fonts)
  if (isStaticAsset(request)) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(request).then((response) => {
          // Cache new asset response
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
          return response;
        });
      })
    );
    return;
  }

  // Everything else — API calls above all — goes straight to the network,
  // untouched and uncached.
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
