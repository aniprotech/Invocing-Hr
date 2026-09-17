/**
 * Quotes answered online: the customer's page draws the quote and, while it
 * can be answered, a name box, a tick and Accept/Decline; accepting needs
 * both and posts the name; the answered/expired page offers no buttons and
 * says what happened. In the app, the quote page says what the customer
 * did and offers the link; Settings has the raise-the-invoice switch.
 * Words are text.
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

const QUOTE = { number: 'QU-0007', title: 'QUOTE', subject: 'Brand <b>refresh</b>', summary: 'Two days', terms: 'Half up front', status: 'Sent', issue_date: '2026-09-10', expiry_date: '2026-09-30',
    reference: '', currency: 'GBP', currency_symbol: '£', subtotal: 1000, tax: 200, total: 1200,
    line_items: [{ name: 'Design', description: 'Brand <i>refresh</i>', qty: 2, price: 500, amount: 1000 }],
    from: { company: 'Northwind <b>Studio</b>', address: '2 Lane', email: 'n@example.com', phone: '', tax_id: '' }, to: { name: 'Prospect Ltd', company: '', address: '', tax_id: '' },
    can_answer: true, accepted_by: '', accepted_at: '', declined_reason: '', invoice: null, brand_color: '#0284c7', logo: '', footer_note: 'Thanks' };

function bootPublic(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'quote.html'), 'utf8').replace(/<link[^>]+>/g, '');
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/quote.html?id=abc123', beforeParse(w) {
        w.sent = [];
        w.fetch = (url, init) => {
            const p = String(url).split('?')[0];
            const method = (init && init.method) || 'GET';
            w.sent.push({ url: p, method, body: init && init.body });
            const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
            if (p === '/api/public/quotes/abc123' && method === 'GET') return opts.missing ? give({ detail: 'gone' }, 404) : give(opts.quote || QUOTE);
            if (p === '/api/public/quotes/abc123/accept') return opts.acceptFails ? give({ detail: 'This quote expired on 2026-09-01' }, 410) : give({ message: 'Accepted', quote: Object.assign({}, QUOTE, { status: 'Invoiced', can_answer: false, accepted_by: 'Dana Buyer', accepted_at: '2026-09-18', invoice: { number: 'INV-0042', due: 1200, status: 'Awaiting Payment', link: 'https://localhost/invoice.html?id=x' } }) });
            if (p === '/api/public/quotes/abc123/decline') return give({ message: 'Declined', quote: Object.assign({}, QUOTE, { status: 'Declined', can_answer: false, declined_reason: 'Too dear' }) });
            return give({}, 404);
        };
        w.prompt = () => opts.declineReason === undefined ? 'Too dear' : opts.declineReason;
        w.print = () => { };
    } });
    return dom.window;
}

(async () => {
    {
        const w = bootPublic();
        await wait(60);
        const doc = w.document;
        const sheet = doc.getElementById('sheet');
        check('the customer page draws the quote: title, number, subject, lines, totals, terms - as text', !sheet.hidden && /QU-0007/.test(sheet.textContent) && /Brand <b>refresh<\/b>/.test(sheet.textContent) && !sheet.querySelector('b') &&
            /Design — Brand <i>refresh<\/i>/.test(sheet.textContent) && /£1200\.00/.test(sheet.textContent) && /Half up front/.test(sheet.textContent) && /Valid until/.test(sheet.textContent) && w.document.title === 'QU-0007 - Northwind <b>Studio</b>');
        check('  the footer note shows', !doc.getElementById('foot').hidden && doc.getElementById('foot').textContent === 'Thanks');
        check('  while it can be answered there is a name box, a tick, Accept and Decline', doc.getElementById('who') && doc.getElementById('agree') && doc.getElementById('acceptBtn') && doc.getElementById('declineBtn'));
        doc.getElementById('acceptBtn').click();
        await wait(20);
        check('  Accept without a name goes nowhere and says so', !w.sent.some(s => s.url.endsWith('/accept')) && /Type your name/.test(doc.getElementById('answerNote').textContent));
        doc.getElementById('who').value = 'Dana Buyer';
        doc.getElementById('acceptBtn').click();
        await wait(20);
        check('  Accept without the tick goes nowhere and says so', !w.sent.some(s => s.url.endsWith('/accept')) && /Tick the box/.test(doc.getElementById('answerNote').textContent));
        doc.getElementById('agree').checked = true;
        doc.getElementById('acceptBtn').click();
        await wait(40);
        const acc = w.sent.find(s => s.url.endsWith('/accept'));
        check('  with both, Accept posts the name', acc && bodyOf(acc).name === 'Dana Buyer', acc && acc.body);
        check('  and the page then says accepted, by whom, with the invoice link, and no buttons', /Accepted/.test(sheet.textContent) && /Dana Buyer on 2026-09-18/.test(sheet.textContent) && /Invoice INV-0042/.test(sheet.textContent) && !doc.getElementById('acceptBtn') && !doc.getElementById('who'));
    }
    {
        const w = bootPublic();
        await wait(60);
        const doc = w.document;
        doc.getElementById('who').value = 'Dana';
        doc.getElementById('declineBtn').click();
        await wait(40);
        const dec = w.sent.find(s => s.url.endsWith('/decline'));
        check('Decline asks why and posts the name and reason', dec && bodyOf(dec).reason === 'Too dear' && bodyOf(dec).name === 'Dana', dec && dec.body);
        check('  and the page then says declined with no buttons', /Declined/.test(doc.getElementById('sheet').textContent) && !doc.getElementById('acceptBtn'));
    }
    {
        const w = bootPublic({ declineReason: null });
        await wait(60);
        w.document.getElementById('declineBtn').click();
        await wait(30);
        check('backing out of the reason declines nothing', !w.sent.some(s => s.url.endsWith('/decline')));
    }
    {
        const w = bootPublic({ acceptFails: true });
        await wait(60);
        const doc = w.document;
        doc.getElementById('who').value = 'Dana';
        doc.getElementById('agree').checked = true;
        doc.getElementById('acceptBtn').click();
        await wait(40);
        check('a refusal from the server is shown and the buttons come back', /expired on 2026-09-01/.test(doc.getElementById('answerNote').textContent) && !doc.getElementById('acceptBtn').disabled);
    }
    {
        const w = bootPublic({ quote: Object.assign({}, QUOTE, { status: 'Expired', can_answer: false }) });
        await wait(60);
        const t = w.document.getElementById('sheet').textContent;
        check('an expired quote says so, with no way to answer', /Expired/.test(t) && /Was valid until/.test(t) && !w.document.getElementById('acceptBtn'));
    }
    {
        const w = bootPublic({ missing: true });
        await wait(60);
        check('a missing quote is said plainly', /no longer available/.test(w.document.getElementById('state').textContent));
    }
    // --- in the app ---------------------------------------------------------
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
        const w = dom.window, doc = w.document, sent = [];
        w.console.error = () => { };
        const Q = { number: 'QU-0007', to: 'Prospect', email: 'b@example.com', date: '2026-09-10', expiry_date: '2026-09-30', status: 'Invoiced', stored_status: 'Invoiced', subtotal: 1000, tax_total: 200, total: 1200, currency: 'GBP',
            line_items: [], company: {}, tracking_id: 'abc123', open_count: 3, last_opened: '2026-09-17 10:00:00', accepted_by: 'Dana <b>Buyer</b>', accepted_at: '2026-09-18 09:00:00', invoice_number: 'INV-0042', declined_reason: '', decided_at: '2026-09-18' };
        w.fetch = (url, init) => {
            const p = String(url).split('?')[0];
            sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
            const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
            if (p === '/api/quotes/QU-0007') return give(w._q || Q);
            if (p === '/api/auth/me') return give({ user: {}, client_id: 1 });
            if (p === '/api/settings') return give({ quote_accept_raises_invoice: '0' });
            return give(p.endsWith('s') ? [] : {});
        };
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        w.showToast = () => { };
        await w.viewQuote('QU-0007');
        await wait(30);
        const strip = doc.getElementById('view-quote-answer');
        check('the quote page in the app says who accepted it online, when, and the invoice raised - as text', strip.style.display === 'block' && /Accepted online by Dana <b>Buyer<\/b> on 2026-09-18/.test(strip.textContent) && !strip.querySelector('b') && /invoice INV-0042 raised/.test(strip.textContent), strip.textContent);
        check('  and the customer link is the quote page with its tracking id', w.quoteCustomerLink() === 'https://localhost/quote.html?id=abc123' && /copyQuoteLink/.test(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')));
        w._q = Object.assign({}, Q, { status: 'Declined', stored_status: 'Declined', accepted_by: 'Dana', invoice_number: '', declined_reason: 'Too <i>dear</i>' });
        await w.viewQuote('QU-0007');
        await wait(30);
        check('  a decline shows by whom and why', /Declined online by Dana on 2026-09-18/.test(strip.textContent) && /Too <i>dear<\/i>/.test(strip.textContent) && !strip.querySelector('i'));
        w._q = Object.assign({}, Q, { status: 'Sent', stored_status: 'Sent', accepted_by: '', invoice_number: '', open_count: 3 });
        await w.viewQuote('QU-0007');
        await wait(30);
        check('  an unanswered one says how often it was opened', /Opened by the customer 3 times/.test(strip.textContent) && /not answered yet/.test(strip.textContent));
        await w.loadOnlinePaymentNotice();
        await wait(20);
        check('Settings reads the raise-the-invoice switch', doc.getElementById('quote-accept-invoice').checked === false);
        doc.getElementById('quote-accept-invoice').checked = true;
        await w.saveQuoteAcceptInvoice(doc.getElementById('quote-accept-invoice'));
        const put = sent.find(s => s.url === '/api/settings' && s.method === 'POST');
        check('  and saves it', put && bodyOf(put).quote_accept_raises_invoice === '1');
    }
    console.log(failures === 0 ? '\nAll quotes-online checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
