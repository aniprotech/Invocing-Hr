/**
 * The landing page's answers to "how do I use it" and "how do I install it".
 *
 * Neither question was answered anywhere on the site. There is no app store
 * listing, so somebody on an iPhone had nothing to follow at all - and the
 * "How It Works" section that did exist opened with "Connect Google", which
 * stopped being how anyone starts once accounts could be made with an email
 * and a password.
 *
 * The other half of this is what got taken out. The page carried three
 * five-star testimonials from people who do not exist and a row of invented
 * numbers, presented as fact on a live commercial site. Those must not come
 * back, so this checks for them by name.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

function boot(ua) {
    const dom = new JSDOM(HTML, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/index.html',
        beforeParse(w) {
            // The page asks the server for its editable copy on load. There is
            // no server here, and none of this is about that.
            w.fetch = () => Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({}), text: () => Promise.resolve('{}'),
            });
            w.console.error = () => { };
            if (ua) Object.defineProperty(w.navigator, 'userAgent',
                { value: ua, configurable: true });
        },
    });
    return dom.window;
}

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const ANDROID = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36';
const DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

const text = (w, sel) => (w.document.querySelector(sel) || {}).textContent || '';
const selectedTab = w => [...w.document.querySelectorAll('.install-tab')]
    .filter(t => t.getAttribute('aria-selected') === 'true');
const openPanels = w => [...w.document.querySelectorAll('.install-panel')]
    .filter(p => !p.hidden);

(async () => {
    // --- the two questions get answered ------------------------------------------
    {
        const w = boot(DESKTOP);
        await wait(60);
        check('the page says how to use the app', !!w.document.getElementById('how'));
        check('and how to install it', !!w.document.getElementById('install'));

        // Both navs, or half the site cannot reach them.
        const links = re => (HTML.match(re) || []).length;
        check('both are reachable from the navigation',
            links(/href="#how"/g) >= 2 && links(/href="#install"/g) >= 2,
            'how=' + links(/href="#how"/g) + ' install=' + links(/href="#install"/g));

        check('and the anchors land on real sections',
            [...w.document.querySelectorAll('a[href^="#"]')]
                .map(a => a.getAttribute('href').slice(1))
                .filter(id => id && id !== 'home')
                .every(id => !!w.document.getElementById(id)));
    }

    // --- the steps are the real ones ---------------------------------------------
    {
        const w = boot(DESKTOP);
        await wait(60);
        const how = text(w, '#how');
        check('starting means making an account, not connecting Google',
            /email and a password/i.test(how) && !/^\s*Connect Google/m.test(how));
        check('and confirming the address, which the app requires',
            /code|confirm/i.test(how));
        check('it covers sending', /send/i.test(how));
        check('and being paid', /paid/i.test(how));
    }

    // --- iOS, which was the one nobody could work out ----------------------------
    {
        const w = boot(DESKTOP);
        await wait(60);
        const ios = text(w, '#panel-ios');
        // Asked of the steps alone: the note underneath mentions Safari too,
        // so the whole panel would pass with the instruction itself gone.
        const iosSteps = text(w, '#panel-ios .install-steps');
        check('the iPhone steps name Safari, because no other browser will do',
            /Safari/.test(iosSteps), iosSteps.slice(0, 60));
        check('and the Share button', /Share/.test(ios));
        check('and the words that appear in the menu',
            /Add to Home Screen/.test(ios));
        check('and warn that signing in happens again inside the app',
            /sign in again/i.test(ios), ios.slice(0, 80));
    }

    {
        const w = boot(DESKTOP);
        await wait(60);
        const android = text(w, '#panel-android');
        check('the Android steps name Chrome', /Chrome/.test(android));
        check('and the menu item it offers', /Install app/i.test(android));

        const desktop = text(w, '#panel-desktop');
        check('the computer steps cover the address bar button',
            /address bar/i.test(desktop));
        check('and the Mac, which hides it in the File menu',
            /Add to Dock/i.test(desktop));
    }

    // --- one at a time -------------------------------------------------------------
    {
        const w = boot(DESKTOP);
        await wait(60);
        check('exactly one device is chosen to begin with',
            selectedTab(w).length === 1, selectedTab(w).length);
        check('and exactly one set of steps is on show',
            openPanels(w).length === 1, openPanels(w).length);

        // Asked of the markup as shipped, because the script fixes this up on
        // load - so this is about the moment before it runs, which is the
        // moment all three would be stacked on top of each other.
        const raw = new JSDOM(HTML).window.document;
        const shipped = [...raw.querySelectorAll('.install-panel')]
            .filter(pn => !pn.hasAttribute('hidden'));
        check('and only one before any script has run',
            shipped.length === 1, shipped.map(pn => pn.id).join(','));

        const android = w.document.getElementById('tab-android');
        android.click();
        check('choosing another device switches the steps',
            openPanels(w).length === 1 && openPanels(w)[0].id === 'panel-android',
            openPanels(w).map(p => p.id).join(','));
        check('and the old tab stops claiming to be selected',
            selectedTab(w).length === 1 && selectedTab(w)[0].id === 'tab-android');
        check('only the chosen tab is in the tab order',
            [...w.document.querySelectorAll('.install-tab')]
                .filter(t => t.tabIndex === 0).length === 1);
    }

    {
        const w = boot(DESKTOP);
        await wait(60);
        const first = w.document.getElementById('tab-ios');
        first.dispatchEvent(new w.KeyboardEvent('keydown',
            { key: 'ArrowRight', bubbles: true }));
        check('arrow keys move between the devices',
            selectedTab(w)[0].id === 'tab-android', selectedTab(w)[0].id);
        w.document.getElementById('tab-android').dispatchEvent(
            new w.KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        check('and back again', selectedTab(w)[0].id === 'tab-ios');
    }

    // --- opened on the device it is about -----------------------------------------
    {
        const w = boot(IPHONE);
        await wait(60);
        check('an iPhone is shown the iPhone steps without hunting for them',
            selectedTab(w)[0].id === 'tab-ios', selectedTab(w)[0].id);
    }

    {
        const w = boot(ANDROID);
        await wait(60);
        check('and an Android phone the Android ones',
            selectedTab(w)[0].id === 'tab-android', selectedTab(w)[0].id);
    }

    // --- animation must never be able to hide the page ------------------------------
    {
        // Hidden-until-revealed is only safe while the script that reveals it
        // is running. Scoped to a class that script sets, a page with no
        // working JavaScript shows everything instead of nothing.
        check('nothing is hidden for the animation except by the script itself',
            !/(^|\})\s*\.reveal\s*\{[^}]*opacity:\s*0/.test(HTML),
            'an unscoped .reveal sets opacity 0');
        check('and the scoped rule is the one that does the hiding',
            /\.js-reveal\s+\.reveal\s*\{[^}]*opacity:\s*0/.test(HTML));

        const w = boot(DESKTOP);
        await wait(60);
        const blocks = [...w.document.querySelectorAll('.reveal')];
        check('there is something to reveal', blocks.length > 0, blocks.length);
        check('reduced motion is respected',
            /prefers-reduced-motion/.test(HTML));
    }

    // --- what was taken out stays out -----------------------------------------------
    {
        const invented = ['Sarah Kim', 'Marcus Rivera', 'Aisha Patel',
            'BrightPath Studio', 'NovaTech Solutions'];
        const back = invented.filter(name => HTML.includes(name));
        check('no reviews from people who do not exist', back.length === 0,
            back.join(', '));

        const numbers = ['500+', '$2M+', '99%'];
        const returned = numbers.filter(nu => HTML.includes(nu));
        check('no figures nobody can stand behind', returned.length === 0,
            returned.join(', '));

        check('and the old product name is gone with them',
            !/AllInOne/.test(HTML));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
