/**
 * The sales and purchase ledgers in the app: the two list screens (tiles, how
 * late things are, an account per row), one account opened (its ledger with a
 * running balance, what is open, what to do about it), suppliers, paying a bill
 * in parts, supplier credit notes, the Bills screen that feeds the ledger, the
 * customer fields that sit behind the sales ledger, and the credit warning on
 * the invoice form.
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

const SALES = {
    as_of: '2026-10-15', currency: 'GBP', other_currencies: ['INR'],
    totals: { balance: 450, overdue: 150, buckets: { current: 300, '1_30': 100, '31_60': 50, '61_90': 0, over_90: 0 }, accounts_owing: 2, over_limit: 1, on_hold: 1, dso: 21 },
    accounts: [
        { contact: 'Big <b>Customer</b>', contact_id: 1, account_ref: 'BC-1', currency: 'GBP', email: 'big@x.test', invoices: 2, oldest_days: 12, total: 300, overdue: 100, current: 200, '1_30': 100, '31_60': 0, '61_90': 0, over_90: 0,
          credit_limit: 250, available_credit: -50, used_pct: 120, credit_state: 'over_limit', on_hold: false, last_invoice: '2026-10-10', last_payment: '2026-09-01' },
        { contact: 'Held Co', contact_id: 2, account_ref: '', currency: 'GBP', email: '', invoices: 1, oldest_days: 40, total: 150, overdue: 150, current: 100, '1_30': 0, '31_60': 50, '61_90': 0, over_90: 0,
          credit_limit: 0, available_credit: null, used_pct: null, credit_state: 'on_hold', on_hold: true, last_invoice: '2026-08-01', last_payment: '' },
        { contact: 'Near Co', contact_id: 3, account_ref: 'NR-3', currency: 'GBP', email: '', invoices: 0, oldest_days: 0, total: 0, overdue: 0, current: 0, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0,
          credit_limit: 100, available_credit: 100, used_pct: 0, credit_state: 'ok', on_hold: false, last_invoice: '', last_payment: '' },
        { contact: 'Walk-in Ltd', contact_id: null, account_ref: '', currency: 'GBP', email: '', invoices: 1, oldest_days: 0, total: 10, overdue: 0, current: 10, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0,
          credit_limit: 0, available_credit: null, used_pct: null, credit_state: 'no_limit', on_hold: false, last_invoice: '2026-10-14', last_payment: '' },
        { contact: 'Abroad Co', contact_id: 5, account_ref: '', currency: 'INR', email: '', invoices: 1, oldest_days: 0, total: 9000, overdue: 0, current: 9000, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0,
          credit_limit: 0, available_credit: null, used_pct: null, credit_state: 'no_limit', on_hold: false, last_invoice: '2026-10-01', last_payment: '' },
    ],
};

const PURCHASES = {
    as_of: '2026-10-15', currency: 'GBP', other_currencies: [],
    totals: { balance: 220, overdue: 70, buckets: { current: 200, '1_30': 70, '31_60': 0, '61_90': 0, over_90: 0 }, accounts_owing: 1, credits: 50, on_hold: 1 },
    accounts: [
        { supplier_id: 7, supplier: 'Acme <i>Supplies</i>', account_ref: 'AC-7', currency: 'GBP', email: 'ap@acme.test', on_hold: false, bills: 2, oldest_days: 10, credits: 50, total: 220, overdue: 70,
          current: 200, '1_30': 70, '31_60': 0, '61_90': 0, over_90: 0, last_bill: '2026-10-10', last_payment: '2026-09-25' },
        { supplier_id: 8, supplier: 'Quiet Co', account_ref: '', currency: 'GBP', email: '', on_hold: true, bills: 0, oldest_days: 0, credits: 0, total: 0, overdue: 0,
          current: 0, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0, last_bill: '', last_payment: '' },
        { supplier_id: 0, supplier: 'No supplier', account_ref: '', currency: 'GBP', email: '', on_hold: false, bills: 1, oldest_days: 0, credits: 0, total: 40, overdue: 0,
          current: 40, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0, last_bill: '2026-10-01', last_payment: '' },
    ],
};

const SALES_DETAIL = {
    account: { id: 1, name: 'Big <b>Customer</b>', email: 'big@x.test', phone_number: '0207', account_ref: 'BC-1', payment_terms_days: 30, on_hold: false, credit_limit: 250,
               credit: { limit: 250, available: -50, used_pct: 120, over_limit: true, state: 'over_limit', on_hold: false, currency: 'GBP', balance: 300 } },
    start: '2026-07-17', end: '2026-10-15', base: 'GBP',
    statements: [{ currency: 'GBP', opening_balance: 0, closing_balance: 300, overdue: 100, lines: [
        { date: '2026-09-05', kind: 'invoice', description: 'Invoice INV-1 <script>x</script>', debit: 100, credit: 0, balance: 100, number: 'INV-1' },
        { date: '2026-10-10', kind: 'invoice', description: 'Invoice INV-2', debit: 200, credit: 0, balance: 300, number: 'INV-2' }] }],
    ageing: [{ currency: 'GBP', contact: 'Big Customer', total: 300, current: 200, '1_30': 100, '31_60': 0, '61_90': 0, over_90: 0 }],
    open_invoices: [{ number: 'INV-1', issue_date: '2026-09-05', due_date: '2026-10-03', outstanding: 100, days_overdue: 12, bucket: '1_30', currency: 'GBP', contact: 'Big Customer' }],
};

const PURCHASE_DETAIL = {
    supplier: { id: 7, name: 'Acme <i>Supplies</i>', account_ref: 'AC-7', contact_person: 'Pat', email: 'ap@acme.test', phone_number: '', payment_terms_days: 30, on_hold: false, bank_details: 'Sort 12-34-56\nAcc 1234' },
    start: '2026-07-17', end: '2026-10-15', base: 'GBP', balance: { GBP: 220 },
    ledgers: [{ currency: 'GBP', opening_balance: 0, closing_balance: 220, increased: 300, decreased: 80, lines: [
        { date: '2026-09-05', kind: 'bill', description: 'Bill B-1, due 2026-10-05', increase: 100, decrease: 0, balance: 100 },
        { date: '2026-09-25', kind: 'payment', description: 'Payment on B-1 (cheque)', increase: 0, decrease: 30, balance: 70 },
        { date: '2026-10-01', kind: 'credit', description: 'Credit note SC-0001: damaged', increase: 0, decrease: 50, balance: 20 },
        { date: '2026-10-10', kind: 'bill', description: 'Bill B-2', increase: 200, decrease: 0, balance: 220 }] }],
    ageing: [{ currency: 'GBP', supplier: 'Acme Supplies', total: 220, current: 200, '1_30': 70, '31_60': 0, '61_90': 0, over_90: 0, credits: 50 }],
    open_bills: [{ bill_id: 11, number: 'B-1', issue_date: '2026-09-05', due_date: '2026-10-05', outstanding: 70, days_overdue: 10, bucket: '1_30', currency: 'GBP', supplier_id: 7 },
                 { bill_id: 12, number: 'B-2', issue_date: '2026-10-10', due_date: '2026-11-09', outstanding: 200, days_overdue: 0, bucket: 'current', currency: 'GBP', supplier_id: 7 }],
    credits: [{ id: 21, number: 'SC-0001', reference: 'THEIR-9', issue_date: '2026-10-01', reason: 'damaged', amount: 50, applied: 0, remaining: 50, currency: 'GBP', status: 'Open', supplier_id: 7 },
              { id: 22, number: 'SC-0002', reference: '', issue_date: '2026-10-02', reason: '', amount: 10, applied: 10, remaining: 0, currency: 'GBP', status: 'Applied', supplier_id: 7 }],
};

const BILLS = [
    { id: 11, number: 'B-1', vendor_name: 'Acme Supplies', supplier_id: 7, issue_date: '2026-09-05', due_date: '2026-10-05', total: 100, amount_paid: 30, balance: 70, status: 'Partially Paid', currency: 'GBP', overdue: true, days_overdue: 10 },
    { id: 12, number: 'B-2', vendor_name: 'Acme Supplies', supplier_id: 7, issue_date: '2026-10-10', due_date: '2026-11-09', total: 200, amount_paid: 0, balance: 200, status: 'Awaiting Payment', currency: 'GBP', overdue: false, days_overdue: 0 },
    { id: 13, number: 'B-3', vendor_name: 'Done Co', supplier_id: 9, issue_date: '2026-08-05', due_date: '2026-09-05', total: 50, amount_paid: 50, balance: 0, status: 'Paid', currency: 'GBP', overdue: false, days_overdue: 0 },
    { id: 14, number: 'B-4', vendor_name: 'Draft <u>Co</u>', supplier_id: 10, issue_date: '2026-10-12', due_date: '2026-11-12', total: 20, amount_paid: 0, balance: 20, status: 'Draft', currency: 'GBP', overdue: false, days_overdue: 0 },
];

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, full, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (opts.reply) {
            const hit = Object.keys(opts.reply).find(k => k === method + ' ' + p || k === p);
            if (hit) { const r = opts.reply[hit](init, full); return give(r.body, r.status); }
        }
        if (p === '/api/ledger/sales' && method === 'GET') return give(opts.sales || SALES);
        if (p === '/api/ledger/purchases' && method === 'GET') return give(opts.purchases || PURCHASES);
        if (p === '/api/ledger/sales/1') return give(SALES_DETAIL);
        if (p === '/api/ledger/purchases/7') return give(PURCHASE_DETAIL);
        if (p === '/api/ledger/purchases/0') return give({ ...PURCHASE_DETAIL, supplier: { id: 0, name: 'No supplier', on_hold: false }, open_bills: [], credits: [] });
        if (p === '/api/suppliers' && method === 'GET') return give([{ id: 7, name: 'Acme Supplies' }, { id: 8, name: 'Quiet Co' }]);
        if (p.startsWith('/api/suppliers/') && method === 'GET') return give({ id: 7, name: 'Acme Supplies', account_ref: 'AC-7', contact_person: 'Pat', email: 'ap@acme.test', phone_number: '020', tax_id: 'GB1', payment_terms_days: 30, currency: '', address: '1 High St', bank_details: 'Sort 12', notes: 'n', on_hold: true });
        if (p === '/api/accounts') return give({ accounts: [{ id: 3, name: 'Current account', active: true }, { id: 4, name: 'Old', active: false }] });
        if (p === '/api/bills' && method === 'GET') return give(opts.bills || BILLS);
        if (p === '/api/bills/11') return give({ ...BILLS[0], payments: [{ id: 1, amount: 20, paid_on: '2026-09-20', method: 'cheque', method_label: 'cheque', reference: 'CHQ 1', account: 'Current account', from_bank: false },
                                                                         { id: 2, amount: 10, paid_on: '2026-09-25', method: 'bank_transfer', method_label: 'bank transfer', reference: 'ACME', account: '', from_bank: true }],
            supplier: { id: 7, name: 'Acme Supplies', bank_details: 'Sort 12-34' }, total: 100 });
        if (p === '/api/bills/12') return give({ ...BILLS[1], payments: [], supplier: null });
        if (p === '/api/bills/post-drafts') return give({ posted: 1 });
        if (p === '/api/next-bill-number') return give({ number: 'BILL-0009' });
        if (p === '/api/payroll/settings') return give({ regime: 'simple' });
        if (p === '/api/contacts' && method === 'GET') return give([{ id: 1, name: 'Big Customer', email: 'big@x.test', account_ref: 'BC-1', credit_limit: 250, on_hold: true }]);
        if (p === '/api/ledger/credit-check') return give(opts.credit || { known: true, warnings: [], state: 'ok' });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m, t) => { w._toasts = (w._toasts || []).concat([[m, t]]); };
    w._asked = [];
    w.uiConfirm = (m) => { w._asked.push(String(m)); return Promise.resolve(opts.confirm !== false); };
    w._forms = [];
    w.uiForm = (fields, o) => { w._forms.push({ fields, o }); return Promise.resolve(opts.form === undefined ? Object.fromEntries(fields.map(f => [f.name, f.value === undefined ? '' : f.value])) : opts.form); };
    w.formatCurrency = (v, cur) => (cur && cur !== 'GBP' ? cur + ' ' : '£') + Number(v || 0).toFixed(2);
    return { w, doc: w.document, sent };
}

const click = (w, el) => el.dispatchEvent(new w.Event('click', { bubbles: true, cancelable: true }));
const text = el => (el ? el.textContent.replace(/\s+/g, ' ') : '');

(async () => {
    // --- on the map -------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        check('the Sales group has a Sales ledger and the Money group a Purchase ledger',
            !!doc.getElementById('nav-sales-ledger') && !!doc.getElementById('nav-purchase-ledger') &&
            doc.getElementById('nav-sales-ledger').closest('[data-nav-group="Sales"]') !== null && doc.getElementById('nav-purchase-ledger').closest('[data-nav-group="Money"]') !== null);
        check('  and each goes to its own screen by address', /sales-ledger/.test(doc.getElementById('nav-sales-ledger').getAttribute('href')) && /purchase-ledger/.test(doc.getElementById('nav-purchase-ledger').getAttribute('href')));
        check('  the screens have their own slugs and highlight their own link', w.ROUTE_SLUGS['sales-ledger-view'] === 'sales-ledger' && w.ROUTE_SLUGS['purchase-ledger-view'] === 'purchase-ledger'
            && w.NAV_FOR_VIEW['sales-ledger-view'] === 'nav-sales-ledger' && w.NAV_FOR_VIEW['purchase-ledger-view'] === 'nav-purchase-ledger');
        w.showView('sales-ledger-view');
        await wait(60);
        check('opening the sales ledger asks the server for it', sent.some(s => s.url === '/api/ledger/sales'));
        w.showView('purchase-ledger-view');
        await wait(60);
        check('and the purchase ledger likewise', sent.some(s => s.url === '/api/ledger/purchases'));
    }

    // --- the sales ledger list ----------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadSalesLedger();
        const tiles = text(doc.getElementById('sales-ledger-tiles'));
        check('the tiles say what is owed, what is overdue, who owes, and who is over limit or on hold',
            /Owed to you\s*£450\.00/.test(tiles) && /Overdue\s*£150\.00/.test(tiles) && /Customers owing\s*2/.test(tiles) && /Over limit or on hold\s*2/.test(tiles), tiles);
        const age = text(doc.getElementById('sales-ledger-ageing'));
        check('how late is shown in five bands as of the day, with other currencies said to be separate',
            /Not yet due\s*£300\.00/.test(age) && /1-30 days late\s*£100\.00/.test(age) && /31-60 days late\s*£50\.00/.test(age) && /Over 90 days late/.test(age) && /as of 2026-10-15/.test(age) && /Also in INR/.test(age), age);
        const rows = () => [...doc.querySelectorAll('#sales-ledger-body tr')];
        check('by default only those who owe are listed (three accounts: two in pounds and the rupee one)', rows().length === 4 && !/Near Co/.test(text(doc.getElementById('sales-ledger-body'))), String(rows().length));
        const first = rows()[0];
        check('a row has the name, reference, balance, overdue and dates', /Big/.test(text(first)) && /BC-1/.test(text(first)) && /£300\.00/.test(text(first)) && /£100\.00/.test(text(first)) && /oldest 12d/.test(text(first)) && /2026-10-10/.test(text(first)) && /2026-09-01/.test(text(first)));
        check('  and the credit used against the limit with a warning', /£300\.00 of £250\.00/.test(text(first)) && /Over limit/.test(text(first)));
        check('  a name typed with markup is text, not markup', !doc.querySelector('#sales-ledger-body b') && /Big <b>Customer<\/b>/.test(text(first)));
        check('  an account on hold says so; one with no limit says no limit', /On hold/.test(text(rows()[1])) && /No limit/.test(text(rows()[1])));
        check('  a customer in another currency is tagged, in its own money', /INR/.test(text(rows()[3])) && /INR 9000\.00/.test(text(rows()[3])));
        check('  somebody with no customer record cannot be opened', !rows()[2].querySelector('[data-ledger-open]'), rows()[2].innerHTML.slice(0, 100));
        const tabs = [...doc.querySelectorAll('#sales-ledger-tabs .tab')];
        const pick = f => { click(w, tabs.find(t => t.getAttribute('data-ledger-filter') === f)); return rows().map(r => text(r.cells[0])).join('|'); };
        check('the Overdue tab keeps only those with something late', /Held Co/.test(pick('overdue')) && !/Walk-in/.test(pick('overdue')) && rows().length === 2);
        pick('limit');
        check('Over or near limit keeps the one over', rows().length === 1 && /Big/.test(text(doc.getElementById('sales-ledger-body'))));
        check('On hold keeps the one on hold', (pick('hold'), rows().length === 1) && /Held Co/.test(text(rows()[0])));
        check('All customers includes one who owes nothing', (pick('all'), rows().length === 5) && /Near Co/.test(text(doc.getElementById('sales-ledger-body'))));
        const s = doc.getElementById('sales-ledger-search');
        s.value = 'nr-3'; s.dispatchEvent(new w.Event('input'));
        check('the search finds a customer by their account reference', rows().length === 1 && /Near Co/.test(text(rows()[0])));
        s.value = 'zzz'; s.dispatchEvent(new w.Event('input'));
        check('and an empty result says so', /No customer accounts match/.test(text(doc.getElementById('sales-ledger-body'))));
        check('the count follows the list', /0 accounts/.test(text(doc.getElementById('sales-ledger-count'))));
        doc.getElementById('sales-ledger-asof').value = '2026-06-30';
        check('the export follows the day chosen', w.ledgerCsvUrl('sales') === '/api/ledger/sales.csv?as_of=2026-06-30' && w.ledgerCsvUrl('purchases') === '/api/ledger/purchases.csv');
        doc.getElementById('sales-ledger-asof').dispatchEvent(new w.Event('change'));
        await wait(30);
        check('changing the day asks for the ledger as of that day', sent.some(x => x.full === '/api/ledger/sales?as_of=2026-06-30'));
    }
    {
        const { w, doc } = boot({ sales: { ...SALES, accounts: [], totals: { ...SALES.totals, balance: 0, overdue: 0, accounts_owing: 0, over_limit: 0, on_hold: 0 } } });
        await w.loadSalesLedger();
        check('with nobody owing, the tiles are calm and the list says so', /Owed to you\s*£0\.00/.test(text(doc.getElementById('sales-ledger-tiles'))) && /No customer accounts match/.test(text(doc.getElementById('sales-ledger-body'))));
    }

    // --- one customer's account ------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadSalesLedger();
        click(w, doc.querySelector('#sales-ledger-body [data-ledger-open="1"]'));
        await wait(60);
        const modal = doc.getElementById('ledger-detail-modal');
        const body = text(doc.getElementById('ledger-detail-body'));
        check('opening a customer shows their account in a window', modal.style.display === 'flex' && /BC-1/.test(text(doc.getElementById('ledger-detail-title'))));
        check('  with the credit position against the limit', /£300\.00 of £250\.00/.test(body) && /£50\.00 over/.test(body) && /Over limit/.test(body), body.slice(0, 300));
        check('  the contact and terms', /big@x\.test/.test(body) && /30 days/.test(body));
        check('  the ledger, with balance brought forward, each line and a running balance, carried forward',
            /Balance brought forward/.test(body) && /Invoice INV-1/.test(body) && /Balance carried forward\s*£300\.00/.test(body) && /£100\.00/.test(body));
        check('  what is open, and how late', /Open invoices/.test(body) && /12 days late/.test(body) && !!doc.querySelector('#ledger-detail-body a[href="#/invoices/INV-1"]'));
        check('  nothing in a name or a description runs as markup', !doc.querySelector('#ledger-detail-body script') && !doc.querySelector('#ledger-detail-title b') && !doc.querySelector('#ledger-detail-body b'));
        check('  the statement can be taken as a CSV for the period', /\/api\/contacts\/1\/statement\.csv\?start=2026-07-17&end=2026-10-15/.test(doc.getElementById('ledger-csv').getAttribute('href')));
        doc.getElementById('ledger-detail-start').value = '2026-01-01';
        doc.getElementById('ledger-detail-end').value = '2026-03-31';
        click(w, doc.getElementById('ledger-detail-apply'));
        await wait(40);
        check('choosing a period asks for that period', sent.some(x => x.full === '/api/ledger/sales/1?start=2026-01-01&end=2026-03-31'));
        click(w, doc.getElementById('ledger-hold'));
        await wait(60);
        const put = sent.find(x => x.url === '/api/contacts/1' && x.method === 'PUT');
        check('Put on hold saves that on the customer', put && bodyOf(put).on_hold === true);
        click(w, doc.getElementById('ledger-email'));
        await wait(60);
        check('Email statement asks first, then sends the period', /Email this statement/.test(w._asked[0]) && sent.some(x => x.url === '/api/contacts/1/statement/send' && x.method === 'POST' && bodyOf(x).start));
        click(w, doc.getElementById('ledger-detail-close'));
        check('Close shuts the window', modal.style.display === 'none');
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.loadSalesLedger();
        click(w, doc.querySelector('#sales-ledger-body [data-ledger-open="1"]'));
        await wait(60);
        click(w, doc.getElementById('ledger-email'));
        await wait(40);
        check('saying no to the statement sends nothing', !sent.some(x => x.url === '/api/contacts/1/statement/send'));
    }
    {
        const { w, doc } = boot();
        w.loadContacts = async () => { w._loaded = true; };
        w.editContact = id => { w._edited = id; };
        w.allContacts = [];
        await w.loadSalesLedger();
        click(w, doc.querySelector('#sales-ledger-body [data-ledger-open="1"]'));
        await wait(60);
        click(w, doc.getElementById('ledger-edit'));
        await wait(40);
        check('Edit account closes the window and opens the customer form', w._edited === 1 && doc.getElementById('ledger-detail-modal').style.display === 'none');
    }

    // --- the purchase ledger list ----------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadPurchaseLedger();
        const tiles = text(doc.getElementById('purchase-ledger-tiles'));
        check('the tiles say what you owe, what is late, who is owed, and credit not yet used',
            /You owe\s*£220\.00/.test(tiles) && /Overdue\s*£70\.00/.test(tiles) && /Suppliers owed\s*1/.test(tiles) && /Credit not yet used\s*£50\.00/.test(tiles), tiles);
        const rows = () => [...doc.querySelectorAll('#purchase-ledger-body tr')];
        check('by default those owed are listed, with the credit that came off', rows().length === 2 && /after £50\.00 credit/.test(text(rows()[0])) && /£70\.00/.test(text(rows()[0])) && /2026-09-25/.test(text(rows()[0])));
        check('  a supplier name typed with markup is text', !doc.querySelector('#purchase-ledger-body i'));
        check('  bills with no supplier are still on the list and can be opened', /No supplier/.test(text(rows()[1])) && !!rows()[1].querySelector('[data-ledger-open="0"]'));
        const tabs = [...doc.querySelectorAll('#purchase-ledger-tabs .tab')];
        const pick = f => { click(w, tabs.find(t => t.getAttribute('data-ledger-filter') === f)); return rows().length; };
        check('Overdue, On hold and All filter the list', pick('overdue') === 1 && pick('hold') === 1 && /Quiet Co/.test(text(rows()[0])) && pick('all') === 3);
    }

    // --- one supplier's account ----------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadPurchaseLedger();
        click(w, doc.querySelector('#purchase-ledger-body [data-ledger-open="7"]'));
        await wait(60);
        const body = text(doc.getElementById('ledger-detail-body'));
        check('a supplier opens with what you owe, how to pay them and their terms', /£220\.00/.test(body) && /Sort 12-34-56/.test(body) && /30 days/.test(body) && /Pat/.test(body));
        check('  the ledger runs bills, a payment and a credit note into a balance', /Bill B-1/.test(body) && /Payment on B-1 \(cheque\)/.test(body) && /Credit note SC-0001/.test(body) && /Balance carried forward\s*£220\.00/.test(body));
        check('  the column heads say billed and paid or credited', /Billed/.test(body) && /Paid or credited/.test(body));
        check('  bills to pay, with how late each is', /Bills to pay/.test(body) && /10 days late/.test(body) && /not yet due/.test(body));
        check('  credit notes: one can be used and voided, one already used cannot be voided', !!doc.querySelector('[data-ledger-use="21"]') && !!doc.querySelector('[data-ledger-void="21"]') && !doc.querySelector('[data-ledger-use="22"]') && !doc.querySelector('[data-ledger-void="22"]'));
        check('  nothing in a name runs as markup', !doc.querySelector('#ledger-detail-body i') && !doc.querySelector('#ledger-detail-title i'));
        check('  the ledger can be exported for the period', /\/api\/ledger\/purchases\/7\/ledger\.csv\?start=2026-07-17&end=2026-10-15/.test(doc.getElementById('ledger-csv').getAttribute('href')));
        // paying a bill from here
        w._forms.length = 0;
        const formFn = w.uiForm;
        w.uiForm = (fields, o) => { w._forms.push({ fields, o }); return Promise.resolve({ amount: '25', paid_on: '2026-10-15', method: 'cheque', account_id: '3', reference: 'CHQ 9' }); };
        click(w, doc.querySelector('[data-ledger-pay="11"]'));
        await wait(100);
        const f = w._forms[0];
        check('Pay asks how much (what is left), when, how, from where and the reference',
            f && f.fields.map(x => x.name).join() === 'amount,paid_on,method,account_id,reference' && f.fields[0].value === 70 && /Pay bill B-1/.test(f.o.title) && /Current account/.test(JSON.stringify(f.fields[3].options)) && !/Old/.test(JSON.stringify(f.fields[3].options)));
        const post = sent.find(x => x.url === '/api/bills/11/payments' && x.method === 'POST');
        check('  and records just that payment', post && bodyOf(post).amount === 25 && bodyOf(post).method === 'cheque' && bodyOf(post).account_id === 3 && bodyOf(post).reference === 'CHQ 9' && bodyOf(post).paid_on === '2026-10-15');
        w.uiForm = formFn;
        // using a credit
        w.uiForm = (fields, o) => { w._forms.push({ fields, o }); return Promise.resolve({ bill_id: '12', amount: '30' }); };
        click(w, doc.querySelector('[data-ledger-use="21"]'));
        await wait(120);
        const alloc = sent.find(x => x.url === '/api/supplier-credits/21/allocate');
        check('Use a credit asks which bill and how much, and sets it', alloc && bodyOf(alloc).bill_id === 12 && bodyOf(alloc).amount === 30);
        click(w, doc.querySelector('[data-ledger-void="21"]'));
        await wait(80);
        check('Void asks first, then voids', /Void this credit note/.test(w._asked[w._asked.length - 1]) && sent.some(x => x.url === '/api/supplier-credits/21/void' && x.method === 'POST'));
        click(w, doc.getElementById('ledger-hold'));
        await wait(60);
        check('Put on hold saves it on the supplier', bodyOf(sent.find(x => x.url === '/api/suppliers/7' && x.method === 'PUT')).on_hold === true);
    }
    {
        const { w, doc } = boot();
        await w.loadPurchaseLedger();
        click(w, doc.querySelector('#purchase-ledger-body [data-ledger-open="0"]'));
        await wait(60);
        check('the account for bills with no supplier opens without supplier actions', !doc.getElementById('ledger-edit') && !doc.getElementById('ledger-newbill') && /No supplier/.test(text(doc.getElementById('ledger-detail-title'))));
    }

    // --- suppliers ----------------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.openSupplierModal(0);
        const val = id => doc.getElementById(id).value;
        check('a new supplier opens blank with no Remove button', doc.getElementById('supplier-modal').style.display === 'flex' && val('supplier-name') === '' && doc.getElementById('supplier-delete').style.display === 'none' && /New supplier/.test(text(doc.getElementById('supplier-modal-title'))));
        click(w, doc.getElementById('supplier-save'));
        await wait(20);
        check('saving with no name says so and sends nothing', (w._toasts || []).some(t => /needs a name/.test(t[0])) && !sent.some(x => x.url === '/api/suppliers' && x.method === 'POST'));
        doc.getElementById('supplier-name').value = '  Northwind ';
        doc.getElementById('supplier-ref').value = 'NW1';
        doc.getElementById('supplier-currency').value = 'usd';
        doc.getElementById('supplier-hold').checked = true;
        click(w, doc.getElementById('supplier-save'));
        await wait(60);
        const post = bodyOf(sent.find(x => x.url === '/api/suppliers' && x.method === 'POST'));
        check('a new supplier is posted with what was typed, tidy', post.name === 'Northwind' && post.account_ref === 'NW1' && post.currency === 'USD' && post.on_hold === true && post.payment_terms_days === null);
        check('  and the window closes', doc.getElementById('supplier-modal').style.display === 'none');
        await w.openSupplierModal(7);
        check('editing loads the supplier, with Remove offered', val('supplier-name') === 'Acme Supplies' && val('supplier-terms') === '30' && val('supplier-bank') === 'Sort 12' && doc.getElementById('supplier-hold').checked && doc.getElementById('supplier-delete').style.display !== 'none');
        doc.getElementById('supplier-terms').value = '';
        click(w, doc.getElementById('supplier-save'));
        await wait(60);
        const put = sent.find(x => x.url === '/api/suppliers/7' && x.method === 'PUT');
        check('saving an edit puts it, and empty terms mean "your default"', put && bodyOf(put).payment_terms_days === null);
        click(w, doc.getElementById('supplier-delete'));
        await wait(60);
        check('Remove asks first and then deletes', /Remove this supplier/.test(w._asked[0]) && sent.some(x => x.url === '/api/suppliers/7' && x.method === 'DELETE'));
    }
    {
        const { w, doc } = boot({ reply: { 'POST /api/suppliers': () => ({ status: 400, body: { detail: 'You already have a supplier called Acme' } }) } });
        await w.openSupplierModal(0);
        doc.getElementById('supplier-name').value = 'Acme';
        click(w, doc.getElementById('supplier-save'));
        await wait(60);
        check('a refusal is shown in the server\'s words and the window stays open', (w._toasts || []).some(t => /already have a supplier/.test(t[0]) && t[1] === 'error') && doc.getElementById('supplier-modal').style.display === 'flex');
    }

    // --- supplier credit notes ------------------------------------------------------------------------------------
    {
        const { w, sent } = boot({ form: { supplier_id: '8', amount: '40.5', issue_date: '2026-10-14', reference: 'THEIR-1', reason: 'short delivery' },
            reply: { 'POST /api/supplier-credits': () => ({ body: { id: 1, number: 'SC-0003' } }) } });
        await w.openSupplierCredit(0);
        const post = bodyOf(sent.find(x => x.url === '/api/supplier-credits'));
        check('a supplier credit note is recorded with supplier, amount, date, their number and the reason', post.supplier_id === 8 && post.amount === 40.5 && post.issue_date === '2026-10-14' && post.reference === 'THEIR-1' && post.reason === 'short delivery');
        check('  and says what number it got', (w._toasts || []).some(t => /SC-0003/.test(t[0])));
        check('  the form offers the suppliers to choose from', JSON.stringify(w._forms[0].fields[0].options).includes('Quiet Co'));
    }
    {
        const { w, sent } = boot({ form: null });
        await w.openSupplierCredit(7);
        check('backing out of the credit form records nothing', !sent.some(x => x.url === '/api/supplier-credits' && x.method === 'POST'));
    }
    {
        const { w } = boot({ reply: { '/api/suppliers': () => ({ body: [] }) } });
        await w.openSupplierCredit(0);
        check('with no suppliers there is nothing to credit and it says why', (w._toasts || []).some(t => /Add a supplier first/.test(t[0])));
    }

    // --- Bills ---------------------------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadBills();
        const rows = [...doc.querySelectorAll('#bills-table-body tr')];
        check('the Bills screen shows total, paid and what is owing, and how late', rows.length === 4 && /£100\.00/.test(text(rows[0])) && /£30\.00/.test(text(rows[0])) && /£70\.00/.test(text(rows[0])) && /10 days late/.test(text(rows[0])));
        check('  a paid bill has no Pay button and no owing figure; a part-paid one has Payments and cannot be deleted',
            !rows[2].querySelector('[data-bill-pay]') && /-/.test(text(rows[2].cells[6])) && !!rows[0].querySelector('[data-bill-payments]') && !rows[0].querySelector('[data-bill-del]') && !!rows[1].querySelector('[data-bill-del]'));
        check('  a draft is marked as one and its name is text', !doc.querySelector('#bills-table-body u') && /Draft/.test(text(rows[3])));
        check('  the supplier is a link to their account', !!rows[0].querySelector('[data-bill-supplier="7"]'));
        const note = doc.getElementById('bills-drafts-note');
        check('draft bills are called out, with a way to post them all', note.style.display !== 'none' && /1 draft bill is not counted/.test(text(note)));
        w.filterBills('Unpaid', null);
        check('Unpaid is awaiting payment or part paid', doc.querySelectorAll('#bills-table-body tr').length === 2);
        w.filterBills('Overdue', null);
        check('Overdue is what is past due', doc.querySelectorAll('#bills-table-body tr').length === 1 && /B-1/.test(text(doc.getElementById('bills-table-body'))));
        w.filterBills('Paid', null);
        check('Paid is paid', doc.querySelectorAll('#bills-table-body tr').length === 1);
        w.filterBills('Draft', null);
        check('Draft is drafts', doc.querySelectorAll('#bills-table-body tr').length === 1);
        await w.postDraftBills();
        check('posting the drafts asks first, then posts', /Post 1 draft bill/.test(w._asked[0]) && sent.some(x => x.url === '/api/bills/post-drafts' && x.method === 'POST'));
    }
    {
        const { w, doc } = boot({ bills: [BILLS[0]] });
        await w.loadBills();
        check('with no drafts there is no call-out', doc.getElementById('bills-drafts-note').style.display === 'none');
    }
    {
        const { w, doc, sent } = boot();
        await w.loadBills();
        click(w, doc.querySelector('[data-bill-pay="12"]'));
        await wait(100);
        const post = sent.find(x => x.url === '/api/bills/12/payments' && x.method === 'POST');
        check('Pay on a bill asks, and with the defaults pays what is left', post && bodyOf(post).amount === 200 && bodyOf(post).method === 'bank_transfer' && w._forms[0].fields[0].value === 200);
        click(w, doc.querySelector('[data-bill-payments="11"]'));
        await wait(100);
        const m = doc.getElementById('bill-payments-modal');
        const t = text(doc.getElementById('bill-payments-body'));
        check('Payments lists each payment, with the total, what is paid and left', m.style.display === 'flex' && /£100\.00/.test(t) && /£70\.00/.test(t) && /CHQ 1/.test(t) && /£20\.00/.test(t) && /£10\.00/.test(t));
        check('  one that came from a bank line cannot be taken back here', !!doc.querySelector('[data-bp-remove="1"]') && !doc.querySelector('[data-bp-remove="2"]') && /bank line/.test(t));
        check('  how to pay the supplier is shown', /Sort 12-34/.test(t));
        click(w, doc.querySelector('[data-bp-remove="1"]'));
        await wait(100);
        check('Take back asks first, then deletes that payment', /Take this payment back/.test(w._asked[w._asked.length - 1]) && sent.some(x => x.url === '/api/bills/11/payments/1' && x.method === 'DELETE'));
        click(w, doc.getElementById('bill-payments-done'));
        check('Close shuts it', m.style.display === 'none');
    }
    {
        const { w, doc, sent } = boot({ form: null });
        await w.loadBills();
        click(w, doc.querySelector('[data-bill-pay="12"]'));
        await wait(80);
        check('backing out of the payment form pays nothing', !sent.some(x => x.url === '/api/bills/12/payments'));
    }
    {
        const { w, doc, sent } = boot({ reply: { 'POST /api/bills/12/payments': () => ({ status: 400, body: { detail: 'That is more than bill B-2 has left (200.00)' } }) } });
        await w.loadBills();
        click(w, doc.querySelector('[data-bill-pay="12"]'));
        await wait(100);
        check('a payment the server refuses is reported in its words', (w._toasts || []).some(t => /more than bill B-2/.test(t[0]) && t[1] === 'error'));
    }
    {
        const { w, doc, sent } = boot();
        await w.showAddBillModal();
        const el = id => doc.getElementById(id);
        check('a new bill starts posted, not a draft, with the supplier list loaded', el('bill-draft').checked === false && el('bill-draft').disabled === false && el('bill-number').value === 'BILL-0009' && el('bill-vendor-list').options.length === 2);
        el('bill-vendor').value = 'Fresh Co';
        el('bill-currency').value = 'usd';
        el('bill-amount').value = '100';
        await w.saveBill();
        const post = bodyOf(sent.find(x => x.url === '/api/bills' && x.method === 'POST'));
        check('saving posts the bill to the supplier named, in its currency, as not a draft', post.vendor_name === 'Fresh Co' && post.currency === 'USD' && post.draft === false && post.number === 'BILL-0009');
        el('bill-draft').checked = true;
        await w.saveBill();
        check('ticking draft saves a draft', bodyOf(sent.filter(x => x.url === '/api/bills' && x.method === 'POST')[1]).draft === true);
        el('bill-vendor').value = '';
        await w.saveBill();
        check('no supplier is refused before anything is sent', (w._toasts || []).some(t => /supplier required/.test(t[0])) && sent.filter(x => x.url === '/api/bills' && x.method === 'POST').length === 2);
    }
    {
        const { w, doc, sent } = boot();
        await w.editBill(11);
        const el = id => doc.getElementById(id);
        check('editing a bill with payments leaves its currency fixed and its status alone', el('bill-currency').disabled === true && el('bill-draft').disabled === true && el('bill-draft').checked === false);
        await w.saveBill();
        const put = bodyOf(sent.find(x => x.url === '/api/bills/11' && x.method === 'PUT'));
        check('  so the save does not say draft or status', !('draft' in put) && !('status' in put));
    }
    {
        const { w, doc, sent } = boot({ bills: BILLS });
        await w.loadBills();
        // a draft bill being edited can be posted by unticking the box
        const { w: w2, doc: d2, sent: s2 } = boot({ reply: { '/api/bills/14': () => ({ body: { ...BILLS[3], payments: [], supplier: null } }) } });
        await w2.editBill(14);
        check('editing a draft shows it ticked and unticking posts it', d2.getElementById('bill-draft').checked === true && d2.getElementById('bill-draft').disabled === false);
        d2.getElementById('bill-draft').checked = false;
        await w2.saveBill();
        check('  by saying it is not a draft', bodyOf(s2.find(x => x.url === '/api/bills/14' && x.method === 'PUT')).draft === false);
    }
    {
        const { w, doc } = boot({ reply: { 'POST /api/bills': () => ({ status: 400, body: { detail: 'Bill number already exists' } }) } });
        await w.showAddBillModal();
        doc.getElementById('bill-vendor').value = 'X';
        await w.saveBill();
        check('a bill the server refuses says why and keeps the form open', (w._toasts || []).some(t => /already exists/.test(t[0])) && doc.getElementById('add-bill-modal').style.display === 'flex');
    }
    {
        const { w, doc } = boot({ reply: { 'DELETE /api/bills/12': () => ({ status: 400, body: { detail: 'Bill B-2 has payments against it.' } }) } });
        await w.loadBills();
        await w.deleteBill(12, 'B-2');
        check('deleting a bill the server will not delete says why', (w._toasts || []).some(t => /has payments against it/.test(t[0])));
    }

    // --- the customer's side of the sales ledger ---------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadContacts();
        await w.editContact(1);
        const el = id => doc.getElementById(id);
        check('a customer form shows the account reference, credit limit and hold', el('contact-account-ref').value === 'BC-1' && el('contact-credit-limit').value === '250' && el('contact-on-hold').checked === true);
        el('contact-credit-limit').value = '';
        el('contact-on-hold').checked = false;
        el('contact-account-ref').value = ' BC-9 ';
        await w.saveContact();
        const put = bodyOf(sent.find(x => x.url === '/api/contacts/1' && x.method === 'PUT'));
        check('saving sends them (no limit is 0)', put.account_ref === 'BC-9' && put.credit_limit === 0 && put.on_hold === false);
        w.showAddContactModal();
        check('a new customer form starts with none of them', el('contact-account-ref').value === '' && el('contact-credit-limit').value === '' && el('contact-on-hold').checked === false);
    }
    {
        const { w, doc } = boot({ reply: { 'PUT /api/contacts/1': () => ({ status: 400, body: { detail: 'Account reference BC-1 is already used by Ann Co' } }) } });
        await w.loadContacts();
        await w.editContact(1);
        await w.saveContact();
        check('a clash on the account reference is shown in the server\'s words', (w._toasts || []).some(t => /already used by Ann Co/.test(t[0])));
    }

    // --- warned on the invoice before selling ------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ credit: { known: true, warnings: ['Big Customer\'s account is on hold.', 'This would take <b>x</b> over.'], state: 'on_hold' } });
        const box = doc.getElementById('inv-credit-warning');
        check('the invoice form has a place for a credit warning, hidden at first', !!box && box.style.display === 'none');
        doc.getElementById('inv-contact').value = 'Big Customer';
        doc.getElementById('summary-total').textContent = '250.00 GBP';
        await w.checkInvoiceCredit();
        const call = sent.find(x => x.url === '/api/ledger/credit-check');
        check('it asks about the customer and the invoice total', call && /name=Big%20Customer/.test(call.full) && /amount=250/.test(call.full), call && call.full);
        check('  and shows each warning as text', box.style.display !== 'none' && /on hold/.test(box.textContent) && !box.querySelector('b'));
    }
    {
        const { w, doc } = boot({ credit: { known: true, warnings: [], state: 'ok' } });
        const box = doc.getElementById('inv-credit-warning');
        doc.getElementById('inv-contact').value = 'Fine Co';
        box.style.display = '';
        await w.checkInvoiceCredit();
        check('no warnings, or no customer yet, hides it', box.style.display === 'none');
        doc.getElementById('inv-contact').value = '';
        box.style.display = '';
        await w.checkInvoiceCredit();
        check('  an empty name too', box.style.display === 'none');
    }
    {
        const { w, doc, sent } = boot();
        doc.getElementById('inv-contact').value = 'Big Customer';
        w.calculateTotals('invoice');
        await wait(1200);
        check('changing the invoice lines re-checks the credit', sent.some(x => x.url === '/api/ledger/credit-check'));
    }
    {
        const { w, doc, sent } = boot({ reply: { '/api/ledger/credit-check': () => ({ status: 500, body: {} }) } });
        const box = doc.getElementById('inv-credit-warning');
        doc.getElementById('inv-contact').value = 'Big Customer';
        box.style.display = '';
        await w.checkInvoiceCredit();
        check('a failed check never gets in the way of raising an invoice', box.style.display === 'none');
    }

    // --- tighter: the currency tag and the credit bar --------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadSalesLedger();
        const rows = [...doc.querySelectorAll('#sales-ledger-body tr')];
        const tag = r => [...r.cells[0].querySelectorAll('span')].map(s => s.textContent.trim());
        check('only a foreign-currency row carries a currency tag', tag(rows[3]).includes('INR') && !tag(rows[0]).includes('GBP'));
        const bar = rows[0].querySelector('div[style*="width:100%"]') || rows[0].querySelector('div[style*="height:5px;border-radius"]');
        check('an account over its limit has its credit bar in the warning colour', bar && /var\(--danger-text\)/.test(bar.getAttribute('style')), bar && bar.getAttribute('style'));
    }

    // --- Aged creditors on the Reports page ------------------------------------------------------------------
    {
        const PAYABLES = { as_of: '2026-10-15', currency: 'GBP', buckets: { current: 200, '1_30': 70, '31_60': 0, '61_90': 0, over_90: 0 }, total_outstanding: 220, overdue: 70, credits: 50,
            suppliers: [{ supplier_id: 7, supplier: 'Acme <i>Supplies</i>', currency: 'GBP', current: 200, '1_30': 70, '31_60': 0, '61_90': 0, over_90: 0, credits: 50, total: 220 },
                        { supplier_id: 8, supplier: 'Quiet Co', currency: 'GBP', current: 0, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0, credits: 0, total: 0 }],
            bills: [], other_currencies: [] };
        const { w, doc, sent } = boot({ reply: { '/api/reports/ageing/payables': () => ({ body: PAYABLES }) } });
        check('the Reports page has an Aged Creditors button', !!doc.getElementById('rpt-payables-btn'));
        await w.loadAgedPayables();
        const box = text(doc.getElementById('payables-buckets'));
        check('it shows what you owe by age, after credit, and what is overdue', doc.getElementById('reports-payables-content').style.display === 'block' &&
            /Not yet due\s*£200\.00/.test(box) && /You owe £220\.00/.test(box) && /after £50\.00 of supplier credit/.test(box) && /overdue £70\.00/.test(box), box);
        const rows = doc.querySelectorAll('#payables-suppliers tbody tr');
        check('  a row per supplier owed, names as text', rows.length === 1 && !doc.querySelector('#payables-suppliers i') && /£220\.00/.test(text(rows[0])));
        check('  and the other report tabs are hidden', doc.getElementById('reports-aged-content').style.display === 'none');
        doc.getElementById('payables-asof').value = '2026-06-30';
        await w.loadAgedPayables();
        check('the day chosen goes to the report and both spreadsheets', sent.some(x => x.full === '/api/reports/ageing/payables?as_of=2026-06-30') &&
            doc.getElementById('payables-csv').getAttribute('href') === '/api/reports/ageing/payables.csv?as_of=2026-06-30' &&
            doc.getElementById('payables-csv-detail').getAttribute('href') === '/api/reports/ageing/payables.csv?as_of=2026-06-30&detail=1');
        w.openPurchaseAccount = id => { w._openedSupplier = id; };
        click(w, doc.querySelector('[data-payables-open="7"]'));
        check('a supplier opens their account', w._openedSupplier === 7);
    }
    {
        const { w, doc } = boot({ reply: { '/api/reports/ageing/payables': () => ({ status: 500, body: {} }) } });
        await w.loadAgedPayables();
        check('a report that fails to load says so', /Could not load/.test(text(doc.getElementById('payables-buckets'))));
    }

    // --- voiding a bill -----------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadBills();
        check('Void is offered on a posted bill nothing has been paid on, and only there',
            !!doc.querySelector('[data-bill-void="12"]') && !doc.querySelector('[data-bill-void="11"]') && !doc.querySelector('[data-bill-void="13"]') && !doc.querySelector('[data-bill-void="14"]'));
        click(w, doc.querySelector('[data-bill-void="12"]'));
        await wait(60);
        check('voiding asks first, then voids', /Void bill B-2/.test(w._asked[0]) && sent.some(x => x.url === '/api/bills/12/void' && x.method === 'POST'));
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.loadBills();
        click(w, doc.querySelector('[data-bill-void="12"]'));
        await wait(60);
        check('saying no voids nothing', !sent.some(x => x.url === '/api/bills/12/void'));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
