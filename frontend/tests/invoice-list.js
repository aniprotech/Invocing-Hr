/**
 * The invoice list at scale: a page comes from the server with the whole
 * match summed; tabs, search (debounced), sort and Load more ask again;
 * ticks bring up a bulk bar that posts one action for all of them and
 * says which could not be done; Export CSV opens the match as a file.
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

function item(n, extra) {
    return Object.assign({ number: 'INV-' + String(n).padStart(4, '0'), ref: '', to: 'Customer <b>' + n + '</b>', email: '', date: '2026-09-0' + (n % 9 + 1), due_date: '2026-09-30', paid: 0, due: 100 * n, total: 100 * n,
        status: 'Awaiting Payment', sent: '', currency: 'GBP', open_count: 0, last_opened: '', is_overdue: false, days_overdue: 0 }, extra || {});
}
const PAGE1 = { items: [item(1), item(2, { is_overdue: true, days_overdue: 9 }), item(3)], total: 5, offset: 0, limit: 3, summary: { count: 5, owed: 1500, overdue_owed: 200, overdue_count: 1, paid: 0 }, currency: 'GBP' };
const PAGE2 = { items: [item(4), item(5, { status: 'Draft' })], total: 5, offset: 3, limit: 3, summary: PAGE1.summary, currency: 'GBP' };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const qs = Object.fromEntries(new w.URLSearchParams(full.split('?')[1] || ''));
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, qs, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/invoice-list') return give(qs.offset === '3' ? PAGE2 : PAGE1);
        if (p === '/api/invoice-list/bulk') return give(opts.bulk || { done: ['INV-0001'], failed: [{ number: 'INV-0003', why: 'Invoice has no email address' }], message: '1 done, 1 could not be' });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    w.uiAlert = (m) => { w._alerted = m; return Promise.resolve(true); };
    w.open = (u) => { w._opened = u; };
    w._invList.limit = 3;
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the list has a select-all box, sortable headers, a bulk bar, a summary foot, Load more and Export CSV',
            /id="invoice-pick-all"/.test(src) && /data-inv-sort="customer"/.test(src) && /id="invoice-bulk-bar"/.test(src) && /id="invoice-list-summary"/.test(src) && /id="invoice-load-more"/.test(src) && /exportInvoicesCsv\(\)/.test(src) && /filterInvoices\('unpaid'/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        await w.fetchInvoices();
        await wait(30);
        const first = sent.find(s => s.url === '/api/invoice-list');
        check('the list asks the server for a page, newest first', first && first.qs.status === 'all' && first.qs.sort === 'number' && first.qs.dir === 'desc' && first.qs.limit === '3' && first.qs.offset === '0', JSON.stringify(first && first.qs));
        const rows = doc.querySelectorAll('#invoices-table-body tr');
        check('  one row per item with a tick box, names as text, the overdue one flagged', rows.length === 3 && rows[0].querySelector('[data-inv-pick="INV-0001"]') && /Customer <b>1<\/b>/.test(rows[0].textContent) && !doc.getElementById('invoices-table-body').querySelector('b') && /9 days overdue/.test(rows[1].innerHTML));
        check('  the count says how many of the whole match are shown, the foot what it adds up to, and Load more is offered',
            /3 of 5 items/.test(doc.getElementById('invoice-count').textContent) && /1,500\.00 owed/.test(doc.getElementById('invoice-list-summary').textContent) && /200\.00 overdue on 1 invoice/.test(doc.getElementById('invoice-list-summary').textContent) && doc.getElementById('invoice-load-more').style.display !== 'none');
        await w.fetchInvoices(true);
        await wait(30);
        const more = sent.filter(s => s.url === '/api/invoice-list').pop();
        check('Load more asks for the next page and appends it', more.qs.offset === '3' && doc.querySelectorAll('#invoices-table-body tr').length === 5 && doc.getElementById('invoice-load-more').style.display === 'none' && /^5 items/.test(doc.getElementById('invoice-count').textContent));
        w.filterInvoices('overdue', null);
        await wait(30);
        check('a tab asks the server with that status, from the first page', sent.filter(s => s.url === '/api/invoice-list').pop().qs.status === 'overdue' && sent.filter(s => s.url === '/api/invoice-list').pop().qs.offset === '0');
        w.filterInvoices('awaiting payment', null);
        await wait(30);
        check('  spaces in a status become hyphens', sent.filter(s => s.url === '/api/invoice-list').pop().qs.status === 'awaiting-payment');
        doc.getElementById('invoice-search').value = 'acme';
        w.searchInvoices();
        w.searchInvoices();
        await wait(320);
        const searches = sent.filter(s => s.url === '/api/invoice-list' && s.qs.q === 'acme');
        check('search waits for typing to stop, then asks once', searches.length === 1, searches.length);
        w.sortInvoices('customer');
        await wait(30);
        let last = sent.filter(s => s.url === '/api/invoice-list').pop();
        check('a header sorts by it, names ascending first', last.qs.sort === 'customer' && last.qs.dir === 'asc');
        w.sortInvoices('customer');
        await wait(30);
        last = sent.filter(s => s.url === '/api/invoice-list').pop();
        check('  and again flips it', last.qs.dir === 'desc' && /To ▼/.test(doc.querySelector('[data-inv-sort="customer"]').textContent));
        w.exportInvoicesCsv();
        check('Export CSV opens the match as a file with the same filters and no paging', /^\/api\/invoice-list\.csv\?/.test(w._opened) && /status=awaiting-payment/.test(w._opened) && /q=acme/.test(w._opened) && /sort=customer/.test(w._opened) && !/limit=/.test(w._opened), w._opened);
    }
    {
        const { w, doc, sent } = boot();
        await w.fetchInvoices();
        await wait(30);
        check('nothing ticked, no bulk bar', doc.getElementById('invoice-bulk-bar').style.display === 'none');
        const box = doc.querySelector('[data-inv-pick="INV-0001"]');
        box.checked = true;
        box.dispatchEvent(new w.Event('change', { bubbles: true }));
        check('one tick brings up the bar with the count', doc.getElementById('invoice-bulk-bar').style.display === 'flex' && doc.getElementById('invoice-bulk-count').textContent === '1 selected');
        w.toggleAllInvoices(true);
        check('  select all ticks the page', doc.getElementById('invoice-bulk-count').textContent === '3 selected');
        w.toggleAllInvoices(false);
        check('  clear empties it', doc.getElementById('invoice-bulk-bar').style.display === 'none');
        box.checked = true;
        box.dispatchEvent(new w.Event('change', { bubbles: true }));
        doc.querySelector('[data-inv-pick="INV-0003"]').checked = true;
        doc.querySelector('[data-inv-pick="INV-0003"]').dispatchEvent(new w.Event('change', { bubbles: true }));
        await w.bulkInvoices('send');
        await wait(40);
        const bulk = sent.find(s => s.url === '/api/invoice-list/bulk');
        check('a bulk action asks, then posts the ticked numbers and the action', bulk && bodyOf(bulk).action === 'send' && JSON.stringify(bodyOf(bulk).numbers) === '["INV-0001","INV-0003"]', bulk && bulk.body);
        check('  what could not be done is shown, and the list reloads with nothing ticked', /INV-0003: Invoice has no email address/.test(w._alerted) && doc.getElementById('invoice-bulk-bar').style.display === 'none' && sent.filter(s => s.url === '/api/invoice-list').length >= 2);
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.fetchInvoices();
        await wait(30);
        w.toggleAllInvoices(true);
        await w.bulkInvoices('delete_drafts');
        check('backing out of the question does nothing', !sent.some(s => s.url === '/api/invoice-list/bulk'));
        await w.bulkInvoices('burn');
        check('an unknown action does nothing', !sent.some(s => s.url === '/api/invoice-list/bulk'));
    }
    console.log(failures === 0 ? '\nAll invoice-list checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
