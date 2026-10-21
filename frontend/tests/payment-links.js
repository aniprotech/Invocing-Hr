/**
 * Payment links.
 *
 * On the business's screen: the list and its tabs and search; what each state
 * offers (an open link can be copied, emailed and - if nothing is paid -
 * cancelled; the rest only link to the invoice behind them); that the form
 * sends exactly what was typed and nothing when cancelled or incomplete; that
 * the link made is copied for them; and that a warning or an email failure is
 * said. On the customer's page: that a payment link reads as a payment request,
 * says "valid until", hides "Billed to" when nobody is named, and says plainly
 * when a link has expired or been cancelled.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { boot, wait, makeChecker, appDocument, fail, ROOT } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const mk = (n, state, extra) => Object.assign({ number: 'INV-000' + n, tracking_id: 'track-' + n, description: 'Deposit ' + n, amount: 250, paid: 0, due: 250, currency: 'GBP',
    customer: 'Dana', email: 'dana@example.com', reference: 'JOB-' + n, state, created: '2026-11-01', expires_on: '2026-12-01', opens: 2 }, extra || {});
const OPEN = mk(1, 'open'), PART = mk(2, 'open', { paid: 100, due: 150 }), PAID = mk(3, 'paid', { paid: 250, due: 0 }), EXPIRED = mk(4, 'expired'),
    CANCELLED = mk(5, 'cancelled'), EVIL = mk(6, 'open', { description: '<b>Evil</b> job', customer: '<i>X</i>' });
const ALL = [OPEN, PART, PAID, EXPIRED, CANCELLED, EVIL];

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        const method = init.method || 'GET';
        if (p === '/api/payment-links' && method === 'GET') {
            if (opts.listFails) return fail(500, 'Server is down');
            const st = (full.match(/status=([a-z]+)/) || [])[1] || 'all';
            const q = decodeURIComponent((full.match(/[?&]q=([^&]*)/) || [])[1] || '').toLowerCase();
            let rows = ALL.filter(l => st === 'all' || l.state === st);
            if (q) rows = rows.filter(l => (l.description + l.customer + l.reference).toLowerCase().includes(q));
            return { links: rows, count: rows.length, open_total: 650, paid_total: 250 };
        }
        if (p === '/api/payment-links' && method === 'POST') {
            if (opts.createFails) return fail(400, opts.createFails);
            return Object.assign({}, OPEN, { warning: opts.warning || '', sent_now: !!opts.sentNow, send_error: opts.sendError || '' });
        }
        if (/^\/api\/payment-links\/[^/]+\/send$/.test(p)) return opts.actionFails ? fail(400, opts.actionFails) : { message: 'Link sent to other@example.com' };
        if (/^\/api\/payment-links\/[^/]+\/cancel$/.test(p)) return opts.actionFails ? fail(400, opts.actionFails) : CANCELLED;
        return undefined;
    };
}
const asking = (w, answers) => { const asked = []; w.uiForm = (f, o) => { asked.push({ fields: f, opts: o || {} }); return Promise.resolve(answers.length ? answers.shift() : null); }; return asked; };

function publicPage(status, body) {
    const html = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/invoice.html?id=t',
        beforeParse(w) {
            w.fetch = (url) => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body), text: () => Promise.resolve('') });
            w.console.error = () => { };
        } });
    return dom.window;
}
// What a person sees: the body without the page's own script text.
const seen = w => { const b = w.document.body.cloneNode(true); b.querySelectorAll('script,style').forEach(e => e.remove()); return b.textContent; };
const labels = w => [...w.document.querySelectorAll('.label')].map(e => e.textContent.trim());
const PAGE = { number: 'INV-0001', title: 'PAYMENT REQUEST', payment_link: true, valid_until: '2026-12-01', status: 'Awaiting Payment', issue_date: '2026-11-01', due_date: '2026-12-01',
    days_overdue: 0, currency: 'GBP', currency_symbol: '£', subtotal: 250, tax: 0, total: 250, paid: 0, amount_due: 250, is_settled: false, credit_notes: [],
    line_items: [{ name: '', description: 'Deposit for the kitchen', qty: 1, price: 250, amount: 250 }], from: { company: 'Acme Ltd', address: '', email: '', phone: '', tax_id: '' },
    to: { name: '', company: '', address: '', tax_id: '' }, bank_details: '', payment_terms: '', footer_note: '', brand_color: '#0284c7', payment: null, logo: '' };

(async () => {
    {
        const doc = appDocument();
        check('Payment links is in the Sales menu, next to Payment options',
            !!doc.querySelector('[data-nav-group="Sales"] #nav-payment-links') && doc.getElementById('nav-payment-links').textContent.trim() === 'Payment links');
        check('the screen has tabs, a search and a table', ['payment-links-view', 'pl-tabs', 'pl-search', 'pl-body', 'pl-summary'].every(id => !!doc.getElementById(id)));
        check('the tabs are all, open, paid, expired and cancelled', [...doc.querySelectorAll('#pl-tabs .tab')].map(b => b.getAttribute('data-pl-status')).join() === 'all,open,paid,expired,cancelled');
        check('the Sales dashboard has a quick link to make one', /newPaymentLink/.test(doc.getElementById('sales-quick-links').innerHTML));
        check('Payment options no longer says links are not available', !/not available yet/.test(doc.getElementById('payment-options-view').textContent) && /payment-links/.test(doc.getElementById('payment-options-view').innerHTML));
    }
    {
        const { w, sent, confirms } = boot(server());
        await wait(60);
        check('the address and highlight are known', w.ROUTE_SLUGS['payment-links-view'] === 'payment-links' && w.NAV_FOR_VIEW['payment-links-view'] === 'nav-payment-links');
        w.showView('payment-links-view');
        await wait(300);
        const doc = w.document, body = doc.getElementById('pl-body');
        const rowOf = x => [...body.querySelectorAll('tr')].find(tr => tr.textContent.includes(x));
        check('it lists every link with amount, status and a summary',
            body.querySelectorAll('tr').length === 6 && /6 links/.test(doc.getElementById('pl-summary').textContent)
            && /650\.00 waiting to be paid/.test(doc.getElementById('pl-summary').textContent) && /250\.00 paid/.test(doc.getElementById('pl-summary').textContent));
        check('status says Open, Paid, Expired and Cancelled',
            /Open/.test(rowOf('Deposit 1').textContent) && /Paid/.test(rowOf('Deposit 3').textContent) && /Expired/.test(rowOf('Deposit 4').textContent) && /Cancelled/.test(rowOf('Deposit 5').textContent));
        check('names can never become markup', body.querySelector('b') === null && body.querySelector('i') === null && /<b>Evil<\/b> job/.test(body.textContent));
        check('an open link offers Copy, Email and Cancel', !!rowOf('Deposit 1').querySelector('[data-pl-copy]') && !!rowOf('Deposit 1').querySelector('[data-pl-send]') && !!rowOf('Deposit 1').querySelector('[data-pl-cancel]'));
        check('a part-paid link cannot be cancelled and says what was paid', !rowOf('Deposit 2').querySelector('[data-pl-cancel]') && /100\.00 paid/.test(rowOf('Deposit 2').textContent));
        check('the others only open the invoice behind them', ['Deposit 3', 'Deposit 4', 'Deposit 5'].every(x => !rowOf(x).querySelector('[data-pl-copy]') && /Invoice/.test(rowOf(x).textContent)));
        w.filterPaymentLinks('paid', doc.querySelector('[data-pl-status="paid"]'));
        await wait(300);
        check('a tab asks for that status and is lit', /status=paid/.test(sent.filter(s => s.url === '/api/payment-links').pop().full) && doc.querySelector('[data-pl-status="paid"]').classList.contains('active'));
        w.filterPaymentLinks('all', doc.querySelector('[data-pl-status="all"]'));
        doc.getElementById('pl-search').value = 'zzz'; w.loadPaymentLinks();
        await wait(300);
        check('the search is sent and an empty answer is said', /q=zzz/.test(sent.filter(s => s.url === '/api/payment-links').pop().full) && /No payment link matches/.test(body.textContent));
        check('the link is the invoice page on this site', w.paymentLinkUrl('abc 1') === 'https://localhost/invoice.html?id=abc%201');
    }

    // --- making one ---------------------------------------------------------------------------
    {
        const { w, sent, toasts } = boot(server({ warning: 'No online payment method is switched on.' }));
        await wait(60);
        let copied = '';
        Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: (x) => { copied = x; return Promise.resolve(); } }, configurable: true });
        const asked = asking(w, [null, { amount: '250', description: ' Deposit for the kitchen ', customer_name: ' Dana ', email: ' dana@example.com ', reference: 'JOB-1', expires_in_days: '14', send: 'no' },
            { amount: '0', description: 'x', expires_in_days: '30', send: 'no' }, { amount: '5', description: '  ', expires_in_days: '30', send: 'no' },
            { amount: '9', description: 'Pens', email: '', expires_in_days: '30', send: 'yes' }]);
        const posts = () => sent.filter(s => s.method === 'POST' && s.url === '/api/payment-links');
        await w.newPaymentLink();
        check('cancelling the form sends nothing', posts().length === 0);
        await w.newPaymentLink();
        const body = posts().length && JSON.parse(posts()[0].body);
        check('Save posts exactly what was typed',
            body && body.amount === 250 && body.description === 'Deposit for the kitchen' && body.customer_name === 'Dana' && body.email === 'dana@example.com'
            && body.reference === 'JOB-1' && body.expires_in_days === 14 && body.send === false, posts()[0] && posts()[0].body);
        check('the link is copied for them, and a warning is said',
            copied === 'https://localhost/invoice.html?id=track-1' && toasts.some(x => /No online payment method/.test(x.m)));
        const n = posts().length;
        await w.newPaymentLink();
        check('an amount is required and nothing is sent without one', toasts.some(x => /more than nothing/.test(x.m)) && posts().length === n);
        await w.newPaymentLink();
        check('so is what it is for', toasts.some(x => /what the payment is for/.test(x.m)) && posts().length === n);
        await w.newPaymentLink();
        check('asking to email it without an address sends nothing to email', JSON.parse(posts()[1].body).send === false);
        check('the form offers lengths of 7 days to a year', asked[0].fields.find(f => f.name === 'expires_in_days').options.map(o => o.value).join() === '7,14,30,60,90,365');
    }
    {
        const { w, toasts } = boot(server({ sentNow: true }));
        await wait(60);
        asking(w, [{ amount: '5', description: 'x', email: 'a@b.co', expires_in_days: '30', send: 'yes' }]);
        await w.newPaymentLink();
        check('a link that was emailed says so', toasts.some(x => /emailed to dana@example.com/.test(x.m)));
    }
    {
        const { w, toasts } = boot(server({ sendError: 'no mail is set up' }));
        await wait(60);
        Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: () => Promise.resolve() }, configurable: true });
        asking(w, [{ amount: '5', description: 'x', email: 'a@b.co', expires_in_days: '30', send: 'yes' }]);
        await w.newPaymentLink();
        check('a link that could not be emailed is still made, and says why', toasts.some(x => /made but not emailed: no mail is set up/.test(x.m)));
    }
    {
        const { w, toasts } = boot(server({ createFails: 'The link can last between 1 and 365 days' }));
        await wait(60);
        asking(w, [{ amount: '5', description: 'x', expires_in_days: '30', send: 'no' }]);
        await w.newPaymentLink();
        check('a refusal from the server is shown', toasts.some(x => /between 1 and 365/.test(x.m)));
    }

    // --- email, cancel ------------------------------------------------------------------------------
    {
        const { w, sent, confirms, toasts } = boot(server());
        await wait(60);
        w.showView('payment-links-view');
        await wait(300);
        const asked = asking(w, [null, { email: ' other@example.com ' }]);
        await w.emailPaymentLink(OPEN);
        check('cancelling the email form sends nothing', !sent.some(s => /\/send$/.test(s.url)));
        await w.emailPaymentLink(OPEN);
        check('the email form starts from the address on the link', asked[0].fields[0].value === 'dana@example.com');
        const post = sent.filter(s => /\/send$/.test(s.url)).pop();
        check('Email posts the address to that link', post && post.url === '/api/payment-links/INV-0001/send' && JSON.parse(post.body).email === 'other@example.com' && toasts.some(x => /Link sent/.test(x.m)));
        await w.cancelPaymentLink(OPEN);
        check('Cancel asks first, naming the link, then cancels',
            confirms.length === 1 && /Deposit 1/.test(confirms[0]) && sent.some(s => s.method === 'POST' && s.url === '/api/payment-links/INV-0001/cancel') && toasts.some(x => /cancelled/.test(x.m)));
    }
    {
        const { w, toasts } = boot(server({ actionFails: 'Only an open link can be cancelled' }), { confirm: true });
        await wait(60);
        await w.cancelPaymentLink(OPEN);
        check('a refusal from cancel is shown', toasts.some(x => /Only an open link/.test(x.m)));
    }
    {
        const { w } = boot(server({ listFails: true }));
        await wait(60);
        w.showView('payment-links-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('pl-body').textContent));
    }

    // --- the page the customer opens ----------------------------------------------------------
    {
        const w = publicPage(200, PAGE);
        await wait(150);
        const text = seen(w);
        check('a payment link reads as a payment request', /PAYMENT REQUEST/.test(text) && /Deposit for the kitchen/.test(text) && /£250\.00/.test(text));
        check('it says valid until, not due', labels(w).includes('Valid until') && !labels(w).includes('Due') && /2026-12-01/.test(text), labels(w).join());
        check('with nobody named there is no Billed to', !labels(w).includes('Billed to'), labels(w).join());
        check('and it says Requested, not Issued', labels(w).includes('Requested') && !labels(w).includes('Issued'), labels(w).join());
    }
    {
        const w = publicPage(200, Object.assign({}, PAGE, { to: { name: 'Dana Smith', company: '', address: '', tax_id: '' } }));
        await wait(150);
        check('a named customer is shown under Billed to', labels(w).includes('Billed to') && /Dana Smith/.test(seen(w)), labels(w).join());
    }
    {
        const w = publicPage(200, Object.assign({}, PAGE, { payment_link: false, title: 'TAX INVOICE', valid_until: '', to: { name: 'Acme', company: '', address: '', tax_id: '' } }));
        await wait(150);
        const text = seen(w);
        check('an ordinary invoice is unchanged: Issued and Due, and Billed to',
            labels(w).includes('Issued') && labels(w).includes('Due') && labels(w).includes('Billed to') && !labels(w).includes('Valid until') && /TAX INVOICE/.test(text), labels(w).join());
    }
    for (const [detail, label] of [['This payment link has expired', 'an expired link says so'], ['This payment link has been cancelled', 'a cancelled link says so']]) {
        const w = publicPage(404, { detail });
        await wait(150);
        check(label, w.document.getElementById('state').textContent.includes(detail) && /ask the business for a new one/.test(w.document.getElementById('state').textContent));
    }
    {
        const w = publicPage(404, { detail: 'That invoice is not available' });
        await wait(150);
        check('an ordinary unavailable invoice keeps its own wording', /This invoice is no longer available/.test(w.document.getElementById('state').textContent));
    }

    t.finish('payment links');
})();
