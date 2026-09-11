/**
 * Claiming money back, as rendered.
 *
 * Somebody paid for something out of their own pocket. The form has to make
 * that easy to say, the list has to show where each claim got to and why,
 * and the one number they open this to see - what they are owed - has to be
 * what has been agreed and not yet paid, not what is still waiting and may
 * be refused.
 *
 * The receipt is a picture somebody uploads and HR's browser then renders,
 * so the page checks it the same way the feed does before the server does
 * it again.
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

const MINE = {
    currency: 'GBP', owed: 45.5, owed_minor: 4550, pending: 1,
    claims: [
        { id: 3, category: 'travel', amount: 12.3, amount_minor: 1230, currency: 'GBP',
          spent_on: '2026-09-10', description: 'Train to the client', has_receipt: true,
          status: 'pending', decided_by: '', decision_note: '', paid_at: '',
          can_withdraw: true },
        { id: 2, category: 'meals', amount: 45.5, amount_minor: 4550, currency: 'GBP',
          spent_on: '2026-09-08', description: 'Client lunch', has_receipt: false,
          status: 'approved', decided_by: 'Dana Boss', decision_note: '', paid_at: '',
          can_withdraw: false },
        { id: 1, category: 'equipment', amount: 8, amount_minor: 800, currency: 'GBP',
          spent_on: '2026-09-01', description: 'HDMI cable', has_receipt: false,
          status: 'rejected', decided_by: 'Dana Boss', decision_note: 'Order through IT next time',
          paid_at: '', can_withdraw: false },
    ],
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const alerts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.alert = m => alerts.push(String(m));
            w.confirm = () => opts.confirm !== false;
            w.prompt = () => opts.promptText === undefined ? 'No receipt' : opts.promptText;
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body });
                const give = (b, status) => Promise.resolve({
                    ok: !status || status < 400, status: status || 200,
                    json: () => Promise.resolve(b) });
                if (p === '/api/employee/expenses' && method === 'GET') {
                    return give(opts.mine === undefined ? MINE : opts.mine);
                }
                if (p === '/api/employee/expenses' && method === 'POST') {
                    if (opts.submitFails) return give({ detail: 'That date is in the future' }, 400);
                    return give({ id: 9 });
                }
                if (/\/api\/employee\/expenses\/\d+$/.test(p) && method === 'DELETE') {
                    if (opts.withdrawFails) return give({ detail: 'This has already been approved and cannot be withdrawn' }, 409);
                    return give({ withdrawn: 3 });
                }
                if (p === '/api/employee/approvals') {
                    return give(opts.approvals || { count: 0, leave: [], corrections: [], expenses: [] });
                }
                if (/\/api\/employee\/approvals\/expense\//.test(p)) return give({ ok: true });
                return give(p.endsWith('s') ? [] : {});
            };
        },
    });
    return { w: dom.window, doc: dom.window.document, sent, alerts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- the tab exists ---------------------------------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('there is an Expenses tab', /data-tab="expenses"/.test(src) && /id="tab-expenses"/.test(src));
        check('switching to it loads the claims', /tab === 'expenses'\)\s*loadExpenses\(\)/.test(src));
    }

    // --- my claims ----------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadExpenses();
        await wait(30);
        const rows = [...doc.querySelectorAll('#exp-list > div')];
        check('every claim is listed', rows.length === 3, rows.length);
        check('the amount is money, not a number',
            /£12\.30/.test(rows[0].textContent), rows[0].textContent);
        check('  and what it was for', /Train to the client/.test(rows[0].textContent));
        check('  and where it got to', /Waiting/.test(rows[0].textContent));
        check('an approved one says who approved it',
            /Approved/.test(rows[1].textContent) && /Dana Boss/.test(rows[1].textContent));
        check('a declined one says why',
            /Declined/.test(rows[2].textContent) && /Order through IT next time/.test(rows[2].textContent),
            rows[2].textContent);

        // What has been agreed and not yet paid. Not the pending one.
        check('what I am owed is the approved amount only',
            /Owed to you: £45\.50/.test(doc.getElementById('exp-owed').textContent),
            doc.getElementById('exp-owed').textContent);

        check('a receipt is a link to the receipt',
            (rows[0].querySelector('a[href="/api/employee/expenses/3/receipt"]') || {}).target === '_blank');
        check('  and a claim without one has no link', !rows[1].querySelector('a'));
        check('only a waiting claim offers Withdraw',
            !!rows[0].querySelector('button') && !rows[1].querySelector('button') && !rows[2].querySelector('button'));
    }
    {
        const { w, doc } = boot({ mine: { currency: 'GBP', owed: 0, owed_minor: 0, pending: 0, claims: [] } });
        await w.loadExpenses();
        await wait(30);
        check('with nothing owed, nothing is said about it', doc.getElementById('exp-owed').textContent === '');
        check('and an empty list says so', /No claims yet/.test(doc.getElementById('exp-list').textContent));
    }

    // --- sending one ------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadExpenses();
        await wait(30);
        check('the date defaults to today', /^\d{4}-\d{2}-\d{2}$/.test(doc.getElementById('exp-date').value));

        doc.getElementById('exp-category').value = 'meals';
        doc.getElementById('exp-amount').value = '7.85';
        doc.getElementById('exp-date').value = '2026-09-11';
        doc.getElementById('exp-desc').value = 'Coffee with the supplier';
        doc.getElementById('expense-form').dispatchEvent(
            new w.Event('submit', { bubbles: true, cancelable: true }));
        await wait(40);

        const call = sent.find(s => s.url === '/api/employee/expenses' && s.method === 'POST');
        check('submitting posts the claim', !!call, sent.map(s => s.method + ' ' + s.url).join(', '));
        const b = bodyOf(call || {});
        check('  with everything typed',
            b.category === 'meals' && b.amount === '7.85' && b.spent_on === '2026-09-11' &&
            b.description === 'Coffee with the supplier', JSON.stringify(b));
        check('  and the amount as typed, not as a float', b.amount === '7.85');
        check('  and no receipt when none was chosen', b.receipt_data === '');
        check('the form clears after', doc.getElementById('exp-amount').value === '' && doc.getElementById('exp-desc').value === '');
        check('and the list is read back', sent.filter(s => s.url === '/api/employee/expenses' && s.method === 'GET').length === 2);
    }
    {
        const { w, doc, sent } = boot();
        await w.loadExpenses();
        await wait(30);
        doc.getElementById('exp-desc').value = 'x';
        doc.getElementById('expense-form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
        await wait(20);
        // The page boots with POSTs of its own (a heartbeat), so the check is
        // that no claim went, not that nothing did.
        check('no amount is stopped on the page',
            !sent.some(s => s.method === 'POST' && s.url === '/api/employee/expenses'));
        check('  and told why', /amount/.test(doc.getElementById('exp-error').textContent));
    }
    {
        const { w, doc } = boot({ submitFails: true });
        await w.loadExpenses();
        await wait(30);
        doc.getElementById('exp-amount').value = '5';
        doc.getElementById('exp-desc').value = 'x';
        doc.getElementById('expense-form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
        await wait(40);
        check('a refusal shows the reason the server gave',
            /in the future/.test(doc.getElementById('exp-error').textContent),
            doc.getElementById('exp-error').textContent);
    }

    // --- the receipt is checked before it is sent ---------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadExpenses();
        await wait(30);
        const input = doc.getElementById('exp-receipt');
        const svg = new w.File(['<svg/>'], 'r.svg', { type: 'image/svg+xml' });
        Object.defineProperty(input, 'files', { value: [svg], configurable: true });
        input.dispatchEvent(new w.Event('change', { bubbles: true }));
        await wait(20);
        check('an SVG receipt is refused on the page', /PNG, JPEG, GIF or WebP/.test(doc.getElementById('exp-error').textContent));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadExpenses();
        await wait(30);
        const input = doc.getElementById('exp-receipt');
        const png = new w.File([new Uint8Array([137, 80, 78, 71])], 'r.png', { type: 'image/png' });
        Object.defineProperty(input, 'files', { value: [png], configurable: true });
        input.dispatchEvent(new w.Event('change', { bubbles: true }));
        await wait(60);
        doc.getElementById('exp-amount').value = '3';
        doc.getElementById('exp-desc').value = 'Parking';
        doc.getElementById('expense-form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
        await wait(40);
        const call = sent.find(s => s.url === '/api/employee/expenses' && s.method === 'POST');
        check('a PNG receipt goes with the claim', !!call && /^data:image\/png;base64,/.test(bodyOf(call).receipt_data));
    }

    // --- withdrawing ------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadExpenses();
        await wait(30);
        doc.querySelector('#exp-list > div button').click();
        await wait(30);
        check('withdrawing sends a DELETE for that claim',
            sent.some(s => s.url === '/api/employee/expenses/3' && s.method === 'DELETE'));
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.loadExpenses();
        await wait(30);
        doc.querySelector('#exp-list > div button').click();
        await wait(30);
        check('but not without asking', !sent.some(s => s.method === 'DELETE'));
    }
    {
        const { w, doc, alerts } = boot({ withdrawFails: true });
        await w.loadExpenses();
        await wait(30);
        doc.querySelector('#exp-list > div button').click();
        await wait(30);
        check('a refused withdrawal says why', alerts.length === 1 && /already been approved/.test(alerts[0]), alerts.join('|'));
    }

    // --- on the manager's list ---------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ approvals: {
            count: 1, leave: [], corrections: [],
            expenses: [{ id: 7, employee: 'Sam Mine', category: 'travel', amount: 33.5, currency: 'GBP',
                         spent_on: '2026-09-10', description: 'Taxi from the station', has_receipt: true }],
        } });
        await w.loadApprovals();
        await wait(30);
        const row = doc.querySelector('#approvals > div');
        check('an expense claim appears on the approvals card', !!row);
        check('  saying who, how much and what for',
            /Sam Mine/.test(row.textContent) && /£33\.50/.test(row.textContent) && /Taxi from the station/.test(row.textContent),
            row.textContent);
        check('  and whether there is a receipt', /Receipt attached/.test(row.textContent));

        row.querySelectorAll('button')[1].click();      // Decline
        await wait(30);
        const call = sent.find(s => /approvals\/expense\/7$/.test(s.url));
        check('declining sends the decision', !!call && bodyOf(call).action === 'reject');
        check('  with the reason asked for', !!call && bodyOf(call).note === 'No receipt', call && call.body);
    }

    // --- HR has a screen for it too ------------------------------------------------------------------------
    {
        const hr = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const js = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        check('the HR app has an Expenses view', /id="expenses-view"/.test(hr) && /id="nav-expenses"/.test(hr));
        check('  routed', /'expenses-view': 'expenses'/.test(js));
        check('  and loaded when shown', /viewId === 'expenses-view'\)\s*loadExpensesView\(\)/.test(js));
        check('  with a way to mark a claim paid', /markExpensePaid/.test(js) && /\/paid'/.test(js));
    }

    console.log(failures === 0
        ? '\nAll expense-claim checks passed.'
        : `\n${failures} expense-claim check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
