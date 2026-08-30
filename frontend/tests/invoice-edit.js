/**
 * Editing an invoice.
 *
 * Bills, contacts, recurring templates, jobs and onboarding requirements all
 * had an Edit. Invoices did not - even though PUT /api/invoices/{number} has
 * existed the whole time, unused by anything. A typo in a customer name or a
 * wrong line meant deleting the invoice and typing it again.
 *
 * The editor is the create form reused, which is where the risks are: saving
 * a new invoice must not overwrite the last one edited, and saving an edit
 * must address the number the invoice had when it was opened rather than
 * whatever is in the box, because that field is editable too.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

const INVOICE = {
    number: 'INV-0007', ref: 'PO-42', to: 'Acme Ltd', email: 'ap@acme.test',
    phone_number: '+44 20 7946 0000', date: '2026-08-01', due_date: '2026-08-15',
    tax_type: 'exclusive', currency: 'GBP', status: 'Draft', paid: 0, due: 120,
    bank_details: 'Acct 12345678',
    line_items: [
        { name: 'Design', description: 'Homepage', qty: 2, price: 50, disc: 0,
          account: '200 - Sales', tax_rate: 'No Tax' },
        { name: 'Hosting', description: 'Annual', qty: 1, price: 20, disc: 0,
          account: '200 - Sales', tax_rate: 'No Tax' },
    ],
};

function boot(invoice) {
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

    const sent = [];
    w.fetch = (url, opts) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (opts && opts.method) || 'GET',
                    body: opts && opts.body ? JSON.parse(opts.body) : null });
        let body = {};
        if (p.startsWith('/api/invoices/')) body = invoice || INVOICE;
        else if (p === '/api/client/me') body = { id: 1, email: 'me@example.com' };
        else if (p === '/api/auth/me') body = { user: { email: 'me@example.com' }, client_id: 1 };
        else if (p.endsWith('s')) body = [];
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return { w, sent };
}

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log('ok    ' + label);
    else { failures++; console.log('FAIL  ' + label + (detail ? ': ' + detail : '')); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const val = (w, id) => (w.document.getElementById(id) || {}).value;

(async () => {
    // --- the button is there, and knows when not to be --------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the invoice screen offers an Edit',
            /id="view-invoice-edit-btn"/.test(raw));
        check('and it calls editInvoice',
            /id="view-invoice-edit-btn"[^>]*editInvoice/.test(raw));
    }

    // --- opening one loads it into the form -------------------------------
    {
        const { w } = boot();
        await wait(30);
        await w.editInvoice('INV-0007');
        await wait(30);

        check('the number is loaded', val(w, 'inv-number') === 'INV-0007', val(w, 'inv-number'));
        check('the customer is loaded', val(w, 'inv-contact') === 'Acme Ltd', val(w, 'inv-contact'));
        check('the reference is loaded', val(w, 'inv-ref') === 'PO-42', val(w, 'inv-ref'));
        check('the email is loaded', val(w, 'inv-email') === 'ap@acme.test', val(w, 'inv-email'));
        check('the dates are loaded',
            val(w, 'inv-issue-date') === '2026-08-01' && val(w, 'inv-due-date') === '2026-08-15',
            val(w, 'inv-issue-date') + ' / ' + val(w, 'inv-due-date'));

        const rows = w.document.querySelectorAll('#line-items-body .line-item-row');
        check('every line comes back', rows.length === 2, rows.length + ' rows');
        check('with its own values',
            rows[0].querySelector('.item-name').value === 'Design' &&
            rows[1].querySelector('.item-price').value === '20',
            rows[0].querySelector('.item-name').value + ' / ' +
            rows[1].querySelector('.item-price').value);

        check('the screen says it is an edit',
            /INV-0007/.test(w.document.getElementById('create-invoice-title').textContent),
            w.document.getElementById('create-invoice-title').textContent);
        check('and offers a way out that does not save',
            w.document.getElementById('inv-cancel-edit-btn').style.display !== 'none');
    }

    // --- saving an edit updates, and does not create -----------------------
    {
        const { w, sent } = boot();
        await wait(30);
        await w.editInvoice('INV-0007');
        await wait(30);
        sent.length = 0;

        await w.submitComplexInvoice('Draft');
        await wait(30);

        const write = sent.find(r => r.method === 'PUT' || r.method === 'POST');
        check('saving an edit is a PUT, not a new invoice',
            write && write.method === 'PUT', write ? write.method : '(nothing sent)');
        check('and it addresses that invoice',
            write && write.url === '/api/invoices/INV-0007', write && write.url);
    }

    // --- renaming addresses the original ----------------------------------
    {
        const { w, sent } = boot();
        await wait(30);
        await w.editInvoice('INV-0007');
        await wait(30);
        // The number field is editable; the PUT must still go to the old one,
        // because the new number does not exist yet.
        w.document.getElementById('inv-number').value = 'INV-9999';
        sent.length = 0;

        await w.submitComplexInvoice('Draft');
        await wait(30);

        const write = sent.find(r => r.method === 'PUT');
        check('renaming still addresses the original number',
            write && write.url === '/api/invoices/INV-0007', write && write.url);
        check('and asks for the new one in the body',
            write && write.body.invoice_number === 'INV-9999',
            write && write.body.invoice_number);
    }

    // --- an edit must not change what state the invoice is in --------------
    {
        const { w, sent } = boot(Object.assign({}, INVOICE, { status: 'Awaiting Payment' }));
        await wait(30);
        await w.editInvoice('INV-0007');
        await wait(30);
        sent.length = 0;

        // "Save as draft" on a sent invoice must not un-send it.
        await w.submitComplexInvoice('Draft');
        await wait(30);

        const write = sent.find(r => r.method === 'PUT');
        check('editing a sent invoice leaves it sent',
            write && write.body.status === 'Awaiting Payment',
            write && write.body.status);
    }

    // --- a new invoice must never overwrite the last one edited -----------
    {
        const { w, sent } = boot();
        await wait(30);
        await w.editInvoice('INV-0007');
        await wait(30);

        // Choosing "New invoice" goes through here.
        w.prepareNewInvoiceForm();
        w.document.getElementById('inv-contact').value = 'Somebody Else';
        const body = w.document.getElementById('line-items-body');
        body.innerHTML = '';
        w.addLineItemRow();
        body.querySelector('.item-name').value = 'Thing';
        body.querySelector('.item-qty').value = '1';
        body.querySelector('.item-price').value = '10';
        sent.length = 0;

        await w.submitComplexInvoice('Draft');
        await wait(30);

        const write = sent.find(r => r.method === 'PUT' || r.method === 'POST');
        check('a new invoice is a POST, not a PUT over the last edit',
            write && write.method === 'POST',
            write ? write.method + ' ' + write.url : '(nothing sent)');
    }

    // --- an invoice with money against it is not editable -----------------
    {
        const { w, sent } = boot(Object.assign({}, INVOICE, { paid: 60 }));
        await wait(30);
        sent.length = 0;
        await w.editInvoice('INV-0007');
        await wait(30);

        check('one with payments against it is refused before the form opens',
            !sent.some(r => r.method === 'PUT'));
        check('and the editor is not left holding it',
            !w.document.getElementById('inv-contact').value,
            w.document.getElementById('inv-contact').value);
    }

    console.log(failures ? '\n' + failures + ' failed' : '\nall good');
    process.exit(failures ? 1 : 0);
})();
