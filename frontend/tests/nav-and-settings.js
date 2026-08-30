/**
 * The header and the settings page, after being thinned out.
 *
 * The header carried every view as its own tab - ten on the invoicing side -
 * and settings stacked a dozen unrelated panels down one page. Related views
 * are now grouped behind a heading that opens on click, and settings shows one
 * section at a time.
 *
 * Both structures are built at runtime from the markup, so the things worth
 * checking are that nothing goes missing in the process and that only one
 * thing is ever on screen.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

function boot(page, opts) {
    opts = opts || {};
    // Nothing else in this file needs a second window, so it is left unclosed
    // for the same reason as the others - pending callbacks.
    const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/' + page,
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    // Shaped like the real Chart.js: the app sets Chart.defaults before drawing,
    // and a stub without it turns every run into a page of noise that a real
    // error could hide in.
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        if (opts.failAuth) return Promise.reject(new Error('offline'));
        const body = p === '/api/client/me' ? { id: 1, email: 'me@example.com' }
            : p === '/api/auth/me' ? { user: { email: 'me@example.com' }, client_id: 1 }
                : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return dom;
}

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

const wait = ms => new Promise(r => setTimeout(r, ms));

// The header must already be grouped in the markup. app.js is half a megabyte,
// and until it has downloaded and run the browser paints whatever the HTML
// says - so if the groups are built by script, every load shows the ungrouped
// header first. That is what kept being reported as the old tabs returning.
// One app now, so one page to check. hr.html is a redirect.
for (const page of ['app.html']) {
    const raw = fs.readFileSync(path.join(ROOT, page), 'utf8');
    const nav = raw.slice(raw.indexOf('id="main-nav"'), raw.indexOf('</nav>'));
    const groups = (nav.match(/class="nav-group"/g) || []).length;
    check(`${page} ships its header already grouped`, groups >= 2,
        `${groups} groups in the markup, so the browser paints a flat header until app.js runs`);
    check(`${page} marks the header as pre-grouped`,
        /id="main-nav"[^>]*data-grouped="1"/.test(raw),
        'the runtime would rebuild what is already there');
}

// Every view has to have a way in. The employee list had none: it was reachable
// only because the HR portal opened on it, so the day something else became the
// landing page it became unreachable, with the markup for it still sitting
// there. A view nothing routes to is invisible, and looks like a missing
// feature rather than a missing link.
{
    const appJs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');

    // The header navigates by href="#/slug" now rather than by an onclick, so
    // a link counts as a way in just as a showView call does. The slug table
    // is read out of app.js so this cannot drift from what the router serves.
    const VIEW_FOR_SLUG = (() => {
        const block = appJs.slice(appJs.indexOf('var ROUTE_SLUGS'),
                                  appJs.indexOf('var VIEW_FOR_SLUG'));
        const m = {};
        for (const [, view, slug] of block.matchAll(/'([a-z0-9-]+-view)':\s*'([^']+)'/g)) {
            m[slug] = view;
        }
        return m;
    })();

    const targets = text => {
        const found = new Set(
            [...text.matchAll(/showView\(\s*(?:'|"|&quot;)([a-z0-9-]+-view)(?:'|"|&quot;)\s*\)/g)]
                .map(m => m[1]));
        for (const [, slug] of text.matchAll(/href="#\/([^"]+)"/g)) {
            if (VIEW_FOR_SLUG[slug]) found.add(VIEW_FOR_SLUG[slug]);
        }
        return found;
    };
    const fromJs = targets(appJs);

    // One app now, so one page to check. hr.html is a redirect.
    for (const page of ['app.html']) {
        const raw = fs.readFileSync(path.join(ROOT, page), 'utf8');
        const dom = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, ''));
        const d = dom.window.document;

        const nav = d.getElementById('main-nav');
        const fromNav = targets(nav.innerHTML);
        const fromPage = targets(raw);
        const reachable = new Set([...fromNav, ...fromPage, ...fromJs]);

        const views = [...d.querySelectorAll('.view-section')].map(el => el.id).filter(Boolean);
        const stranded = views.filter(v => !reachable.has(v));
        check(`${page}: every view has a way in`, stranded.length === 0,
            stranded.join(', '));

        // And the reverse - a link to a view that is not on the page is a dead
        // tab that silently does nothing.
        const dead = [...fromNav].filter(v => !d.getElementById(v));
        check(`${page}: no nav item points at a view that is not there`,
            dead.length === 0, dead.join(', '));
    }

    // The one that broke, named outright, because "reachable from somewhere" is
    // not the same as "in the menu where somebody would look for it". It lives
    // in the one app now, shown or hidden by the plan rather than by which
    // file was opened.
    const merged = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
    const mergedNav = merged.getElementById('main-nav').innerHTML;
    check('the app has an Employees link in its header',
        /href="#\/people"/.test(mergedNav));
    check('and it sits in the People menu',
        /data-nav-group="People"[\s\S]*?href="#\/people"[\s\S]*?<\/div>\s*<\/div>/.test(mergedNav));
    check('and the header ships nothing hidden, so the plan decides',
        !/id="nav-[a-z-]+"[^>]*style="display: *none/.test(mergedNav),
        'a nav item is hidden in the markup, which is the old per-file split');
}

(async () => {
    // One app now, so one page to check. hr.html is a redirect.
    for (const page of ['app.html']) {
        console.log(`\n-- ${page} --`);
        const dom = boot(page);
        const w = dom.window;
        await wait(400);
        const d = w.document;

        const nav = d.getElementById('main-nav');
        const visible = el => el && el.style.display !== 'none';

        // Nothing may be lost by grouping: every nav item this portal shows is
        // still reachable, either directly or from inside a menu.
        const allItems = Array.from(nav.querySelectorAll('.nav-item'))
            .filter(el => el.id && visible(el));
        const inMenus = Array.from(nav.querySelectorAll('.nav-group-menu .nav-item'));
        check('every visible tab survives the grouping',
            allItems.length > 0 && allItems.every(el => nav.contains(el)),
            `${allItems.length} items`);

        // The bar itself has to be short.
        // Only what is actually on screen counts. A group belonging to the
        // other portal is present in the markup but hidden.
        const topLevel = Array.from(nav.children).filter(el =>
            visible(el) &&
            (el.classList.contains('nav-group') || el.classList.contains('nav-item')));
        check('the header shows at most seven top-level entries',
            topLevel.length <= 7, `${topLevel.length} entries`);
        check('grouping actually moved items into menus', inMenus.length >= 2,
            `${inMenus.length} items in menus`);

        // A menu opens only when its heading is clicked.
        const group = nav.querySelector('.nav-group');
        check('a group exists', !!group);
        if (group) {
            check('menus start closed', !group.classList.contains('open'));
            group.querySelector('.nav-group-toggle').dispatchEvent(
                new w.MouseEvent('click', { bubbles: true }));
            check('clicking the heading opens it', group.classList.contains('open'));

            // Opening a second group closes the first, so only one is ever open.
            const groups = nav.querySelectorAll('.nav-group');
            if (groups.length > 1) {
                groups[1].querySelector('.nav-group-toggle').dispatchEvent(
                    new w.MouseEvent('click', { bubbles: true }));
                check('only one menu is open at a time',
                    !groups[0].classList.contains('open') && groups[1].classList.contains('open'));
            }

            // The whole point of a menu: the item inside it must navigate to
            // its own view, not merely leave some view on screen.
            // A menu item this portal does not serve is hidden by
            // enforcePortalSeparation, and the router deliberately refuses to
            // open one - an invoicing view on the HR side falls back rather
            // than showing a screen with no way back to it. So the item under
            // test has to be one this portal actually offers.
            const inner = [...nav.querySelectorAll('.nav-group-menu .nav-item')]
                .find(el => el.style.display !== 'none');
            check('a menu holds at least one item this portal offers', !!inner);
            if (!inner) return;
            const href = inner.getAttribute('href') || '';
            const slug = (href.match(/^#\/(.+)$/) || [])[1];
            const wanted = slug && w.VIEW_FOR_SLUG ? w.VIEW_FOR_SLUG[slug] : null;
            check('the menu item is wired to a view', !!wanted,
                `${inner.id} has href="${href}", which is not a route`);
            if (wanted) {
                w.eval("showView('dashboard-view')");   // somewhere else first
                // jsdom does not follow a link's default action, so the hash
                // is set and the event the browser would fire is dispatched.
                // This still proves the href survived being moved into a menu,
                // which is what could break.
                w.location.hash = href;
                w.dispatchEvent(new w.Event('hashchange'));
                const shown = d.querySelector('.view-section.active');
                check('an item inside a menu opens its own view',
                    shown && shown.id === wanted,
                    `clicked ${inner.id}, wanted ${wanted}, got ${shown && shown.id}`);
                check('the group heading shows where you are',
                    !!nav.querySelector('.nav-group .nav-group-toggle.active') ||
                    !!nav.querySelector('.nav-group .nav-item.active'),
                    'nothing in the header marks the current view');
            }

            w.eval("showView('settings-view')");
            check('choosing a view closes the menus',
                !nav.querySelector('.nav-group.open'));
        }

        // The header must not wait on the network. It used to be grouped only
        // after the session check, so every refresh showed the old flat tabs
        // until that returned - and never grouped at all if it failed.
        const dead = boot(page, { failAuth: true });
        await wait(400);
        const deadNav = dead.window.document.getElementById('main-nav');
        check('the header is grouped even when the session check fails',
            deadNav.querySelectorAll('.nav-group').length > 0,
            'grouping depends on a network call');

        // --- settings, one section at a time ---
        const rail = d.getElementById('settings-rail');
        const panels = d.getElementById('settings-panels');
        check('settings has a rail and panels', !!rail && !!panels);

        if (rail && panels) {
            const sections = panels.querySelectorAll(':scope > [data-settings-section]');
            const buttons = rail.querySelectorAll('button');
            check('every section has a button', sections.length === buttons.length,
                `${sections.length} sections, ${buttons.length} buttons`);
            check('settings was split into several sections', sections.length >= 4,
                `${sections.length} sections`);

            const active = () => Array.from(sections).filter(s => s.classList.contains('is-active'));
            check('exactly one section shows at a time', active().length === 1,
                `${active().length} showing`);

            // Every button must reach its own section, and only that one.
            let wrong = 0;
            buttons.forEach(b => {
                b.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
                const showing = active();
                if (showing.length !== 1 ||
                    showing[0].getAttribute('data-settings-section') !== b.getAttribute('data-settings-target')) {
                    wrong++;
                }
            });
            check('every button opens its own section and no other', wrong === 0,
                `${wrong} of ${buttons.length} wrong`);

            check('the chosen button is marked',
                rail.querySelectorAll('button.is-active').length === 1);
        }

        // Deliberately not closed: pending callbacks from this page would
        // then fire against a torn-down document and crash the next one.
        void dom;
    }

    console.log(failures ? `\n${failures} check(s) failed` : '\nthe header is short and settings opens one page at a time');
    process.exit(failures ? 1 : 0);
})();
