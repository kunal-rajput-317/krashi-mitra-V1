// v7 is a forced purge, like v6 before it: caches written during the 11 Aug 2026
// outage hold Netlify's `{"error":"usage_exceeded"}` 503 under the URL of a real
// page or stylesheet, and the activate step deletes every cache that isn't the
// current name.
const CACHE_NAME = 'krashimitra-v32'; // v32: terms.html and privacy-policy.html no longer load AdSense (owner: never ads on legal pages) — privacy-policy.html is precached cache-first, so a returning phone would keep the copy that still loads Auto ads. // v31: a declined नीला टिक application or a removed tick now tells the member why — a KrashiBook सूचना card with the reason and a फिर से आवेदन करें button, and a matching card on profile.html (precached). krashibook.js joins SHELL_SCRIPTS so a stale copy cannot hide the next notice. v30: khoj-kb.js (cache-first static) named Dinocap, a pesticide India banned in 2023 — returning phones must drop that copy; terms/privacy corrected the blue-tick wording; profile.html gains the आपका डेटा card. v29: v29: privacy-policy.html is precached cache-first and its old copy made false statements (no passwords, no exact location, no financial data, anonymous chat) — a returning phone must get the corrected policy. profile.html (also precached) gains the खाता हटाएँ card, which a stale copy would never show; krashi_bajar.html gains the ⋯ → रिपोर्ट करें menu on every card (IT Rules complaint mechanism). // v28: a farmer can finally replace a listing's photo. krashi_bajar.html is precached cache-first, so a returning phone — the people who have listings old enough to want re-shooting — would keep the edit form that says "फोटो/वीडियो अभी नहीं बदल सकते" and keep being told to delete the post and lose its offers and comment thread. The page also carries the new POST /bazar/posts/{id}/media call and the shared checkAndShrink() that holds the 12MB/40MB/90s client-side limits, so a stale copy cannot reach the endpoint at all. // v27: km-mandi-memory.js ships — the "आपकी मंडी" recall band and the "पिछली बार से" change line, which are the only things on a /bhav page that make a returning farmer's visit differ from a stranger's. It joins SHELL_SCRIPTS below because it decides what price history to compare against, and a stale copy comparing on an older rule would state a change that never happened. // v26: /uploads now stamps immutable Cache-Control headers (CachedStaticFiles in main.py), so Cloudflare caches every bazar photo, avatar and PDF at the edge instead of fetching fresh from Render on every page load — the single biggest lever against the 5 GB/month bandwidth cap. No precached file changed, so this bump is a no-op for the browser cache; it is here so the next true shell change starts from a clean slate. v25: the फॉलो करें button paints on the tap. It used to wait for /bazar/me AND the follow POST before anything changed on screen, so on a cold Render dyno the farmer pressed it, saw nothing, and pressed again. krashi_bajar.html is precached cache-first, so without this bump every returning phone — the people who actually follow sellers — keeps the two-round-trip button. v24: api-config.js now rings the header avatar in ocean blue for a कृषि मित्र प्रीमियम member, and clears that flag on logout. It is cache-first and referenced without a ?v= from every page, so without this bump the ring would appear in the bazar feed and on /profile but never in the header — and a member who let his term lapse would keep a ringed avatar on every returning phone, which is the site showing a badge nobody is paying for. v23: the blue tick changed meaning — it is a paid कृषि मित्र प्रीमियम membership now, not a phone-verified identity check. krashi_bajar.html and profile.html are both precached, so without this bump every returning phone would keep publishing the OLD claim (\"कृषि मित्र ने फ़ोन पर इस विक्रेता का नाम, मोबाइल नंबर और गाँव जाँचा है\") under every ticked seller — a claim about a named person that nobody checks any more, which is the exact legal exposure the rewrite exists to remove. It also carries the in-feed offer card, the ocean-blue ring on a member's avatar and the प्रीमियम card on /profile, none of which a stale copy can render. v22: the site finally asks for money — km-support.js appends विज्ञापन दें (/sponsor) and सहयोग करें (/donate) to every page's footer, and drawer-menu.js bootstraps it. A returning phone holds a cache-first drawer-menu.js, so without this bump the entire returning audience — the people most likely to give — would keep getting the footer that asks for nothing; km-support.js joins SHELL_SCRIPTS below so a later change to what we ask for cannot be swallowed the same way. v21: the composer's map is satellite now, its ✕ is pinned to a sticky header, and photos are downscaled to 1600px IN THE PHONE before upload — a cached copy keeps uploading 6MB originals against metered egress; v20: the Krashi Bazar composer asks where the crop is (device location, a map pin, and राज्य/ज़िला pickers fed by /bhav/api/places) — krashi_bajar.html is precached, so a returning farmer would keep getting the placeless form and keep posting listings no district page can find; v19: loading skeletons ship across the site (km-skeleton.css, new markup inside the static pages, and drawer-menu.js bootstraps the stylesheet) — a returning phone holds cache-first copies of those pages and of the shell script, so it would keep showing the old spinner-or-nothing while the new pages' skeleton markup renders as invisible empty blocks; v18: the forecast API moved to /api/weather so the page could have /weather back (the router was answering every मौसम देखें button with raw JSON once Netlify left and one origin served both); a precached weather.html keeps calling the old path and gets the page's own HTML back instead of a forecast; v17: backend origin → https://krashi-mitra-v1-xek3.onrender.com; every browser holds a cache-first api-config.js pointing at the old one; v16: shop.html retired (2026-09-16, /product is the shop now) — dropped from precache, or a returning phone keeps offering the dead page offline; v15: krashi_bajar.html is precached and changed twice over — listing media moved to Cloudflare R2 (the client-side upload caps came down with it, 12MB photo / 40MB video, so a cache-first copy would keep offering a returning farmer the old 50MB/120MB limits and his phone would spend minutes uploading a file the server refuses on arrival), and the feed card was rebuilt — a stale copy renders the old six-band card, which cannot read the new crop_image field the API now sends, so every listing on a returning phone would stay a grey text box), and the comment thread gained replies, comment likes and delete — a cached copy cannot render any of them and would keep awaiting the network before painting; v14: km-journey.js ships and REWRITES the hrefs of the आगे क्या करें strip from the reader's stored district — a cache-first copy would keep a returning phone on an older rule for links the whole ecosystem now navigates by; it joins SHELL_SCRIPTS below; v13: bottomnav.js was cache-first and its link rule changed — a stale copy keeps sending दुकान and कृषि न्यूज़ to a sibling of whatever nested page the farmer is on (two of four tabs 404ing across /pashupalan, /naksha and /rental); it joins SHELL_SCRIPTS below so this cannot recur; v12: backend origin → https://krashi-mitra-v1-p099.onrender.com; every browser holds a cache-first api-config.js pointing at the old one; v11: backend origin → https://api.krashimitra.in; every browser holds a cache-first api-config.js pointing at the old one; v10: km-social.js ships (channel stickers + invite popup) and carries the channel URLs, so a stale copy would keep showing yesterday's links — or none; // v9: ads.js shipped, but drawer-menu.js (which bootstraps it) is referenced without a ?v= query from the articles and the static pages, so cache-first kept handing returning phones the pre-ads copy and no ad ever rendered for them; // v8: backend moved to a new Render host — every returning browser held a cache-first api-config.js pointing at the dead one; v7: never cache a failed response; v6: never cache authenticated API responses; v5: mandi.html retired, mandi data lives on /bhav; v4: shared analytics.js (GA4 + Clarity); v3: web push (mandi bhav alerts); v2: bell → KrashiBook // v25: the फॉलो करें button paints on the tap. It used to wait for /bazar/me AND the follow POST before anything changed on screen, so on a cold Render dyno the farmer pressed it, saw nothing, and pressed again. krashi_bajar.html is precached cache-first, so without this bump every returning phone — the people who actually follow sellers — keeps the two-round-trip button. v24: api-config.js now rings the header avatar in ocean blue for a कृषि मित्र प्रीमियम member, and clears that flag on logout. It is cache-first and referenced without a ?v= from every page, so without this bump the ring would appear in the bazar feed and on /profile but never in the header — and a member who let his term lapse would keep a ringed avatar on every returning phone, which is the site showing a badge nobody is paying for. v23: the blue tick changed meaning — it is a paid कृषि मित्र प्रीमियम membership now, not a phone-verified identity check. krashi_bajar.html and profile.html are both precached, so without this bump every returning phone would keep publishing the OLD claim ("कृषि मित्र ने फ़ोन पर इस विक्रेता का नाम, मोबाइल नंबर और गाँव जाँचा है") under every ticked seller — a claim about a named person that nobody checks any more, which is the exact legal exposure the rewrite exists to remove. It also carries the in-feed offer card, the ocean-blue ring on a member's avatar and the प्रीमियम card on /profile, none of which a stale copy can render. v22: the site finally asks for money — km-support.js appends विज्ञापन दें (/sponsor) and सहयोग करें (/donate) to every page's footer, and drawer-menu.js bootstraps it. A returning phone holds a cache-first drawer-menu.js, so without this bump the entire returning audience — the people most likely to give — would keep getting the footer that asks for nothing; km-support.js joins SHELL_SCRIPTS below so a later change to what we ask for cannot be swallowed the same way. v21: the composer's map is satellite now, its ✕ is pinned to a sticky header, and photos are downscaled to 1600px IN THE PHONE before upload — a cached copy keeps uploading 6MB originals against metered egress; v20: the Krashi Bazar composer asks where the crop is (device location, a map pin, and राज्य/ज़िला pickers fed by /bhav/api/places) — krashi_bajar.html is precached, so a returning farmer would keep getting the placeless form and keep posting listings no district page can find; v19: loading skeletons ship across the site (km-skeleton.css, new markup inside the static pages, and drawer-menu.js bootstraps the stylesheet) — a returning phone holds cache-first copies of those pages and of the shell script, so it would keep showing the old spinner-or-nothing while the new pages' skeleton markup renders as invisible empty blocks; v18: the forecast API moved to /api/weather so the page could have /weather back (the router was answering every मौसम देखें button with raw JSON once Netlify left and one origin served both); a precached weather.html keeps calling the old path and gets the page's own HTML back instead of a forecast; v17: backend origin → https://krashi-mitra-v1-xek3.onrender.com; every browser holds a cache-first api-config.js pointing at the old one; v16: shop.html retired (2026-09-16, /product is the shop now) — dropped from precache, or a returning phone keeps offering the dead page offline; v15: krashi_bajar.html is precached and changed twice over — listing media moved to Cloudflare R2 (the client-side upload caps came down with it, 12MB photo / 40MB video, so a cache-first copy would keep offering a returning farmer the old 50MB/120MB limits and his phone would spend minutes uploading a file the server refuses on arrival), and the feed card was rebuilt — a stale copy renders the old six-band card, which cannot read the new crop_image field the API now sends, so every listing on a returning phone would stay a grey text box), and the comment thread gained replies, comment likes and delete — a cached copy cannot render any of them and would keep awaiting the network before painting; v14: km-journey.js ships and REWRITES the hrefs of the आगे क्या करें strip from the reader's stored district — a cache-first copy would keep a returning phone on an older rule for links the whole ecosystem now navigates by; it joins SHELL_SCRIPTS below; v13: bottomnav.js was cache-first and its link rule changed — a stale copy keeps sending दुकान and कृषि न्यूज़ to a sibling of whatever nested page the farmer is on (two of four tabs 404ing across /pashupalan, /naksha and /rental); it joins SHELL_SCRIPTS below so this cannot recur; v12: backend origin → https://krashi-mitra-v1-p099.onrender.com; every browser holds a cache-first api-config.js pointing at the old one; v11: backend origin → https://api.krashimitra.in; every browser holds a cache-first api-config.js pointing at the old one; v10: km-social.js ships (channel stickers + invite popup) and carries the channel URLs, so a stale copy would keep showing yesterday's links — or none; // v9: ads.js shipped, but drawer-menu.js (which bootstraps it) is referenced without a ?v= query from the articles and the static pages, so cache-first kept handing returning phones the pre-ads copy and no ad ever rendered for them; // v8: backend moved to a new Render host — every returning browser held a cache-first api-config.js pointing at the dead one; v7: never cache a failed response; v6: never cache authenticated API responses; v5: mandi.html retired, mandi data lives on /bhav; v4: shared analytics.js (GA4 + Clarity); v3: web push (mandi bhav alerts); v2: bell → KrashiBook
const ASSETS_TO_CACHE = [
  './',
  './analytics.js',
  './km-skeleton.css',
  './index.html',
  './weather.html',
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
  // logo-512.png (328 KB) removed from precache — it is only read by the
  // manifest's install prompt, which requires being online anyway.  Every
  // CACHE_NAME bump re-downloads all of these, and 328 KB × users adds up
  // against Render's 5 GB/month bandwidth cap.
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
// km-social.js belongs here for the same reason api-config.js does: it carries
// an address (the channel invite links) rather than just behaviour. Under
// cache-first, pasting a new Facebook or Instagram URL into it would never
// reach a phone that had already loaded the site — the exact failure mode that
// put api-config.js and drawer-menu.js on this list.
// bottomnav.js carries addresses too — it DECIDES the href of every tab in the
// bar, from the page's own path. When that rule was corrected (2026-09-12,
// nested sections were sending दुकान and कृषि न्यूज़ to a sibling of the
// current page), a cache-first copy would have kept every returning phone on
// the broken one, on the tab bar the whole site navigates by.
const SHELL_SCRIPTS = /\/(api-config|drawer-menu|ads|km-social|bottomnav|km-journey|km-support|km-mandi-memory|krashibook)\.js$/;

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
