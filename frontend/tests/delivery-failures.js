/**
 * Showing a delivery that did not arrive.
 *
 * An invoice that reached nobody used to look exactly like one that did. That
 * was fixed on the server - it is no longer marked Sent - but the failure was
 * then recorded and displayed nowhere, which is only marginally better: the
 * invoice is silent rather than wrongly labelled.
 *
 * So what is checked is that a failure is visible, that it says why in the
 * provider's own words, and that a delivered invoice is not decorated with a
 * warning it does not deserve.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

const FAILED = {
    id: 3, kind: 'invoice', reference: 'INV-0010', to_email: 'ada@acme.test',
    status: 'failed', error: '550 mailbox unavailable', refunded: true,
    created_at: '2026-09-02 10:00:00', completed_at: '2026-09-02 10:00:04',
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.fetch = (u) => {
        const p = String(u).split('?')[0];
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        if (p === '/api/deliveries') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({
                    deliveries: opts.rows || [], failed_count: (opts.rows || []).length }) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return w;
}

const el = (w, id) => w.document.getElementById(id);

(async () => {
    // --- on the invoice itself ------------------------------------------------
    {
        const w = boot();
        await wait(60);
        w.showInvoiceDelivery({ number: 'INV-0010', last_delivery: FAILED });

        const bar = el(w, 'invoice-undelivered');
        check('an invoice that did not arrive says so', bar.style.display === 'flex');
        check('in the provider\'s own words, not "could not send"',
            /550 mailbox unavailable/.test(el(w, 'invoice-undelivered-why').textContent),
            el(w, 'invoice-undelivered-why').textContent);
        check('and says the money came back',
            /not been charged/i.test(el(w, 'invoice-undelivered-why').textContent));
        check('with a way to try again',
            /Try again/.test(bar.textContent));
    }

    {
        const w = boot();
        await wait(60);
        w.showInvoiceDelivery({
            number: 'INV-0011',
            last_delivery: Object.assign({}, FAILED, { status: 'sent', error: '' }),
        });
        check('a delivered invoice is not warned about',
            el(w, 'invoice-undelivered').style.display === 'none');
    }

    {
        const w = boot();
        await wait(60);
        w.showInvoiceDelivery({ number: 'INV-0012', last_delivery: null });
        check('one never sent is not warned about either',
            el(w, 'invoice-undelivered').style.display === 'none');
    }

    // --- on the list ------------------------------------------------------------
    {
        const w = boot({ rows: [] });
        await wait(60);
        await w.loadDeliveryFailures();
        check('nothing failed means nothing shouted about',
            el(w, 'delivery-failures').style.display === 'none');
    }

    {
        const w = boot({ rows: [FAILED] });
        await wait(60);
        await w.loadDeliveryFailures();
        const bar = el(w, 'delivery-failures');
        check('a failure is counted where the invoices are',
            bar.style.display === 'flex');
        check('and reads as one, not "1 invoices"',
            /^1 invoice or payslip/.test(el(w, 'delivery-failures-text').textContent),
            el(w, 'delivery-failures-text').textContent);

        w.showFailedDeliveries();
        const list = el(w, 'delivery-failure-list');
        check('opening it names which one',
            /INV-0010/.test(list.textContent), list.textContent.slice(0, 60));
        check('who it was for', /ada@acme\.test/.test(list.textContent));
        check('and why it failed',
            /550 mailbox unavailable/.test(list.textContent));
    }

    {
        const w = boot({ rows: [FAILED, Object.assign({}, FAILED, { id: 4 })] });
        await wait(60);
        await w.loadDeliveryFailures();
        check('two reads as two',
            /^2 invoices or payslips/.test(el(w, 'delivery-failures-text').textContent),
            el(w, 'delivery-failures-text').textContent);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
