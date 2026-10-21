/**
 * Supplier credit notes.
 *
 * The figures and statuses are the server's. What the page decides: which
 * actions a note offers (a used-up note offers none, a note with credit
 * applied cannot be voided), that each form sends exactly what was typed and
 * nothing when it is cancelled, that a refusal is shown, that a name can
 * never become markup, and that the detail is reopened with the new figures.
 */
const { boot, wait, makeChecker, appDocument, fail } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const OPEN = { id: 1, number: 'SCN-0001', supplier_ref: 'CN-778', vendor_name: 'Paper Co', issue_date: '2026-11-01', reason: 'Damaged', total: 36, allocated: 6, refunded: 0,
    remaining: 30, bill_number: 'B-1', status: 'Open', allocations: [{ payment_id: 21, bill_id: 1, bill_number: 'B-1', amount: 6, date: '2026-11-01' }] };
const USED = { id: 2, number: 'SCN-0002', supplier_ref: '', vendor_name: '<b>Evil</b> Ltd', issue_date: '2026-11-02', reason: '', total: 10, allocated: 10, refunded: 0,
    remaining: 0, bill_number: '', status: 'Applied', allocations: [{ payment_id: 22, bill_id: 2, bill_number: 'B-2', amount: 10, date: '2026-11-02' }] };
const FRESH = { id: 3, number: 'SCN-0003', supplier_ref: '', vendor_name: 'Tea Ltd', issue_date: '2026-11-03', reason: '', total: 5, allocated: 0, refunded: 0,
    remaining: 5, bill_number: '', status: 'Open', allocations: [] };
const VOID = { id: 4, number: 'SCN-0004', vendor_name: 'Gone', total: 1, allocated: 0, refunded: 0, remaining: 1, status: 'Void', voided_on: '2026-11-04', void_reason: 'Twice', allocations: [] };
const ALL = [OPEN, USED, FRESH, VOID];
const BILLS = [
    { id: 1, number: 'B-1', vendor_name: 'Paper Co', total: 100, amount_paid: 6, status: 'Partially Paid' },
    { id: 2, number: 'B-2', vendor_name: 'Tea Ltd', total: 50, amount_paid: 50, status: 'Paid' },
    { id: 3, number: 'B-3', vendor_name: 'Tea Ltd', total: 20, amount_paid: 0, status: 'Unpaid' },
    { id: 4, number: 'B-4', vendor_name: 'Paper Co', total: 15, amount_paid: 0, status: 'Draft' },
];

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        const method = init.method || 'GET';
        if (p === '/api/bills' && method === 'GET') return BILLS;
        if (p === '/api/supplier-credit-notes' && method === 'GET') {
            if (opts.listFails) return fail(500, 'Server is down');
            const st = (full.match(/status=([a-z]+)/) || [])[1] || 'all';
            const q = decodeURIComponent((full.match(/[?&]q=([^&]*)/) || [])[1] || '').toLowerCase();
            let rows = ALL.filter(n => st === 'all' || n.status.toLowerCase() === st);
            if (q) rows = rows.filter(n => (n.vendor_name + n.number).toLowerCase().includes(q));
            return { credit_notes: rows, count: rows.length, open_total: 35 };
        }
        if (p === '/api/supplier-credit-notes' && method === 'POST') return opts.createFails ? fail(400, opts.createFails) : Object.assign({}, FRESH, { number: 'SCN-0009' });
        const one = p.match(/^\/api\/supplier-credit-notes\/(\d+)$/);
        if (one && method === 'GET') return ALL.find(n => n.id === +one[1]);
        if (/^\/api\/supplier-credit-notes\/\d+\/(allocate|refund|void)$/.test(p) || /\/allocations\/\d+$/.test(p)) {
            return opts.actionFails ? fail(400, opts.actionFails) : ALL.find(n => n.id === 1);
        }
        return undefined;
    };
}

function asking(w, answers) {
    const asked = [];
    w.uiForm = (fields, o) => { asked.push({ fields, opts: o || {} }); return Promise.resolve(answers.length ? answers.shift() : null); };
    return asked;
}

(async () => {
    {
        const doc = appDocument();
        check('Supplier credit notes is in the Purchases menu, with a different name from Sales credit notes',
            !!doc.querySelector('[data-nav-group="Purchases"] #nav-supplier-credit-notes') && !!doc.querySelector('[data-nav-group="Sales"] #nav-credit-notes')
            && doc.getElementById('nav-supplier-credit-notes').textContent.trim() !== doc.getElementById('nav-credit-notes').textContent.trim());
        check('the screen has tabs, a search, a table and a detail panel',
            ['scn-tabs', 'scn-search', 'scn-body', 'scn-detail-modal', 'scn-detail-body', 'scn-detail-actions'].every(id => !!doc.getElementById(id)));
        const tabs = [...doc.querySelectorAll('#scn-tabs .tab')].map(b => b.getAttribute('data-scn-status'));
        check('tabs: all, open, used up, void', tabs.join() === 'all,open,applied,void', tabs.join());
    }
    {
        const { w, sent } = boot(server());
        await wait(60);
        check('the address and highlight are known',
            w.ROUTE_SLUGS['supplier-credit-notes-view'] === 'supplier-credit-notes' && w.NAV_FOR_VIEW['supplier-credit-notes-view'] === 'nav-supplier-credit-notes');
        w.showView('supplier-credit-notes-view');
        await wait(300);
        const doc = w.document;
        const body = doc.getElementById('scn-body');
        const rowOf = x => [...body.querySelectorAll('tr')].find(tr => tr.textContent.includes(x));
        check('it lists every note with its balance and a summary of what is still to use',
            body.querySelectorAll('tr').length === 4 && /still to use/.test(doc.getElementById('scn-summary').textContent) && /35\.00/.test(doc.getElementById('scn-summary').textContent));
        check('status says Open, Used up and Void', /Open/.test(rowOf('SCN-0001').textContent) && /Used up/.test(rowOf('SCN-0002').textContent) && /Void/.test(rowOf('SCN-0004').textContent));
        check('a supplier name can never become markup', body.querySelector('b') === null && /<b>Evil<\/b> Ltd/.test(body.textContent));

        // tabs and search ask the server
        w.filterSupplierCreditNotes('open', doc.querySelector('[data-scn-status="open"]'));
        await wait(300);
        check('a tab asks for that status, and is lit',
            /status=open/.test(sent.filter(s => s.url === '/api/supplier-credit-notes').pop().full) && doc.querySelector('[data-scn-status="open"]').classList.contains('active')
            && !doc.querySelector('[data-scn-status="all"]').classList.contains('active'));
        doc.getElementById('scn-search').value = 'tea';
        w.loadSupplierCreditNotes();
        await wait(300);
        check('the search is sent', /q=tea/.test(sent.filter(s => s.url === '/api/supplier-credit-notes').pop().full));
        w.filterSupplierCreditNotes('all', doc.querySelector('[data-scn-status="all"]'));
        doc.getElementById('scn-search').value = 'zzz';
        w.loadSupplierCreditNotes();
        await wait(300);
        check('and says when nothing matches', /No credit note matches/.test(body.textContent));
    }

    // --- the detail and what it offers ----------------------------------------------
    {
        const { w } = boot(server());
        await wait(60);
        const doc = w.document;
        const buttons = () => [...doc.querySelectorAll('#scn-detail-actions button')].map(b => b.textContent.trim());
        await w.openSupplierCreditNote(1);
        check('a note with credit left offers to set it against a bill and to record a refund; not Void while some is applied',
            buttons().includes('Set against a bill') && buttons().includes('Record a refund') && !buttons().includes('Void'), buttons().join());
        check('it shows the figures and the bills it was taken off, with Take off',
            /30\.00/.test(doc.getElementById('scn-detail-body').textContent) && /B-1/.test(doc.getElementById('scn-detail-body').textContent)
            && doc.querySelectorAll('#scn-detail-body [data-scn-unallocate]').length === 1);
        await w.openSupplierCreditNote(2);
        check('a used-up note offers nothing but Close', buttons().join() === 'Close', buttons().join());
        await w.openSupplierCreditNote(3);
        check('an untouched note can also be voided', buttons().includes('Void'));
        await w.openSupplierCreditNote(4);
        check('a void note offers nothing but Close, and says why it was voided', buttons().join() === 'Close' && /Twice/.test(doc.getElementById('scn-detail-body').textContent));
    }

    // --- create ---------------------------------------------------------------------
    {
        const { w, sent, toasts } = boot(server());
        await wait(60);
        const asked = asking(w, [null, { bill_id: '3', vendor_name: ' ', amount: '12.5', tax_amount: '2.5', supplier_ref: ' CN-9 ', issue_date: '2026-11-05', reason: 'Wrong price', apply_to_bill: 'no' }]);
        const before = sent.length;
        await w.newSupplierCreditNote();
        check('cancelling the form sends nothing', !sent.slice(before).some(s => s.method === 'POST'));
        const bills = asked[0].fields.find(f => f.name === 'bill_id').options;
        check('the form offers only bills that still owe something',
            bills.map(o => o.value).join() === ',1,3', bills.map(o => o.value).join());
        await w.newSupplierCreditNote();
        const post = sent.filter(s => s.method === 'POST' && s.url === '/api/supplier-credit-notes').pop();
        const body = post && JSON.parse(post.body);
        check('Save posts exactly what was typed',
            body && body.bill_id === 3 && body.amount === 12.5 && body.tax_amount === 2.5 && body.supplier_ref === 'CN-9' && body.vendor_name === ''
            && body.issue_date === '2026-11-05' && body.reason === 'Wrong price' && body.apply_to_bill === false, post && post.body);
        check('and says what was recorded', toasts.some(x => /SCN-0009 recorded/.test(x.m)));
        asking(w, [{ bill_id: '', vendor_name: 'X', amount: '0' }]);
        const n = sent.filter(s => s.method === 'POST').length;
        await w.newSupplierCreditNote();
        check('an amount is required and nothing is sent without one',
            toasts.some(x => /more than nothing/.test(x.m)) && sent.filter(s => s.method === 'POST').length === n);
    }
    {
        const { w, toasts } = boot(server({ createFails: 'Supplier name is required' }));
        await wait(60);
        asking(w, [{ bill_id: '', vendor_name: '', amount: '5' }]);
        await w.newSupplierCreditNote();
        check('a refusal from the server is shown', toasts.some(x => /Supplier name is required/.test(x.m)));
    }

    // --- allocate, refund, void, take off ------------------------------------------------------
    {
        const { w, sent, confirms, toasts } = boot(server());
        await wait(60);
        await w.openSupplierCreditNote(1);
        const asked = asking(w, [{ bill_id: '1', amount: '10' }, { amount: '5', date: '2026-11-06', method: 'cheque', reference: ' RF-1 ' }, { reason: ' Entered twice ' }]);
        await w.allocateSupplierCredit(1);
        const options = asked[0].fields.find(f => f.name === 'bill_id').options;
        check('allocation lists bills that still owe, the same supplier first',
            options.map(o => o.value).join() === '1,3', options.map(o => o.value).join());
        check('and starts from what is left on the note', asked[0].fields.find(f => f.name === 'amount').value === '30');
        const alloc = sent.filter(s => s.url === '/api/supplier-credit-notes/1/allocate').pop();
        check('allocate posts the bill and amount', alloc && JSON.parse(alloc.body).bill_id === 1 && JSON.parse(alloc.body).amount === 10, alloc && alloc.body);
        check('and the detail is opened again with the new figures', sent.filter(s => s.url === '/api/supplier-credit-notes/1' && s.method === 'GET').length >= 2);
        await w.refundSupplierCredit(1);
        const refund = JSON.parse(sent.filter(s => s.url === '/api/supplier-credit-notes/1/refund').pop().body);
        check('refund posts what was typed', refund.amount === 5 && refund.date === '2026-11-06' && refund.method === 'cheque' && refund.reference === 'RF-1', JSON.stringify(refund));
        await w.voidSupplierCredit(3);
        const voided = sent.filter(s => s.url === '/api/supplier-credit-notes/3/void').pop();
        check('void posts the reason', voided && JSON.parse(voided.body).reason === 'Entered twice');
        asking(w, []);
        const n = sent.length;
        await w.refundSupplierCredit(1);
        check('cancelling a form sends nothing', sent.length === n);
        await w.unallocateSupplierCredit(1, 21);
        check('Take off asks first, then deletes that credit',
            confirms.length === 1 && sent.some(s => s.method === 'DELETE' && s.url === '/api/supplier-credit-notes/1/allocations/21'));
    }
    {
        const { w, toasts } = boot(server({ actionFails: 'Only 30.00 of this credit note is left' }));
        await wait(60);
        await w.openSupplierCreditNote(1);
        asking(w, [{ amount: '99' }]);
        await w.refundSupplierCredit(1);
        check('a refusal from an action is shown', toasts.some(x => /Only 30.00/.test(x.m)));
    }
    {
        const { w } = boot(server({ listFails: true }));
        await wait(60);
        w.showView('supplier-credit-notes-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('scn-body').textContent));
    }

    t.finish('supplier credit notes');
})();
