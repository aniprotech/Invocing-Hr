/**
 * The joins on screen: a dashboard item lands on the work it names, and a
 * search hit for a bill, supplier, credit note, item or payslip opens that
 * thing rather than the front of a list.
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

function boot() {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/search') return give({ results: [
            { type: 'bill', label: 'BILL-0001 - Paper <b>Co</b>', sub: 'Awaiting Payment', number: 'BILL-0001', id: 4 },
            { type: 'supplier', label: 'Paper Co', sub: 'PC01', number: '', id: 9 },
            { type: 'credit_note', label: 'CN-0001 - Dee', sub: 'against INV-0003', number: 'CN-0001', id: 2 },
            { type: 'item', label: 'BOX - Box', sub: '6 in stock', number: 'BOX 1', id: 3 },
        ] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    return { w, doc: w.document };
}

(async () => {
    // --- the dashboard ----------------------------------------------------------------------
    {
        const { w, doc } = boot();
        let loaded = 0, shown = [];
        w.showView = v => shown.push(v);
        w.loadExpensesView = () => { loaded++; };
        w.goToAttention({ key: 'expenses_unpaid', view: 'expenses-view', filter: 'approved' });
        check('Approved expenses not repaid opens claims filtered to approved', shown[0] === 'expenses-view' && doc.getElementById('exp-filter').value === 'approved' && loaded === 1);
        w.goToAttention({ key: 'expenses_pending', view: 'expenses-view', filter: 'pending' });
        check('  and claims to decide, filtered to waiting', doc.getElementById('exp-filter').value === 'pending' && loaded === 2);
        let scrolled = null;
        doc.getElementById('pension-panel').scrollIntoView = function () { scrolled = 'pension'; };
        w.goToAttention({ key: 'pension_letters', view: 'payroll-view', filter: 'pension' });
        await wait(450);
        check('Pension letters opens Payroll at the pension panel', shown.indexOf('payroll-view') !== -1 && scrolled === 'pension');
        doc.getElementById('hmrc-panel').scrollIntoView = function () { scrolled = 'hmrc'; };
        w.goToAttention({ key: 'fps_not_sent', view: 'payroll-view', filter: 'hmrc' });
        await wait(450);
        check('  and pay days not sent opens it at the HMRC panel', scrolled === 'hmrc');
        w.goToAttention({ key: 'customers_over_limit', view: 'sales-ledger-view', filter: '' });
        check('Customers over their limit opens the sales ledger', shown[shown.length - 1] === 'sales-ledger-view');
    }

    // --- search ----------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.runGlobalSearch('pap');
        const box = doc.getElementById('global-search-results') || doc.querySelector('.search-results');
        const t = box ? box.textContent : doc.body.textContent;
        check('search shows bills, suppliers, credit notes and items under their own headings', /Bills/.test(t) && /Suppliers/.test(t) && /Credit notes/.test(t) && /Items/.test(t), t.slice(0, 200));
        check('  with labels as text', !(box || doc.body).querySelector('.search-result-item b'));
    }
    {
        const { w } = boot();
        const calls = [];
        w.showView = v => { if (v !== 'dashboard-view') calls.push(['view', v]); };     // the page's own start-up route lands late
        w.editBill = id => calls.push(['bill', id]);
        w.openPurchaseAccount = id => calls.push(['supplier', id]);
        w.viewCreditNote = n => calls.push(['cn', n]);
        w.viewPayslip = id => calls.push(['payslip', id]);
        w.loadInventory = () => calls.push(['inventory']);
        w.openSearchResult('bill', 'BILL-0001', 4);
        await wait(300);
        check('a bill hit opens that bill', JSON.stringify(calls.slice(-2)) === JSON.stringify([['view', 'bills-view'], ['bill', 4]]), JSON.stringify(calls));
        w.openSearchResult('supplier', '', 9);
        check('a supplier hit opens their purchase ledger account', JSON.stringify(calls.slice(-2)) === JSON.stringify([['view', 'purchase-ledger-view'], ['supplier', 9]]));
        w.openSearchResult('credit_note', encodeURIComponent('CN-0001'), 2);
        check('a credit note hit opens it', JSON.stringify(calls[calls.length - 1]) === JSON.stringify(['cn', 'CN-0001']));
        w.openSearchResult('payslip', 'PS-1', 12);
        check('a payslip hit opens the payslip', JSON.stringify(calls[calls.length - 1]) === JSON.stringify(['payslip', 12]));
        w.openSearchResult('item', encodeURIComponent('BOX 1'), 3);
        check('an item hit opens Stock on every item, searched for its code',
            w._inventory.view === 'all' && w.document.getElementById('inventory-search').value === 'BOX 1' && JSON.stringify(calls.slice(-2)) === JSON.stringify([['view', 'inventory-view'], ['inventory']]));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
