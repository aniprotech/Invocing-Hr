/**
 * Stock moved by documents, on screen: a bill's goods received into stock, a
 * customer's goods returned on a credit note, goods sent back to a supplier,
 * and a recurring invoice that keeps the item it sells.
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
const text = el => (el ? el.textContent.replace(/\s+/g, ' ') : '');

const ITEMS = [
    { id: 4, code: 'BOX', name: 'Box <b>big</b>', quantity_on_hand: 10, stock_status: 'ok' },
    { id: 5, code: 'TAPE', name: 'Tape', quantity_on_hand: 2, stock_status: 'low' },
];

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url), p = full.split('?')[0], method = (init && init.method) || 'GET';
        sent.push({ url: p, full, method, body: init && init.body ? JSON.parse(init.body) : null });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (opts.reply && opts.reply[p]) { const r = opts.reply[p](init, sent); return give(r.body, r.status); }
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/inventory') return give({ items: opts.items || ITEMS, totals: {} });
        if (p === '/api/bills/9') return give({ id: 9, number: 'BILL-0009', vendor_name: 'Acme <i>x</i>', issue_date: '2026-10-01', status: 'Awaiting Payment' });
        if (p === '/api/bills/9/stock') return give({ received: opts.received || [] });
        if (p === '/api/invoices/INV-0007') return give({ number: 'INV-0007', line_items: [{ item_id: 4, qty: 3 }, { item_id: null, qty: 1 }, { item_id: 99, qty: 1 }] });
        if (method === 'POST') return give({ received: [], returned: [] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m, t) => { w._toasts = (w._toasts || []).concat([[m, t]]); };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    return { w, doc: w.document, sent };
}
const modal = doc => doc.getElementById('stock-move-modal');
const rows = doc => Array.from(doc.querySelectorAll('#stock-move-lines .stock-move-row'));
const tick = () => new Promise(r => setTimeout(r, 0));

(async () => {
    // --- a bill ----------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ received: [{ code: 'BOX', quantity: 5, moved_on: '2026-10-02' }] });
        const done = w.receiveBillStock(9);
        await tick(); await tick(); await tick();
        check('Stock in on a bill opens the form with what is tracked, names as text', modal(doc).style.display === 'flex' &&
            doc.querySelectorAll('#stock-move-lines option').length === 2 && !doc.querySelector('#stock-move-lines b') && /Box <b>big<\/b>/.test(text(doc.getElementById('stock-move-lines'))));
        check('  it asks the cost and the day, the day being the bill date', !!rows(doc)[0].querySelector('.sm-cost') && doc.getElementById('stock-move-date-wrap').style.display === '' && doc.getElementById('stock-move-date').value === '2026-10-01');
        check('  and says what was already received on it', /Already received on this bill: BOX x 5 on 2026-10-02/.test(text(doc.getElementById('stock-move-done'))));
        check('  the supplier name stays text', /Acme <i>x<\/i>/.test(text(doc.getElementById('stock-move-intro'))) && !doc.querySelector('#stock-move-intro i'));
        rows(doc)[0].querySelector('.sm-item').value = '5';
        rows(doc)[0].querySelector('.sm-qty').value = '12';
        rows(doc)[0].querySelector('.sm-cost').value = '1.5';
        doc.getElementById('stock-move-add').onclick();
        check('  Add an item adds a line', rows(doc).length === 2);
        doc.getElementById('stock-move-go').onclick();
        const ok = await done;
        const post = sent.find(s => s.method === 'POST');
        check('  Receive sends the filled lines only, with cost and day', ok === true && post.url === '/api/bills/9/receive' &&
            JSON.stringify(post.body) === JSON.stringify({ lines: [{ item_id: 5, quantity: 12, unit_cost: 1.5 }], date: '2026-10-01' }), JSON.stringify(post && post.body));
        check('  and closes, saying so', modal(doc).style.display === 'none' && (w._toasts || []).some(t => /Received into stock/.test(t[0])));
    }
    {
        const { w, doc, sent } = boot();
        const done = w.receiveBillStock(9);
        await tick(); await tick(); await tick();
        doc.getElementById('stock-move-go').onclick();
        await tick();
        check('nothing filled in is refused before it is sent', !sent.some(s => s.method === 'POST') && (w._toasts || []).some(t => /at least one item/.test(t[0])));
        doc.getElementById('stock-move-cancel').onclick();
        check('  Cancel closes it with nothing done', (await done) === false && modal(doc).style.display === 'none');
    }
    {
        let n = 0;
        const { w, doc, sent } = boot({ reply: { '/api/bills/9/receive': () => (++n === 1 ? { status: 409, body: { detail: 'Stock has already been received on bill BILL-0009.' } } : { body: { received: [] } }) } });
        const done = w.receiveBillStock(9);
        await tick(); await tick(); await tick();
        rows(doc)[0].querySelector('.sm-qty').value = '2';
        doc.getElementById('stock-move-go').onclick();
        await done;
        const posts = sent.filter(s => s.method === 'POST');
        check('a second delivery on the same bill is asked about, then sent again', posts.length === 2 && !posts[0].body.again && posts[1].body.again === true);
    }
    {
        let n = 0;
        const { w, doc, sent } = boot({ confirm: false, reply: { '/api/bills/9/receive': () => (++n, { status: 409, body: { detail: 'already' } }) } });
        w.receiveBillStock(9);
        await tick(); await tick(); await tick();
        rows(doc)[0].querySelector('.sm-qty').value = '2';
        await doc.getElementById('stock-move-go').onclick();
        check('  and saying no sends nothing more', n === 1 && modal(doc).style.display === 'flex');
    }
    {
        const { w, doc } = boot({ reply: { '/api/bills/9/receive': () => ({ status: 400, body: { detail: 'TAPE is not tracked - start tracking it first' } }) } });
        w.receiveBillStock(9);
        await tick(); await tick(); await tick();
        rows(doc)[0].querySelector('.sm-qty').value = '2';
        await doc.getElementById('stock-move-go').onclick();
        check('a refusal is said, and the form stays open', (w._toasts || []).some(t => /not tracked/.test(t[0])) && modal(doc).style.display === 'flex');
    }
    {
        const { w, doc } = boot({ items: [] });
        const ok = await w.receiveBillStock(9);
        check('with nothing tracked, it says to start tracking instead of opening', ok === false && modal(doc).style.display !== 'flex' && (w._toasts || []).some(t => /Start tracking/.test(t[0])));
    }

    // --- a customer's credit note -----------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        w.currentCreditNote = { number: 'CN-0002', invoice_number: 'INV-0007', to: 'Dee', status: 'Issued' };
        const done = w.restockCreditNote();
        await tick(); await tick(); await tick(); await tick();
        check('Return goods to stock starts from what the invoice sold of tracked items', rows(doc).length === 1 &&
            rows(doc)[0].querySelector('.sm-item').value === '4' && rows(doc)[0].querySelector('.sm-qty').value === '3' && !rows(doc)[0].querySelector('.sm-cost'));
        check('  no day and no cost asked', doc.getElementById('stock-move-date-wrap').style.display === 'none');
        rows(doc)[0].querySelector('.sm-qty').value = '1';
        doc.getElementById('stock-move-go').onclick();
        await done;
        const post = sent.find(s => s.method === 'POST');
        check('  and sends it to the credit note', post.url === '/api/credit-notes/CN-0002/restock' && JSON.stringify(post.body) === JSON.stringify({ lines: [{ item_id: 4, quantity: 1 }] }));
    }

    // --- goods back to a supplier --------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        const done = w.returnStockToSupplier(3, 'SC-1');
        await tick(); await tick();
        rows(doc)[0].querySelector('.sm-qty').value = '4';
        doc.getElementById('stock-move-go').onclick();
        await done;
        const post = sent.find(s => s.method === 'POST');
        check('Return goods on a supplier credit takes them out of stock', post.url === '/api/supplier-credit-notes/3/return-stock' && post.body.lines[0].quantity === 4 &&
            (w._toasts || []).some(t => /taken out of stock/.test(t[0])));
    }

    // --- the buttons are where they should be ------------------------------------------------------
    {
        const { w, doc } = boot();
        w.allBills = [];
        w.renderBills([{ id: 9, number: 'B1', status: 'Awaiting Payment', total: 10, amount_paid: 0, balance: 10 },
                       { id: 10, number: 'B2', status: 'Draft', total: 10, amount_paid: 0, balance: 10 },
                       { id: 11, number: 'B3', status: 'Void', total: 10, amount_paid: 0, balance: 0 }]);
        const stockBtns = Array.from(doc.querySelectorAll('[data-bill-stock]')).map(b => b.getAttribute('data-bill-stock'));
        check('only a posted bill offers Stock in', JSON.stringify(stockBtns) === '["9"]');
        let asked = null;
        w.receiveBillStock = id => { asked = id; };
        doc.querySelector('[data-bill-stock]').dispatchEvent(new w.Event('click'));
        check('  and pressing it opens the form for that bill', asked === 9);
    }
    {
        const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('a credit note has a Return goods to stock button', /id="cn-restock-btn"[^>]*onclick="restockCreditNote\(\)"/.test(html));
        const { w } = boot();
        check('the stock history names returns', w.INVENTORY_KIND ? (w.INVENTORY_KIND.return_in === 'Returned by customer' && w.INVENTORY_KIND.return_out === 'Returned to supplier')
            : /return_in: 'Returned by customer', return_out: 'Returned to supplier'/.test(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8')));
    }

    // --- a recurring invoice keeps its item ----------------------------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const fn = src.slice(src.indexOf('async function makeInvoiceRecurring'), src.indexOf('window.makeInvoiceRecurring'));
        check('Make recurring sends the item on each line', /tax_rate: tax_rate, item_id: lineItemId\(row\)/.test(fn));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
