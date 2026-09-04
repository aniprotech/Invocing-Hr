/**
 * Money the platform is holding that belongs to somebody else.
 *
 * In platform mode every customer payment lands in our own Razorpay account,
 * so each one is a debt to the business that raised the invoice until it is
 * paid out. The endpoints for all of that existed and nothing called them:
 * the only way to know what was owed, or to record that it had been sent, was
 * to read the table by hand.
 *
 * The part worth guarding hardest is the payout reference. It is the only
 * record that the money actually left, so the screen must not let somebody
 * mark a debt settled without one.
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

const OWED = [
    { id: 7, client_id: 3, business: 'Bright Ltd', invoice_number: 'INV-0041',
      amount: '1240.00', currency: 'INR', status: 'owed',
      collected_at: '2026-09-01 10:22:00', paid_out_at: '', payout_reference: '',
      gateway_payment_id: 'pay_abc' },
    { id: 6, client_id: 4, business: 'Harbour Co', invoice_number: 'INV-0040',
      amount: '85.50', currency: 'GBP', status: 'owed',
      collected_at: '2026-08-30 09:00:00', paid_out_at: '', payout_reference: '',
      gateway_payment_id: 'pay_xyz' },
];
const SETTLED = [
    { id: 5, client_id: 3, business: 'Bright Ltd', invoice_number: 'INV-0039',
      amount: '300.00', currency: 'INR', status: 'paid_out',
      collected_at: '2026-08-01 10:00:00', paid_out_at: '2026-08-03 12:00:00',
      payout_reference: 'NEFT-99812', gateway_payment_id: 'pay_old' },
];
const MODE = {
    mode: 'platform', modes: ['direct', 'platform'], platform_keys_ready: true,
    platform_key_env: ['RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET'],
    owed_to_tenants: [{ currency: 'GBP', amount: '85.50' },
                      { currency: 'INR', amount: '1240.00' }],
    owed_count: 2,
    note: 'In platform mode every customer payment lands in the platform account.',
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const sent = [];
    const alerts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const query = String(url).split('?')[1] || '';
                sent.push({ url: p, query, method: (init && init.method) || 'GET',
                            body: init && init.body });
                if (p === '/api/superadmin/me') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ username: 'op', email: 'op@x' }) });
                }
                if (p === '/api/superadmin/settlements') {
                    const rows = opts.rows !== undefined ? opts.rows
                        : (/status=paid_out/.test(query) ? SETTLED : OWED);
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ settlements: rows }) });
                }
                if (p === '/api/superadmin/collection-mode') {
                    if (init && init.method === 'PUT') {
                        return opts.saveError
                            ? Promise.resolve({ ok: false, status: 400,
                                json: () => Promise.resolve({ detail: opts.saveError }) })
                            : Promise.resolve({ ok: true, status: 200,
                                json: () => Promise.resolve({ mode: 'platform' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve(
                            Object.assign({}, MODE, opts.mode || {})) });
                }
                if (/\/paid-out$/.test(p)) {
                    return opts.payoutError
                        ? Promise.resolve({ ok: false, status: 400,
                            json: () => Promise.resolve({ detail: opts.payoutError }) })
                        : Promise.resolve({ ok: true, status: 200,
                            json: () => Promise.resolve({ id: 7, status: 'paid_out' }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(p.endsWith('s') ? [] : {}) });
            };
            w.alert = m => alerts.push(m);
            w.confirm = () => true;
            w.prompt = () => (opts.typed === undefined ? 'NEFT-12345' : opts.typed);
        },
    });
    const w = dom.window;
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    return { w, sent, alerts };
}

const list = w => w.document.getElementById('settlements-list');
const payouts = sent => sent.filter(s => /\/paid-out$/.test(s.url));

(async () => {
    // --- it is reachable at all -------------------------------------------------
    {
        const { w } = boot();
        check('the operator panel has a settlements section', !!list(w));
        check('and it loads with the rest of the billing tab',
            /billing:.*loadSettlements/.test(
                fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8')));
    }

    // --- what is owed ---------------------------------------------------------------
    {
        const { w } = boot();
        await w.loadSettlements();
        await wait(40);
        const text = list(w).textContent;
        check('the money owed is listed', /Bright Ltd/.test(text) && /Harbour Co/.test(text));
        check('with the amount and its currency, not a bare number',
            /1240\.00 INR/.test(text) && /85\.50 GBP/.test(text), text.slice(0, 140));
        check('and which invoice it came from', /INV-0041/.test(text));
        check('marked as owed rather than left ambiguous', /Owed/.test(text));
        check('with a way to record that it was sent', /Mark paid out/.test(text));
    }

    // --- the total, which is the number that matters ----------------------------------
    {
        const { w } = boot();
        await w.loadSettlements();
        await wait(40);
        const box = w.document.getElementById('collection-mode-box').textContent;
        check('the total owed is shown, per currency',
            /85\.50 GBP/.test(box) && /1240\.00 INR/.test(box), box.slice(0, 160));
        check('and how many payments make it up', /2 payments/.test(box), box);
        check('with what platform mode means said out loud',
            /lands in the platform account/i.test(box));
    }

    // --- the reference, which is the whole point -----------------------------------------
    {
        const { w, sent } = boot({ typed: 'NEFT-12345' });
        await w.loadSettlements();
        await wait(40);
        await w.markSettlementPaid(OWED[0]);
        await wait(40);
        const posted = payouts(sent);
        check('marking it paid out records the reference', posted.length === 1);
        check('and sends what was typed',
            JSON.parse(posted[0].body).reference === 'NEFT-12345',
            posted[0] && posted[0].body);
        check('to the right settlement', /\/7\/paid-out$/.test(posted[0].url),
            posted[0].url);
    }

    {
        // The reference is the only record that the money left. An empty one
        // would mark a debt settled with nothing behind it.
        const { w, sent, alerts } = boot({ typed: '   ' });
        await w.loadSettlements();
        await wait(40);
        await w.markSettlementPaid(OWED[0]);
        await wait(40);
        check('an empty reference does not settle anything',
            payouts(sent).length === 0);
        check('and says why', /reference/i.test(alerts.join(' ')), alerts.join(' | '));
    }

    {
        const { w, sent } = boot({ typed: null });   // cancelled
        await w.loadSettlements();
        await wait(40);
        await w.markSettlementPaid(OWED[0]);
        await wait(40);
        check('and changing your mind sends nothing at all',
            payouts(sent).length === 0);
    }

    {
        const { w, alerts } = boot({ payoutError: 'Already marked paid out' });
        await w.loadSettlements();
        await wait(40);
        await w.markSettlementPaid(OWED[0]);
        await wait(40);
        check('a refusal from the server is shown rather than swallowed',
            /Already marked paid out/.test(alerts.join(' ')), alerts.join(' | '));
    }

    // --- what has already been paid ----------------------------------------------------
    {
        const { w } = boot({ rows: SETTLED });
        await w.loadSettlements();
        await wait(40);
        const text = list(w).textContent;
        check('a settled one shows its reference, which is the proof',
            /NEFT-99812/.test(text), text.slice(0, 140));
        check('and offers no button to settle it twice',
            !/Mark paid out/.test(text));
    }

    {
        const { w } = boot({ rows: [] });
        await w.loadSettlements();
        await wait(40);
        check('nothing owed says so plainly',
            /Nothing is owed/.test(list(w).textContent), list(w).textContent);
    }

    // --- where the money lands ------------------------------------------------------------
    {
        const { w, sent } = boot();
        await w.loadSettlements();
        await wait(40);
        const pick = w.document.getElementById('collection-mode-pick');
        check('the collection mode can be seen', !!pick);
        check('and reflects what is in force', pick.value === 'platform', pick.value);

        pick.value = 'direct';
        await w.saveCollectionMode();
        await wait(40);
        const put = sent.filter(s => s.url === '/api/superadmin/collection-mode'
                                     && s.method === 'PUT');
        check('and can be changed', put.length === 1);
        check('sending the mode that was chosen',
            put.length && JSON.parse(put[0].body).mode === 'direct',
            put[0] && put[0].body);
    }

    {
        // Switching to platform mode without keys is refused by the server;
        // saying so first saves finding out by error message.
        const { w } = boot({ mode: { platform_keys_ready: false } });
        await w.loadSettlements();
        await wait(40);
        const box = w.document.getElementById('collection-mode-box').textContent;
        check('missing platform keys are called out before anybody tries',
            /RAZORPAY_KEY_ID/.test(box), box.slice(0, 160));
    }

    {
        const { w, alerts } = boot({ saveError: 'Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET first' });
        await w.loadSettlements();
        await wait(40);
        await w.saveCollectionMode();
        await wait(40);
        check('and a refused change is reported',
            /RAZORPAY_KEY_ID/.test(alerts.join(' ')), alerts.join(' | '));
    }

    // --- the filters ----------------------------------------------------------------------
    {
        const { w, sent } = boot();
        await w.loadSettlements();
        await wait(40);
        await w.setSettlementFilter('paid_out');
        await wait(40);
        const asked = sent.filter(s => s.url === '/api/superadmin/settlements');
        check('the list can be narrowed to what has been paid',
            /status=paid_out/.test(asked[asked.length - 1].query),
            asked[asked.length - 1].query);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
