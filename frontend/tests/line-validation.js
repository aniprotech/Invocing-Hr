/**
 * Which invoice cell is wrong, and why.
 *
 * Saving refused with one toast at the top of the screen - "Add at least one
 * line item" - which names neither the row nor the cell. And mostly it did not
 * refuse: parseFloat('12a') || 0 is 0, so a typo became a zero and the invoice
 * saved wrong and silent. The discount input carried max="100", which the
 * browser draws and nothing enforced, so a typed 150 sent a line worth less
 * than nothing.
 *
 * The checks that matter here are the ones that used to pass silently: a
 * quantity of zero, a discount over the whole line, and a row of numbers with
 * nothing saying what was sold.
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

function boot() {
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
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET' });
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'me@x' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        const body = p.endsWith('s') ? [] : {};
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

// One row, filled in as asked. Returns the row so a test can spoil one cell.
function addRow(w, vals) {
    w.addLineItemRow('invoice');
    const rows = w.scopedLineRows('invoice');
    const row = rows[rows.length - 1];
    Object.keys(vals).forEach(sel => {
        const el = row.querySelector(sel);
        if (el) el.value = vals[sel];
    });
    return row;
}

const banner = w => w.document.getElementById('invoice-line-errors');
const bannerText = w => (banner(w) && banner(w).style.display !== 'none')
    ? banner(w).textContent : '';

const GOOD = { '.item-name': 'Widget', '.item-qty': '2', '.item-price': '10' };

(async () => {
    // --- a row that is fine is left alone ------------------------------------
    {
        const { w } = boot();
        await wait(60);
        addRow(w, GOOD);
        check('a complete row passes', w.validateInvoiceLines('invoice') === true);
        check('and nothing is marked', !w.document.querySelector('.cell-invalid'));
        check('and no summary is shown', bannerText(w) === '', bannerText(w));
    }

    // --- the failures that used to be silent ---------------------------------
    {
        const { w } = boot();
        await wait(60);
        const row = addRow(w, { '.item-name': 'Widget', '.item-qty': '0', '.item-price': '10' });
        check('a quantity of zero is refused', w.validateInvoiceLines('invoice') === false);
        check('and it is the quantity cell that is marked',
            row.querySelector('.item-qty').classList.contains('cell-invalid'));
        check('while the price cell is left clean',
            !row.querySelector('.item-price').classList.contains('cell-invalid'));
        check('the cell carries its own reason',
            /quantity greater than zero/.test(row.querySelector('.item-qty').title),
            row.querySelector('.item-qty').title);
        check('and is announced as invalid',
            row.querySelector('.item-qty').getAttribute('aria-invalid') === 'true');
        check('the summary counts cells, not rows',
            bannerText(w) === '1 of the table cells has invalid data entered', bannerText(w));
    }

    {
        const { w } = boot();
        await wait(60);
        const row = addRow(w, Object.assign({}, GOOD, { '.item-disc': '150' }));
        check('a discount bigger than the line is refused',
            w.validateInvoiceLines('invoice') === false);
        check('in the words from the brief',
            row.querySelector('.item-disc').title
                === 'Enter a discount equal to or less than the amount',
            row.querySelector('.item-disc').title);
    }

    {
        // "equal to" is allowed - the whole line free is a real thing to do.
        const { w } = boot();
        await wait(60);
        addRow(w, Object.assign({}, GOOD, { '.item-disc': '100' }));
        check('a discount of exactly the amount is allowed',
            w.validateInvoiceLines('invoice') === true);
    }

    {
        const { w } = boot();
        await wait(60);
        const row = addRow(w, { '.item-qty': '2', '.item-price': '10' });
        check('numbers with nothing saying what was sold are refused',
            w.validateInvoiceLines('invoice') === false);
        check('and the item cell is the one marked',
            row.querySelector('.item-name').classList.contains('cell-invalid'));
    }

    // --- what must NOT be flagged --------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        addRow(w, GOOD);
        addRow(w, {});                        // the spare row the form keeps
        check('a blank spare row is not a mistake',
            w.validateInvoiceLines('invoice') === true,
            bannerText(w));
    }

    {
        const { w } = boot();
        await wait(60);
        addRow(w, { '.item-name': 'A', '.item-qty': '0', '.item-price': '10',
                    '.item-disc': '150' });
        w.validateInvoiceLines('invoice');
        check('two bad cells are counted as two',
            bannerText(w) === '2 of the table cells have invalid data entered',
            bannerText(w));
    }

    {
        const { w } = boot();
        await wait(60);
        check('an empty form still says to add a line',
            w.validateInvoiceLines('invoice') === false);
        check('and says that, rather than counting cells',
            /Add at least one line/.test(bannerText(w)), bannerText(w));
    }

    // --- a line that only says something ------------------------------------
    {
        // Reported from a real invoice: bank details typed into the
        // description of their own line, with no quantity and no price, were
        // marked as errors. A note line is a normal thing to put on an
        // invoice and Xero allows it.
        const { w } = boot();
        await wait(60);
        const row = addRow(w, {
            '.item-desc': 'Account Details: Sort Code 30-54-66, Account No 11591362',
        });
        addRow(w, GOOD);
        check('a description with no money on it is not an error',
            w.validateInvoiceLines('invoice') === true, bannerText(w));
        check('and nothing on that row is marked',
            !row.querySelector('.item-qty').classList.contains('cell-invalid') &&
            !row.querySelector('.item-price').classList.contains('cell-invalid'));
    }

    {
        // The other half of the same rule: charging for something still needs
        // a quantity, or the line bills nothing while looking like it bills.
        const { w } = boot();
        await wait(60);
        const row = addRow(w, { '.item-name': 'Widget', '.item-qty': '0', '.item-price': '80' });
        check('a price with no quantity is still refused',
            w.validateInvoiceLines('invoice') === false);
        check('on the quantity cell',
            row.querySelector('.item-qty').classList.contains('cell-invalid'));
    }

    {
        // Giving something away is a real thing to do.
        const { w } = boot();
        await wait(60);
        addRow(w, { '.item-name': 'Sample', '.item-qty': '2', '.item-price': '0' });
        check('a free line is allowed', w.validateInvoiceLines('invoice') === true,
            bannerText(w));
    }

    {
        const { w } = boot();
        await wait(60);
        const row = addRow(w, { '.item-name': 'Widget', '.item-qty': '-1', '.item-price': '10' });
        check('a negative quantity is refused',
            w.validateInvoiceLines('invoice') === false);
        check('and named as negative rather than as missing',
            /less than zero/.test(row.querySelector('.item-qty').title),
            row.querySelector('.item-qty').title);
    }

    // --- it actually stops the save ------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        w.document.getElementById('inv-contact').value = 'Acme Ltd';
        addRow(w, { '.item-name': 'Widget', '.item-qty': '0', '.item-price': '10' });
        sent.length = 0;
        await w.submitComplexInvoice('Awaiting Payment');
        await wait(50);
        check('a bad line never reaches the server',
            !sent.some(s => s.method === 'POST' && /invoice/i.test(s.url)),
            JSON.stringify(sent.map(s => s.method + ' ' + s.url)));
    }

    // --- fixing it clears it --------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        w.document.getElementById('inv-contact').value = 'Acme Ltd';
        const row = addRow(w, { '.item-name': 'Widget', '.item-qty': '0', '.item-price': '10' });
        await w.submitComplexInvoice('Awaiting Payment');
        await wait(50);
        check('the cell is marked after a refused save',
            row.querySelector('.item-qty').classList.contains('cell-invalid'));

        const qty = row.querySelector('.item-qty');
        qty.value = '3';
        qty.dispatchEvent(new w.Event('input', { bubbles: true }));
        await wait(20);
        check('correcting it clears the mark without saving again',
            !qty.classList.contains('cell-invalid'));
        check('and takes the summary away with it', bannerText(w) === '', bannerText(w));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
