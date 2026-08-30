/**
 * Surviving a response that is not the shape the caller expected.
 *
 * loadWallet's try/catch covered the fetch and nothing after it, so four
 * unguarded .toFixed() calls ran outside any handler. A 200 carrying an
 * unexpected shape - a partial response, a renamed field, an error body served
 * with the wrong status - threw an uncaught TypeError part way through the
 * render, and everything queued behind it never ran.
 *
 * That is not hypothetical here: the same shape of bug took the invoice PDF
 * preview and the emailed attachment down together once already, because both
 * called the one generator that threw.
 *
 * The point is not that the server sends bad data. It is that one endpoint
 * having a bad day should cost one panel, not the page.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');
const APPJS = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

// Uncaught throws inside jsdom callbacks land on the process, not in a catch
// here, so they are collected rather than allowed to end the run.
const thrown = [];
process.on('uncaughtException', e => thrown.push(String(e.message)));
process.on('unhandledRejection', e => thrown.push('rejection: ' + String(e && e.message)));

function boot(bodies) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = Object.prototype.hasOwnProperty.call(bodies, p)
            ? bodies[p]
            : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(APPJS);
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return w;
}

(async () => {
    // --- the wallet ----------------------------------------------------------
    // Every one of these is a 200. None of them carries the numbers the tiles
    // are built from.
    const badWallets = {
        'an empty object': {},
        'nulls where numbers go': {
            balance: null, lifetime_spent: null, lifetime_topped_up: null, low_balance: null,
        },
        'an error body served as 200': { detail: 'Something went wrong' },
        'strings instead of numbers': {
            balance: '25.00', lifetime_spent: 'n/a', lifetime_topped_up: '', low_balance: '5',
        },
    };

    for (const [name, body] of Object.entries(badWallets)) {
        thrown.length = 0;
        const w = boot({ '/api/wallet': body });
        await wait(60);
        w.showView('wallet-view');
        await wait(120);

        check(`the wallet survives ${name}`, thrown.length === 0, thrown[0]);

        const stats = w.document.getElementById('wallet-stats');
        check(`  and still renders its four tiles`,
            !!stats && stats.querySelectorAll('.stat-card').length === 4,
            stats && String(stats.querySelectorAll('.stat-card').length));
        check(`  showing a figure rather than a blank`,
            !!stats && /\d/.test(stats.textContent), stats && stats.textContent.slice(0, 60));
    }

    // A number that did arrive is still shown as itself.
    {
        const w = boot({
            '/api/wallet': {
                symbol: '₹', balance: 250, lifetime_spent: 12.5,
                lifetime_topped_up: 300, low_balance: 5,
            },
        });
        await wait(60);
        w.showView('wallet-view');
        await wait(120);
        const text = w.document.getElementById('wallet-stats').textContent;
        check('a real balance is unchanged by the guard',
            text.includes('250.00') && text.includes('12.50'), text.slice(0, 80));
    }

    // --- lists that arrive as something else ---------------------------------
    {
        thrown.length = 0;
        const w = boot({ '/api/onboarding/hub': { detail: 'nope' } });
        await wait(60);
        w.showView('onboarding-hub-view');
        await wait(120);
        check('the onboarding hub survives an object where a list belongs',
            thrown.length === 0, thrown[0]);
    }

    // --- and the guard is not just a try/catch swallowing everything ---------
    check('the wallet render no longer reads .toFixed straight off the response',
        !/_wallet\.\w+\.toFixed/.test(APPJS),
        'an unguarded .toFixed on a response field is back');

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
