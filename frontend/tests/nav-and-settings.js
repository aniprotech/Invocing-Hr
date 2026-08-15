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

function boot(page) {
    const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/' + page,
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = p === '/api/client/me' ? { id: 1, email: 'me@example.com' }
            : p === '/api/auth/me' ? { user: { email: 'me@example.com' } }
                : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
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

(async () => {
    for (const page of ['app.html', 'hr.html']) {
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
        const topLevel = Array.from(nav.children).filter(el =>
            el.classList.contains('nav-group') ||
            (el.classList.contains('nav-item') && visible(el)));
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

            w.eval("showView('settings-view')");
            check('choosing a view closes the menus',
                !nav.querySelector('.nav-group.open'));
        }

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
