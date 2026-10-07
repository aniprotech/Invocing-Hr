/**
 * Inventory, under Sales.
 *
 * The screen asks the server what is held and shows it; every number is the
 * server's, and nothing is worked out here. So the things worth pinning are the
 * ones the page does decide: that it asks for what the tab says, that a row
 * offers only what is true of it (an untracked item can be started, not
 * received), that each action sends exactly what was typed and nothing when it
 * is cancelled, that an item's name can never become markup - and, on the
 * invoice itself, that a line remembers the item it was picked from, shows
 * what is in stock, and forgets the link the moment the box is retyped.
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

const WIDGET = { id: 11, code: 'WID', name: 'Widget', sale_price: 10, purchase_price: 4, track_inventory: true,
    quantity_on_hand: 12, reorder_level: 5, average_cost: 4, stock_value: 48, stock_status: 'ok', is_active: true };
const LOW = { id: 12, code: 'BOLT', name: 'Bolt', sale_price: 1, purchase_price: 0.5, track_inventory: true,
    quantity_on_hand: 3, reorder_level: 5, average_cost: 0.5, stock_value: 1.5, stock_status: 'low', is_active: true };
const OUT = { id: 13, code: 'NUT', name: 'Nut', sale_price: 1, purchase_price: 0.2, track_inventory: true,
    quantity_on_hand: 0, reorder_level: 0, average_cost: 0.2, stock_value: 0, stock_status: 'out', is_active: true };
const OVER = { id: 14, code: 'WASHER', name: 'Washer', sale_price: 1, purchase_price: 0.1, track_inventory: true,
    quantity_on_hand: -2, reorder_level: 0, average_cost: 0.1, stock_value: 0, stock_status: 'over', is_active: true };
const PLAIN = { id: 15, code: 'CONSULT', name: 'Consulting', sale_price: 100, purchase_price: 0, track_inventory: false,
    quantity_on_hand: 0, reorder_level: 0, average_cost: 0, stock_value: 0, stock_status: 'untracked', is_active: true };
const EVIL = { id: 16, code: '<img src=x onerror=alert(1)>', name: '<b>bold</b>', sale_price: 1, purchase_price: 0,
    track_inventory: true, quantity_on_hand: 1, reorder_level: 0, average_cost: 0, stock_value: 0, stock_status: 'ok', is_active: true };

const TOTALS = { tracked: 4, untracked: 1, stock_value: 49.5, low: 1, out: 1, over: 1 };

const MOVES = [
    { id: 6, kind: 'adjustment', quantity: -2, affects_stock: true, unit_cost: 4, balance_after: 12, invoice_number: '', reason: 'damaged', note: 'Water', moved_on: '2026-10-05' },
    { id: 5, kind: 'sale_reversal', quantity: 3, affects_stock: true, unit_cost: 4, balance_after: 14, invoice_number: 'INV-0008', reason: '', note: '', moved_on: '2026-10-04' },
    { id: 4, kind: 'sale', quantity: -3, affects_stock: true, unit_cost: 4, balance_after: 11, invoice_number: 'INV-0008', reason: '', note: 'Invoice INV-0008', moved_on: '2026-10-03' },
    { id: 3, kind: 'baseline', quantity: -5, affects_stock: false, unit_cost: 4, balance_after: 14, invoice_number: 'INV-0001', reason: '', note: 'Out before tracking started', moved_on: '2026-10-02' },
    { id: 2, kind: 'received', quantity: 4, affects_stock: true, unit_cost: 4, balance_after: 14, invoice_number: '', reason: '', note: 'Delivery 88', moved_on: '2026-10-01' },
    { id: 1, kind: 'opening', quantity: 10, affects_stock: true, unit_cost: 4, balance_after: 10, invoice_number: '', reason: '', note: '', moved_on: '2026-09-30' },
];

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
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
    const items = opts.items || [WIDGET, LOW, OUT, OVER, PLAIN];
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, full, method, body: init && init.body });
        if (p === '/api/auth/me') return reply(200, { user: { email: 'me@x' }, client_id: 1 });
        if (p === '/api/client/me') return reply(200, { id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/inventory') {
            if (opts.inventoryFails) return reply(500, { detail: 'Server is down' });
            const view = (full.match(/view=([a-z]+)/) || [])[1] || 'tracked';
            const q = decodeURIComponent((full.match(/[?&]q=([^&]*)/) || [])[1] || '').toLowerCase();
            let shown = items.filter(i => view === 'all' || (view === 'tracked' && i.track_inventory)
                || (view === 'untracked' && !i.track_inventory) || (view === 'low' && ['low', 'out', 'over'].includes(i.stock_status))
                || (view === 'out' && ['out', 'over'].includes(i.stock_status)));
            if (q) shown = shown.filter(i => (i.code + ' ' + i.name).toLowerCase().includes(q));
            return reply(200, { items: shown, shown: shown.length, totals: opts.totals || TOTALS, view, currency: 'GBP' });
        }
        if (/^\/api\/inventory\/\d+\/movements$/.test(p)) {
            return reply(200, { item: WIDGET, movements: opts.noMoves ? [] : MOVES });
        }
        if (/^\/api\/inventory\/\d+\/(receive|count|track)$/.test(p)) {
            if (opts.actionFails) return reply(400, { detail: opts.actionFails });
            return reply(200, WIDGET);
        }
        if (/^\/api\/items\/\d+$/.test(p) && method === 'PUT') return reply(200, WIDGET);
        if (p === '/api/items' && method === 'POST') {
            if (opts.createFails) return reply(400, { detail: opts.createFails });
            return reply(200, Object.assign({ id: 99 }, JSON.parse(init.body)));
        }
        if (p === '/api/items') return reply(200, { items: opts.lookup || items });
        if (p === '/api/invoices' && method === 'POST') return reply(200, { number: 'INV-0042' });
        if (/^\/api\/invoices\/[^/]+$/.test(p) && method === 'GET') return reply(200, opts.invoice || {});
        if (p === '/api/next-invoice-number') return reply(200, { number: 'INV-0042' });
        return reply(200, p.endsWith('s') ? [] : {});
    };

    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    const asked = [];
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    // The questions are answered by the test, and recorded, instead of drawn.
    w.uiForm = (fields, o) => { asked.push({ fields, opts: o || {} }); return Promise.resolve(opts.answer === undefined ? null : opts.answer); };
    const toasts = [];
    w.showToast = (m, k) => toasts.push({ m, k });
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent, asked, toasts };
}

const tbody = w => w.document.getElementById('inventory-table-body');
const rowFor = (w, code) => [...tbody(w).querySelectorAll('tr')].find(tr => tr.textContent.includes(code));
const btn = (row, act) => row.querySelector(`[data-inv-act="${act}"]`);

(async () => {
    // --- the markup ---------------------------------------------------------------
    {
        const doc = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
        const link = doc.getElementById('nav-inventory');
        check('Inventory is in the Sales menu', !!link && !!link.closest('[data-nav-group="Sales"]'));
        check('  on the invoicing plan, at its own address', link.getAttribute('data-portal') === 'invoicing' && link.getAttribute('href') === '#/inventory');
        check('the screen has tiles, tabs, a search, a table and a history panel',
            ['inventory-tiles', 'inventory-tabs', 'inventory-search', 'inventory-table-body', 'inventory-history'].every(id => !!doc.getElementById(id)));
        check('and a way to export the valuation and to add an item',
            /downloadInventoryCsv/.test(doc.getElementById('inventory-view').innerHTML) && /newInventoryItem/.test(doc.getElementById('inventory-view').innerHTML));
        const tabs = [...doc.querySelectorAll('#inventory-tabs .tab')].map(b => b.getAttribute('data-inv-view'));
        check('tabs: tracked, low, out of stock, not tracked, all', tabs.join() === 'tracked,low,out,untracked,all', tabs.join());
    }

    {
        const { w } = boot();
        await wait(80);
        check('the address is /inventory and lights up its menu entry',
            w.ROUTE_SLUGS['inventory-view'] === 'inventory' && w.VIEW_FOR_SLUG['inventory'] === 'inventory-view'
            && w.NAV_FOR_VIEW['inventory-view'] === 'nav-inventory');
    }

    // --- opening it -----------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        sent.length = 0;
        w.showView('inventory-view');
        await wait(120);
        const ask = sent.find(s => s.url === '/api/inventory');
        check('opening it asks the server for the tracked items, by GET', !!ask && ask.method === 'GET' && /view=tracked/.test(ask.full), ask && ask.full);
        const tiles = w.document.getElementById('inventory-tiles').textContent;
        check('the tiles show what the server totalled, not a sum made here',
            /Items tracked\s*4/.test(tiles) && /Stock value\s*£49\.50/.test(tiles) && /Low on stock\s*1/.test(tiles) && /Out of stock\s*2/.test(tiles), tiles);
        check('every tracked item is a row', ['WID', 'BOLT', 'NUT', 'WASHER'].every(c => !!rowFor(w, c)) && !rowFor(w, 'CONSULT'));
        const cells = [...rowFor(w, 'WID').children].map(c => c.textContent);
        check('  with its quantity, reorder line, cost and value',
            cells[1] === '12' && cells[2] === '5' && cells[3] === '£4.00' && cells[4] === '£48.00', cells.join(' | '));
        const pill = code => rowFor(w, code).querySelector('.status-pill');
        check('  a healthy one reads In stock in green, a low one Low in amber',
            pill('WID').textContent === 'In stock' && pill('WID').classList.contains('status-paid')
            && pill('BOLT').textContent === 'Low' && pill('BOLT').classList.contains('status-low'));
        check('  an empty one is red, and one sold past zero says Oversold, in red, with its negative number',
            pill('NUT').classList.contains('status-out') && pill('NUT').textContent === 'Out of stock'
            && pill('WASHER').textContent === 'Oversold' && pill('WASHER').classList.contains('status-out') && /-2/.test(rowFor(w, 'WASHER').textContent));
        check('a tracked row offers Receive, Count, History and Edit - and not Start tracking',
            ['receive', 'count', 'history', 'edit'].every(a => !!btn(rowFor(w, 'WID'), a)) && !btn(rowFor(w, 'WID'), 'track'));
        check('the active tab is the one that was asked for', w.document.querySelector('#inventory-tabs .tab.active').getAttribute('data-inv-view') === 'tracked');
        check('the count says how many', /4 items/.test(w.document.getElementById('inventory-count').textContent), w.document.getElementById('inventory-count').textContent);
    }

    // --- arriving from the dashboard ----------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        sent.length = 0;
        w.goToAttention({ key: 'stock_low', view: 'inventory-view', filter: 'low', count: 3 });
        await wait(150);
        const asks = sent.filter(s => s.url === '/api/inventory');
        check('"Items to reorder" on the dashboard opens Inventory on the Low tab, asking once',
            asks.length === 1 && /view=low/.test(asks[0].full) && w.document.querySelector('#inventory-tabs .tab.active').getAttribute('data-inv-view') === 'low',
            JSON.stringify(asks.map(a => a.full)));
    }

    // --- tabs and search ---------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        w.setInventoryView('untracked');
        await wait(100);
        check('a tab asks the server for that view', sent.some(s => s.url === '/api/inventory' && /view=untracked/.test(s.full)), JSON.stringify(sent.map(s => s.full)));
        check('  and the tab lights up', w.document.querySelector('#inventory-tabs .tab.active').getAttribute('data-inv-view') === 'untracked');
        check('an untracked item offers Start tracking, not Receive or Count',
            !!btn(rowFor(w, 'CONSULT'), 'track') && !btn(rowFor(w, 'CONSULT'), 'receive') && !btn(rowFor(w, 'CONSULT'), 'count') && !btn(rowFor(w, 'CONSULT'), 'history'));
        check('  and shows dashes where a number would be a lie', /Not tracked/.test(rowFor(w, 'CONSULT').textContent));

        sent.length = 0;
        w.setInventoryView('low');
        await wait(100);
        check('the Low tab includes what is out and oversold, which need ordering more',
            ['BOLT', 'NUT', 'WASHER'].every(c => !!rowFor(w, c)) && !rowFor(w, 'WID'));

        sent.length = 0;
        const box = w.document.getElementById('inventory-search');
        box.value = 'bolt';
        w.debounceInventory();
        w.debounceInventory();
        w.debounceInventory();
        await wait(400);
        const asks = sent.filter(s => s.url === '/api/inventory');
        check('typing in the search waits, and asks once, with what was typed', asks.length === 1 && /q=bolt/.test(asks[0].full), JSON.stringify(asks.map(a => a.full)));
    }

    // --- a tile is a shortcut ---------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        [...w.document.querySelectorAll('#inventory-tiles .stat-card')].find(b => /Low on stock/.test(b.textContent)).click();
        await wait(100);
        check('the Low on stock tile opens the Low tab', sent.some(s => /view=low/.test(s.full)));
    }

    // --- nothing, and trouble ---------------------------------------------------------------
    {
        const { w } = boot({ items: [], totals: { tracked: 0, untracked: 0, stock_value: 0, low: 0, out: 0, over: 0 } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        check('with nothing tracked it says what to do next', /Nothing is tracked yet/.test(tbody(w).textContent), tbody(w).textContent);
    }
    {
        const { w } = boot({ inventoryFails: true });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        check('a server that is down is said, not left blank', /Could not load your inventory/.test(tbody(w).textContent), tbody(w).textContent);
    }

    // --- what a name can do ---------------------------------------------------------------------
    {
        const { w } = boot({ items: [EVIL], totals: TOTALS });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        check('an item name is shown as text, never as markup',
            !tbody(w).querySelector('img') && !tbody(w).querySelector('b') && /<img src=x/.test(tbody(w).textContent));
    }

    // --- receiving ---------------------------------------------------------------------------------
    {
        const { w, sent, asked, toasts } = boot({ answer: { quantity: '24', unit_cost: '5', date: '2026-10-07', note: 'Delivery 88' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'receive').click();
        await wait(150);
        const q = asked[0];
        check('Receive asks how many, what each cost, the date, and a note',
            ['quantity', 'unit_cost', 'date', 'note'].every(n => q.fields.some(f => f.name === n)) && /Receive WID/.test(q.opts.title));
        check('  starting from the current average cost, today, and saying what is on hand now',
            q.fields.find(f => f.name === 'unit_cost').value === 4 && /^\d{4}-\d{2}-\d{2}$/.test(q.fields.find(f => f.name === 'date').value) && /12 on hand now/.test(q.opts.message), q.opts.message);
        const post = sent.find(s => /\/receive$/.test(s.url));
        check('it posts exactly what was typed, to that item', !!post && post.url === '/api/inventory/11/receive' && post.method === 'POST'
            && JSON.stringify(JSON.parse(post.body)) === JSON.stringify({ quantity: '24', unit_cost: '5', date: '2026-10-07', note: 'Delivery 88' }), post && post.body);
        check('  says it worked and reloads the shelf', toasts.some(t => t.k === 'success') && sent.some(s => s.url === '/api/inventory'));
    }
    {
        const { w, sent } = boot({ answer: null });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'receive').click();
        await wait(150);
        check('cancelling sends nothing at all', sent.length === 0, JSON.stringify(sent.map(s => s.url)));
    }
    {
        const { w, toasts } = boot({ answer: { quantity: '0', unit_cost: '1' }, actionFails: 'Quantity received must be more than nothing' });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        btn(rowFor(w, 'WID'), 'receive').click();
        await wait(150);
        check('the server\'s reason is shown when it refuses', toasts.some(t => t.k === 'error' && /more than nothing/.test(t.m)), JSON.stringify(toasts));
    }

    // --- counting ---------------------------------------------------------------------------------------
    {
        const { w, sent, asked } = boot({ answer: { counted: '8', reason: 'damaged', note: 'Water in the van' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'count').click();
        await wait(150);
        const reasons = asked[0].fields.find(f => f.name === 'reason').options.map(o => o.value);
        check('a count starts from what the book says and asks why it differs',
            asked[0].fields.find(f => f.name === 'counted').value === 12 && /The book says 12/.test(asked[0].opts.message)
            && ['stocktake', 'damaged', 'lost', 'found', 'returned', 'other'].every(r => reasons.includes(r)), reasons.join());
        const post = sent.find(s => /\/count$/.test(s.url));
        check('it posts the count and the reason', !!post && JSON.stringify(JSON.parse(post.body)) === JSON.stringify({ counted: '8', reason: 'damaged', note: 'Water in the van' }), post && post.body);
    }

    // --- starting to track ---------------------------------------------------------------------------------
    {
        const { w, sent, asked } = boot({ answer: { quantity: '30', unit_cost: '2.5', reorder_level: '10' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        w.setInventoryView('untracked');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'CONSULT'), 'track').click();
        await wait(150);
        check('starting to track says invoices already issued are not taken out again', /already issued are not taken out of it again/.test(asked[0].opts.message), asked[0].opts.message);
        const post = sent.find(s => /\/track$/.test(s.url));
        check('and posts the count, the cost and the reorder line', !!post && post.url === '/api/inventory/15/track'
            && JSON.stringify(JSON.parse(post.body)) === JSON.stringify({ quantity: '30', unit_cost: '2.5', reorder_level: '10' }), post && post.body);
    }

    // --- editing --------------------------------------------------------------------------------------------------
    {
        const { w, sent, asked } = boot({ answer: { name: 'Widget 2', sale_price: '12', purchase_price: '5', reorder_level: '6', tracking: 'on' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'edit').click();
        await wait(150);
        check('editing a tracked item offers its reorder line and the tracking switch', ['reorder_level', 'tracking'].every(n => asked[0].fields.some(f => f.name === n)));
        const put = sent.find(s => s.method === 'PUT');
        const body = put && JSON.parse(put.body);
        check('it saves to the item, and leaves tracking alone when it stays on', !!put && put.url === '/api/items/11' && body.name === 'Widget 2'
            && body.reorder_level === '6' && !('track_inventory' in body), put && put.body);
    }
    {
        const { w, sent } = boot({ answer: { name: 'Widget', sale_price: '10', purchase_price: '4', reorder_level: '5', tracking: 'off' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'edit').click();
        await wait(150);
        const put = sent.find(s => s.method === 'PUT');
        check('switching tracking off says so to the server', !!put && JSON.parse(put.body).track_inventory === false, put && put.body);
    }
    {
        const { w, asked } = boot({ answer: null });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        w.setInventoryView('untracked');
        await wait(100);
        btn(rowFor(w, 'CONSULT'), 'edit').click();
        await wait(100);
        check('an untracked item has no tracking switch to edit - it is started from its own button', !asked[0].fields.some(f => f.name === 'tracking'));
    }

    // --- a new item ----------------------------------------------------------------------------------------------------
    {
        const { w, sent } = boot({ answer: { code: 'NEW1', name: 'New thing', sale_price: '9', purchase_price: '3', tracking: 'yes', quantity: '7', reorder_level: '2' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        await w.newInventoryItem();
        await wait(100);
        const post = sent.find(s => s.url === '/api/items' && s.method === 'POST');
        const b = post && JSON.parse(post.body);
        check('a new tracked item is created with its opening count', !!b && b.code === 'NEW1' && b.track_inventory === true && b.quantity_on_hand === '7' && b.reorder_level === '2', post && post.body);
        check('  and the screen moves to where it will be', /view=tracked/.test(sent.filter(s => s.url === '/api/inventory').pop().full));
    }
    {
        const { w, sent } = boot({ answer: { code: 'SVC', name: 'Service', sale_price: '50', purchase_price: '', tracking: 'no', quantity: '99', reorder_level: '' } });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        await w.newInventoryItem();
        await wait(100);
        const b = JSON.parse(sent.find(s => s.url === '/api/items' && s.method === 'POST').body);
        check('an untracked new item carries no quantity, whatever the box said', b.track_inventory === false && b.quantity_on_hand === 0, JSON.stringify(b));
        check('  and the screen moves to the Not tracked tab', /view=untracked/.test(sent.filter(s => s.url === '/api/inventory').pop().full));
    }
    {
        const { w, toasts } = boot({ answer: { code: 'WID', tracking: 'no', quantity: 0 }, createFails: "'WID' is already in your items" });
        await wait(80);
        await w.newInventoryItem();
        await wait(100);
        check('a code already taken is explained', toasts.some(t => t.k === 'error' && /already in your items/.test(t.m)));
    }
    {
        const { w, sent } = boot({ answer: null });
        await wait(80);
        sent.length = 0;
        await w.newInventoryItem();
        check('cancelling a new item creates nothing', !sent.some(s => s.method === 'POST'));
    }

    // --- the history -----------------------------------------------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        sent.length = 0;
        btn(rowFor(w, 'WID'), 'history').click();
        await wait(200);
        check('History asks for that item\'s movements', sent.some(s => s.url === '/api/inventory/11/movements' && s.method === 'GET'));
        const card = w.document.getElementById('inventory-history');
        const rows = [...card.querySelectorAll('tbody tr')];
        check('the panel opens, titled with the item', card.style.display === 'block' && /WID - Widget/.test(w.document.getElementById('inventory-history-title').textContent));
        check('every movement is a row, newest first', rows.length === 6 && /Count/.test(rows[0].textContent) && /Opening count/.test(rows[5].textContent));
        check('  a count says why, a sale says which invoice, and the change has its sign',
            /Count: damaged/.test(rows[0].textContent) && /-2/.test(rows[0].textContent)
            && /Put back/.test(rows[1].textContent) && /\+3/.test(rows[1].textContent)
            && /Sold/.test(rows[2].textContent) && /-3/.test(rows[2].textContent));
        const link = rows[2].querySelector('a');
        check('  the invoice is a link to it', !!link && link.getAttribute('href') === '#/invoices/INV-0008' && link.textContent === 'INV-0008');
        check('  a sale that was already out before tracking is shown faintly and moved nothing',
            /Already out before tracking/.test(rows[3].textContent) && rows[3].style.opacity === '0.6' && /-/.test(rows[3].children[2].textContent) && !/-5/.test(rows[3].children[2].textContent));
        check('  with the balance after each', rows[5].children[3].textContent === '10' && rows[0].children[3].textContent === '12');
        w.closeInventoryHistory();
        check('Close puts it away', card.style.display === 'none');
    }
    {
        const { w } = boot({ noMoves: true });
        await wait(80);
        w.showView('inventory-view');
        await wait(100);
        btn(rowFor(w, 'WID'), 'history').click();
        await wait(150);
        check('an item nothing has happened to says so', /Nothing has happened to this item yet/.test(w.document.getElementById('inventory-history-body').textContent));
    }

    // --- the lines of an invoice ----------------------------------------------------------------------------------------------
    const firstRow = w => {
        const body = w.document.getElementById('line-items-body');
        if (!body.querySelector('.line-item-row')) w.addLineItemRow('invoice');
        return body.querySelector('.line-item-row');
    };
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        w.applyItemToRow(row, WIDGET);
        check('picking an item remembers which one, and what it is called on the line', row.dataset.itemId === '11' && row.dataset.itemName === 'Widget');
        const hint = row.querySelector('.stock-hint');
        check('a tracked item shows what is in stock under it', !!hint && hint.textContent === '12 in stock' && !hint.classList.contains('is-short'), hint && hint.textContent);
        row.querySelector('.item-qty').value = '20';
        row.querySelector('.item-qty').dispatchEvent(new w.Event('input', { bubbles: true }));
        check('asking for more than there is warns, in red, and says how many there are', hint.textContent === 'Only 12 in stock' && hint.classList.contains('is-short'), hint.textContent);
        row.querySelector('.item-qty').value = '12';
        row.querySelector('.item-qty').dispatchEvent(new w.Event('input', { bubbles: true }));
        check('asking for exactly what there is is fine', hint.textContent === '12 in stock' && !hint.classList.contains('is-short'));
        w.applyItemToRow(row, OUT);
        check('an item with none says so', row.querySelector('.stock-hint').textContent === 'None in stock');
        w.applyItemToRow(row, PLAIN);
        check('an untracked item keeps the link but shows no stock', row.dataset.itemId === '15' && !row.querySelector('.stock-hint'));
    }
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        w.applyItemToRow(row, WIDGET);
        const box = row.querySelector('.item-name');
        w.onItemBoxInput(box);
        check('focusing the box again keeps the link - nothing was retyped', row.dataset.itemId === '11' && !!row.querySelector('.stock-hint'));
        box.value = 'Widget deluxe';
        w.onItemBoxInput(box);
        check('retyping the box cuts the link, so stock is not taken for something else',
            !row.dataset.itemId && !row.dataset.itemName && !row.querySelector('.stock-hint'), JSON.stringify(row.dataset));
        check('  and the line then sends no item', w.lineItemId(row) === null);
    }
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        row.querySelector('.item-name').value = 'WID';
        w.applyItemToRow(row, Object.assign({}, WIDGET, { name: '' }));
        w.onItemBoxInput(row.querySelector('.item-name'));
        check('an item with no name keeps its link when the box still shows what was typed to find it', row.dataset.itemId === '11');
    }
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        check('a line that was never picked from the catalogue has no item', w.lineItemId(row) === null);
        row.dataset.itemId = 'abc';
        check('a damaged value is no item rather than a wrong one', w.lineItemId(row) === null);
    }
    {
        const { w, sent } = boot();
        await wait(80);
        const row = firstRow(w);
        w.document.getElementById('inv-contact').value = 'Customer Ltd';
        w.applyItemToRow(row, WIDGET);
        row.querySelector('.item-qty').value = '2';
        w.addLineItemRow('invoice');
        const rows = w.document.getElementById('line-items-body').querySelectorAll('.line-item-row');
        rows[1].querySelector('.item-name').value = 'Postage';
        rows[1].querySelector('.item-qty').value = '1';
        rows[1].querySelector('.item-price').value = '3';
        sent.length = 0;
        await w.submitComplexInvoice('Awaiting Payment');
        await wait(150);
        const post = sent.find(s => s.url === '/api/invoices' && s.method === 'POST');
        const lines = post && JSON.parse(post.body).line_items;
        check('saving an invoice sends the item each line was picked from', !!lines && lines[0].item_id === 11, post && post.body);
        check('  and null for a line typed by hand', !!lines && lines[1].item_id === null, post && post.body);
    }
    {
        const { w } = boot({ invoice: { number: 'INV-0009', contact: 'Customer Ltd', status: 'Draft', issue_date: '2026-01-01', due_date: '2026-01-31', tax_type: 'exclusive',
            line_items: [{ name: 'Widget', description: 'd', qty: 3, price: 10, disc: 0, account: '200 - Sales', tax_rate: 'No Tax', item_id: 11 },
                         { name: 'Postage', description: '', qty: 1, price: 3, disc: 0, account: '200 - Sales', tax_rate: 'No Tax', item_id: null }] } });
        await wait(80);
        await w.editInvoice('INV-0009');
        await wait(150);
        const rows = w.document.getElementById('line-items-body').querySelectorAll('.line-item-row');
        check('editing an invoice puts the link back on the lines that had one', rows.length === 2 && rows[0].dataset.itemId === '11' && !rows[1].dataset.itemId, [...rows].map(r => r.dataset.itemId).join());
        const box = rows[0].querySelector('.item-name');
        w.onItemBoxInput(box);
        check('  and a line that is left alone keeps it', rows[0].dataset.itemId === '11');
    }
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        const dropdown = row.querySelector('.item-lookup');
        w.renderItemLookup(dropdown, row.querySelector('.item-name'), [WIDGET, OUT, PLAIN], 'x');
        const text = dropdown.textContent;
        check('the lookup says how many are in stock beside each tracked item, and nothing for one that is not',
            /12 in stock/.test(text) && /none in stock/.test(text) && !/CONSULT.*in stock/.test(text.replace(/\s+/g, ' ').split('Create new item')[0].split('CONSULT')[1] || ''), text);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
