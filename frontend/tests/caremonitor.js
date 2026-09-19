/**
 * The Caremonitor block on the front page.
 *
 * The company's other product lives on its own host. The front page says
 * what it is, who it is for, and has the way in from the block, the header,
 * the drop-down and the footer. The panel beside the copy is a picture of
 * the product, not live data, and says so to a screen reader. The words are
 * the operator's to change, like every other section's.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const SITE = 'https://caremonitor.aniprotech.com/';

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

function boot(copy) {
    const dom = new JSDOM(HTML, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/index.html',
        beforeParse(w) {
            w.fetch = url => Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve(String(url).indexOf('/api/platform/landing') >= 0 && copy ? { landing: copy, items: {} } : {}),
                text: () => Promise.resolve('{}'),
            });
            w.console.error = () => { };
        },
    });
    return dom.window;
}

(async () => {
    const w = boot();
    const d = w.document;
    const section = d.getElementById('caremonitor');
    check('the front page has a Caremonitor section', !!section);

    const h2 = section && section.querySelector('h2');
    check('  it is headed, and the heading is the operator\'s to change',
        h2 && /Caremonitor/.test(h2.textContent) && h2.getAttribute('data-cms') === 'caremonitor_title');
    check('  the strapline and paragraph are too',
        section && section.querySelector('[data-cms="caremonitor_eyebrow"]') && section.querySelector('[data-cms="caremonitor_intro"]'));
    check('  it says what Caremonitor does in words a care provider uses',
        section && /care plans/i.test(section.textContent) && /rostering/i.test(section.textContent)
            && /eMAR/.test(section.textContent) && /invoicing/i.test(section.textContent));

    // --- the way in ---------------------------------------------------------
    const links = section ? [...section.querySelectorAll('a')] : [];
    check('the block has the button and the address, both going to the product',
        links.length === 2 && links.every(a => a.href === SITE)
            && /Open Caremonitor/.test(links[0].textContent) && /caremonitor\.aniprotech\.com/.test(links[1].textContent),
        links.map(a => a.href).join(' '));
    check('  the header has a Caremonitor link to the section',
        !!d.querySelector('.nav-links a[href="#caremonitor"]'));
    check('  so does the phone drop-down',
        !!d.querySelector('#mobile-menu a[href="#caremonitor"]'));
    const footer = [...d.querySelectorAll('footer a')].find(a => /Caremonitor/.test(a.textContent));
    check('  and the footer goes straight to the product', footer && footer.href === SITE, footer && footer.href);
    check('  nothing about Caremonitor opens a new window or leaks the referrer',
        ![...d.querySelectorAll('a[href*="caremonitor"]')].some(a => a.getAttribute('target')));

    // --- a picture, not a claim -------------------------------------------------
    const shot = section && section.querySelector('.cm-shot');
    check('the panel is an image to a screen reader, with a label saying it is a preview',
        shot && shot.getAttribute('role') === 'img' && /preview/i.test(shot.getAttribute('aria-label') || ''));
    check('  its figures are hidden from the reader so they are not read out as facts',
        shot && [...shot.querySelectorAll('.cm-stats, .cm-rows')].every(el => el.getAttribute('aria-hidden') === 'true'));

    // --- the operator's copy -----------------------------------------------------
    {
        const w2 = boot({ caremonitor_title: 'Care software <b>for you</b>', caremonitor_intro: 'Short.' });
        await new Promise(r => setTimeout(r, 30));
        const t = w2.document.querySelector('[data-cms="caremonitor_title"]');
        const p = w2.document.querySelector('[data-cms="caremonitor_intro"]');
        check('the operator\'s heading replaces the shipped one, as text and never markup',
            t && t.textContent === 'Care software <b>for you</b>' && !t.querySelector('b'), t && t.innerHTML);
        check('  and so does the paragraph', p && p.textContent === 'Short.');
    }

    // --- the palette ----------------------------------------------------------------
    {
        const css = (HTML.match(/\/\* --- Caremonitor[\s\S]*?\/\* --- Footer columns/) || [''])[0];
        check('the block has styles of its own', css.length > 500);
        check('  its dark blue is the deep end of the site\'s sky, not a colour of its own',
            /#082f49/.test(css) && /#0c4a6e/.test(css) && !/#071a33/i.test(css));
    }

    // --- the header still fits -------------------------------------------------
    // An eleventh link is what made the Sign in button wrap onto two lines
    // on a 1280px screen. Nothing in the row may wrap; below the width the
    // row can hold, the header folds into the menu.
    {
        const rule = sel => (HTML.match(new RegExp(sel.replace(/[.#]/g, '\\$&') + '\\s*\\{[^}]*\\}')) || [''])[0];
        check('header links and buttons never wrap',
            /white-space:\s*nowrap/.test(rule('.nav-links a')) && /white-space:\s*nowrap/.test(rule('.nav-login')));
        const fold = HTML.match(/@media \(max-width: (\d+)px\) \{\s*\.nav-links \{ display: none; \}/);
        check('  the header folds into the menu well before a phone width', fold && Number(fold[1]) >= 1100, fold && fold[1]);
    }

    // --- the door -------------------------------------------------------------------
    // Somebody with a Caremonitor account who lands on this sign-in page
    // should see their own door beside the employee one, going straight to
    // the product's sign-in rather than its front page.
    {
        const login = new JSDOM(fs.readFileSync(path.join(ROOT, 'login.html'), 'utf8'), { url: 'https://localhost/login.html' }).window.document;
        const door = login.querySelector('a[href="https://caremonitor.aniprotech.com/login"]');
        check('the sign-in page offers Caremonitor as a door of its own',
            door && /Caremonitor/.test(door.textContent) && /sign in/i.test(door.getAttribute('aria-label') || ''));
        const doors = door && [...door.parentElement.querySelectorAll('a')];
        check('  beside the Employee Portal, each saying who it is for',
            doors && doors.length === 2 && doors[0].getAttribute('href') === '/employee-login.html'
                && doors.every(a => a.querySelectorAll('.block').length === 2), doors && doors.map(a => a.getAttribute('href')).join(' '));
        check('  neither opens a new window', doors && !doors.some(a => a.getAttribute('target')));
    }

    console.log(failures === 0 ? '\nAll Caremonitor checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
