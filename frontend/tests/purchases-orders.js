/**
 * Purchase orders.
 *
 * The figures and statuses are the server's. What the page decides: what each
 * status offers (a draft can be approved, edited or deleted; an approved one
 * billed or voided; nothing else), that the editor works the totals out as you
 * type and sends exactly what was typed, that a bad line is caught before
 * anything is sent, that a refusal is shown, and that no name becomes markup.
 */
const { boot, wait, makeChecker, appDocument, fail } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const LINES = [{ description: 'Reams of paper', qty: 10, price: 4.5, tax_rate: 20, net: 45 }, { description: 'Delivery', qty: 1, price: 5, tax_rate: 0, net: 5 }];
const mk = (id, status, extra) => Object.assign({ id, number: 'PO-000' + id, vendor_name: 'Paper Co', vendor_email: 'ap@paper.example', issue_date: '2026-11-01',
    delivery_date: '2026-11-08', reference: 'REQ-' + id, notes: '', subtotal: 50, tax_total: 9, total: 59, status, bill_number: '', lines: LINES }, extra || {});
const DRAFT = mk(1, 'Draft'), APPROVED = mk(2, 'Approved'), BILLED = mk(3, 'Billed', { bill_number: 'BILL-0007', bill_id: 7 }),
    VOID = mk(4, 'Void', { voided_on: '2026-11-04', void_reason: 'Cancelled by us' }), EVIL = mk(5, 'Draft', { vendor_name: '<b>Evil</b> Ltd' });
const ALL = [DRAFT, APPROVED, BILLED, VOID, EVIL];

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        const method = init.method || 'GET';
        if (p === '/api/tax-rates') return [{ label: 'VAT 20%', percent: 20 }, { label: 'Reduced 5%', percent: 5 }];
        if (p === '/api/bills') return [];
        if (p === '/api/purchase-orders' && method === 'GET') {
            if (opts.listFails) return fail(500, 'Server is down');
            const st = (full.match(/status=([a-z]+)/) || [])[1] || 'all';
            const q = decodeURIComponent((full.match(/[?&]q=([^&]*)/) || [])[1] || '').toLowerCase();
            let rows = ALL.filter(o => st === 'all' || o.status.toLowerCase() === st);
            if (q) rows = rows.filter(o => (o.vendor_name + o.number + o.reference).toLowerCase().includes(q));
            return { orders: rows, count: rows.length, approved_total: 59 };
        }
        if (p === '/api/purchase-orders' && method === 'POST') return opts.saveFails ? fail(400, opts.saveFails) : mk(9, 'Draft');
        const one = p.match(/^\/api\/purchase-orders\/(\d+)$/);
        if (one && method === 'GET') return ALL.find(o => o.id === +one[1]);
        if (one && method === 'PUT') return mk(+one[1], 'Draft');
        if (one && method === 'DELETE') return { message: 'Draft deleted' };
        if (/^\/api\/purchase-orders\/\d+\/bill$/.test(p)) return opts.actionFails ? fail(400, opts.actionFails) : { order: BILLED, bill_id: 7, bill_number: 'BILL-0007' };
        if (/^\/api\/purchase-orders\/\d+\/(approve|void)$/.test(p)) return opts.actionFails ? fail(400, opts.actionFails) : APPROVED;
        return undefined;
    };
}
const asking = (w, answers) => { const asked = []; w.uiForm = (f, o) => { asked.push({ fields: f, opts: o || {} }); return Promise.resolve(answers.length ? answers.shift() : null); }; return asked; };

(async () => {
    {
        const doc = appDocument();
        check('Purchase orders is in the Purchases menu', !!doc.querySelector('[data-nav-group="Purchases"] #nav-purchase-orders'));
        check('the screen, the editor and the detail exist',
            ['purchase-orders-view', 'po-tabs', 'po-search', 'po-body', 'po-modal', 'po-lines', 'po-totals', 'po-detail-modal', 'po-detail-body', 'po-detail-actions'].every(id => !!doc.getElementById(id)));
        check('tabs: all, draft, approved, billed, void', [...doc.querySelectorAll('#po-tabs .tab')].map(b => b.getAttribute('data-po-status')).join() === 'all,draft,approved,billed,void');
    }
    {
        const { w, sent } = boot(server());
        await wait(60);
        check('the address and highlight are known', w.ROUTE_SLUGS['purchase-orders-view'] === 'purchase-orders' && w.NAV_FOR_VIEW['purchase-orders-view'] === 'nav-purchase-orders');
        w.showView('purchase-orders-view');
        await wait(300);
        const doc = w.document, body = doc.getElementById('po-body');
        const rowOf = x => [...body.querySelectorAll('tr')].find(tr => tr.textContent.includes(x));
        check('it lists every order with total and status, and what is approved and unbilled',
            body.querySelectorAll('tr').length === 5 && /59\.00/.test(rowOf('PO-0002').textContent) && /approved and not yet billed/.test(doc.getElementById('po-summary').textContent));
        check('status says Draft, Approved, Billed and Void',
            /Draft/.test(rowOf('PO-0001').textContent) && /Approved/.test(rowOf('PO-0002').textContent) && /Billed/.test(rowOf('PO-0003').textContent) && /Void/.test(rowOf('PO-0004').textContent));
        check('a supplier name can never become markup', body.querySelector('b') === null && /<b>Evil<\/b> Ltd/.test(body.textContent));
        w.filterPurchaseOrders('approved', doc.querySelector('[data-po-status="approved"]'));
        await wait(300);
        check('a tab asks for that status and is lit', /status=approved/.test(sent.filter(s => s.url === '/api/purchase-orders').pop().full)
            && doc.querySelector('[data-po-status="approved"]').classList.contains('active') && !doc.querySelector('[data-po-status="all"]').classList.contains('active'));
        w.filterPurchaseOrders('all', doc.querySelector('[data-po-status="all"]'));
        doc.getElementById('po-search').value = 'zzz'; w.loadPurchaseOrders();
        await wait(300);
        check('the search is sent and an empty answer is said', /q=zzz/.test(sent.filter(s => s.url === '/api/purchase-orders').pop().full) && /No purchase order matches/.test(body.textContent));
    }

    // --- what each status offers ---------------------------------------------------------
    {
        const { w } = boot(server());
        await wait(60);
        const doc = w.document;
        const buttons = () => [...doc.querySelectorAll('#po-detail-actions button')].map(b => b.textContent.trim()).join();
        await w.openPurchaseOrder(1);
        check('a draft offers Approve, Edit and Delete', buttons() === 'Approve,Edit,Delete,Close', buttons());
        check('and shows its lines and totals', /Reams of paper/.test(doc.getElementById('po-detail-body').textContent) && /Total £59\.00/.test(doc.getElementById('po-detail-body').textContent));
        await w.openPurchaseOrder(2);
        check('an approved order offers Create bill and Void', buttons() === 'Create bill,Void,Close', buttons());
        await w.openPurchaseOrder(3);
        check('a billed order offers nothing but Close, and names its bill', buttons() === 'Close' && /BILL-0007/.test(doc.getElementById('po-detail-body').textContent));
        await w.openPurchaseOrder(4);
        check('a void order offers nothing but Close, and says why', buttons() === 'Close' && /Cancelled by us/.test(doc.getElementById('po-detail-body').textContent));
    }

    // --- the editor ------------------------------------------------------------------------
    {
        const { w, sent, toasts } = boot(server());
        await wait(60);
        const doc = w.document;
        w.showView('settings-view');          // loads the tax rates, as the real app has by now
        await wait(60);
        w.newPurchaseOrder();
        const lines = () => [...doc.querySelectorAll('#po-lines .po-line')];
        check('the editor opens with one empty line, today and a title', lines().length === 1 && doc.getElementById('po-modal').style.display === 'flex'
            && /New purchase order/.test(doc.getElementById('po-modal-title').textContent) && /^\d{4}-\d\d-\d\d$/.test(doc.getElementById('po-date').value));
        check('tax rates come from the business\'s own list, plus No tax',
            [...lines()[0].querySelector('.po-rate').options].map(o => o.value).join() === '0,20,5');
        const fill = (row, d, q, p, r) => { row.querySelector('.po-desc').value = d; row.querySelector('.po-qty').value = q; row.querySelector('.po-price').value = p; row.querySelector('.po-rate').value = r; row.dispatchEvent(new w.Event('input', { bubbles: true })); };
        fill(lines()[0], 'Reams of paper', '10', '4.5', '20');
        w.addPurchaseOrderLine();
        fill(lines()[1], 'Delivery', '1', '5', '0');
        check('the totals follow the lines as you type', /Subtotal £50\.00/.test(doc.getElementById('po-totals').textContent) && /Tax £9\.00/.test(doc.getElementById('po-totals').textContent)
            && /Total £59\.00/.test(doc.getElementById('po-totals').textContent), doc.getElementById('po-totals').textContent);
        check('each line shows its own amount', lines()[0].querySelector('.po-net').textContent === '£45.00');
        lines()[1].querySelector('.po-remove').click();
        check('a line can be removed, and the last one cannot', lines().length === 1 && (lines()[0].querySelector('.po-remove').click(), lines().length === 1));
        check('removing a line updates the totals', /Total £54\.00/.test(doc.getElementById('po-totals').textContent), doc.getElementById('po-totals').textContent);
        w.addPurchaseOrderLine(); fill(lines()[1], 'Delivery', '1', '5', '0');

        const before = sent.filter(s => s.method === 'POST').length;
        await w.savePurchaseOrder();
        check('a supplier is required, and nothing is sent without one', toasts.some(x => /Supplier name/.test(x.m)) && sent.filter(s => s.method === 'POST').length === before);
        doc.getElementById('po-vendor').value = 'Paper Co';
        fill(lines()[1], '', '1', '5', '0');
        await w.savePurchaseOrder();
        check('a line without a description is caught before sending', toasts.some(x => /Line 2 needs a description/.test(x.m)) && sent.filter(s => s.method === 'POST').length === before);
        fill(lines()[1], 'Delivery', '0', '5', '0');
        await w.savePurchaseOrder();
        check('a line with no quantity is caught too', toasts.some(x => /Line 2: the quantity/.test(x.m)) && sent.filter(s => s.method === 'POST').length === before);
        fill(lines()[1], 'Delivery', '1', '5', '0');
        doc.getElementById('po-email').value = ' ap@paper.example '; doc.getElementById('po-reference').value = ' REQ-5 '; doc.getElementById('po-delivery').value = '2026-11-08';
        await w.savePurchaseOrder();
        const post = sent.filter(s => s.method === 'POST' && s.url === '/api/purchase-orders').pop();
        const body = post && JSON.parse(post.body);
        check('Save posts exactly what was typed',
            body && body.vendor_name === 'Paper Co' && body.vendor_email === 'ap@paper.example' && body.reference === 'REQ-5' && body.delivery_date === '2026-11-08'
            && body.lines.length === 2 && body.lines[0].description === 'Reams of paper' && body.lines[0].qty === 10 && body.lines[0].price === 4.5 && body.lines[0].tax_rate === 20
            && body.lines[1].tax_rate === 0, post && post.body);
        check('and says what was created and closes the editor', toasts.some(x => /Created PO-0009/.test(x.m)) && doc.getElementById('po-modal').style.display === 'none');
    }
    {
        const { w, sent } = boot(server());
        await wait(60);
        await w.openPurchaseOrder(1);
        w.purchaseOrderAction(1, 'edit');
        const doc = w.document;
        check('Edit opens the editor filled from the draft',
            doc.getElementById('po-id').value === '1' && doc.getElementById('po-vendor').value === 'Paper Co' && doc.querySelectorAll('#po-lines .po-line').length === 2
            && doc.querySelector('#po-lines .po-rate').value === '20' && /Edit PO-0001/.test(doc.getElementById('po-modal-title').textContent)
            && doc.getElementById('po-detail-modal').style.display === 'none');
        await w.savePurchaseOrder();
        check('and saving an edit puts to that order', sent.some(s => s.method === 'PUT' && s.url === '/api/purchase-orders/1'));
    }
    {
        const { w, toasts } = boot(server({ saveFails: 'The delivery date cannot be before the order date' }));
        await wait(60);
        w.newPurchaseOrder();
        const doc = w.document;
        doc.getElementById('po-vendor').value = 'X'; doc.querySelector('.po-desc').value = 'x';
        await w.savePurchaseOrder();
        check('a refusal from the server is shown and the editor stays open',
            toasts.some(x => /delivery date cannot/.test(x.m)) && doc.getElementById('po-modal').style.display === 'flex');
    }

    // --- the actions -----------------------------------------------------------------------
    {
        const { w, sent, confirms, toasts } = boot(server());
        await wait(60);
        await w.openPurchaseOrder(1);
        await w.purchaseOrderAction(1, 'approve');
        check('Approve posts, says so, and reopens the order', sent.some(s => s.method === 'POST' && s.url === '/api/purchase-orders/1/approve')
            && toasts.some(x => /approved/.test(x.m)) && sent.filter(s => s.url === '/api/purchase-orders/1' && s.method === 'GET').length >= 2);
        await w.openPurchaseOrder(1);
        await w.purchaseOrderAction(1, 'delete');
        check('Delete asks first, then deletes and closes', confirms.length === 1 && sent.some(s => s.method === 'DELETE' && s.url === '/api/purchase-orders/1')
            && w.document.getElementById('po-detail-modal').style.display === 'none');
        await w.openPurchaseOrder(2);
        const asked = asking(w, [null, { due_days: '14' }, { due_days: 'soon' }, { reason: ' Cancelled ' }]);
        const n = sent.filter(s => s.method === 'POST').length;
        await w.purchaseOrderAction(2, 'bill');
        check('cancelling the bill form sends nothing', sent.filter(s => s.method === 'POST').length === n);
        await w.openPurchaseOrder(2);
        await w.purchaseOrderAction(2, 'bill');
        const bill = sent.filter(s => s.url === '/api/purchase-orders/2/bill').pop();
        check('Create bill posts the payment terms and names the bill', bill && JSON.parse(bill.body).due_days === 14 && toasts.some(x => /Bill BILL-0007 created/.test(x.m)), bill && bill.body);
        await w.openPurchaseOrder(2);
        await w.purchaseOrderAction(2, 'bill');
        check('terms that are not a number fall back to 30 days', JSON.parse(sent.filter(s => s.url === '/api/purchase-orders/2/bill').pop().body).due_days === 30);
        await w.openPurchaseOrder(2);
        await w.purchaseOrderAction(2, 'void');
        check('Void posts the reason', JSON.parse(sent.filter(s => s.url === '/api/purchase-orders/2/void').pop().body).reason === 'Cancelled');
    }
    {
        const { w, toasts } = boot(server({ actionFails: 'Approve the order before making a bill from it' }));
        await wait(60);
        await w.openPurchaseOrder(2);
        asking(w, [{ due_days: '30' }]);
        await w.purchaseOrderAction(2, 'bill');
        check('a refusal from an action is shown', toasts.some(x => /Approve the order/.test(x.m)));
    }
    {
        const { w } = boot(server({ listFails: true }));
        await wait(60);
        w.showView('purchase-orders-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('po-body').textContent));
    }

    t.finish('purchase orders');
})();
