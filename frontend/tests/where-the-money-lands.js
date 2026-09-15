/**
 * Where the money lands, on screen: the receive-payment form asks which
 * account, the invoice says where each receipt went, Settings lists the
 * accounts with their totals, and a gateway's keys can be checked before
 * a customer finds out. Names are the business's own words - text, always.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const ACCOUNTS = { currency: 'GBP', kinds: ['bank', 'cash', 'gateway', 'other'], untracked: { count: 2, all_time: 40, this_month: 0, last_month: 0, last_on: '' }, accounts: [
    { id: 1, name: 'HDFC <b>current</b>', kind: 'bank', provider: '', details: 'A/c 1234', is_default: true, active: true, totals: { this_month: 100, last_month: 200, all_time: 300, count: 2, last_on: '2026-09-10' } },
    { id: 2, name: 'Cash box', kind: 'cash', provider: '', details: '', is_default: false, active: true, totals: { this_month: 30, last_month: 0, all_time: 30, count: 1, last_on: '2026-09-11' } },
    { id: 3, name: 'Old bank', kind: 'bank', provider: '', details: '', is_default: false, active: false, totals: { this_month: 0, last_month: 0, all_time: 0, count: 0, last_on: '' } },
] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], forms = [];
    let added = null;            // the account POSTed, so the next GET lists it
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/accounts' && method === 'GET') {
            const base = opts.accounts || ACCOUNTS;
            return give(added ? Object.assign({}, base, { accounts: base.accounts.concat([added]) }) : base);
        }
        if (p === '/api/accounts' && method === 'POST') { added = { id: 9, name: 'Kotak', kind: 'bank', provider: '', details: '', is_default: false, active: true, totals: {} }; return give(added); }
        if (p.startsWith('/api/accounts/') && method === 'PUT') return give({ id: 2 });
        if (p.startsWith('/api/accounts/') && method === 'DELETE') return give({ message: 'Closed - 1 receipt names it, so it stays on record', closed: true });
        if (p === '/api/invoices/INV-1/payments' && method === 'POST') return give({ message: 'Payment recorded', due: 0 });
        if (p === '/api/invoices/INV-1' && method === 'GET') return give({ number: 'INV-1', due: 0, paid: 50, status: 'Paid', is_overdue: false, line_items: [], company: {},
            payments: [{ id: 4, amount: 50, paid_on: '2026-09-10', method: 'bank_transfer', reference: 'TXN1', account_id: 1, account_name: 'HDFC <b>current</b>' }] });
        if (p === '/api/payment-gateways' && method === 'GET') return give({ gateways: [
            { provider: 'razorpay', label: 'Razorpay', public_key: 'rzp_test_x', secret_key: '****', has_secret: true, is_active: true, is_live: false, updated_at: '' },
            { provider: 'stripe', label: 'Stripe (cards)', public_key: '', secret_key: '', has_secret: false, is_active: false, is_live: false, updated_at: '' },
            { provider: 'paypal', label: 'PayPal', public_key: '', secret_key: '', has_secret: false, is_active: false, is_live: false, updated_at: '' } ] });
        if (p === '/api/payment-gateways/razorpay/check') return give(opts.checkResult || { ok: true, message: 'Razorpay accepted the keys (test mode)', live: false, warning: 'These are test keys but the box says live - real customers will not be charged', offered: true });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    w.uiForm = (fields) => { forms.push(fields); return Promise.resolve(opts.form === undefined ? null : opts.form); };
    return { w, doc: w.document, sent, forms };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the receive form has a Paid-into select with a way to add an account, and Settings has the accounts widget',
            /id="payment-account"/.test(src) && /addAccount\(true\)/.test(src) && /id="accounts-list"/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        w._viewOutstanding = 50;
        w.recordPayment('INV-1');
        await wait(40);
        const sel = doc.getElementById('payment-account');
        check('the form lists the open accounts, default first and selected, closed ones left out, names as text',
            sel.options.length === 2 && sel.value === '1' && /HDFC <b>current<\/b> · default/.test(sel.options[0].textContent) && /Cash box \(cash\)/.test(sel.options[1].textContent) && !sel.querySelector('b'),
            Array.from(sel.options).map(o => o.textContent).join('|'));
        doc.getElementById('payment-amount').value = '50';
        doc.getElementById('payment-date').value = '2026-09-10';
        sel.value = '2';
        await w.confirmPayment();
        await wait(40);
        const post = sent.find(s => s.url === '/api/invoices/INV-1/payments' && s.method === 'POST');
        check('  and the receipt is sent with the chosen account as a number', post && bodyOf(post).account_id === 2 && bodyOf(post).amount === 50, post && post.body);
        await w.viewInvoice('INV-1');
        await wait(40);
        const host = doc.getElementById('view-inv-payments');
        check('the invoice says how and where each receipt went, in words, as text', /Bank transfer → HDFC <b>current<\/b>/.test(host.textContent) && !host.querySelector('b'), host.textContent.slice(0, 200));
    }
    {
        const { w, doc, sent } = boot({ accounts: { accounts: [], untracked: { count: 0 }, kinds: [] } });
        w._viewOutstanding = 50;
        w.recordPayment('INV-1');
        await wait(40);
        const sel = doc.getElementById('payment-account');
        check('with no accounts the form says the receipt is not tracked and how to fix that', sel.options.length === 1 && sel.value === '' && /Add an account/.test(doc.getElementById('payment-account-hint').textContent));
        doc.getElementById('payment-amount').value = '50';
        doc.getElementById('payment-date').value = '2026-09-10';
        await w.confirmPayment();
        await wait(30);
        const post = sent.find(s => s.url === '/api/invoices/INV-1/payments' && s.method === 'POST');
        check('  and sends no account rather than a zero', post && bodyOf(post).account_id === null, post && post.body);
    }
    {
        const { w, doc, sent } = boot({ form: { name: 'Kotak', kind: 'bank', details: '' } });
        w._viewOutstanding = 50;
        w.recordPayment('INV-1');
        await wait(30);
        await w.addAccount(true);
        await wait(40);
        const post = sent.find(s => s.url === '/api/accounts' && s.method === 'POST');
        check('adding an account from the form posts it and selects the new one', post && bodyOf(post).name === 'Kotak' && doc.getElementById('payment-account').value === '9');
    }
    {
        const { w, doc, sent } = boot();
        await w.loadAccounts();
        await wait(40);
        const host = doc.getElementById('accounts-list');
        const text = host.textContent;
        check('Settings lists every account with kind, this month, last month, all time, names as text',
            /HDFC <b>current<\/b>/.test(text) && !host.querySelector('b') && /£100\.00/.test(text) && /£200\.00/.test(text) && /£300\.00/.test(text) && /Cash/.test(text) && /default/.test(text) && /closed/.test(text), text.slice(0, 300));
        check('  and mentions the receipts recorded before accounts existed', /2 older receipts \(£40\.00\)/.test(text));
        const mk = host.querySelector('[data-acct-default="2"]');
        check('  the default has no Make-default button; the others do; a closed one can be reopened', mk && !host.querySelector('[data-acct-default="1"]') && host.querySelector('[data-acct-reopen="3"]'));
        mk.click();
        await wait(30);
        const put = sent.find(s => s.url === '/api/accounts/2' && s.method === 'PUT');
        check('  making one the default sends is_default', put && bodyOf(put).is_default === true);
        host.querySelector('[data-acct-close="2"]').click();
        await wait(30);
        check('  closing asks, then deletes (the server decides whether to close or remove)', sent.some(s => s.url === '/api/accounts/2' && s.method === 'DELETE'));
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.loadAccounts();
        await wait(30);
        doc.querySelector('[data-acct-close="2"]').click();
        await wait(30);
        check('backing out of a close deletes nothing', !sent.some(s => s.method === 'DELETE'));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadPaymentGateways();
        await wait(40);
        const host = doc.getElementById('gateway-list');
        check('a gateway with keys saved offers Check keys; one without does not', host.querySelector('#gw-check-razorpay') && !host.querySelector('#gw-check-stripe'));
        check('Stripe is no longer described as unwired, PayPal still is', !/Stripe[^]*?not wired/.test(host.innerHTML) && /PayPal[^]*?cannot be paid with this yet/.test(host.innerHTML));
        await w.checkPaymentGateway('razorpay');
        await wait(30);
        const out = doc.getElementById('gw-result-razorpay');
        check('  checking asks the server and shows what the provider said, with the live/test warning',
            sent.some(s => s.url === '/api/payment-gateways/razorpay/check' && s.method === 'POST') && /✓ Razorpay accepted the keys/.test(out.textContent) && /test keys but the box says live/.test(out.textContent) && out.style.display === 'block');
    }
    {
        const { w, doc } = boot({ checkResult: { ok: false, message: 'Razorpay refused the keys: Authentication failed', live: null, warning: '', offered: false } });
        await w.loadPaymentGateways();
        await wait(30);
        await w.checkPaymentGateway('razorpay');
        await wait(30);
        check('a refusal is shown as one', /✗ Razorpay refused the keys/.test(doc.getElementById('gw-result-razorpay').textContent));
    }
    console.log(failures === 0 ? '\nAll where-the-money-lands checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
