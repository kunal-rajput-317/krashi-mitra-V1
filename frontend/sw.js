// v7 is a forced purge, like v6 before it: caches written during the 11 Aug 2026
// outage hold Netlify's `{"error":"usage_exceeded"}` 503 under the URL of a real
// page or stylesheet, and the activate step deletes every cache that isn't the
// current name.
const CACHE_NAME = 'krashimitra-v9'; // v9: ads.js shipped, but drawer-menu.js (which bootstraps it) is referenced without a ?v= query from the articles and the static pages, so cache-first kept handing returning phones the pre-ads copy and no ad ever rendered for them; // v8: backend moved to a new Render host — every returning browser held a cache-first api-config.js pointing at the dead one; v7: never cache a failed response; v6: never cache authenticated API responses; v5: mandi.html retired, mandi data lives on /bhav; v4: shared analytics.js (GA4 + Clarity); v3: web push (mandi bhav alerts); v2: bell → KrashiBook
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

// Last-known-good copy of a URL, else the offline shell, else whatever the
// network said. `fallback` is the network's own response, handed back when
// there is nothing cached, so a genuine failure still surfaces as one.
function lastKnownGood(request, fallback) {
  return caches.match(request)
    .then((hit) => hit || caches.match('./index.html'))
    .then((hit) => hit || fallback || Response.error());
}

// Assets that must never be served from a stale cache: they carry the address
// of something else (the backend) or load something else (the rest of the shell),
// so a stale copy silently disables a whole feature instead of looking broken.
const SHELL_SCRIPTS = /\/(api-config|drawer-menu|ads)\.js$/;

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
          // A 5xx is a *resolved* fetch, so the .catch() below never sees it.
          // Left alone this branch wrote the host's outage page over the last
          // good copy of the page and then replayed it offline — on 11 Aug 2026
          // that meant farmers holding a cached `{"error":"usage_exceeded"}`
          // where the day's bhav used to be. Serve the last good page instead,
          // and leave the cache as it was.
          if (response.status >= 500) return lastKnownGood(request, response);
          // A 404 is the server's real answer about this URL, not an outage:
          // pass it through, but never let it overwrite the cache either.
          if (!response.ok) return response;
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
          return response;
        })
        .catch(() => lastKnownGood(request, null))
    );
    return;
  }

  // api-config.js is the one asset that must never be served stale. It carries
  // the backend's address, and cache-first has no revalidation step — so when
  // Render reassigned the subdomain, every browser that had ever loaded the
  // site kept calling the dead host and every API-backed panel came up empty,
  // with nothing on the page to suggest why. Bumping CACHE_NAME fixes that
  // once; network-first stops it being possible.
  //
  // The cache is still written and still used, so an offline visit is exactly
  // as good as before — the only change is that a reachable network wins.
  // The same trap catches the shell bootstrap scripts. drawer-menu.js is what
  // injects ads.js (and krashibook.js) into every article and static page, and
  // those pages reference it as a bare path with no ?v= — so under cache-first
  // a browser that had loaded the site even once before ads shipped kept
  // replaying the pre-ads copy and never rendered a single unit. /bhav was
  // unaffected only because bhav.py's _asset() stamps a ?v=<mtime> that changed
  // the URL. Anything that bootstraps the rest of the shell belongs here.
  if (SHELL_SCRIPTS.test(requestUrl.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (!response.ok) return lastKnownGood(request, response);
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => lastKnownGood(request, null))
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
          // Only ever cache a real asset. This branch is cache-*first*, so a
          // stored failure is permanent: one stylesheet fetched during an
          // outage would keep the site looking broken long after the outage
          // ended, with no re-fetch to correct it.
          if (!response.ok) return response;
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
