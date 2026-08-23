/**
 * The address bar has to follow the view.
 *
 * Views were swapped by toggling display alone, so the URL stayed on
 * app.html whatever you were looking at. Nothing could be bookmarked or sent
 * to a colleague, Back left the app instead of going back a screen, and a
 * refresh always returned you to the dashboard however deep you were.
 *
 * These check the three things that behaviour rests on: navigating writes the
 * URL, loading a URL restores the view, and a link into a portal this tenant
 * does not have falls back rather than stranding them on a blank page.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

function boot(page, hash) {
    const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/' + page + (hash || ''),
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
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

const shown = w => {
    const el = w.document.querySelector('.view-section.active');
    return el ? el.id : '';
};

(async () => {
    // --- Navigating writes the URL ---------------------------------------
    {
        const w = boot('app.html').window;
        await wait(30);

        w.showView('invoices-view');
        check('moving to a view puts it in the address bar',
            w.location.hash === '#/invoices', w.location.hash);

        w.showView('settings-view');
        check('and the next one replaces it',
            w.location.hash === '#/settings', w.location.hash);

        // The whole point of pushState over assignment: the previous screen
        // is still in history, so Back is a way around the app.
        check('each move is a history entry, so Back has somewhere to go',
            w.history.length > 1, 'length ' + w.history.length);
    }

    // --- Loading a URL restores the view ----------------------------------
    {
        const w = boot('app.html', '#/reports').window;
        await wait(30);
        check('a bookmarked view opens on that view, not the dashboard',
            shown(w) === 'reports-view', shown(w));
    }

    {
        const w = boot('app.html').window;
        await wait(30);
        check('with no hash at all the invoicing portal opens its dashboard',
            shown(w) === 'dashboard-view', shown(w));
    }

    {
        const w = boot('hr.html').window;
        await wait(30);
        check('and the HR portal opens its own',
            shown(w) === 'hr-dashboard-view', shown(w));
    }

    // --- Nonsense and out-of-reach links ----------------------------------
    {
        const w = boot('app.html', '#/nowhere').window;
        await wait(30);
        check('a URL we do not serve falls back instead of showing nothing',
            shown(w) === 'dashboard-view', shown(w));
    }

    {
        // Payroll is HR-only. enforcePortalSeparation() hides it on the
        // invoicing side, so a pasted HR link must not open a view whose nav
        // entry is not even there.
        const w = boot('app.html', '#/payroll').window;
        await wait(30);
        check('an HR link opened by an invoicing account falls back',
            shown(w) === 'dashboard-view', shown(w));
    }

    // --- Back and forward -------------------------------------------------
    {
        const w = boot('app.html').window;
        await wait(30);
        w.showView('invoices-view');
        w.showView('reports-view');

        // jsdom does not run history traversal, so drive the same event the
        // browser would fire and check the app responds to it.
        w.location.hash = '#/invoices';
        w.dispatchEvent(new w.Event('hashchange'));
        await wait(30);
        check('going back to a previous URL shows that view again',
            shown(w) === 'invoices-view', shown(w));
    }

    // --- Deep links to a single record ------------------------------------
    {
        const w = boot('app.html').window;
        await wait(30);
        // Every call is recorded, not just the last: unrelated background
        // loads keep firing and would otherwise be the one left in the box.
        const asked = [];
        w.fetch = (url) => {
            asked.push(String(url));
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({
                    number: 'INV-0042', currency: 'GBP', due: 0, line_items: [],
                }),
                text: () => Promise.resolve('{}'),
            });
        };
        w.location.hash = '#/invoices/INV-0042';
        w.dispatchEvent(new w.Event('hashchange'));
        await wait(60);
        check('a link to one invoice fetches that invoice',
            asked.some(u => u.includes('INV-0042')),
            asked.join(', ') || '(nothing fetched)');
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
