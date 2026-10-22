/**
 * "View and pay online" on the invoice.
 *
 * The browser draws a PDF too (generateInvoicePDF), and the server draws the
 * same document (pdf.py); the block has to appear in both, in the same place,
 * from the same data. This runs the browser's engine with a jsPDF that records
 * what is drawn, and checks: the code is the matrix it was given, the badges
 * are the ones named, nothing is drawn for another invoice's data, when hidden,
 * or on a quote, a long list of badges wraps instead of running off, and the
 * customer's page shows the same badges beside the Pay button.
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

// A jsPDF that remembers what it was asked to draw.
class Spy extends jsPDF {
    constructor(...args) {
        super(...args);
        const calls = this.__calls = [];
        for (const name of ['text', 'rect', 'roundedRect', 'circle']) {
            const real = this[name].bind(this);
            this[name] = (...a) => { calls.push([name, ...a]); return real(...a); };
        }
    }
}

function pdfWindow() {
    const html = `<!DOCTYPE html><html><body>
      <span id="view-inv-contact">Anika Care Limited</span><span id="view-inv-email-display">billing@example.com</span>
      <span id="view-inv-phone-display">+44 121 000 0000</span><span id="view-inv-issue-date">14 Aug 2026</span>
      <span id="view-inv-due-date">31 Aug 2026</span><span id="view-inv-number-val">INV-0273</span>
      <span id="view-inv-bank-content"></span><span id="view-inv-ref"></span><span id="view-inv-due-currency">£</span>
      <span id="view-summary-subtotal">100.00</span><span id="view-summary-vat">20.00</span><span id="view-summary-total">120.00</span>
      <span id="view-inv-company-name">aniprotech</span><span id="view-inv-company-address">53 Newbridge Cres</span>
      <span id="view-inv-company-email">hello@example.com</span><span id="view-inv-company-phone">01902521476</span><span id="view-inv-company-abn">123</span>
      <table><tbody id="view-line-items-body"><tr><td>X-1</td><td>Design work</td><td>1</td><td>100.00</td><td>0</td><td>20</td><td>100.00</td></tr></tbody></table>
    </body></html>`;
    const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.jspdf = { jsPDF: Spy };
    w.localStorage.setItem('company_logo', '');
    w.fetch = () => Promise.reject(new Error('offline'));
    w.showToast = () => { };
    w.Chart = function () { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.eval('_brandTheme = ' + JSON.stringify({ font: 'helvetica', brand_color: '#0284c7', show_quantity: true, show_price: true, show_page_numbers: true }) + ';');
    return w;
}

const MATRIX = ['1110111', '1010101', '1110111', '0001000', '1110111', '1010101', '1110111'];    // not a real code: its shape is what is checked
const texts = doc => doc.__calls.filter(c => c[0] === 'text').map(c => Array.isArray(c[1]) ? c[1].join(' ') : String(c[1]));
const rects = doc => doc.__calls.filter(c => c[0] === 'rect' && c[5] === 'F');
const badges = doc => doc.__calls.filter(c => c[0] === 'roundedRect').length;
const draw = (w, isDummy, kind) => w.eval(`generateInvoicePDF(${isDummy}, "${kind || 'invoice'}")`);
const given = (w, block) => { w._viewPayOnline = block; };
const BLOCK = (over) => Object.assign({ number: 'INV-0273', heading: 'View and pay online', badges: ['visa', 'mastercard', 'applepay', 'googlepay'], matrix: MATRIX }, over || {});

(async () => {
    // --- the sample in the branding preview ----------------------------------------
    {
        const w = pdfWindow();
        const doc = draw(w, true);
        check('the branding preview shows the block, so a business can see where it will sit',
            texts(doc).includes('View and pay online') && badges(doc) >= 4, texts(doc).join('|'));
        check('with a code made of many squares', rects(doc).length > 60);
        check('and it is still a PDF', doc.output('datauristring').split('base64,')[1].length > 1000);
    }

    // --- a real invoice ------------------------------------------------------------
    {
        const w = pdfWindow();
        given(w, BLOCK());
        const doc = draw(w, false);
        check('an invoice with a block draws the heading and the sentence under it',
            texts(doc).includes('View and pay online') && texts(doc).includes('Scan the code with your phone to pay.'));
        check('and one badge for each way to pay', badges(doc) === 4, String(badges(doc)));
        const qr = rects(doc).filter(c => c[1] >= 45 && c[1] <= 45 + 70 && c[3] < 70);
        const runs = MATRIX.reduce((n, row) => n + (row.match(/1+/g) || []).length, 0);
        check('the code is the matrix it was given: one rectangle per run of dark squares', qr.length === runs, `${qr.length} of ${runs}`);
        check('every square is inside the 70-point box on the left margin',
            qr.every(c => c[1] >= 45 && c[1] + c[3] <= 45 + 70.5 && c[2] >= 0), JSON.stringify(qr.slice(0, 2)));
        const labels = doc.__calls.filter(c => c[0] === 'text' && c[1] === 'TOTAL  GBP');
        check('the totals are still drawn beside it', texts(doc).includes('Subtotal') && labels.length === 1);
        check('the heading sits level with the totals', (() => {
            const head = doc.__calls.find(c => c[0] === 'text' && c[1] === 'View and pay online');
            const sub = doc.__calls.find(c => c[0] === 'text' && c[1] === 'Subtotal');
            return head && sub && Math.abs(head[3] - sub[3]) < 12;
        })());
    }
    {
        const w = pdfWindow();
        given(w, BLOCK({ number: 'INV-9999' }));
        check('data that belongs to another invoice is never drawn on this one', !texts(draw(w, false)).includes('View and pay online'));
        given(w, null);
        check('no block means nothing drawn', !texts(draw(w, false)).includes('View and pay online'));
    }
    {
        const w = pdfWindow();
        given(w, BLOCK());
        w.eval('window._invoiceLayout = [{ id: "pay_online", visible: false }];');
        check('a business that hid it from its template does not get it', !texts(draw(w, false)).includes('View and pay online'));
        w.eval('window._invoiceLayout = [{ id: "bank_details", visible: false }];');
        check('and one that hid something else does', texts(draw(w, false)).includes('View and pay online'));
    }
    {
        const w = pdfWindow();
        given(w, BLOCK());
        check('a quote never gets one', !texts(draw(w, true, 'quote')).includes('View and pay online'));
        check('nor a credit note', !texts(draw(w, true, 'credit_note')).includes('View and pay online'));
    }
    {
        const w = pdfWindow();
        given(w, BLOCK({ badges: ['visa', 'mastercard', 'amex', 'applepay', 'googlepay', 'paypal', 'upi', 'bank'] }));
        const doc = draw(w, false);
        check('eight badges are all drawn', badges(doc) === 8, String(badges(doc)));
        const rows = new Set(doc.__calls.filter(c => c[0] === 'roundedRect').map(c => Math.round(c[2])));
        check('and wrap onto a second row instead of running into the totals', rows.size === 2, [...rows].join());
        const right = Math.max.apply(null, doc.__calls.filter(c => c[0] === 'roundedRect').map(c => c[1] + c[3]));
        check('no badge reaches the totals column', right < 595.28 - 45 - 150, String(right));
    }
    {
        // a long invoice: the block goes with the totals, wherever they land
        const w = pdfWindow();
        const body = w.document.getElementById('view-line-items-body');
        for (let i = 0; i < 40; i++) body.insertAdjacentHTML('beforeend', '<tr><td>R-' + i + '</td><td>Row ' + i + ' with some words to fill the line</td><td>1</td><td>10.00</td><td>0</td><td>0</td><td>10.00</td></tr>');
        given(w, BLOCK());
        let doc, err = '';
        try { doc = draw(w, false); } catch (e) { err = e.message; }
        check('a long invoice still draws, with the block', !err && texts(doc).includes('View and pay online') && doc.getNumberOfPages() >= 2, err);
        const headY = doc.__calls.find(c => c[0] === 'text' && c[1] === 'View and pay online')[3];
        check('and it is on the page, not off the bottom', headY < 841.89 - 80, String(headY));
    }

    // --- the layout list ---------------------------------------------------------------
    {
        const w = pdfWindow();
        check('the template lists "View and pay online" as a block a business can hide', w.eval('defaultInvoiceLayout.some(function (b) { return b.id === "pay_online"; })') && w.eval('HIDEABLE_BLOCKS.indexOf("pay_online") >= 0'));
        const saved = JSON.stringify([{ id: 'header', visible: true, label: 'Header' }, { id: 'payment_stub', visible: false, label: 'Payment Stub' }]);
        w.eval(`initTemplateBuilder(${JSON.stringify(saved)});`);
        const layout = w.eval('window._invoiceLayout');
        check('a layout saved before it existed gets it added, shown, and keeps what was chosen',
            layout.some(b => b.id === 'pay_online' && b.visible === true) && layout.find(b => b.id === 'payment_stub').visible === false);
    }

    // --- the customer's page --------------------------------------------------------------
    function publicPage(badgesList) {
        const html = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const inv = { number: 'INV-1', title: 'TAX INVOICE', payment_link: false, status: 'Awaiting Payment', issue_date: '2026-11-01', due_date: '2026-12-01', days_overdue: 0,
            currency: 'GBP', currency_symbol: '£', subtotal: 100, tax: 0, total: 100, paid: 0, amount_due: 100, is_settled: false, credit_notes: [],
            line_items: [{ name: '', description: 'Work', qty: 1, price: 100, amount: 100 }], from: { company: 'Acme', address: '', email: '', phone: '', tax_id: '' },
            to: { name: 'Dana', company: '', address: '', tax_id: '' }, bank_details: '', payment_terms: '', footer_note: '', brand_color: '#0284c7',
            payment: { provider: 'stripe', key_id: '', providers: ['stripe'], badges: badgesList }, logo: '' };
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/invoice.html?id=t',
            beforeParse(win) {
                win.fetch = (url) => {
                    const body = /\/pay\/methods/.test(url) ? { methods: [{ provider: 'stripe' }], is_paid: false } : inv;
                    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body), text: () => Promise.resolve('') });
                };
                win.console.error = () => { };
            } });
        return dom.window;
    }
    {
        const w = publicPage(['visa', 'mastercard', 'amex', 'applepay', 'googlepay', 'nonsense']);
        await wait(300);
        const strip = w.document.querySelector('#payBox .badges');
        check('the page shows the badges beside the Pay button', !!strip && /Pay online with/.test(strip.textContent));
        check('one for each way to pay, in order, and nothing it does not know',
            [...strip.querySelectorAll('.pb')].map(e => e.className.replace('pb ', '')).join() === 'pb-visa,pb-mastercard,pb-amex,pb-applepay,pb-googlepay');
        check('the Pay button is still there', !!w.document.getElementById('payOpen'));
    }
    {
        const w = publicPage([]);
        await wait(300);
        check('with no badges the page is as it was', !w.document.querySelector('#payBox .badges') && !!w.document.getElementById('payOpen'));
    }

    if (failures) { console.log(`\n${failures} pay-online check(s) failed.`); process.exit(1); }
    console.log('\nAll pay-online checks passed.');
})();
