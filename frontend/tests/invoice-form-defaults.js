/**
 * The new-invoice form has to be usable every time, not just the first time.
 *
 * Saving an invoice calls form.reset(), which blanks the dates and the
 * currency. Those were filled once at page load, so invoice one came out
 * right and every invoice after it opened with empty date fields that had to
 * be typed by hand. This loads the real page and checks the form after a
 * reset, which is the state a user is actually in most of the time.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

function boot() {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');

    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
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

    const routes = {
        '/api/client/me': { id: 1, email: 'me@example.com', company_name: 'aniprotech', currency: 'GBP' },
        '/api/auth/me': { user: { email: 'me@example.com' }, client_id: 1 },
        '/api/settings': { currency: 'GBP' },
        '/api/next-invoice-number': { next_number: 'INV-0029', payment_terms_days: 30 },
        '/api/branding-themes/default': { brand_color: '#4f46e5', font: 'helvetica' },
    };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = routes[p] !== undefined ? routes[p] : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body),
            text: () => Promise.resolve(JSON.stringify(body)),
        });
    };

    let src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
    // BREAK_FORM=1 removes the fix, to confirm this file actually catches the
    // regression rather than passing for some other reason.
    if (process.env.BREAK_FORM) {
        src = src.replace(
            "if (viewId === 'create-invoice-view' && typeof prepareNewInvoiceForm === 'function') prepareNewInvoiceForm();",
            '');
    }
    w.eval(src);
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return dom;
}

const wait = ms => new Promise(r => setTimeout(r, ms));
const ISO = /^\d{4}-\d{2}-\d{2}$/;

(async () => {
    const dom = boot();
    const w = dom.window;
    await wait(400);

    const val = id => {
        const el = w.document.getElementById(id);
        return el ? el.value : null;
    };

    let failures = 0;
    const check = (label, ok, detail) => {
        if (ok) console.log(`ok    ${label}`);
        else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
    };

    // 1. A freshly loaded page.
    check('a fresh page has an issue date', ISO.test(val('inv-issue-date') || ''), val('inv-issue-date'));
    check('a fresh page has a due date', ISO.test(val('inv-due-date') || ''), val('inv-due-date'));

    // 2. The state after saving: reset the form, then reopen it the way the
    //    app does. This is what was broken.
    const form = w.document.getElementById('complex-invoice-form');
    if (!form) { console.log('FAIL  no invoice form in app.html'); process.exit(1); }
    form.reset();

    check('a reset really does blank the dates', !val('inv-issue-date'), 'reset left ' + val('inv-issue-date'));

    w.eval('showView("create-invoice-view")');
    await wait(400);

    check('reopening refills the issue date', ISO.test(val('inv-issue-date') || ''), val('inv-issue-date'));
    check('reopening refills the due date', ISO.test(val('inv-due-date') || ''), val('inv-due-date'));

    // 3. The due date must follow the issue date, and the tenant's terms.
    const issue = val('inv-issue-date'), due = val('inv-due-date');
    const days = Math.round((new Date(due) - new Date(issue)) / 86400000);
    check('the due date follows the issue date', new Date(due) > new Date(issue), `${issue} -> ${due}`);
    check('the due date uses the tenant terms (30 days)', days === 30, `${days} days`);

    // 4. And the number is still fetched, which always worked.
    check('the invoice number is filled', (val('inv-number') || '').startsWith('INV-'), val('inv-number'));

    dom.window.close();
    console.log(failures ? `\n${failures} check(s) failed` : '\nthe new-invoice form opens ready every time');
    process.exit(failures ? 1 : 0);
})();
