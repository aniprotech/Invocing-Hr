/**
 * Receiving a payment against an invoice.
 *
 * This used to be two prompt boxes in a row - the amount, then a reference -
 * with nowhere at all to say when the money arrived. So every payment was
 * dated the day somebody typed it, which is wrong for anything banked earlier
 * and wrong in every figure that measures how long customers take to pay.
 *
 * The checks that matter: the date is sent, an amount larger than the invoice
 * never leaves the browser, and a settled invoice says so rather than leaving
 * somebody to notice a status pill changed word.
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

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        if (p.endsWith('/payments')) {
            if (opts.serverError) {
                return Promise.resolve({ ok: false, status: 400,
                    json: () => Promise.resolve({ detail: opts.serverError }) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({
                    message: 'Payment recorded', status: 'Paid',
                    paid: 100, due: opts.dueAfter === undefined ? 0 : opts.dueAfter,
                }) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

    w._viewOutstanding = opts.outstanding === undefined ? 250 : opts.outstanding;
    w.fetchInvoices = () => { };
    w.viewInvoice = () => { };
    return { w, sent };
}

const el = (w, id) => w.document.getElementById(id);
const today = () => {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
        '-' + String(d.getDate()).padStart(2, '0');
};

(async () => {
    // --- the form ---------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        w.recordPayment('INV-0010');

        check('a form opens instead of a prompt box',
            el(w, 'payment-modal').style.display === 'flex');
        check('and nothing has been recorded yet',
            !sent.some(s => s.url.endsWith('/payments')));
        check('the amount is filled with what is outstanding',
            el(w, 'payment-amount').value === '250.00', el(w, 'payment-amount').value);
        check('the invoice and its balance are named',
            /INV-0010/.test(el(w, 'payment-owed').textContent) &&
            /250\.00/.test(el(w, 'payment-owed').textContent),
            el(w, 'payment-owed').textContent);

        check('there is a date, which used not to exist at all',
            el(w, 'payment-date').value === today(), el(w, 'payment-date').value);
        check('and it cannot be set past today',
            el(w, 'payment-date').max === today(), el(w, 'payment-date').max);
        check('how the money arrived can be said',
            el(w, 'payment-method').options.length >= 4);
        check('this settles it in full is said before recording',
            /settles the invoice in full/.test(el(w, 'payment-remainder').textContent),
            el(w, 'payment-remainder').textContent);
    }

    {
        const { w } = boot({ outstanding: 250 });
        await wait(60);
        w.recordPayment('INV-0010');
        el(w, 'payment-amount').value = '100';
        w.updatePaymentRemainder();
        check('a part payment says what will still be owed',
            /150\.00/.test(el(w, 'payment-remainder').textContent),
            el(w, 'payment-remainder').textContent);
    }

    // --- what actually gets sent --------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        w.recordPayment('INV-0010');
        el(w, 'payment-amount').value = '120.50';
        el(w, 'payment-date').value = '2026-08-14';
        el(w, 'payment-method').value = 'cheque';
        el(w, 'payment-reference').value = 'Chq 4471';
        sent.length = 0;
        await w.confirmPayment();
        await wait(40);

        const post = sent.find(s => s.url.endsWith('/payments'));
        check('recording posts once', !!post);
        const body = post && JSON.parse(post.body);
        check('with the amount', body && body.amount === 120.5, body && body.amount);
        check('and the date the money actually arrived, not today',
            body && body.paid_on === '2026-08-14', body && body.paid_on);
        check('how it was paid', body && body.method === 'cheque', body && body.method);
        check('and the reference', body && body.reference === 'Chq 4471');
        check('the form closes on success',
            el(w, 'payment-modal').style.display === 'none');
    }

    // --- refusals -------------------------------------------------------------------
    {
        const { w, sent } = boot({ outstanding: 100 });
        await wait(60);
        w.recordPayment('INV-0010');
        el(w, 'payment-amount').value = '500';
        sent.length = 0;
        await w.confirmPayment();

        check('more than the invoice never reaches the server',
            !sent.some(s => s.url.endsWith('/payments')));
        check('and the outstanding amount is quoted back',
            /100\.00/.test(el(w, 'payment-error').textContent),
            el(w, 'payment-error').textContent);
        check('the form stays open to be corrected',
            el(w, 'payment-modal').style.display === 'flex');
    }

    {
        const { w, sent } = boot();
        await wait(60);
        w.recordPayment('INV-0010');
        el(w, 'payment-amount').value = '0';
        sent.length = 0;
        await w.confirmPayment();
        check('nothing is not a payment',
            !sent.some(s => s.url.endsWith('/payments')));
    }

    {
        const { w, sent } = boot();
        await wait(60);
        w.recordPayment('INV-0010');
        el(w, 'payment-date').value = '2099-01-01';
        sent.length = 0;
        await w.confirmPayment();
        check('money cannot have arrived in the future',
            !sent.some(s => s.url.endsWith('/payments')));
        check('and it says so', /future/i.test(el(w, 'payment-error').textContent),
            el(w, 'payment-error').textContent);
    }

    {
        const { w } = boot({ serverError: 'This invoice has no outstanding balance' });
        await wait(60);
        w.recordPayment('INV-0010');
        await w.confirmPayment();
        await wait(40);
        check('a refusal from the server is shown, not swallowed',
            /no outstanding balance/.test(el(w, 'payment-error').textContent),
            el(w, 'payment-error').textContent);
        check('and the form stays open with the figures still in it',
            el(w, 'payment-modal').style.display === 'flex' &&
            el(w, 'payment-amount').value === '250.00');
    }

    // --- the invoice afterwards --------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        const host = w.document.getElementById('view-inv-payments');
        w.renderInvoicePayments({
            number: 'INV-0010', paid: 250, due: 0, payments: [
                { id: 1, amount: 250, paid_on: '2026-08-14', method: 'cheque' }],
        });
        check('a settled invoice says it is paid in full',
            /Paid in full/.test(host.textContent), host.textContent.slice(0, 80));
        check('with the date it was settled',
            /2026-08-14/.test(host.textContent));
    }

    {
        const { w } = boot();
        await wait(60);
        const host = w.document.getElementById('view-inv-payments');
        w.renderInvoicePayments({
            number: 'INV-0010', paid: 100, due: 150, payments: [
                { id: 1, amount: 100, paid_on: '2026-08-14', method: 'cheque' }],
        });
        check('a part paid invoice does not claim to be settled',
            !/Paid in full/.test(host.textContent));
        check('and still shows what is outstanding',
            /150\.00/.test(host.textContent), host.textContent.slice(-90));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
