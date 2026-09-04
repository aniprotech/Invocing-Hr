/**
 * Telling people how to install, on the platforms that never offer.
 *
 * Chrome on Android fires beforeinstallprompt and shows its own banner, so
 * nothing here is needed there. Safari fires nothing at all: on an iPhone the
 * only way in is Share then Add to Home Screen, and on a Mac it is File then
 * Add to Dock. Somebody who has been told an app exists and finds no way to
 * get it concludes there isn't one.
 *
 * Shown once, dismissible, and never to somebody already running it installed.
 */
(function () {
    var KEY = 'install-hint-dismissed';

    function alreadyInstalled() {
        // iOS reports it on navigator; everything else through the media query.
        if (window.navigator.standalone === true) return true;
        try {
            return window.matchMedia('(display-mode: standalone)').matches;
        } catch (e) {
            return false;
        }
    }

    function dismissed() {
        try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; }
    }

    function remember() {
        try { localStorage.setItem(KEY, '1'); } catch (e) { /* private window */ }
    }

    // Safari is the one that offers nothing. Chrome and Edge on a Mac have
    // their own install button, so telling them about the Dock would be wrong.
    function advice() {
        var ua = navigator.userAgent;
        var isSafari = /^((?!chrome|android|crios|fxios|edgios).)*safari/i.test(ua);
        if (!isSafari) return null;

        var isIOS = /iPad|iPhone|iPod/.test(ua) ||
            // iPadOS reports itself as a Mac, and the touch points give it away.
            (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
        if (isIOS) {
            return 'Install this app: tap Share, then Add to Home Screen.';
        }
        if (/Macintosh/.test(ua)) {
            return 'Install this app: choose File, then Add to Dock.';
        }
        return null;
    }

    // Only app.html loads the shared stylesheet, and this appears on the
    // marketing pages too, so it brings its own. Both palettes are covered
    // because the same bar shows on a white landing page and a dark app.
    function style() {
        if (document.getElementById('install-hint-style')) return;
        var css = document.createElement('style');
        css.id = 'install-hint-style';
        css.textContent =
            '.install-hint{position:fixed;left:12px;right:12px;bottom:12px;' +
            'z-index:900;display:flex;align-items:center;gap:12px;' +
            'max-width:460px;margin:0 auto;padding:12px 14px;border-radius:12px;' +
            'font:400 0.86rem/1.4 inherit;background:#ffffff;color:#0f172a;' +
            'border:1px solid #e2e8f0;box-shadow:0 8px 24px rgba(15,23,42,0.18);}' +
            '.install-hint-close{margin-left:auto;background:none;border:0;' +
            'cursor:pointer;color:inherit;opacity:0.6;font-size:1.2rem;' +
            'line-height:1;padding:0 4px;}' +
            '.install-hint-close:hover{opacity:1;}' +
            '@media (prefers-color-scheme: dark){' +
            '.install-hint{background:#0f172a;color:#e2e8f0;border-color:#334155;}}';
        document.head.appendChild(css);
    }

    function show(message) {
        style();
        var bar = document.createElement('div');
        bar.className = 'install-hint';
        bar.setAttribute('role', 'note');

        var text = document.createElement('span');
        text.textContent = message;
        bar.appendChild(text);

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'install-hint-close';
        close.setAttribute('aria-label', 'Dismiss');
        close.textContent = '×';
        close.onclick = function () {
            remember();
            bar.remove();
        };
        bar.appendChild(close);

        document.body.appendChild(bar);
    }

    function start() {
        if (alreadyInstalled() || dismissed()) return;
        var message = advice();
        if (message) show(message);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
