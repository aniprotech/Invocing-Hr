/**
 * Credit notes: the list, the note itself with the buttons its state allows,
 * the invoice page's Credit note button and the notes against it, and the
 * modal that issues one from ticked lines - total follows the ticks, the
 * quantity is capped at what was invoiced, the note is sent when asked.
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

const NOTE = { id: 1, number: 'CN-0001', invoice_number: 'INV-0001', to: 'Acme <b>Ltd</b>', email: 'a@example.com', phone_number: '', to_company: 'Acme Ltd', to_address: '1 Road', to_tax_id: 'GB1',
    date: '2026-09-10', reason: 'Short <i>delivery</i>', status: 'Issued', sent: '', tax_type: 'exclusive', currency: 'GBP', subtotal: 300, tax_total: 60, total: 360,
    applied: 200, allocated: 0, refunded: 0, unapplied: 160, refunded_on: '', refund_method: '', refund_reference: '', voided_on: '', void_reason: '',
    company: { name: 'Northwind', address: '2 Lane', email: 'n@example.com', phone_number: '', abn: 'GB2' },
    line_items: [{ name: 'Design', description: 'One day', qty: 1, price: 300, disc: 0, tax_rate: '20% VAT', tax_percent: 20, amount: 300 }], allocations: [], refund_account_name: '' };
const VOID = Object.assign({}, NOTE, { number: 'CN-0002', status: 'Void', voided_on: '2026-09-11', void_reason: 'Wrong one', unapplied: 0, applied: 0 });
const LIST = [NOTE, VOID];
const INVOICE = { number: 'INV-0001', to: 'Acme', email: 'a@example.com', date: '2026-09-01', due_date: '2026-09-30', paid: 0, due: 640, subtotal: 1000, tax_total: 0, total: 1000,
    is_overdue: false, days_overdue: 0, payments: [], refunds: [], refunded_total: 0, status: 'Awaiting Payment', currency: 'GBP', company: {}, bill_to: {}, bill_from: {}, tax_type: 'exclusive',
    line_items: [{ name: 'Design', description: 'Design work', qty: 2, price: 300, disc: 0, tax_rate: 'No Tax', tax_percent: 0, amount: 600 },
                 { name: 'Hosting', description: '', qty: 1, price: 400, disc: 0, tax_rate: 'No Tax', tax_percent: 0, amount: 400 }],
    chasing: { paused: false, chased: true, why_not: '', fees_allowed: true, fee_why_not: '', reminders: [], next: null, late_fees: [], late_fee_total: 0, late_fee_next: null, policy: { enabled: true, late_fee: { enabled: false } } },
    credit_notes: [{ number: 'CN-0001', date: '2026-09-10', reason: 'Short <i>delivery</i>', total: 360, unapplied: 160, status: 'Issued' }], credited: 200 };

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
        if (p === '/api/credit-notes' && method === 'POST') return give(Object.assign({}, NOTE, { number: 'CN-0009' }));
        if (p === '/api/credit-notes') return give(opts.list || LIST);
        if (p === '/api/credit-notes/CN-0001') return give(opts.note || NOTE);
        if (p === '/api/credit-notes/CN-0002') return give(VOID);
        if (p === '/api/credit-notes/CN-0009') return give(Object.assign({}, NOTE, { number: 'CN-0009' }));
        if (p.startsWith('/api/credit-notes/')) return give({ message: 'ok', credit_note: NOTE, invoice: {} });
        if (p === '/api/invoices/INV-0001') return give(opts.invoice || INVOICE);
        if (p === '/api/invoices') return give([]);
        if (p === '/api/accounts') return give({ accounts: [{ id: 1, name: 'Bank', active: true, is_default: true }] });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/client/logo') return give({ logo_url: '' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiPrompt = () => Promise.resolve(opts.prompt === undefined ? 'Wrong one' : opts.prompt);
    w.uiForm = () => Promise.resolve(opts.form === undefined ? { invoice_number: 'INV-0002', amount: '100', method: 'cash', reference: 'R1', account_id: '1' } : opts.form);
    w.uiAlert = () => Promise.resolve(true);
    w.fetchInvoices = () => Promise.resolve();
    w.getCurrencySymbol = () => '£';
    w.generateInvoicePDF = () => ({ output: () => 'data:application/pdf;base64,QUJD', save: () => { } });
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Sales has a Credit notes page, the note has its own view for the PDF, the invoice page a button and a modal',
            /id="nav-credit-notes"/.test(src) && /id="credit-notes-view"/.test(src) && /id="view-credit-note-view"/.test(src) && /id="view-cn-line-items-body"/.test(src) &&
            /id="view-invoice-credit-btn"/.test(src) && /id="credit-note-modal"/.test(src) && /id="view-inv-credits"/.test(src));
        const pub = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8');
        check('the customer\'s page lists credit notes under the totals', /inv\.credit_notes/.test(pub) && /Credit note /.test(pub));
    }
    {
        const { w, doc, sent } = boot();
        check('the route and nav maps know the pages', w.ROUTE_SLUGS['credit-notes-view'] === 'credit-notes' && w.NAV_FOR_VIEW['view-credit-note-view'] === 'nav-credit-notes' && w.PDF_DOC_TYPES.credit_note.heading === 'CREDIT NOTE');
        await w.fetchCreditNotes();
        await wait(30);
        const rows = doc.querySelectorAll('#credit-notes-table-body tr');
        check('the list has one row per note, names and reasons as text, what is left, and a withdrawn one says so',
            rows.length === 2 && /Acme <b>Ltd<\/b>/.test(rows[0].textContent) && !doc.getElementById('credit-notes-table-body').querySelector('b') && /£360\.00/.test(rows[0].textContent) && /£160\.00/.test(rows[0].textContent) &&
            /Credit to use/.test(rows[0].textContent) && /Withdrawn/.test(rows[1].textContent), rows.length);
        doc.getElementById('credit-note-search').value = 'wrong';
        w.renderCreditNotes();
        check('  search narrows it', doc.querySelectorAll('#credit-notes-table-body tr').length === 1);
        await w.viewCreditNote('CN-0001');
        await wait(30);
        check('the note fills its view: number, against, reason, customer, lines and totals', doc.getElementById('view-cn-number-val').textContent === 'CN-0001' && doc.getElementById('view-cn-due-date').textContent === 'INV-0001' &&
            doc.getElementById('view-cn-ref').textContent === 'Short <i>delivery</i>' && doc.getElementById('view-cn-contact').textContent === 'Acme <b>Ltd</b>' && doc.querySelectorAll('#view-cn-line-items-body tr').length === 1 &&
            doc.getElementById('view-cn-summary-total').textContent === '360.00' && doc.getElementById('view-cn-due-currency').textContent === '£');
        check('  the state strip says what happened to it', /£200\.00 taken off INV-0001/.test(doc.getElementById('view-cn-state').textContent) && /£160\.00 still the customer/.test(doc.getElementById('view-cn-state').textContent));
        check('  with credit left it offers Set against, Pay back and Withdraw', doc.getElementById('cn-allocate-btn').style.display !== 'none' && doc.getElementById('cn-refund-btn').style.display !== 'none' && doc.getElementById('cn-void-btn').style.display !== 'none');
        await w.allocateCreditNote();
        await wait(30);
        const alloc = sent.find(s => s.url === '/api/credit-notes/CN-0001/allocate');
        check('Set against posts the invoice and amount', alloc && bodyOf(alloc).invoice_number === 'INV-0002' && bodyOf(alloc).amount === 100, alloc && alloc.body);
        await w.refundCreditNote();
        await wait(30);
        const ref = sent.find(s => s.url === '/api/credit-notes/CN-0001/refund');
        check('Pay back posts amount, how, reference and the account', ref && bodyOf(ref).amount === 100 && bodyOf(ref).method === 'cash' && bodyOf(ref).reference === 'R1' && bodyOf(ref).account_id === 1, ref && ref.body);
        await w.voidCreditNote();
        await wait(30);
        const vd = sent.find(s => s.url === '/api/credit-notes/CN-0001/void');
        check('Withdraw asks why and posts it', vd && bodyOf(vd).reason === 'Wrong one');
        await w.sendCreditNoteEmail();
        await wait(30);
        const snd = sent.find(s => s.url === '/api/credit-notes/CN-0001/send');
        check('Send Email posts the PDF it drew', snd && bodyOf(snd).pdf_data === 'QUJD');
        await w.viewCreditNote('CN-0002');
        await wait(30);
        check('a withdrawn note offers nothing but the PDF', doc.getElementById('cn-allocate-btn').style.display === 'none' && doc.getElementById('cn-refund-btn').style.display === 'none' && doc.getElementById('cn-void-btn').style.display === 'none' && doc.getElementById('cn-send-btn').style.display === 'none' && /Withdrawn on 2026-09-11: Wrong one/.test(doc.getElementById('view-cn-state').textContent));
    }
    {
        const { w, doc, sent } = boot();
        await w.viewInvoice('INV-0001');
        await wait(40);
        const host = doc.getElementById('view-inv-credits');
        check('the invoice page lists the notes against it, reason as text, with what is left', host.style.display === 'block' && /CN-0001/.test(host.textContent) && /Short <i>delivery<\/i>/.test(host.textContent) && !host.querySelector('i') && /£160\.00 to have back/.test(host.textContent) && /-£360\.00/.test(host.textContent));
        check('  and offers a Credit note button', doc.getElementById('view-invoice-credit-btn').style.display === 'inline-block');
        w.openCreditNoteModal();
        const lines = doc.querySelectorAll('#credit-note-lines [data-cn-line]');
        check('the modal lists every line ticked, at its full quantity, and totals them', lines.length === 2 && doc.getElementById('credit-note-total').textContent === '£1000.00' && doc.getElementById('credit-note-modal').style.display === 'flex');
        lines[0].querySelector('[data-cn-qty]').value = '1';
        lines[0].querySelector('[data-cn-qty]').dispatchEvent(new w.Event('input', { bubbles: true }));
        lines[1].querySelector('[data-cn-pick]').checked = false;
        lines[1].querySelector('[data-cn-pick]').dispatchEvent(new w.Event('change', { bubbles: true }));
        check('  the total follows the ticks and quantities', doc.getElementById('credit-note-total').textContent === '£300.00', doc.getElementById('credit-note-total').textContent);
        lines[0].querySelector('[data-cn-qty]').value = '9';
        doc.getElementById('credit-note-reason').value = 'One day not done';
        doc.getElementById('credit-note-send').checked = true;
        await w.issueCreditNote();
        await wait(60);
        const post = sent.find(s => s.url === '/api/credit-notes' && s.method === 'POST');
        const b = post && bodyOf(post);
        check('Issue posts the ticked lines with the quantity capped at what was invoiced, and the reason',
            b && b.invoice_number === 'INV-0001' && b.line_items.length === 1 && b.line_items[0].qty === 2 && b.line_items[0].name === 'Design' && b.reason === 'One day not done', post && post.body);
        check('  then opens the note and sends it, as asked', sent.some(s => s.url === '/api/credit-notes/CN-0009') && sent.some(s => s.url === '/api/credit-notes/CN-0009/send') && doc.getElementById('credit-note-modal').style.display === 'none');
    }
    {
        const { w, doc, sent } = boot();
        await w.viewInvoice('INV-0001');
        await wait(40);
        w.openCreditNoteModal();
        doc.querySelectorAll('#credit-note-lines [data-cn-pick]').forEach(b => { b.checked = false; });
        await w.issueCreditNote();
        check('nothing ticked issues nothing', !sent.some(s => s.url === '/api/credit-notes' && s.method === 'POST'));
        const draft = Object.assign({}, INVOICE, { status: 'Draft', credit_notes: [] });
        const b2 = boot({ invoice: draft });
        await b2.w.viewInvoice('INV-0001');
        await wait(40);
        check('a draft has no Credit note button', b2.doc.getElementById('view-invoice-credit-btn').style.display === 'none' && b2.doc.getElementById('view-inv-credits').style.display === 'none');
    }
    console.log(failures === 0 ? '\nAll credit-note checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
