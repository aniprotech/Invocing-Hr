/**
 * Needs you today.
 *
 * The panel that opens the dashboard: what is waiting on this business,
 * worst first, each row a link to the work rather than to the front of a
 * section. Nothing waiting draws nothing at all - an empty panel taking up
 * the top of the screen teaches people to ignore the top of the screen.
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

const ITEMS = [
    { key: 'overdue', count: 3, label: 'Overdue invoices', hint: 'past their due date and still unpaid', view: 'invoices-view', filter: 'overdue', tone: 'bad', amount: 1840.5, currency: 'GBP' },
    { key: 'bank_to_code', count: 6, label: 'Bank lines to code', hint: 'money out with no home yet', view: 'bank-view', filter: 'out', tone: 'warn', amount: null, currency: '' },
    { key: 'bank_to_match', count: 2, label: 'Bank lines to match', hint: 'money in with no invoice against it', view: 'bank-view', filter: 'unmatched', tone: 'warn', amount: 250, currency: 'GBP' },
    { key: 'quotes_open', count: 1, label: 'Quotes awaiting an answer', hint: 'sent and not yet accepted or declined', view: 'quotes-view', filter: '', tone: 'info', amount: 500, currency: 'GBP' }
];

function boot(items) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/dashboard/attention') return give({ items: items, currency: 'GBP' });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    const went = [];
    w.showView = (v) => went.push(v);
    return { w, doc: w.document, went };
}

(async () => {
    // --- with work waiting ---------------------------------------------------
    {
        const { w, doc } = boot(ITEMS);
        await w.loadAttention();
        await wait(20);
        const host = doc.getElementById('dash-attention');
        check('the panel is on the dashboard and shows itself when there is work', host && host.style.display !== 'none');
        const rows = doc.querySelectorAll('#dash-attention [data-attention]');
        check('one row per thing waiting', rows.length === 4, String(rows.length));
        check('  the header counts them', /4 things waiting/.test(host.textContent), host.textContent.slice(0, 120));
        check('  each row says the count, what it is and why it matters',
            /3/.test(rows[0].textContent) && /Overdue invoices/.test(rows[0].textContent) && /still unpaid/.test(rows[0].textContent), rows[0].textContent);
        check('  an amount is shown where there is one, and left out where there is not',
            /£1840\.50/.test(rows[0].textContent) && !/£/.test(rows[1].textContent), rows[0].textContent + ' | ' + rows[1].textContent);
        check('  the worst is drawn in the danger colour, the rest are not',
            /--danger-color/.test(rows[0].outerHTML) && !/--danger-color/.test(rows[2].outerHTML));
    }

    // --- nothing waiting -------------------------------------------------------
    {
        const { doc, w } = boot([]);
        await w.loadAttention();
        await wait(20);
        const host = doc.getElementById('dash-attention');
        check('with nothing waiting the panel takes up no room at all', host.style.display === 'none' && host.innerHTML === '');
    }

    // --- every row goes somewhere ----------------------------------------------
    {
        const { w, doc, went } = boot(ITEMS);
        await w.loadAttention();
        await wait(20);
        const rows = doc.querySelectorAll('#dash-attention [data-attention]');
        rows[0].click();
        check('a row opens the screen the work is on', went[went.length - 1] === 'invoices-view', went.join(','));
        rows[1].click();
        check('  the bank rows open the Bank screen', went[went.length - 1] === 'bank-view', went.join(','));
        rows[3].click();
        check('  a quote row opens Quotes', went[went.length - 1] === 'quotes-view', went.join(','));
    }

    // --- the bank rows land on the right tab -------------------------------------
    {
        const { w, doc } = boot(ITEMS);
        await w.loadAttention();
        await wait(20);
        const clicked = [];
        doc.querySelectorAll('#bank-tabs .tab').forEach(t => { t.addEventListener('click', () => clicked.push(t.textContent.trim())); });
        doc.querySelector('[data-attention="bank_to_code"]').click();
        await wait(220);
        check('the money-out row lands on To code, not the front of the Bank screen', clicked.includes('To code'), clicked.join(','));
        doc.querySelector('[data-attention="bank_to_match"]').click();
        await wait(220);
        check('  and the money-in row lands on To match', clicked.includes('To match'), clicked.join(','));
    }

    // --- the tabs the dashboard aims at --------------------------------------------
    {
        const { w, doc } = boot(ITEMS);
        // The cash-flow range buttons on the dashboard carry the same class as
        // the invoice tabs and sit earlier in the document. A lookup by class
        // found those instead, so every stat card - and every row here - landed
        // on an unfiltered list and nothing said why.
        const first = doc.querySelector('.invoices-tabs');
        check('the first .invoices-tabs on the page is the cash-flow range, not the invoice tabs',
            first && first.id === 'cf-range', first && first.id);
        check('  so the invoice tabs are found by their own id', !!doc.getElementById('invoice-tabs'));
        const clicked = [];
        doc.querySelectorAll('#invoice-tabs .tab').forEach(t => { t.addEventListener('click', () => clicked.push(t.textContent.trim())); });
        await w.loadAttention();
        await wait(20);
        doc.querySelector('[data-attention="overdue"]').click();
        await wait(320);
        check('  the overdue row filters the list to Overdue', clicked.includes('Overdue'), clicked.join(','));
    }

    // --- names are text, not markup ------------------------------------------------
    {
        const nasty = [{ key: 'overdue', count: 1, label: 'Overdue <i>invoices</i>', hint: 'a "quoted" hint', view: 'invoices-view', filter: 'overdue', tone: 'bad', amount: 1, currency: 'GBP' }];
        const { w, doc } = boot(nasty);
        await w.loadAttention();
        await wait(20);
        const host = doc.getElementById('dash-attention');
        check('a label with markup in it is printed, not rendered',
            /Overdue <i>invoices<\/i>/.test(host.textContent) && !host.querySelector('#dash-attention i') && !host.querySelector('i'));
    }

    // --- a broken answer is not a broken dashboard -----------------------------------
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
        const w = dom.window;
        w.console.error = () => { };
        w.fetch = () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'boom' }) });
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        w.showToast = () => { };
        await w.loadAttention();
        await wait(20);
        check('a failed call hides the panel rather than throwing', dom.window.document.getElementById('dash-attention').style.display === 'none');
    }

    console.log(failures ? `\n${failures} check(s) failed.` : '\nAll needs-you-today checks passed.');
    process.exit(failures ? 1 : 0);
})();
