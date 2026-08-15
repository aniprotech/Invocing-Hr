/**
 * A logo must not print on top of anything.
 *
 * The header is three columns - heading left, dates centre, logo and company
 * details right. Moving the logo left or centre put it straight through one of
 * the other two, which is only visible by looking at a rendered page. Here the
 * drawing calls are intercepted instead, so the collision is arithmetic.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const APP_JS = path.resolve(__dirname, '..', 'app.js');
const LOGO = 'data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';

function run(position) {
    const html = `<!DOCTYPE html><html><body>
      <span id="view-inv-contact">Anika Care Limited</span>
      <span id="view-inv-email-display">b@example.com</span>
      <span id="view-inv-phone-display">+44 121 000 0000</span>
      <span id="view-inv-issue-date">14 Aug 2026</span>
      <span id="view-inv-due-date">31 Aug 2026</span>
      <span id="view-inv-number-val">INV-0273</span>
      <span id="view-inv-bank-content">Account 000963</span>
      <span id="view-inv-ref">REF-1982</span>
      <span id="view-inv-due-currency">£</span>
      <span id="view-summary-subtotal">168.00</span>
      <span id="view-summary-vat">0.00</span>
      <span id="view-summary-total">168.00</span>
      <span id="view-inv-company-name">aniprotech</span>
      <span id="view-inv-company-address">53 Newbridge Cres</span>
      <span id="view-inv-company-email">Email: hello@example.com</span>
      <span id="view-inv-company-phone">Phone: 01902521476</span>
      <span id="view-inv-company-abn">ABN: 123</span>
      <table><tbody id="view-line-items-body">
        <tr><td>A</td><td>Work</td><td>1</td><td>21.00</td><td>0</td><td>0</td><td>168.00</td></tr>
      </tbody></table>
    </body></html>`;

    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;

    // Record where the logo goes and where text goes, on page 1 only.
    // jsPDF copies its API onto each instance, so neither subclassing nor
    // patching the prototype intercepts anything. A constructor that returns a
    // patched instance does - `new` honours an explicitly returned object.
    const drawn = { logo: null, texts: [] };
    function Recording() {
        const doc = new jsPDF(...arguments);
        const realImage = doc.addImage.bind(doc);
        const realText = doc.text.bind(doc);
        doc.addImage = function (data, fmt, x, yy, ww, hh) {
            if (doc.internal.getNumberOfPages() === 1) drawn.logo = { x, y: yy, w: ww, h: hh };
            // jsdom cannot decode a real image; the placement is what matters.
            try { return realImage.apply(null, arguments); } catch (e) { return doc; }
        };
        doc.text = function (txt, x, yy, opts) {
            if (doc.internal.getNumberOfPages() === 1 && typeof txt === 'string') {
                drawn.texts.push({
                    txt, x, y: yy, align: (opts && opts.align) || 'left',
                    size: doc.getFontSize(),
                });
            }
            return realText.apply(null, arguments);
        };
        return doc;
    }
    w.jspdf = { jsPDF: Recording };
    w.fetch = () => Promise.reject(new Error('offline'));
    w.showToast = () => { };
    w.Chart = function () { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    let src = fs.readFileSync(APP_JS, 'utf8');
    if (process.env.BREAK_LOGO) src = src.replace('if (logoOffRight) y += logoH + 12;', '');
    w.eval(src);
    w.eval(`_brandTheme = ${JSON.stringify({
        logo_position: position, logo_data: LOGO, font: 'helvetica',
        brand_color: '#4f46e5', show_quantity: true, show_price: true,
        approved_invoice_title: 'TAX INVOICE', show_page_numbers: true,
    })};`);
    try {
        w.eval('generateInvoicePDF(false, "invoice")');
    } finally {
        dom.window.close();
    }
    return drawn;
}

let failures = 0;

for (const position of ['right', 'left', 'center']) {
    const { logo, texts } = run(position);
    const problems = [];

    if (!logo) problems.push('no logo drawn');
    else {
        // jsPDF's y is the baseline, so a line occupies about one ascent above
        // it - measured from the font actually in use rather than guessed, or
        // text sitting neatly under the logo reads as a clash.
        const clashes = texts.filter(t => {
            if (typeof t.x !== 'number' || typeof t.y !== 'number') return false;
            if (t.y > logo.y + logo.h + 40) return false;      // well below the logo
            const ascent = (t.size || 9) * 0.78;
            const top = t.y - ascent, bottom = t.y;
            const vertical = bottom > logo.y && top < logo.y + logo.h;
            // Width is approximate; the alignment tells us which side of x it runs.
            const width = t.txt.length * (t.size || 9) * 0.5;
            const left = t.align === 'right' ? t.x - width : (t.align === 'center' ? t.x - width / 2 : t.x);
            const horizontal = (left + width) > logo.x && left < (logo.x + logo.w);
            return vertical && horizontal;
        });
        if (clashes.length) {
            problems.push(`${clashes.length} overlapping: ` +
                clashes.slice(0, 3).map(c => JSON.stringify(c.txt)).join(', '));
        }
    }

    if (problems.length) { failures++; console.log(`FAIL  logo ${position}: ${problems.join('; ')}`); }
    else console.log(`ok    logo ${position.padEnd(7)} at x=${logo.x.toFixed(0)} y=${logo.y.toFixed(0)}, nothing printed over it`);
}

console.log(failures ? `\n${failures} logo position(s) collide` : '\nno logo position prints over the header text');
process.exit(failures ? 1 : 0);
