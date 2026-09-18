/**
 * A customer's own terms: the contact form carries payment terms, currency
 * and a copy address; picking the customer on an invoice moves the due
 * date by their terms and sets the currency; the send preview names the
 * copy address. Send later: the invoice page offers it, asks for a day,
 * posts it, shows what is scheduled, cancels it; the list shows the day.
 * Recurring: the list says which templates send themselves. Words are text.
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

const INVOICE = { number: 'INV-0001', to: 'Acme', email: 'a@example.com', date: '2026-09-01', due_date: '2026-09-30', paid: 0, due: 100, subtotal: 100, tax_total: 0, total: 100,
    is_overdue: false, days_overdue: 0, payments: [], refunds: [], refunded_total: 0, status: 'Draft', sent: '', send_at: '2026-09-25', currency: 'GBP', company: {}, bill_to: {}, bill_from: {}, tax_type: 'exclusive',
    line_items: [], credit_notes: [], credited: 0,
    chasing: { paused: false, chased: true, why_not: '', fees_allowed: true, fee_why_not: '', reminders: [], next: null, late_fees: [], late_fee_total: 0, late_fee_next: null, policy: { enabled: true, late_fee: { enabled: false } } } };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/invoices/INV-0001') return give(opts.invoice || INVOICE);
        if (p === '/api/invoices/INV-0001/schedule') return give({ message: 'It will be sent on 2026-09-26', send_at: '2026-09-26' });
        if (p === '/api/invoice-list') return give({ items: [Object.assign({}, INVOICE, { open_count: 0 })], total: 1, summary: { count: 1, owed: 100, overdue_owed: 0, overdue_count: 0, paid: 0 } });
        if (p === '/api/invoices/INV-0001/email-preview') return give({ to: 'a@example.com', cc: 'accounts@acme.example.com', subject: 'Invoice INV-0001', body: 'Hi', missing: [] });
        if (p === '/api/email-templates') return give({ templates: [] });
        if (p === '/api/recurring-invoices') return give([{ id: 1, name: 'Retainer', to: 'Acme', frequency: 'monthly', next_run: '2026-10-01', total: 500, currency: 'GBP', invoices_created: 2, is_active: true, auto_send: true },
                                                          { id: 2, name: 'Drafts', to: 'Bolt', frequency: 'monthly', next_run: '2026-10-01', total: 50, currency: 'GBP', invoices_created: 0, is_active: true, auto_send: false }]);
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/client/logo') return give({ logo_url: '' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiPrompt = () => Promise.resolve(opts.prompt === undefined ? '2026-09-26' : opts.prompt);
    w.uiConfirm = () => Promise.resolve(true);
    w.fetchInvoices = () => Promise.resolve();
    w.getCurrencySymbol = () => '£';
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the contact form has terms, currency and a copy address; the invoice page a Send later button and a scheduled strip',
            /id="contact-terms"/.test(src) && /id="contact-currency"/.test(src) && /id="contact-cc"/.test(src) && /id="view-invoice-later-btn"/.test(src) && /id="view-inv-scheduled"/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        w.allContacts = [{ id: 4, name: 'Acme', email: 'a@example.com', payment_terms_days: 45, currency: 'USD', cc_email: 'accounts@acme.example.com', chase: true, late_fees: true }];
        w.editContact(4);
        check('editing a contact shows their terms, currency and copy address', doc.getElementById('contact-terms').value === '45' && doc.getElementById('contact-currency').value === 'USD' && doc.getElementById('contact-cc').value === 'accounts@acme.example.com');
        doc.getElementById('contact-terms').value = '';
        doc.getElementById('contact-currency').value = 'inr';
        await w.saveContact();
        await wait(20);
        const put = sent.find(s => s.url === '/api/contacts/4' && s.method === 'PUT');
        check('  saving sends blank terms as none and the currency upper-cased', put && bodyOf(put).payment_terms_days === null && bodyOf(put).currency === 'INR' && bodyOf(put).cc_email === 'accounts@acme.example.com', put && put.body);
        w.showAddContactModal();
        check('  a new contact starts blank', doc.getElementById('contact-terms').value === '' && doc.getElementById('contact-cc').value === '');
    }
    {
        const { w, doc } = boot();
        doc.getElementById('inv-issue-date').value = '2026-09-01';
        doc.getElementById('inv-due-date').value = '2026-09-15';
        let picked = null;
        w.setCurrencyPickerDisplay = (name, code) => { picked = name + ':' + code; };
        w.applyCustomerDefaults('inv', { payment_terms_days: 45, currency: 'usd' });
        check('picking a customer with 45-day terms moves the due date 45 days from the issue date, and sets their currency', doc.getElementById('inv-due-date').value === '2026-10-16' && picked === 'invCurrency:USD', doc.getElementById('inv-due-date').value + ' ' + picked);
        doc.getElementById('inv-due-date').value = '2026-09-15';
        w.applyCustomerDefaults('inv', { payment_terms_days: null, currency: '' });
        check('  a customer with no terms of their own leaves the date and currency alone', doc.getElementById('inv-due-date').value === '2026-09-15');
    }
    {
        const { w, doc, sent } = boot();
        await w.viewInvoice('INV-0001');
        await wait(40);
        const strip = doc.getElementById('view-inv-scheduled');
        check('the invoice page says when it will send itself, to whom, with Cancel', strip.style.display === 'block' && /Will be emailed to a@example.com on 2026-09-25/.test(strip.textContent) && strip.querySelector('[data-unschedule]'));
        check('  and offers Send later on an unsent invoice with an address', doc.getElementById('view-invoice-later-btn').style.display === 'inline-block');
        strip.querySelector('[data-unschedule]').click();
        await wait(30);
        const cancel = sent.find(s => s.url === '/api/invoices/INV-0001/schedule');
        check('Cancel posts a blank day', cancel && bodyOf(cancel).send_at === '');
        await w.scheduleInvoiceSend();
        await wait(30);
        const sched = sent.filter(s => s.url === '/api/invoices/INV-0001/schedule').pop();
        check('Send later asks for a day and posts it', sched && bodyOf(sched).send_at === '2026-09-26', sched && sched.body);
        await w.sendEmail();
        await wait(60);
        check('the send preview names the copy address', /Cc: accounts@acme.example.com/.test(doc.getElementById('preview-to').textContent), doc.getElementById('preview-to').textContent);
    }
    {
        const sentInv = Object.assign({}, INVOICE, { status: 'Sent', sent: '2026-09-02', send_at: '' });
        const { w, doc } = boot({ invoice: sentInv });
        await w.viewInvoice('INV-0001');
        await wait(40);
        check('a sent invoice has no Send later and no strip', doc.getElementById('view-invoice-later-btn').style.display === 'none' && doc.getElementById('view-inv-scheduled').style.display === 'none');
    }
    {
        const { w, doc } = boot();
        w._invList.limit = 50;
        await w.fetchInvoices === undefined;
        // The real list renderer, fed directly.
        w._invList.total = 1; w._invList.summary = null;
        w.renderInvoices([Object.assign({}, INVOICE, { open_count: 0 })]);
        const row = doc.querySelector('#invoices-table-body tr');
        check('the list shows the day an unsent invoice will send itself', row && /2026-09-25/.test(row.lastElementChild.textContent) && /Will be sent on 2026-09-25/.test(row.lastElementChild.innerHTML));
    }
    {
        const { w, doc } = boot();
        await w.loadRecurring();
        await wait(30);
        const rows = doc.querySelectorAll('#recurring-table-body tr');
        check('the recurring list says which templates send themselves', rows.length === 2 && /Sends itself/.test(rows[0].textContent) && !/Sends itself/.test(rows[1].textContent));
    }
    console.log(failures === 0 ? '\nAll customer-defaults checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
