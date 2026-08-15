/**
 * Actually run generateInvoicePDF.
 *
 * The last two PDF regressions were both "a variable stopped existing and
 * jsPDF threw", which no amount of reading the diff caught. This builds the
 * DOM the function reads, loads app.js into it, and generates a document for
 * every combination of theme columns - the thing the email attachment and the
 * preview both depend on.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const APP_JS = path.resolve(__dirname, '..', 'app.js');

function buildDom() {
    const rows = [
        ['GS-100', 'Supply and install garden shed netting', '1', '900.00', '0', '10', '900.00'],
        ['GS-210', 'Supply and install steel poles that need a much longer description so the text wraps across several lines inside the cell', '4', '164.00', '5', '10', '660.00'],
        ['RS-004', 'Roofing screws', '2', '18.90', '0', '0', '37.80'],
    ];
    const body = rows.map(r => '<tr>' + r.map(c => `<td>${c}</td>`).join('') + '</tr>').join('');

    const html = `<!DOCTYPE html><html><body>
      <span id="view-inv-contact">Anika Care Limited\n34 Quinns Mill Road</span>
      <span id="view-inv-email-display">billing@example.com</span>
      <span id="view-inv-phone-display">+44 121 000 0000</span>
      <span id="view-inv-issue-date">14 Aug 2026</span>
      <span id="view-inv-due-date">31 Aug 2026</span>
      <span id="view-inv-number-val">INV-0273</span>
      <span id="view-inv-bank-content">Account 000963, sort 77-07-08</span>
      <span id="view-inv-ref">REF-1982</span>
      <span id="view-inv-due-currency">£</span>
      <span id="view-summary-subtotal">1497.80</span>
      <span id="view-summary-vat">149.78</span>
      <span id="view-summary-total">1647.58</span>
      <span id="view-inv-company-name">aniprotech</span>
      <span id="view-inv-company-address">53 Newbridge Cres\nWolverhampton</span>
      <span id="view-inv-company-email">Email: hello@example.com</span>
      <span id="view-inv-company-phone">Phone: 01902521476</span>
      <span id="view-inv-company-abn">ABN: 123</span>
      <table><tbody id="view-line-items-body">${body}</tbody></table>
    </body></html>`;

    const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.localStorage.setItem('company_logo', '');
    // app.js calls these at load; stub what a browser would provide.
    w.fetch = () => Promise.reject(new Error('offline'));
    w.showToast = () => { };
    w.Chart = function () { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    return dom;
}

process.on('uncaughtException', e => {
    console.log('UNCAUGHT:', (e && (e.stack || e.message)) || String(e));
    process.exit(1);
});

const dom = buildDom();
let source = fs.readFileSync(APP_JS, 'utf8');
// app.js registers listeners and fires network calls at load; we only need its
// function declarations, so let it run with the stubs above.
try {
    dom.window.eval(source);
} catch (e) {
    console.log('FAIL  app.js threw while loading:', e.message);
    process.exit(1);
}

const w = dom.window;
if (typeof w.generateInvoicePDF !== 'function' && typeof w.eval('typeof generateInvoicePDF') === 'undefined') {
    console.log('FAIL  generateInvoicePDF is not defined');
    process.exit(1);
}

const flags = ['show_quantity', 'show_price', 'show_discount', 'show_tax'];
let failures = 0, checked = 0;

for (let mask = 0; mask < 16; mask++) {
    for (const showItem of [false, true]) {
        const theme = { show_item: showItem, font: 'helvetica', brand_color: '#4f46e5' };
        flags.forEach((f, i) => { theme[f] = !!(mask & (1 << i)); });
        theme.label_quantity = 'Hours';
        theme.label_amount = 'Total';
        theme.approved_invoice_title = 'TAX INVOICE';
        theme.show_page_numbers = true;
        theme.footer_note = 'Thank you';

        w.eval(`_brandTheme = ${JSON.stringify(theme)};`);
        const on = flags.filter(f => theme[f]).map(f => f.replace('show_', '')).join('+') || 'none';
        checked++;
        try {
            const doc = w.eval('generateInvoicePDF(false, "invoice")');
            // The email path: this is exactly what sendEmail() does.
            const uri = doc.output('datauristring');
            const b64 = uri.split('base64,')[1] || '';
            if (!b64) throw new Error('no base64 produced - the email attachment would be empty');
            const bytes = Buffer.from(b64, 'base64');
            if (bytes.slice(0, 4).toString() !== '%PDF') throw new Error('output is not a PDF');
            if (bytes.length < 1000) throw new Error('PDF suspiciously small: ' + bytes.length);
        } catch (e) {
            failures++;
            console.log(`FAIL  item=${showItem} cols=${on}: ${e.message}`);
        }
    }
}

// And the quote variant, which shares the generator.
try {
    const doc = w.eval('generateInvoicePDF(true, "quote")');
    const b64 = doc.output('datauristring').split('base64,')[1] || '';
    if (!Buffer.from(b64, 'base64').slice(0, 4).toString().startsWith('%PDF')) throw new Error('not a PDF');
    checked++;
} catch (e) {
    failures++;
    console.log('FAIL  quote: ' + e.message);
}

console.log(failures
    ? `\n${failures} of ${checked} failed`
    : `\nall ${checked} PDFs generated, each a real %PDF with base64 for the email attachment`);
process.exit(failures ? 1 : 0);
