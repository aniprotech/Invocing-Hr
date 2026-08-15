/**
 * What happens when an invoice does not fit on one page.
 *
 * The generator breaks pages itself, reprints the table header, and closes the
 * row borders before moving on. None of that had ever been run against an
 * invoice long enough to need it, so this puts 60 items and some very long
 * descriptions through it and checks nothing is dropped.
 *
 * jsPDF writes its text streams uncompressed, so the finished document can be
 * searched for each row - which is the only way to prove a line did not simply
 * vanish at a page boundary.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const APP_JS = path.resolve(__dirname, '..', 'app.js');

const LONG = 'Supply and install galvanised roofing screws with integral sealing '
    + 'washers, including all associated labour, access equipment and the removal '
    + 'of waste from site on completion of the works';

function makeRow(i) {
    return [
        `SKU-${String(i).padStart(3, '0')}`,
        // Every few rows carries a description long enough to wrap several lines,
        // which is what actually straddles a page boundary.
        i % 4 === 0 ? `${LONG} (batch ${i})` : `Line item number ${i}`,
        String(i % 9 + 1), '21.00', '0', '10', '168.00',
    ];
}

function buildDom(rowCount) {
    const rows = Array.from({ length: rowCount }, (_, i) => makeRow(i + 1));
    const body = rows.map(r => '<tr>' + r.map(c => `<td>${c}</td>`).join('') + '</tr>').join('');

    const html = `<!DOCTYPE html><html><body>
      <span id="view-inv-contact">Anika Care Limited</span>
      <span id="view-inv-email-display">billing@example.com</span>
      <span id="view-inv-phone-display">+44 121 000 0000</span>
      <span id="view-inv-issue-date">14 Aug 2026</span>
      <span id="view-inv-due-date">31 Aug 2026</span>
      <span id="view-inv-number-val">INV-0273</span>
      <span id="view-inv-bank-content">Account 000963</span>
      <span id="view-inv-ref">REF-1982</span>
      <span id="view-inv-due-currency">£</span>
      <span id="view-summary-subtotal">10080.00</span>
      <span id="view-summary-vat">1008.00</span>
      <span id="view-summary-total">11088.00</span>
      <span id="view-inv-company-name">aniprotech</span>
      <span id="view-inv-company-address">53 Newbridge Cres</span>
      <span id="view-inv-company-email">Email: hello@example.com</span>
      <span id="view-inv-company-phone">Phone: 01902521476</span>
      <span id="view-inv-company-abn">ABN: 123</span>
      <table><tbody id="view-line-items-body">${body}</tbody></table>
    </body></html>`;

    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.fetch = () => Promise.reject(new Error('offline'));
    w.showToast = () => { };
    w.Chart = function () { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    dom.window.eval(fs.readFileSync(APP_JS, 'utf8'));
    return dom;
}

process.on('uncaughtException', e => {
    console.log('UNCAUGHT:', (e && (e.stack || e.message)) || String(e));
    process.exit(1);
});

let failures = 0;

/** jsPDF escapes ( ) and \ inside text strings; undo that to search the stream. */
function pdfText(bytes) {
    return bytes.toString('latin1').replace(/\\([()\\])/g, '$1');
}

for (const [rowCount, theme] of [
    [60, { show_quantity: true, show_price: true, show_tax: true }],
    [60, { show_quantity: true, show_price: true, show_discount: true, show_tax: true, show_item: true }],
    [120, { show_quantity: true, show_price: true }],
    [3, { show_quantity: true, show_price: true }],   // the single-page control
]) {
    const label = `${rowCount} items, ${Object.keys(theme).filter(k => theme[k]).length} columns`;
    let dom;
    try {
        dom = buildDom(rowCount);
        const w = dom.window;
        w.eval(`_brandTheme = ${JSON.stringify(Object.assign({
            font: 'helvetica', brand_color: '#4f46e5', label_quantity: 'Quantity',
            label_amount: 'Amount', approved_invoice_title: 'TAX INVOICE',
            show_page_numbers: true,
        }, theme))};`);

        const doc = w.eval('generateInvoicePDF(false, "invoice")');
        const bytes = Buffer.from(doc.output('datauristring').split('base64,')[1], 'base64');
        const text = pdfText(bytes);
        const pages = doc.internal.getNumberOfPages();

        const problems = [];

        if (rowCount > 10 && pages < 2) problems.push(`only ${pages} page for ${rowCount} items`);
        if (rowCount === 3 && pages !== 1) problems.push(`${pages} pages for 3 items`);

        // Every item's code must survive. This is the assertion that catches a
        // row eaten by a page break.
        const missing = [];
        for (let i = 1; i <= rowCount; i++) {
            const sku = `SKU-${String(i).padStart(3, '0')}`;
            if (theme.show_item && !text.includes(sku)) missing.push(sku);
        }
        if (missing.length) problems.push(`${missing.length} items missing, e.g. ${missing.slice(0, 3).join(', ')}`);

        // The column header has to reappear on every page, or pages 2+ are
        // unreadable columns of bare numbers.
        const headerCount = (text.match(/Quantity/g) || []).length;
        if (headerCount < pages) problems.push(`header on ${headerCount} of ${pages} pages`);

        // The totals belong at the end, exactly once.
        const totalCount = (text.match(/TOTAL/g) || []).length;
        if (totalCount !== 1) problems.push(`TOTAL appears ${totalCount} times`);

        // Page numbering must run to the last page.
        if (!text.includes('Page ' + pages)) problems.push(`no "Page ${pages}" footer`);

        if (problems.length) {
            failures++;
            console.log(`FAIL  ${label}: ${problems.join('; ')}`);
        } else {
            console.log(`ok    ${label.padEnd(26)} -> ${pages} page(s), header repeated ${headerCount}x, all items present`);
        }
    } catch (e) {
        failures++;
        console.log(`FAIL  ${label}: ${e.message}`);
    } finally {
        if (dom) dom.window.close();
    }
}

console.log(failures ? `\n${failures} pagination check(s) failed` : '\nlong invoices paginate without losing anything');
process.exit(failures ? 1 : 0);
