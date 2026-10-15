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
        if (p === '/api/payment-gateways') return reply(200, { gateways: opts.gateways || [], platform_methods: opts.platform || [] });
        return reply(200, p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
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
        for (const id of ['nav-purchases-overview', 'nav-bills', 'nav-purchases-settings']) {
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
            ['sales-overview-view', 'purchases-overview-view', 'payment-options-view'].every(id => !!doc.getElementById(id)));
    }

    // --- addresses and highlight -------------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        check('the new screens have addresses and light up their entries',
            w.ROUTE_SLUGS['sales-overview-view'] === 'sales' && w.ROUTE_SLUGS['purchases-overview-view'] === 'purchases'
            && w.ROUTE_SLUGS['payment-options-view'] === 'payment-options'
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
        const active = w.document.querySelector('#bills-view .invoices-tabs .tab.active');
        check('a tile opens bills on the matching tab', active && /Unpaid/.test(active.textContent), active && active.textContent);
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
