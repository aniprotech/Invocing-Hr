/**
 * The decisions waiting on a manager.
 *
 * Leave and attendance corrections could only ever be decided by HR - both
 * endpoints take the business account - so every request in a company
 * funnelled through one desk, and the person who actually knows whether
 * somebody can be spared that week had no say and no view of it.
 *
 * The thing this screen has to get right is the number beside the decision.
 * Approving leave without knowing what is left of somebody's entitlement is
 * the decision people get wrong, and it is the one the server can work out
 * and the manager cannot.
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

const WAITING = {
    count: 2,
    leave: [{
        id: 5, employee_id: 2, employee: 'Sam Mine', leave_type: 'annual',
        days: 3, start_date: '2026-11-02', end_date: '2026-11-04',
        reason: 'Family visit', requested_at: '2026-10-01 09:00:00',
        annual_remaining: 12, sick_remaining: 5,
    }],
    corrections: [{
        id: 9, employee_id: 3, employee: 'Lee Hours', date: '2026-10-05',
        was: '09:00:00 to -', asked_for: '09:00:00 to 17:30:00',
        reason: 'Forgot to clock out', requested_at: '2026-10-06 08:00:00',
    }],
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
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET',
                            body: init && init.body });
                const give = b => Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(b) });
                if (p === '/api/employee/approvals') {
                    if (opts.fails) {
                        return Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({}) });
                    }
                    return give(opts.waiting === undefined ? WAITING : opts.waiting);
                }
                if (/\/api\/employee\/approvals\//.test(p)) {
                    if (opts.refused) {
                        return Promise.resolve({ ok: false, status: 400,
                            json: () => Promise.resolve({
                                detail: 'Approving this would exceed the annual entitlement (25 days)' }) });
                    }
                    return give({ ok: true });
                }
                return give(p.endsWith('s') ? [] : {});
            };
            w.alert = m => alerts.push(String(m));
        },
    });
    return { w: dom.window, doc: dom.window.document, sent, alerts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- a manager with decisions to make -------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadApprovals();
        await wait(30);

        check('the portal asks for them at all',
            sent.some(s => s.url === '/api/employee/approvals'),
            'the endpoint would stay unreachable');
        check('and shows the card', doc.getElementById('approvalsCard').hidden === false);

        const rows = [...doc.querySelectorAll('#approvals > div')];
        check('both kinds are listed together', rows.length === 2, rows.length);
        check('  leave says who and how long',
            /Sam Mine/.test(rows[0].textContent) && /3 day/.test(rows[0].textContent),
            rows[0].textContent);
        check('  and when',
            /2026-11-02/.test(rows[0].textContent) && /2026-11-04/.test(rows[0].textContent));

        // The number the manager cannot work out and the server can.
        check('  and what it leaves them with',
            /12 day\(s\) of annual leave left/.test(rows[0].textContent),
            rows[0].textContent);
        check('  and why they asked',
            /Family visit/.test(rows[0].textContent));

        check('a correction shows the change being asked for',
            /09:00:00 to -/.test(rows[1].textContent) &&
            /17:30:00/.test(rows[1].textContent),
            rows[1].textContent);
        check('  on the day it is about',
            /2026-10-05/.test(rows[1].textContent));
    }

    // --- sick leave reads its own balance, not the annual one --------------------
    {
        const { w, doc } = boot({ waiting: {
            count: 1, corrections: [],
            leave: [Object.assign({}, WAITING.leave[0], {
                leave_type: 'sick', annual_remaining: 12, sick_remaining: 4 })],
        } });
        await w.loadApprovals();
        await wait(30);
        const text = doc.querySelector('#approvals > div').textContent;
        check('sick leave is measured against sick leave',
            /4 day\(s\) of sick leave left/.test(text), text);
    }

    // --- most people are not managers ---------------------------------------------
    {
        const { w, doc } = boot({ waiting: { count: 0, leave: [], corrections: [] } });
        await w.loadApprovals();
        await wait(30);
        check('somebody with nothing to decide sees no card',
            doc.getElementById('approvalsCard').hidden === true);
    }

    {
        const { w, doc } = boot({ fails: true });
        await w.loadApprovals();
        await wait(30);
        check('a failed load hides the card rather than showing a broken one',
            doc.getElementById('approvalsCard').hidden === true);
    }

    // --- deciding --------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadApprovals();
        await wait(30);
        doc.querySelectorAll('#approvals > div')[0]
           .querySelectorAll('button')[0].click();
        await wait(30);

        const call = sent.find(s => s.method === 'POST' && /approvals\/leave\//.test(s.url));
        check('approving leave reaches the leave endpoint', !!call,
            sent.map(s => s.method + ' ' + s.url).join(', '));
        check('  for that request', !!call && /\/5$/.test(call.url), call && call.url);
        check('  as an approval', !!call && bodyOf(call).action === 'approve',
            call && call.body);
        check('  and the list is read back',
            sent.filter(s => s.url === '/api/employee/approvals').length === 2);
    }

    {
        const { w, doc, sent } = boot();
        await w.loadApprovals();
        await wait(30);
        doc.querySelectorAll('#approvals > div')[0]
           .querySelectorAll('button')[1].click();
        await wait(30);
        const call = sent.find(s => s.method === 'POST' && /approvals\/leave\//.test(s.url));
        check('declining sends a rejection', !!call && bodyOf(call).action === 'reject',
            call && call.body);
    }

    {
        const { w, doc, sent } = boot();
        await w.loadApprovals();
        await wait(30);
        doc.querySelectorAll('#approvals > div')[1]
           .querySelectorAll('button')[0].click();
        await wait(30);
        const call = sent.find(s => s.method === 'POST' && /approvals\/correction\//.test(s.url));
        check('a correction goes to the correction endpoint', !!call && /\/9$/.test(call.url),
            call && call.url);
        check('  which takes a decision, not an action',
            !!call && bodyOf(call).decision === 'approve', call && call.body);
    }

    // --- when the server says no ---------------------------------------------------------
    {
        const { w, doc, alerts } = boot({ refused: true });
        await w.loadApprovals();
        await wait(30);
        doc.querySelectorAll('#approvals > div')[0]
           .querySelectorAll('button')[0].click();
        await wait(30);
        check('a refused approval says why', alerts.length === 1, alerts.join(' | '));
        // "Would exceed the entitlement" and "somebody already decided this"
        // need different things done about them.
        check('  in the words the server used',
            /exceed the annual entitlement/.test(alerts[0] || ''), alerts[0]);
    }

    // --- and it is wired into the page ------------------------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the overview tab loads it', /loadApprovals\(\);/.test(src));
        check('the card is in the markup', /id="approvalsCard"/.test(src));
    }

    console.log(failures === 0
        ? '\nAll manager-approval checks passed.'
        : `\n${failures} manager-approval check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
