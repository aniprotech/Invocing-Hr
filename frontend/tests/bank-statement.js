/**
 * The bank page: a statement file is dry-run, confirmed and imported into
 * an account; each line of money in shows what it is probably for with
 * Record / Choose / Ignore; a line already typed in shows "Same one";
 * confident matches can be recorded in one go; the other tabs list what
 * was matched, ignored, spent, and which files came in. Words are text.
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

const LINES = { counts: { unmatched: 3, matched: 1, out: 2 }, unmatched_total: 1380, auto: 1, accounts: [{ id: 1, name: 'HDFC <b>current</b>' }, { id: 2, name: 'Cash box' }], lines: [
    { id: 11, date: '2026-09-14', description: 'FPS ACME <i>LTD</i> INV-0001', reference: '', amount: 780, balance: null, status: 'unmatched', allocated: 0, remaining: 780, payment_ids: [], note: '',
      suggestions: [{ invoice_id: 5, number: 'INV-0001', contact: 'Acme <i>Ltd</i>', due: 780, due_date: '2026-09-30', currency: 'GBP', confidence: 'auto', why: 'exact amount, invoice number in narrative', score: 7 }] },
    { id: 12, date: '2026-09-15', description: 'BACS 8812', reference: 'R1', amount: 500, balance: null, status: 'unmatched', allocated: 0, remaining: 500, payment_ids: [], note: '',
      suggestions: [{ invoice_id: 6, number: 'INV-0002', contact: 'Bramley', due: 500, due_date: '', currency: 'GBP', confidence: 'likely', why: 'exact amount', score: 4 },
                    { invoice_id: 7, number: 'INV-0003', contact: 'Other', due: 500, due_date: '', currency: 'GBP', confidence: 'likely', why: 'exact amount', score: 4 }] },
    { id: 13, date: '2026-09-15', description: 'FPS ACME', reference: '', amount: 100, balance: null, status: 'unmatched', allocated: 0, remaining: 100, payment_ids: [], note: '',
      suggestions: [], already_recorded: { payment_id: 44, amount: 100, paid_on: '2026-09-14', reference: 'typed' } } ] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, q: full.split('?')[1] || '', method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/bank/lines') return give(opts.lines || LINES);
        if (p === '/api/bank/imports') return give({ imports: [{ id: 3, account_id: 1, account: 'HDFC <b>current</b>', filename: 'sept.csv', kind: 'csv', lines: 12, duplicates: 2, created_at: '2026-09-16 10:00:00', imported_by: 'me' }] });
        if (p === '/api/bank/import') return give(full.indexOf('dry_run=1') !== -1
            ? { summary: { rows: 4, new: 3, duplicates: 1, unreadable: 0, money_in: 2, money_out: 1, kind: 'csv', first: '2026-09-14', last: '2026-09-16', account_id: 1 }, sample: [] }
            : { summary: { new: 3 }, import_id: 9 });
        if (p === '/api/bank/record-all') return give({ recorded: 1, left: 2 });
        if (p.startsWith('/api/bank/lines/11/record')) return give({ message: 'Recorded against INV-0001', payment_id: 1, invoice: { number: 'INV-0001', status: 'Paid', due: 0 }, line: {} });
        if (p.startsWith('/api/bank/lines/')) return give({ message: 'ok', line: {} });
        if (p === '/api/accounts') return give({ accounts: [{ id: 1, name: 'HDFC', active: true }, { id: 2, name: 'Cash', active: true }] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    w.uiPrompt = () => Promise.resolve(opts.prompt === undefined ? 'INV-0009' : opts.prompt);
    w.uiChoose = () => Promise.resolve(opts.choose === undefined ? '2' : opts.choose);
    w.uiAlert = () => Promise.resolve(true);
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Money has a Bank page with an account picker, import and record-all', /id="nav-bank"/.test(src) && /id="bank-view"/.test(src) && /id="bank-account"/.test(src) && /id="bank-file"/.test(src) && /id="bank-record-all"/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        check('the route and nav maps know the page', w.ROUTE_SLUGS['bank-view'] === 'bank' && w.VIEW_FOR_SLUG.bank === 'bank-view');
        await w.loadBankView();
        await wait(40);
        const tiles = doc.getElementById('bank-tiles').textContent;
        check('the tiles count what is to match, the confident ones, the matched and the money out', /3/.test(tiles) && /£1380\.00 unexplained/.test(tiles) && /Confident matches\s*1/.test(tiles.replace(/\s+/g, ' ')) && /Money out\s*2/.test(tiles.replace(/\s+/g, ' ')), tiles);
        check('the account picker is filled, names as text', doc.getElementById('bank-account').options.length === 3 && /HDFC <b>current<\/b>/.test(doc.getElementById('bank-account').options[1].textContent));
        const rows = doc.querySelectorAll('#bank-list tbody tr');
        check('one row per line, narrative as text', rows.length === 3 && /FPS ACME <i>LTD<\/i> INV-0001/.test(rows[0].textContent) && !doc.getElementById('bank-list').querySelector('i'));
        check('  a confident match shows the invoice, the customer, why, and a primary Record button',
            /INV-0001/.test(rows[0].textContent) && /Acme <i>Ltd<\/i>/.test(rows[0].textContent) && /Confident: exact amount, invoice number in narrative/.test(rows[0].textContent) && rows[0].querySelector('[data-bank-record].btn-primary'));
        check('  a likely match with a rival shows both and an outline button', /Likely: exact amount/.test(rows[1].textContent) && /or INV-0003/.test(rows[1].textContent) && rows[1].querySelector('[data-bank-record].btn-outline'));
        check('  a line already typed in offers "Same one" instead of Record', /Already typed in: £100\.00 on 2026-09-14/.test(rows[2].textContent) && rows[2].querySelector('[data-bank-link]') && !rows[2].querySelector('[data-bank-record]'));
        check('  every unmatched line can be chosen for or ignored', doc.querySelectorAll('[data-bank-pick]').length === 3 && doc.querySelectorAll('[data-bank-ignore]').length === 3);
        rows[0].querySelector('[data-bank-record]').click();
        await wait(30);
        const rec = sent.find(s => s.url === '/api/bank/lines/11/record');
        check('Record posts the suggested invoice number', rec && bodyOf(rec).invoice_number === 'INV-0001', rec && rec.body);
        rows[1].querySelector('[data-bank-pick]').click();
        await wait(30);
        const pick = sent.find(s => s.url === '/api/bank/lines/12/record');
        check('Choose asks for a number and records it', pick && bodyOf(pick).invoice_number === 'INV-0009');
        rows[2].querySelector('[data-bank-link]').click();
        await wait(30);
        const link = sent.find(s => s.url === '/api/bank/lines/13/link');
        check('Same one links the line to the receipt on the books', link && bodyOf(link).payment_id === 44);
        rows[1].querySelector('[data-bank-ignore]').click();
        await wait(30);
        const ign = sent.find(s => s.url === '/api/bank/lines/12/ignore');
        check('Ignore asks why and posts the note', ign && bodyOf(ign).note === 'INV-0009');
        await w.recordAllBankLines();
        await wait(30);
        check('Record confident matches asks, then posts', sent.some(s => s.url === '/api/bank/record-all'));
    }
    {
        const { w, doc, sent } = boot();
        await w.previewBankStatement('Date,Description,Amount\n14/09/2026,X,1', 'sept.csv');
        await wait(40);
        const dry = sent.find(s => s.url === '/api/bank/import' && /dry_run=1/.test(s.q));
        const real = sent.find(s => s.url === '/api/bank/import' && !/dry_run/.test(s.q));
        check('a file is dry-run first with the chosen account, then imported for real with the same body',
            dry && real && bodyOf(dry).account_id === 2 && bodyOf(real).account_id === 2 && bodyOf(real).filename === 'sept.csv' && bodyOf(real).text.indexOf('14/09/2026') !== -1, dry && dry.body);
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.previewBankStatement('Date,Description,Amount\n14/09/2026,X,1', 'sept.csv');
        await wait(40);
        check('backing out of the confirmation imports nothing', !sent.some(s => s.url === '/api/bank/import' && !/dry_run/.test(s.q)));
    }
    {
        const { w, doc } = boot();
        w.switchBankTab('imports');
        await wait(40);
        const text = doc.getElementById('bank-list').textContent;
        check('the Files tab lists what came in, names as text', /sept\.csv/.test(text) && /HDFC <b>current<\/b>/.test(text) && !doc.getElementById('bank-list').querySelector('b') && /12/.test(text) && doc.querySelector('[data-bank-import-remove="3"]'));
    }
    {
        const { w, doc } = boot({ lines: { counts: {}, unmatched_total: 0, auto: 0, accounts: [], lines: [] } });
        await w.loadBankView();
        await wait(30);
        check('with nothing waiting the page says how to start', /Import a statement/.test(doc.getElementById('bank-list').textContent) && doc.getElementById('bank-record-all').style.display === 'none');
    }
    console.log(failures === 0 ? '\nAll bank-statement checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
