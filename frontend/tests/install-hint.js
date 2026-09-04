/**
 * Installing on the platforms that never offer.
 *
 * The app installed on Android and not on an iPhone, and the reason was that
 * Safari does not read display:standalone out of the manifest. Without the
 * apple meta tags, Add to Home Screen makes a bookmark that opens in Safari
 * with the browser chrome still around it - which from the outside is exactly
 * "we cannot install it on iOS".
 *
 * Safari also fires no install event at all, so nothing ever tells anybody the
 * app can be installed. These check the tags are there and that the hint
 * appears for the browsers that need it and nobody else.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const MAC_SAFARI = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';
const MAC_CHROME = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';
const ANDROID = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36';
const IOS_CHROME = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0 Mobile/15E148 Safari/604.1';

function run(ua, opts) {
    opts = opts || {};
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
        url: 'https://localhost/', pretendToBeVisual: true,
        runScripts: 'outside-only',
    });
    const w = dom.window;
    Object.defineProperty(w.navigator, 'userAgent', { value: ua, configurable: true });
    Object.defineProperty(w.navigator, 'maxTouchPoints',
        { value: opts.touch || 0, configurable: true });
    if (opts.standalone) w.navigator.standalone = true;
    w.matchMedia = () => ({ matches: !!opts.installed });
    if (opts.dismissed) {
        try { w.localStorage.setItem('install-hint-dismissed', '1'); } catch (e) { }
    }
    w.eval(fs.readFileSync(path.join(ROOT, 'install-hint.js'), 'utf8'));
    return w;
}

const hint = w => w.document.querySelector('.install-hint');

(async () => {
    // --- the tags Safari actually reads --------------------------------------
    {
        const pages = fs.readdirSync(ROOT)
            .filter(f => f.endsWith('.html') && !f.startsWith('__'));
        const missing = pages.filter(f =>
            !/apple-mobile-web-app-capable/.test(
                fs.readFileSync(path.join(ROOT, f), 'utf8')));
        check('every page tells Safari it can run standalone',
            missing.length === 0, missing.join(', '));

        const home = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
        check('and what to call it on the home screen',
            /apple-mobile-web-app-title/.test(home));
        check('with an icon Safari will use',
            /apple-touch-icon/.test(home));

        const manifest = JSON.parse(
            fs.readFileSync(path.join(ROOT, 'manifest.webmanifest'), 'utf8'));
        check('the manifest still asks for standalone',
            manifest.display === 'standalone', manifest.display);
        check('and has a stable identity', !!manifest.id, manifest.id);
    }

    // --- who gets told ----------------------------------------------------------
    {
        const w = run(IPHONE);
        await wait(20);
        check('an iPhone is told how, since Safari never offers', !!hint(w));
        check('in the words that match the menu',
            /Share.*Add to Home Screen/.test(hint(w).textContent),
            hint(w).textContent);
    }

    {
        const w = run(MAC_SAFARI);
        await wait(20);
        check('Safari on a Mac is told too', !!hint(w));
        check('with the Mac wording, not the phone one',
            /File.*Add to Dock/.test(hint(w).textContent), hint(w).textContent);
    }

    {
        // iPadOS reports itself as a Mac; the touch points give it away.
        const w = run(MAC_SAFARI, { touch: 5 });
        await wait(20);
        check('an iPad is not told to use the File menu it does not have',
            /Add to Home Screen/.test(hint(w).textContent), hint(w).textContent);
    }

    // --- who does not ------------------------------------------------------------
    {
        const w = run(ANDROID);
        await wait(20);
        check('Android is left alone, because Chrome offers by itself',
            !hint(w));
    }

    {
        const w = run(MAC_CHROME);
        await wait(20);
        check('Chrome on a Mac is left alone for the same reason', !hint(w));
    }

    {
        const w = run(IOS_CHROME);
        await wait(20);
        check('Chrome on an iPhone is not given Safari instructions', !hint(w));
    }

    {
        const w = run(IPHONE, { standalone: true });
        await wait(20);
        check('somebody already running it installed is not told to install it',
            !hint(w));
    }

    {
        const w = run(MAC_SAFARI, { installed: true });
        await wait(20);
        check('nor is a window already in standalone', !hint(w));
    }

    // --- dismissing ---------------------------------------------------------------
    {
        const w = run(IPHONE);
        await wait(20);
        w.document.querySelector('.install-hint-close').click();
        check('it can be dismissed', !hint(w));
        check('and is remembered',
            w.localStorage.getItem('install-hint-dismissed') === '1');
    }

    {
        const w = run(IPHONE, { dismissed: true });
        await wait(20);
        check('so it does not come back', !hint(w));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
