/**
 * Sales and Purchases, each with its own menu, dashboard and settings.
 *
 * An accountant asked for the two sides to be reachable separately: a Sales
 * menu (dashboard, invoices, quotations, credit notes, payment options,
 * customers, reports, settings) and a Purchases menu (dashboard, bills,
 * settings). The numbers on the dashboards are the server's; what is pinned
 * here is what the page decides - where each item lives, that a tile opens
 * the list it counts with the matching tab lit, that a name can never become
 * markup, that a failure says so, and that each settings entry opens the
 * section that holds the setting rather than the top of one long page.
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

const SALES = { draft: { count: 2, amount: 120 }, awaiting: { count: 1, amount: 300 }, overdue: { count: 3, amount: 1482 },
    done: { count: 7, amount: 5000 }, due_this_week: 200, due_next_week: 80, currency: 'GBP',
    customers_owing_most: [{ name: 'Acme', owed: 900 }, { name: '<b>Evil</b>', owed: 50 }] };
const BUYING = { draft: { count: 0, amount: 0 }, awaiting: { count: 2, amount: 640 }, overdue: { count: 0, amount: 0 },
    done: { count: 4, amount: 900 }, due_this_week: 40, due_next_week: 0, currency: 'GBP',
    suppliers_owed_most: [{ name: 'Paper Co', owed: 640 }] };

const BILLS = [
    { id: 1, number: 'B-1', vendor_name: 'Paper Co', total: 100, amount_paid: 0, status: 'Unpaid', due_date: '2026-01-01', issue_date: '2025-12-01' },
    { id: 2, number: 'B-2', vendor_name: 'Tea Ltd', total: 50, amount_paid: 50, status: 'Paid', due_date: '2026-01-01', issue_date: '2025-12-01' },
    { id: 3, number: 'B-3', vendor_name: 'Tea Ltd', total: 20, amount_paid: 0, status: 'Draft', due_date: '2026-02-01', issue_date: '2026-01-01' },
];
const RECURRING = [
    { id: 5, name: 'Office rent', vendor_name: 'Landlord Ltd', vendor_email: '', category: 'rent', reference: '', notes: '', amount: 1000, tax_amount: 200, total: 1200,
      frequency: 'monthly', payment_terms_days: 30, next_run: '2026-12-01', end_date: '', is_active: true, auto_approve: true, bills_created: 3 },
    { id: 6, name: '<b>Old</b> retainer', vendor_name: 'Cray', vendor_email: '', category: 'general', reference: '', notes: '', amount: 50, tax_amount: 0, total: 50,
      frequency: 'weekly', payment_terms_days: 7, next_run: '2026-01-10', end_date: '2026-01-05', is_active: false, auto_approve: false, bills_created: 9 },
    { id: 7, name: 'Paused one', vendor_name: 'Tea Ltd', vendor_email: '', category: 'general', reference: '', notes: '', amount: 20, tax_amount: 0, total: 20,
      frequency: 'quarterly', payment_terms_days: 30, next_run: '2027-01-01', end_date: '', is_active: false, auto_approve: false, bills_created: 1 },
];
const SUPPLIERS = [
    { name: 'Paper Co', email: 'ap@paper.example', bills: 1, billed: 100, owed: 100, overdue: 1, last_bill: '2025-12-01' },
    { name: '<i>Evil</i> Ltd', email: '', bills: 2, billed: 70, owed: 0, overdue: 0, last_bill: '2026-01-01' },
];

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    const sent = [];
    const reply = (status, body) => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, full: String(url) });
        if (p === '/api/auth/me') return reply(200, { user: { email: 'me@x' }, client_id: 1 });
        if (p === '/api/client/me') return reply(200, { id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/sales/overview') return opts.fails ? reply(500, { detail: 'Server is down' }) : reply(200, SALES);
        if (p === '/api/purchases/overview') return opts.fails ? reply(500, { detail: 'Server is down' }) : reply(200, BUYING);
        if (p === '/api/bills') return reply(200, BILLS);
        if (p === '/api/recurring-bills' && (!init || !init.method || init.method === 'GET')) return opts.fails ? reply(500, { detail: 'Server is down' }) : reply(200, RECURRING);
        if (/^\/api\/recurring-bills/.test(p)) { sent[sent.length - 1].body = init && init.body; sent[sent.length - 1].method = init && init.method; return reply(opts.saveFails ? 400 : 200, opts.saveFails ? { detail: opts.saveFails } : {}); }
        if (p === '/api/purchases/suppliers') return opts.fails ? reply(500, { detail: 'Server is down' }) : reply(200, { suppliers: SUPPLIERS });
        if (p === '/api/payment-gateways') return reply(200, { gateways: opts.gateways || [], platform_methods: opts.platform || [] });
        return reply(200, p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    // Questions are answered by the test, and what the page said is recorded.
    const confirms = [];
    w.uiConfirm = (m) => { confirms.push(m); return Promise.resolve(opts.confirm !== false); };
    const toasts = [];
    w.showToast = (m, k) => toasts.push({ m, k });
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent, confirms, toasts };
}

(async () => {
    // --- the menus ---------------------------------------------------------------
    {
        const doc = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
        const group = name => doc.querySelector(`[data-nav-group="${name}"]`);
        const inGroup = (name, id) => !!group(name) && !!group(name).querySelector('#' + id);
        for (const id of ['nav-sales-overview', 'nav-invoices', 'nav-quotes', 'nav-credit-notes', 'nav-payment-options',
            'nav-contacts', 'nav-sales-reports', 'nav-sales-settings']) {
            check(`${id} is in the Sales menu`, inGroup('Sales', id));
        }
        for (const id of ['nav-purchases-overview', 'nav-bills', 'nav-recurring-bills', 'nav-suppliers', 'nav-purchases-settings']) {
            check(`${id} is in the Purchases menu`, inGroup('Purchases', id));
        }
        check('Bills moved out of Money', !inGroup('Money', 'nav-bills'));
        check('Sales and Purchases are separate menus', group('Sales') !== group('Purchases') && !!group('Purchases'));
        const labels = id => doc.getElementById(id).textContent.trim();
        check('the Sales items carry the names the accountant asked for',
            labels('nav-sales-overview') === 'Sales dashboard' && labels('nav-invoices') === 'Sales invoices'
            && labels('nav-quotes') === 'Quotations' && labels('nav-contacts') === 'Customers directory'
            && labels('nav-payment-options') === 'Payment options');
        check('every new entry is on the invoicing plan',
            ['nav-sales-overview', 'nav-payment-options', 'nav-purchases-overview', 'nav-sales-settings', 'nav-purchases-settings']
                .every(id => doc.getElementById(id).getAttribute('data-portal') === 'invoicing'));
        check('the three new screens exist',
            ['sales-overview-view', 'purchases-overview-view', 'payment-options-view', 'suppliers-view', 'recurring-bills-view', 'recurring-bill-modal'].every(id => !!doc.getElementById(id)));
    }

    // --- addresses and highlight -------------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        check('the new screens have addresses and light up their entries',
            w.ROUTE_SLUGS['sales-overview-view'] === 'sales' && w.ROUTE_SLUGS['purchases-overview-view'] === 'purchases'
            && w.ROUTE_SLUGS['payment-options-view'] === 'payment-options' && w.ROUTE_SLUGS['suppliers-view'] === 'suppliers'
            && w.NAV_FOR_VIEW['suppliers-view'] === 'nav-suppliers'
            && w.ROUTE_SLUGS['recurring-bills-view'] === 'recurring-bills' && w.NAV_FOR_VIEW['recurring-bills-view'] === 'nav-recurring-bills'
            && w.NAV_FOR_VIEW['sales-overview-view'] === 'nav-sales-overview'
            && w.NAV_FOR_VIEW['purchases-overview-view'] === 'nav-purchases-overview'
            && w.NAV_FOR_VIEW['payment-options-view'] === 'nav-payment-options');
    }

    // --- the sales dashboard -----------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        w.showView('sales-overview-view');
        await wait(60);
        const tiles = w.document.getElementById('sales-overview-tiles').textContent;
        check('it asks the server for the summary', sent.some(s => s.url === '/api/sales/overview'));
        check('the four tiles show the server\'s counts and amounts',
            /Draft \(2\)/.test(tiles) && /Awaiting payment \(1\)/.test(tiles) && /Overdue \(3\)/.test(tiles) && /Completed \(7\)/.test(tiles)
            && /1,482\.00/.test(tiles) && /5,000\.00/.test(tiles), tiles);
        const owing = w.document.getElementById('sales-overview-owing');
        check('who owes most is listed', /Acme/.test(owing.textContent));
        check('a customer name can never become markup',
            owing.querySelector('b') === null && /<b>Evil<\/b>/.test(owing.textContent));
        check('what falls due soon is shown',
            /200\.00/.test(w.document.getElementById('sales-overview-coming').textContent)
            && /80\.00/.test(w.document.getElementById('sales-overview-coming').textContent));

        w.openInvoicesFiltered('overdue');
        await wait(60);
        const active = w.document.querySelector('#invoices-view .invoices-tabs .tab.active');
        check('a tile opens the invoice list on the matching tab', active && /Overdue/.test(active.textContent), active && active.textContent);
        check('and the list is asked for that status', sent.some(s => /invoice-list/.test(s.url) && /status=overdue/.test(s.full)));
    }

    // --- the purchases dashboard -----------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        w.showView('purchases-overview-view');
        await wait(60);
        const tiles = w.document.getElementById('purchases-overview-tiles').textContent;
        check('purchases asks its own endpoint and shows its numbers',
            sent.some(s => s.url === '/api/purchases/overview') && /Awaiting payment \(2\)/.test(tiles) && /640\.00/.test(tiles), tiles);
        check('suppliers owed most are listed', /Paper Co/.test(w.document.getElementById('purchases-overview-owing').textContent));
        w.openBillsFiltered('Unpaid');
        await wait(60);
        const active = w.document.querySelector('#bills-view .invoices-tabs .tab.active');
        check('a tile opens bills on the matching tab', active && /Unpaid/.test(active.textContent), active && active.textContent);
        const shown = w.document.getElementById('bills-table-body').textContent;
        check('and the table agrees with the tab, after the bills have loaded',
            /B-1/.test(shown) && !/B-2/.test(shown) && !/B-3/.test(shown), shown);
    }

    // --- the suppliers directory ----------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        w.showView('suppliers-view');
        await wait(60);
        const body = w.document.getElementById('suppliers-table-body');
        check('suppliers lists what the server worked out', /Paper Co/.test(body.textContent) && /100\.00/.test(body.textContent), body.textContent);
        check('a supplier name can never become markup', body.querySelector('i') === null && /<i>Evil<\/i> Ltd/.test(body.textContent));
        check('overdue is said', /1 overdue/.test(body.textContent));
        const box = w.document.getElementById('suppliers-search');
        box.value = 'paper'; w.renderSuppliers();
        check('the search narrows the list', /Paper Co/.test(body.textContent) && !/Evil/.test(body.textContent) &&
            /1 supplier\b/.test(w.document.getElementById('suppliers-count').textContent));
        box.value = 'zzz'; w.renderSuppliers();
        check('and says when nothing matches', /No supplier matches/.test(body.textContent));
        box.value = '';
        await w.openSupplierBills('Tea Ltd');
        await wait(30);
        check('a supplier\'s Bills button opens the bills list searched for them',
            w.document.getElementById('bill-search').value === 'Tea Ltd'
            && /B-2/.test(w.document.getElementById('bills-table-body').textContent)
            && !/B-1/.test(w.document.getElementById('bills-table-body').textContent));
        const doc = w.document;
        check('both dashboards carry quick links',
            doc.querySelectorAll('#sales-quick-links button').length >= 3 && doc.querySelectorAll('#purchases-quick-links button').length >= 2);
    }
    {
        const { w } = boot({ fails: true });
        await wait(60);
        w.showView('suppliers-view');
        await wait(60);
        check('a failed suppliers load says so', /Server is down/.test(w.document.getElementById('suppliers-table-body').textContent));
    }

    // --- recurring bills ----------------------------------------------------------
    {
        const { w, sent, confirms, toasts } = boot();
        await wait(60);
        w.showView('recurring-bills-view');
        await wait(60);
        const body = () => w.document.getElementById('recurring-bills-body');
        const rowOf = text => [...body().querySelectorAll('tr')].find(tr => tr.textContent.includes(text));
        check('recurring bills asks the server and lists every template', sent.some(s => s.url === '/api/recurring-bills')
            && body().querySelectorAll('tr').length === 3 && /3 items/.test(w.document.getElementById('recurring-bills-count').textContent));
        const rent = rowOf('Office rent');
        check('a row shows supplier, schedule, next date, total and how many were entered',
            /Landlord Ltd/.test(rent.textContent) && /Month/.test(rent.textContent) && /2026-12-01/.test(rent.textContent)
            && /1,200\.00/.test(rent.textContent) && rent.querySelectorAll('td')[5].textContent === '3', rent.textContent);
        check('an active one says Active and that it approves itself, and can be paused',
            /Active/.test(rent.textContent) && /Approves itself/.test(rent.textContent) && /Pause/.test(rent.textContent));
        check('one past its end date says Ended and offers no Resume', /Ended/.test(rowOf('retainer').textContent) && !/Resume/.test(rowOf('retainer').textContent));
        check('a paused one says Paused and can be resumed', /Paused/.test(rowOf('Paused one').textContent) && /Resume/.test(rowOf('Paused one').textContent));
        check('a name can never become markup', body().querySelector('b') === null && /<b>Old<\/b> retainer/.test(body().textContent));

        // pause / resume
        rowOf('Office rent').querySelector('[data-rb-toggle]').click();
        await wait(40);
        check('Pause posts to the pause address', sent.some(s => s.url === '/api/recurring-bills/5/pause' && s.method === 'POST'));
        rowOf('Paused one').querySelector('[data-rb-toggle]').click();
        await wait(40);
        check('Resume posts to the resume address', sent.some(s => s.url === '/api/recurring-bills/7/resume' && s.method === 'POST'));

        // delete asks first, and says what is kept
        rowOf('Paused one').querySelector('[data-rb-delete]').click();
        await wait(40);
        check('Delete asks first and says entered bills stay', confirms.length === 1 && /already entered/.test(confirms[0]));
        check('and then deletes', sent.some(s => s.url === '/api/recurring-bills/7' && s.method === 'DELETE'));

        // create
        w.openRecurringBillModal();
        const doc = w.document;
        check('the form opens empty with sensible defaults',
            doc.getElementById('recurring-bill-modal').style.display === 'flex' && doc.getElementById('rb-id').value === ''
            && doc.getElementById('rb-frequency').value === 'monthly' && doc.getElementById('rb-terms').value === '30'
            && /^\d{4}-\d\d-\d\d$/.test(doc.getElementById('rb-next').value));
        doc.getElementById('rb-amount').value = '100'; w.calcRecurringBillTotal();
        check('the total follows the amount and tax', doc.getElementById('rb-total').value === '100.00');
        doc.getElementById('rb-tax').value = '20'; w.calcRecurringBillTotal();
        check('and the tax', doc.getElementById('rb-total').value === '120.00');
        const before = sent.length;
        await w.saveRecurringBill();
        check('a supplier is required, and nothing is sent without one',
            toasts.some(t => /Supplier name/.test(t.m)) && sent.length === before);
        doc.getElementById('rb-vendor').value = 'Landlord Ltd';
        doc.getElementById('rb-amount').value = '0';
        await w.saveRecurringBill();
        check('an amount is required too', toasts.some(t => /more than nothing/.test(t.m)) && sent.length === before);
        doc.getElementById('rb-amount').value = '1000'; doc.getElementById('rb-tax').value = '200';
        doc.getElementById('rb-approve').checked = true;
        await w.saveRecurringBill();
        const post = sent.filter(s => s.url === '/api/recurring-bills' && s.method === 'POST').pop();
        const sentBody = post && JSON.parse(post.body);
        check('Save posts exactly what was typed',
            sentBody && sentBody.vendor_name === 'Landlord Ltd' && sentBody.amount === 1000 && sentBody.tax_amount === 200
            && sentBody.frequency === 'monthly' && sentBody.payment_terms_days === 30 && sentBody.auto_approve === true && sentBody.is_active === true,
            post && post.body);
        check('and closes the form', doc.getElementById('recurring-bill-modal').style.display === 'none');

        // edit
        w.openRecurringBillModal(5);
        check('Edit fills the form from the template',
            doc.getElementById('rb-id').value === '5' && doc.getElementById('rb-vendor').value === 'Landlord Ltd'
            && doc.getElementById('rb-total').value === '1200.00' && doc.getElementById('rb-approve').checked === true
            && /Edit/.test(doc.getElementById('recurring-bill-title').textContent));
        await w.saveRecurringBill();
        const put = sent.filter(s => s.url === '/api/recurring-bills/5' && s.method === 'PUT').pop();
        check('Save on an edit puts to that template', !!put);
        w.openRecurringBillModal(7);
        await w.saveRecurringBill();
        const put7 = sent.filter(s => s.url === '/api/recurring-bills/7' && s.method === 'PUT').pop();
        check('saving an edit never reactivates one that was paused', put7 && JSON.parse(put7.body).is_active === false);
    }
    {
        const { w, toasts } = boot({ saveFails: 'Frequency must be one of: weekly' });
        await wait(60);
        w.showView('recurring-bills-view');
        await wait(60);
        w.openRecurringBillModal();
        w.document.getElementById('rb-vendor').value = 'X'; w.document.getElementById('rb-amount').value = '5';
        await w.saveRecurringBill();
        check('a refusal from the server is shown, and the form stays open',
            toasts.some(t => /Frequency must be/.test(t.m)) && w.document.getElementById('recurring-bill-modal').style.display === 'flex');
    }
    {
        const { w } = boot({ fails: true });
        await wait(60);
        w.showView('recurring-bills-view');
        await wait(60);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('recurring-bills-body').textContent));
    }

    // --- failure is said ------------------------------------------------------------
    {
        const { w } = boot({ fails: true });
        await wait(60);
        w.showView('sales-overview-view');
        await wait(60);
        check('a failed load says so instead of showing zeros',
            /Server is down/.test(w.document.getElementById('sales-overview-tiles').textContent));
    }

    // --- payment options ------------------------------------------------------------
    {
        const { w } = boot({ gateways: [{ label: 'Razorpay', is_active: true }, { label: 'Stripe', is_active: false }],
            platform: [{ label: 'Pay from your bank (Salt Edge)', offered: true, currencies: ['GBP', 'EUR'] }] });
        await wait(60);
        w.showView('payment-options-view');
        await wait(60);
        const text = w.document.getElementById('payment-options-list').textContent;
        check('payment options lists what is switched on, bank payment included',
            /Razorpay/.test(text) && /Salt Edge/.test(text) && /GBP, EUR/.test(text) && !/Stripe/.test(text), text);
    }
    {
        const { w } = boot();
        await wait(60);
        w.showView('payment-options-view');
        await wait(60);
        check('and says so when nothing is on', /No online payment method/.test(w.document.getElementById('payment-options-list').textContent));
    }

    // --- settings open the right section -----------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        w.openSalesSettings();
        await wait(60);
        const section = () => w.document.querySelector('#settings-panels > [data-settings-section].is-active');
        check('Sales settings opens the Payments section', section() && section().getAttribute('data-settings-section') === 'payments');
        w.openPurchasesSettings();
        await wait(60);
        check('Purchases settings opens Tax Rates', section() && section().getAttribute('data-settings-section') === 'tax-rates');
    }

    if (failures) { console.log(`\n${failures} sales and purchases check(s) failed.`); process.exit(1); }
    console.log('\nAll sales and purchases checks passed.');
})();
