/**
 * The worker behind the app.
 *
 * Every page that ships a manifest is offering to be installed, and only one
 * of them - the employee dashboard - ever registered a worker. The others
 * advertised an app with nothing behind it: no precache, no offline
 * behaviour, and on Android a weaker install. Chrome will happily make a
 * home-screen shortcut from a manifest alone, but it reserves the real thing
 * for a page a service worker is actually controlling, so the same site
 * installed properly from one page and as a bookmark from the next.
 *
 * Registered after load so it never competes with first paint, and a failure
 * is ignored on purpose: this buys caching and offline, and every page works
 * without it. sw.js caches static assets only - never an API response, never
 * an HTML page - because this is a multi-tenant app and a cached response is
 * one tenant's data waiting for whoever signs in next.
 */
(function () {
    if (!('serviceWorker' in navigator)) return;

    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js').catch(function () {
            /* An optimisation. Nothing here is required for the page to work. */
        });
    });
})();
