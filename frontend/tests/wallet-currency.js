/**
 * Changing a wallet's currency from the operator screen.
 *
 * The endpoint existed for a while with no button on it, so the only way to put
 * a wallet into INR - which Razorpay needs - was a hand-written API call. The
 * control now sits under the balance it applies to.
 *
 * The rule it has to respect: a balance is a count of minor units of one
 * currency, so it can only be switched while the wallet is empty. The server
 * enforces that; the point of testing the page is that it says so up front
 * rather than letting somebody discover it by pressing the button.
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

function boot(wallet, opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
    });
    const w = dom.window;
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });

        if (p.endsWith('/transactions')) {
            return Promise.resolve({
                ok: true, status: 200, json: () => Promise.resolve({
                    client: { name: 'Acme Ltd', email: 'acme@example.com' },
                    balance: wallet.balance, currency: wallet.currency, transactions: [],
                }),
            });
        }
        if (p.endsWith('/razorpay-check')) {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve(opts.check || { ok: true, reason: 'These test keys work.' }),
            });
        }
        if (p.endsWith('/currency')) {
            const bad = opts.refuse;
            return Promise.resolve({
                ok: !bad, status: bad ? 409 : 200,
                json: () => Promise.resolve(bad ? { detail: opts.refuse } : { currency: 'INR', changed: true }),
            });
        }
        // The rest of the page loads on boot too. These are stubbed only far
        // enough to keep its own error handling quiet, so a real failure here
        // still stands out.
        const rest = {
            '/api/superadmin/insights': {
                total_clients: 0, active_clients: 0, total_invoices: 0, total_outstanding: 0,
            },
            '/api/superadmin/trends': {
                months: [], revenue: [], active_users: [], total_revenue: 0,
            },
        };
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(rest[p] || (p.endsWith('s') ? [] : {})),
        });
    };

    // The whole page script is inline, so it is pulled out and run rather than
    // loaded - the same thing the browser does.
    const scripts = [...dom.window.document.querySelectorAll('script')]
        .filter(s => !s.src).map(s => s.textContent).join('\n');
    w.eval(scripts);
    return { w, sent };
}

(async () => {
    // --- an empty wallet can be switched -------------------------------------
    {
        const { w, sent } = boot({ balance: 0, currency: 'GBP' });
        await w.adjustWallet(7);
        await wait(20);

        const sel = w.document.getElementById('wallet-currency');
        check('an empty wallet offers a currency picker', !!sel);
        check('INR is one of the choices',
            !!sel && [...sel.options].some(o => o.value === 'INR'));
        check('it starts on the currency the wallet is already in',
            !!sel && sel.value === 'GBP', sel && sel.value);

        sel.value = 'INR';
        await w.applyWalletCurrency();
        await wait(20);

        const put = sent.find(r => r.method === 'PUT');
        check('changing it sends a PUT for that wallet',
            !!put && put.url === '/api/superadmin/wallets/7/currency', put && put.url);
        check('and asks for the currency that was picked',
            !!put && JSON.parse(put.body).currency === 'INR');
    }

    // --- a wallet holding money says why not ---------------------------------
    {
        const { w, sent } = boot({ balance: 42.5, currency: 'GBP' });
        await w.adjustWallet(7);
        await wait(20);

        const body = w.document.getElementById('wallet-panel-body').textContent;
        check('a wallet with money in it shows no picker',
            !w.document.getElementById('wallet-currency'));
        check('and says what has to happen first',
            /zero/i.test(body), body.slice(0, 160));
        check('naming the currency it is stuck in', body.includes('GBP'));
        check('nothing was sent', !sent.some(r => r.method === 'PUT'));
    }

    // --- a refusal is shown, not swallowed -----------------------------------
    {
        const { w } = boot({ balance: 0, currency: 'GBP' },
            { refuse: 'This wallet holds 12.00 GBP. Adjust it to zero first' });
        await w.adjustWallet(7);
        await wait(20);
        w.document.getElementById('wallet-currency').value = 'INR';
        await w.applyWalletCurrency();
        await wait(20);

        const note = w.document.getElementById('wallet-currency-note');
        check("the server's reason reaches the screen",
            !!note && note.textContent.includes('Adjust it to zero first'),
            note && note.textContent);
    }

    // --- picking what it already is does nothing -----------------------------
    {
        const { w, sent } = boot({ balance: 0, currency: 'INR' });
        await w.adjustWallet(7);
        await wait(20);
        await w.applyWalletCurrency();
        await wait(20);

        check('re-picking the current currency sends nothing',
            !sent.some(r => r.method === 'PUT'));
        check('and says so',
            /already/i.test(w.document.getElementById('wallet-currency-note').textContent));
    }

    // --- the key check, on a button rather than a URL ------------------------
    {
        const { w } = boot({ balance: 0, currency: 'INR' }, {
            check: {
                ok: false, status: 401,
                reason: 'Razorpay rejected the keys. Check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.',
                shape: { mode: 'test', key_id_tail: 'NCj', secret_length: 20,
                         notes: ['The secret is 20 characters; Razorpay secrets are 24.'] },
                hint: 'Regenerating a key replaces both halves.',
            },
        });
        await w.checkRazorpayKeys();
        await wait(20);

        const out = w.document.getElementById('razorpay-check').textContent;
        check('a rejection says what Razorpay said', out.includes('rejected the keys'), out);
        check('the keys are described without being shown',
            out.includes('test keys') && out.includes('NCj') && !out.includes('rzp_test_'), out);
        check('a suspicious secret length is called out', /24/.test(out), out);
        check('and the rotation trap is spelled out', /both halves/.test(out), out);
    }

    {
        const { w } = boot({ balance: 0, currency: 'INR' }, {
            check: { ok: true, reason: 'These test keys work.',
                     shape: { mode: 'test', key_id_tail: 'NCj', secret_length: 24, notes: [] } },
        });
        await w.checkRazorpayKeys();
        await wait(20);
        const el = w.document.getElementById('razorpay-check');
        check('working keys say so plainly', /work/.test(el.textContent), el.textContent);
        check('and are not coloured as a failure', el.style.color !== 'rgb(255, 0, 60)', el.style.color);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
