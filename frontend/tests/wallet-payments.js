/**
 * The payment settings that had no screen.
 *
 * Three endpoints existed and nothing in the browser called them. The wallet
 * could top itself up and there was no switch, so the only way to avoid
 * running dry in the middle of a payroll run was to watch the balance by
 * hand. Spending was listed transaction by transaction and never grouped, so
 * "why is this month higher" had no answer. And a customer who had agreed
 * their invoices could be charged automatically could not be seen from
 * anywhere, let alone stopped.
 *
 * Two things are guarded hardest. Turning auto top-up on without a payment
 * method is refused by the server, so the control has to say why rather than
 * let somebody find out by error message. And stopping the wallet's own
 * arrangement also stops it topping itself up - which is not something the
 * word "Stop" conveys on its own.
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

const WITH_METHOD = {
    enabled: true, threshold: '500.00', amount: '2000.00', currency: 'INR',
    balance: '320.00', has_mandate: true,
    mandate: { id: 9, payer_type: 'tenant', payer_ref: '', method: 'card',
               masked: 'card ending 4242', status: 'active', currency: 'INR',
               max_amount: null, created_at: '2026-01-01', last_used_at: '',
               failure_reason: '' },
};
const NO_METHOD = {
    enabled: false, threshold: '0.00', amount: '0.00', currency: 'INR',
    balance: '320.00', has_mandate: false, mandate: null,
};
const USAGE = {
    currency: 'INR', symbol: '₹', total_spent: '1450.00',
    by_action: [
        { action_key: 'invoice_send', units: 120, spent: '1200.00' },
        { action_key: 'payslip_send', units: 25, spent: '250.00' },
    ],
    by_month: [{ month: '2026-07', spent: '600.00' },
               { month: '2026-08', spent: '850.00' }],
};
const MANDATES = {
    own: { id: 9, payer_type: 'tenant', payer_ref: '', method: 'card',
           masked: 'card ending 4242', status: 'active', currency: 'INR',
           max_amount: null, created_at: '2026-01-01', last_used_at: '2026-08-30 10:00:00',
           failure_reason: '' },
    customers: [
        { id: 11, payer_type: 'customer', payer_ref: 'Harbour Co', method: 'bank',
          masked: '****3312', status: 'active', currency: 'GBP', max_amount: '500.00',
          created_at: '2026-02-01', last_used_at: '', failure_reason: '' },
        { id: 12, payer_type: 'customer', payer_ref: 'Bright Ltd', method: 'card',
          masked: 'card ending 1111', status: 'failed', currency: 'GBP',
          max_amount: null, created_at: '2026-03-01', last_used_at: '',
          failure_reason: 'card expired' },
    ],
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };

    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const query = String(url).split('?')[1] || '';
        sent.push({ url: p, query, method: (init && init.method) || 'GET',
                    body: init && init.body });
        const give = b => Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(b) });
        if (p === '/api/auth/me') {
            return give({ user: { email: 'a@b' }, client_id: 1 });
        }
        if (p === '/api/client/me') return give({ id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/wallet/auto-topup') {
            if (init && init.method === 'PUT') {
                return opts.saveError
                    ? Promise.resolve({ ok: false, status: 400,
                        json: () => Promise.resolve({ detail: opts.saveError }) })
                    : give(Object.assign({}, opts.topup || WITH_METHOD,
                                         JSON.parse(init.body)));
            }
            return give(opts.topup || WITH_METHOD);
        }
        if (p === '/api/wallet/usage') return give(opts.usage || USAGE);
        if (p === '/api/autopay/mandates') return give(opts.mandates || MANDATES);
        if (/\/api\/autopay\/mandates\/\d+$/.test(p)) return give({ id: 9, status: 'cancelled' });
        return give(p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

    const toasts = [];
    w.showToast = (m, t) => toasts.push({ m, t });
    return { w, sent, toasts };
}

const el = (w, id) => w.document.getElementById(id);
const text = (w, id) => (el(w, id) || {}).textContent || '';
const called = (sent, p) => sent.filter(s => s.url === p);

(async () => {
    // --- topping itself up --------------------------------------------------
    {
        const { w } = boot();
        await wait(50);
        await w.loadAutoTopUp();
        check('the wallet screen has an automatic top-up control',
            !!el(w, 'autotopup-on'));
        check('showing whether it is on', el(w, 'autotopup-on').checked === true);
        check('and the level it triggers at',
            el(w, 'autotopup-threshold').value === '500.00',
            el(w, 'autotopup-threshold').value);
        check('and how much it adds',
            el(w, 'autotopup-amount').value === '2000.00');
        check('naming the method it will charge',
            /4242/.test(text(w, 'wallet-autotopup')), text(w, 'wallet-autotopup'));
    }

    {
        // The server refuses this outright, so the screen has to say why
        // rather than let somebody discover it by pressing Save.
        const { w } = boot({ topup: NO_METHOD });
        await wait(50);
        await w.loadAutoTopUp();
        check('without a payment method it cannot be switched on',
            el(w, 'autotopup-on').disabled === true);
        check('and says a method is needed first',
            /Authorise a payment method/i.test(text(w, 'wallet-autotopup')),
            text(w, 'wallet-autotopup').slice(0, 120));
    }

    {
        const { w, sent } = boot();
        await wait(50);
        await w.loadAutoTopUp();
        el(w, 'autotopup-threshold').value = '750';
        el(w, 'autotopup-amount').value = '3000';
        await w.saveAutoTopUp();
        await wait(40);
        const put = sent.filter(s => s.url === '/api/wallet/auto-topup' && s.method === 'PUT');
        check('the settings can be saved', put.length === 1);
        const body = put.length ? JSON.parse(put[0].body) : {};
        check('sending both numbers, not just the switch',
            body.threshold === 750 && body.amount === 3000, put[0] && put[0].body);
        check('and whether it is on', body.enabled === true);
    }

    {
        const { w, toasts } = boot({ saveError: 'Set how much to top up by' });
        await wait(50);
        await w.loadAutoTopUp();
        await w.saveAutoTopUp();
        await wait(40);
        check('a refusal from the server is shown rather than swallowed',
            toasts.some(t => /how much to top up/.test(t.m)),
            toasts.map(t => t.m).join(' | '));
    }

    // --- where the credit went -------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(50);
        await w.loadWalletUsage();
        const out = text(w, 'wallet-usage');
        check('the wallet says what the credit was spent on',
            /invoice send/.test(out), out.slice(0, 120));
        check('with the amount per action', /1200\.00/.test(out));
        check('and how many of each', /120/.test(out));
        check('and a total', /1450\.00/.test(out));
        check('broken down by month, which is what makes a jump explainable',
            /2026-08/.test(out) && /850\.00/.test(out), out);
        check('for a period that can be changed',
            /months=/.test((called(sent, '/api/wallet/usage')[0] || {}).query || ''),
            (called(sent, '/api/wallet/usage')[0] || {}).query);
    }

    {
        const { w } = boot({ usage: { currency: 'INR', symbol: '₹',
            total_spent: '0.00', by_action: [], by_month: [] } });
        await wait(50);
        await w.loadWalletUsage();
        check('a period with no spending says so',
            /Nothing spent/.test(text(w, 'wallet-usage')));
    }

    // --- who has agreed to be charged ---------------------------------------------
    {
        const { w } = boot();
        await wait(50);
        await w.loadMandates();
        const out = text(w, 'wallet-mandates');
        check('customers paying automatically are listed',
            /Harbour Co/.test(out), out.slice(0, 160));
        check('with the method, masked', /3312/.test(out));
        check("and the business's own arrangement kept separate",
            /Your own/.test(out) && /Topping up this wallet/.test(out));
        // A failed one is why a payment that used to go through has stopped.
        check('one that has failed says so, and why',
            /failed/.test(out) && /card expired/.test(out), out);
    }

    {
        const { w } = boot({ mandates: { own: null, customers: [] } });
        await wait(50);
        await w.loadMandates();
        check('nobody paying automatically says so',
            /Nobody has agreed/.test(text(w, 'wallet-mandates')));
    }

    // --- stopping one ------------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(50);
        await w.loadMandates();
        let asked = null;
        w.uiConfirm = (m) => { asked = m; return Promise.resolve(false); };
        await w.cancelMandate(MANDATES.customers[0], 'Harbour Co');
        await wait(40);
        check('stopping one asks first', !!asked, asked);
        check('naming who it affects', /Harbour Co/.test(asked || ''), asked);
        check('and nothing is sent when the answer is no',
            sent.filter(s => s.method === 'DELETE').length === 0);
    }

    {
        // Stopping the wallet's own arrangement also stops it topping itself
        // up, which "Stop" does not convey.
        const { w } = boot();
        await wait(50);
        await w.loadMandates();
        let asked = null;
        w.uiConfirm = (m) => { asked = m; return Promise.resolve(false); };
        await w.cancelMandate(MANDATES.own, 'Topping up this wallet');
        await wait(40);
        check('stopping your own says top-up stops with it',
            /top-up will stop/i.test(asked || ''), asked);
    }

    {
        const { w, sent } = boot();
        await wait(50);
        await w.loadMandates();
        w.uiConfirm = () => Promise.resolve(true);
        await w.cancelMandate(MANDATES.customers[0], 'Harbour Co');
        await wait(40);
        const gone = sent.filter(s => s.method === 'DELETE');
        check('agreeing stops it', gone.length === 1);
        check('the right one', /\/mandates\/11$/.test(gone[0].url), gone[0] && gone[0].url);
    }

    // --- all three load with the wallet --------------------------------------------------
    {
        const { sent } = boot();
        await wait(50);
        const { w } = boot();
        await wait(50);
        await w.loadWallet();
        await wait(60);
        const asked = sent.concat([]);
        void asked;
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const block = src.slice(src.indexOf('async function loadWallet()'),
                                src.indexOf('window.loadWallet'));
        ['loadAutoTopUp', 'loadWalletUsage', 'loadMandates'].forEach(fn => {
            check(`${fn} runs when the wallet is opened`, block.includes(fn + '()'));
        });
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
