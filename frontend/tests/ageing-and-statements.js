/**
 * Ageing by customer and statements, on screen: the report's customer
 * table with DSO and an as-of date, and the customer page's statement
 * with a running balance, CSV, and a send dialog. Names are text.
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

const AGEING = { as_of: '2026-09-16', currency: 'GBP', buckets: { current: 250, '1_30': 400, '31_60': 200, '61_90': 0, over_90: 100 }, total_outstanding: 950,
    dso: 61.1, sales_90d: 1400, customers_owing: 2, other_currencies: ['USD'],
    customers: [
        { contact: 'Acme <b>Ltd</b>', currency: 'GBP', email: 'a@x', contact_id: 7, invoices: 3, oldest_days: 95, total: 550, current: 250, '1_30': 0, '31_60': 200, '61_90': 0, over_90: 100 },
        { contact: 'Bolt', currency: 'GBP', email: '', contact_id: null, invoices: 1, oldest_days: 10, total: 400, current: 0, '1_30': 400, '31_60': 0, '61_90': 0, over_90: 0 },
        { contact: 'Acme <b>Ltd</b>', currency: 'USD', email: 'a@x', contact_id: 7, invoices: 1, oldest_days: 0, total: 900, current: 900, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0 } ],
    invoices: [{ number: 'INV-1', contact: 'Acme <b>Ltd</b>', due_date: '2026-06-13', issue_date: '2026-06-08', outstanding: 100, days_overdue: 95, bucket: 'over_90', currency: 'GBP' }] };
const STATEMENT = { contact: { id: 7, name: 'Acme <b>Ltd</b>', email: 'a@x' }, company: 'Me Ltd', start: '2026-06-18', end: '2026-09-16', statements: [
    { currency: 'GBP', opening_balance: 60, closing_balance: 210, overdue: 210, invoiced: 300, received: 200, lines: [
        { date: '2026-08-17', kind: 'invoice', ref: 'INV-2', number: 'INV-2', description: 'Invoice INV-2, due 2026-09-15', debit: 300, credit: 0, balance: 360 },
        { date: '2026-08-27', kind: 'payment', ref: 'FPS <i>1</i>', number: 'INV-2', description: 'Payment on INV-2 (bank transfer)', debit: 0, credit: 200, balance: 160 },
        { date: '2026-09-06', kind: 'refund', ref: '', number: 'INV-2', description: 'Refund on INV-2: Short delivery', debit: 50, credit: 0, balance: 210 } ] },
    { currency: 'USD', opening_balance: 0, closing_balance: 900, overdue: 0, invoiced: 900, received: 0, lines: [
        { date: '2026-09-10', kind: 'invoice', ref: 'INV-3', number: 'INV-3', description: 'Invoice INV-3', debit: 900, credit: 0, balance: 900 } ] } ] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], forms = [];
    w.console.error = () => { };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} }; w.Chart.register = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, q: full.split('?')[1] || '', method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/reports/ageing') return give(AGEING);
        if (p === '/api/contacts/7/detail') return give({ contact: { id: 7, name: 'Acme <b>Ltd</b>', email: 'a@x' }, summary: { outstanding: [], billed: [], paid: [], invoice_count: 1, overdue_count: 0 }, invoices: [], quotes: [], payments: [] });
        if (p === '/api/contacts/7/statement' && method === 'GET') return give(STATEMENT);
        if (p === '/api/contacts/7/statement/send') return give({ message: 'Statement sent to a@x', to: 'a@x' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiForm = (fields) => { forms.push(fields); return Promise.resolve(opts.form === undefined ? null : opts.form); };
    return { w, doc: w.document, sent, forms };
}

(async () => {
    {
        const { w, doc, sent } = boot();
        doc.getElementById('aged-asof').value = '2026-09-16';
        await w.loadAgedReceivables();
        await wait(40);
        const asked = sent.find(s => s.url === '/api/reports/ageing');
        check('the report asks as of the chosen day and the CSV links follow it',
            asked && /as_of=2026-09-16/.test(asked.q) && /as_of=2026-09-16/.test(doc.getElementById('aged-csv').href) && /detail=1/.test(doc.getElementById('aged-csv-detail').href));
        const head = doc.getElementById('aged-buckets').textContent;
        check('DSO and how many customers owe sit with the total, and other currencies are named but not added',
            /DSO\s*61\.1 days/.test(head.replace(/\s+/g, ' ')) && /2 customers owing/.test(head) && /Also owed in USD/.test(head), head.slice(-200));
        const table = doc.getElementById('aged-customers');
        const rows = table.querySelectorAll('tbody tr');
        check('one row per customer per currency, biggest first, names as text',
            rows.length === 3 && /Acme <b>Ltd<\/b>/.test(rows[0].textContent) && !table.querySelector('b') && /Bolt/.test(rows[1].textContent) && /USD/.test(rows[2].textContent), table.textContent.slice(0, 200));
        check('  the buckets and the oldest day per customer',
            /£100\.00/.test(rows[0].textContent) && /95d/.test(rows[0].textContent) && /£400\.00/.test(rows[1].textContent) && /not due/.test(rows[2].textContent));
        check('  a known customer links to their page and has a Statement button; an unknown name does not',
            rows[0].querySelector('a') && rows[0].querySelector('[data-statement-for="7"]') && !rows[1].querySelector('a') && !rows[1].querySelector('[data-statement-for]'));
        let opened = null; w.openCustomer = (id) => { opened = id; };
        rows[0].querySelector('[data-statement-for="7"]').click();
        check('  and Statement opens the customer', opened === 7);
    }
    {
        const { w, doc, sent } = boot();
        await w.openCustomer(7);
        await wait(60);
        const st = doc.getElementById('stmt-start').value, en = doc.getElementById('stmt-end').value;
        check('opening a customer sets a ninety-day period and loads the statement',
            /^\d{4}-\d{2}-\d{2}$/.test(st) && /^\d{4}-\d{2}-\d{2}$/.test(en) && st < en && sent.some(s => s.url === '/api/contacts/7/statement' && new RegExp('start=' + st).test(s.q)));
        const host = doc.getElementById('cust-statement');
        const text = host.textContent.replace(/\s+/g, ' ');
        check('the statement runs from the balance brought forward through each line to the balance carried forward, per currency, as text',
            /Balance brought forward/.test(text) && /£60\.00/.test(text) && /Invoice INV-2, due 2026-09-15/.test(text) && /£360\.00/.test(text) && /FPS <i>1<\/i>/.test(text) && !host.querySelector('i') &&
            /Refund on INV-2: Short delivery/.test(text) && /Balance carried forward/.test(text) && /£210\.00/.test(text) && /USD/.test(text) && /\$900\.00|US\$900\.00|900\.00/.test(text), text.slice(0, 400));
        check('  overdue money is called out', /£210\.00 of this is past its due date/.test(text));
        check('  the CSV link carries the period', /\/api\/contacts\/7\/statement\.csv\?start=/.test(doc.getElementById('stmt-csv').href));
        check('  an invoice line opens the invoice', host.querySelector('a') && /viewInvoice/.test(host.querySelector('a').getAttribute('onclick')));
    }
    {
        const { w, sent, forms } = boot({ form: { note: 'Please settle by Friday.' } });
        await w.openCustomer(7);
        await wait(60);
        await w.sendStatement();
        await wait(30);
        const f = forms[forms.length - 1];
        check('sending asks for a line at the top', f && f[0].name === 'note');
        const post = sent.find(s => s.url === '/api/contacts/7/statement/send');
        check('  and posts the period and the note', post && bodyOf(post).note === 'Please settle by Friday.' && /^\d{4}-\d{2}-\d{2}$/.test(bodyOf(post).start) && /^\d{4}-\d{2}-\d{2}$/.test(bodyOf(post).end), post && post.body);
    }
    {
        const { w, sent, forms } = boot({ form: null });
        await w.openCustomer(7);
        await wait(60);
        await w.sendStatement();
        await wait(30);
        check('backing out sends nothing', !sent.some(s => s.url === '/api/contacts/7/statement/send'));
    }
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Settings has the monthly statements switch', /id="monthly-statements"/.test(src) && /saveMonthlyStatements/.test(src));
        const { w, doc, sent } = boot();
        const box = doc.getElementById('monthly-statements');
        box.checked = true;
        await w.saveMonthlyStatements(box);
        await wait(20);
        const post = sent.find(s => s.url === '/api/settings' && s.method === 'POST');
        check('  which saves as a setting', post && bodyOf(post).monthly_statements === '1');
    }
    console.log(failures === 0 ? '\nAll ageing-and-statement checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
