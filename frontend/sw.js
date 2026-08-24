/**
 * Service worker.
 *
 * manifest.webmanifest has been shipping for a while, so the app was
 * installable but had no worker behind it: no offline behaviour and no
 * caching, which is most of what installing is supposed to buy.
 *
 * What is deliberately NOT cached
 * -------------------------------
 * Anything under /api/, and every HTML document.
 *
 * This is a multi-tenant business app. A cached API response is one tenant's
 * invoices, payroll or employee records sitting in a cache keyed by URL
 * alone - the next person to sign in on a shared machine would be served the
 * previous tenant's data, and it would look entirely legitimate. The same
 * goes for HTML pages, which are only reachable when signed in and would
 * otherwise be served from cache to somebody who is not.
 *
 * So this caches static assets only: the stylesheets, the script bundle, the
 * icons. Those carry no tenant data and are identical for everybody, which
 * is what makes them safe to share across sessions.
 */

// Bump this to retire the previous cache. The assets themselves are already
// versioned with ?v=NN, so a changed asset is a different cache key anyway;
// this exists to clear out the old entries rather than to invalidate them.
const CACHE = 'aniprotech-static-v1';

const PRECACHE = [
    '/styles.css?v=78',
    // The employee portal's stylesheet. It used to come from the Tailwind
    // CDN, which this worker refuses to cache because it is another origin -
    // so the busiest page in the product got none of the benefit.
    '/tailwind.css?v=78',
    '/mobile.css?v=78',
    '/app.js?v=78',
    '/icons/icon-192.png',
    '/icons/icon-512.png',
    '/icons/icon.svg',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        // One failed asset must not fail the whole install, or a single
        // renamed file leaves the app with no worker at all.
        caches.open(CACHE)
            .then((c) => Promise.allSettled(PRECACHE.map((u) => c.add(u))))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

// Only these are ever served from cache. Checked against the pathname, so a
// query string cannot be used to slip something else past it.
const CACHEABLE = /\.(?:css|js|png|jpg|jpeg|svg|webp|woff2?|ttf|ico)$/i;

function isStaticAsset(url) {
    return url.origin === self.location.origin
        && !url.pathname.startsWith('/api/')
        && CACHEABLE.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
    const req = event.request;

    // A cache keyed by URL cannot tell one signed-in user from another, so
    // anything that is not a plain GET goes straight to the network.
    if (req.method !== 'GET') return;

    const url = new URL(req.url);
    if (!isStaticAsset(url)) return;   // API calls and HTML: network, always.

    // Stale-while-revalidate: serve the cached copy at once, and refresh it in
    // the background so a deploy is picked up on the following load rather
    // than needing the cache name bumped.
    event.respondWith(
        caches.open(CACHE).then((cache) =>
            cache.match(req).then((hit) => {
                const fresh = fetch(req).then((res) => {
                    if (res && res.ok) cache.put(req, res.clone());
                    return res;
                }).catch(() => hit);   // offline: the cached copy is the answer
                return hit || fresh;
            })
        )
    );
});
