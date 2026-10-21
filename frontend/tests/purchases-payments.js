/**
 * Paying supplier bills, and the Payments list.
 *
 * The totals and statuses are the server's. What the page decides: that Pay
 * opens a form (part or all) rather than paying in one click, that the form
 * sends exactly what was typed, that a refusal is shown and nothing is lost,
 * that a payment can be removed but a credit note cannot be from here, that
 * the list asks for what the filters say, and that no name becomes markup.
 */
const { boot, wait, makeChecker, appDocument, fail } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const BILLS = [
    { id: 1, number: 'B-1', vendor_name: 'Paper Co', total: 100, amount_paid: 40, status: 'Partially Paid', due_date: '2026-12-01', issue_date: '2026-11-01' },
    { id: 2, number: 'B-2', vendor_name: 'Tea Ltd', total: 50, amount_paid: 50, status: 'Paid', due_date: '2026-12-01', issue_date: '2026-11-01' },
];
const LEDGER = { total: 100, paid: 40, outstanding: 60, payments: [
    { id: 11, bill_id: 1, amount: 40, paid_on: '2026-11-10', method: 'card', reference: 'VISA-9', account: '' },
    { id: 12, bill_id: 1, amount: 0, paid_on: '2026-11-11', method: 'credit_note', reference: 'CN-1', account: '' },
] };
const LIST = { count: 2, total: 90, payments: [
    { id: 11, bill_id: 1, bill_number: 'B-1', supplier: '<b>Evil</b> Co', amount: 40, paid_on: '2026-11-10', method: 'card', reference: 'VISA-9', account: 'Current' },
    { id: 12, bill_id: 2, bill_number: 'B-2', supplier: 'Tea Ltd', amount: 50, paid_on: '2026-11-09', method: 'credit_note', reference: 'CN-1', account: '' },
] };

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        const method = init.method || 'GET';
        if (p === '/api/bills' && method === 'GET') return BILLS;
        if (p === '/api/bills/1/payments' && method === 'GET') return LEDGER;
        if (p === '/api/bills/1/payments' && method === 'POST') return opts.payFails ? fail(400, opts.payFails) : { status: 'Paid', outstanding: 0 };
        if (/^\/api\/bills\/1\/payments\/\d+$/.test(p) && method === 'DELETE') return { status: 'Unpaid' };
        if (/^\/api\/bills\/\d+\/payments\/\d+$/.test(p) && method === 'DELETE') return {};
        if (p === '/api/accounts') return { accounts: [{ id: 3, name: 'Current account', active: true, is_default: true }, { id: 4, name: 'Old', active: false }] };
        if (p === '/api/bill-payments') return opts.listFails ? fail(500, 'Server is down') : LIST;
        return undefined;
    };
}

(async () => {
    {
        const doc = appDocument();
        const inGroup = id => !!doc.querySelector('[data-nav-group="Purchases"] #' + id);
        check('Payments is in the Purchases menu', inGroup('nav-bill-payments'));
        check('and has a list, filters and a CSV link',
            ['bill-payments-view', 'bill-payments-body', 'bill-payments-search', 'bill-payments-from', 'bill-payments-to', 'bill-payments-method', 'bill-payments-csv', 'bill-payment-modal']
                .every(id => !!doc.getElementById(id)));
    }
    {
        const { w, sent, toasts, confirms } = boot(server());
        await wait(60);
        check('the address and highlight are known',
            w.ROUTE_SLUGS['bill-payments-view'] === 'bill-payments' && w.NAV_FOR_VIEW['bill-payments-view'] === 'nav-bill-payments');

        // Pay opens a form; it does not pay
        w.showView('bills-view');
        await wait(60);
        const before = sent.length;
        const rows = [...w.document.querySelectorAll('#bills-table-body tr')];
        const payOf = number => rows.find(tr => tr.textContent.includes(number)).querySelector('[data-bill-pay]');
        check('a part-paid bill offers Pay and a paid one does not', !!payOf('B-1') && !payOf('B-2'));
        check('Pay goes to the form, not straight to paying', payOf('B-1').getAttribute('data-bill-pay') === '1' && /return openBillPaymentModal\(id\)/.test(String(w.markBillPaid)));
        await w.markBillPaid(1);
        await wait(80);
        const doc = w.document;
        check('Pay opens the form and pays nothing yet',
            doc.getElementById('bill-payment-modal').style.display === 'flex'
            && !sent.slice(before).some(s => s.method === 'POST' || s.method === 'DELETE'));
        check('the form is filled with what is still owed, and says the totals',
            doc.getElementById('bp-amount').value === '60.00' && /still owed/.test(doc.getElementById('bp-summary').textContent)
            && /Pay B-1/.test(doc.getElementById('bill-payment-title').textContent));
        check('the default account is chosen and closed ones are not offered',
            doc.getElementById('bp-account').value === '3' && ![...doc.getElementById('bp-account').options].some(o => /Old/.test(o.textContent)));
        check('payments so far are listed; a credit note has no Remove',
            /VISA-9/.test(doc.getElementById('bp-history').textContent)
            && doc.querySelectorAll('#bp-history [data-bp-remove]').length === 1);

        doc.getElementById('bp-amount').value = '0';
        const n = sent.length;
        await w.saveBillPayment();
        check('an amount is required and nothing is sent without one',
            toasts.some(x => /more than nothing/.test(x.m)) && sent.length === n);
        doc.getElementById('bp-amount').value = '25.5';
        doc.getElementById('bp-method').value = 'cheque';
        doc.getElementById('bp-reference').value = ' CHQ-77 ';
        await w.saveBillPayment();
        const post = sent.filter(s => s.method === 'POST' && s.url === '/api/bills/1/payments').pop();
        const body = post && JSON.parse(post.body);
        check('Save posts exactly what was typed',
            body && body.amount === 25.5 && body.method === 'cheque' && body.reference === 'CHQ-77' && body.account_id === 3 && /^\d{4}-\d\d-\d\d$/.test(body.paid_on),
            post && post.body);
        check('and closes the form', doc.getElementById('bill-payment-modal').style.display === 'none');

        // remove from the form
        await w.openBillPaymentModal(1);
        doc.querySelector('#bp-history [data-bp-remove]').click();
        await wait(60);
        check('Remove asks first, then deletes that payment',
            confirms.length === 1 && sent.some(s => s.method === 'DELETE' && s.url === '/api/bills/1/payments/11'));
    }
    {
        const { w, toasts } = boot(server({ payFails: 'A payment of 99.00 is more than the 60.00 still owed' }));
        await wait(60);
        w.showView('bills-view');
        await wait(60);
        await w.openBillPaymentModal(1);
        w.document.getElementById('bp-amount').value = '99';
        await w.saveBillPayment();
        check('a refusal from the server is shown and the form stays open',
            toasts.some(x => /more than the 60/.test(x.m)) && w.document.getElementById('bill-payment-modal').style.display === 'flex');
    }

    // --- the Payments list ---------------------------------------------------------
    {
        const { w, sent, confirms } = boot(server());
        await wait(60);
        w.showView('bill-payments-view');
        await wait(300);
        const doc = w.document;
        const body = doc.getElementById('bill-payments-body');
        check('the list asks the server and shows the summary',
            sent.some(s => s.url === '/api/bill-payments') && /2 payments/.test(doc.getElementById('bill-payments-summary').textContent)
            && /90\.00/.test(doc.getElementById('bill-payments-summary').textContent));
        check('a supplier name can never become markup', body.querySelector('b') === null && /<b>Evil<\/b> Co/.test(body.textContent));
        check('method and account are shown', /Card/.test(body.textContent) && /Current/.test(body.textContent) && /Credit note/.test(body.textContent));
        check('a credit note payment has no Remove; the others do', body.querySelectorAll('[data-bp-del]').length === 1);
        doc.getElementById('bill-payments-search').value = 'visa';
        doc.getElementById('bill-payments-from').value = '2026-11-01';
        doc.getElementById('bill-payments-method').value = 'card';
        w.loadBillPayments();
        await wait(300);
        const last = sent.filter(s => s.url === '/api/bill-payments').pop();
        check('the filters are sent', /q=visa/.test(last.full) && /start=2026-11-01/.test(last.full) && /method=card/.test(last.full), last.full);
        check('and the CSV link carries the same filters', /\/api\/bill-payments\.csv\?/.test(doc.getElementById('bill-payments-csv').getAttribute('href'))
            && /q=visa/.test(doc.getElementById('bill-payments-csv').getAttribute('href')));
        body.querySelector('[data-bp-del]').click();
        await wait(60);
        check('Remove on the list asks, then deletes',
            confirms.length === 1 && sent.some(s => s.method === 'DELETE' && s.url === '/api/bills/1/payments/11'));
    }
    {
        const { w } = boot(server({ listFails: true }));
        await wait(60);
        w.showView('bill-payments-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('bill-payments-body').textContent));
    }

    t.finish('purchases payments');
})();
