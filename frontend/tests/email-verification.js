/**
 * Confirming the address on a new account.
 *
 * Signing up asked for an address and believed it, so anybody could register
 * with somebody else's and then send invoices in their name.
 *
 * The thing worth checking here is the pairing: sending is held back until the
 * address is proved, so there has to be somewhere to prove it that a person
 * can actually find. A gate with no way through it is worse than no gate.
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

function boot(opts) {
    opts = opts || {};
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
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET',
                    body: init && init.body });
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        if (p === '/api/client/verification-status') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({
                    verified: !!opts.verified, email: 'owner@acme.test' }) });
        }
        if (p === '/api/client/verify-email') {
            if (opts.badCode) {
                return Promise.resolve({ ok: false, status: 400,
                    json: () => Promise.resolve({ detail: 'That code is not valid' }) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ verified: true }) });
        }
        if (p === '/api/client/resend-verification') {
            if (opts.resendFails) {
                return Promise.resolve({ ok: false, status: 503,
                    json: () => Promise.resolve({
                        detail: 'This server cannot send email at the moment.' }) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ message: 'A new code is on its way.' }) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

const el = (w, id) => w.document.getElementById(id);

(async () => {
    // --- the gate has a door --------------------------------------------------
    {
        const backend = fs.readFileSync(
            path.resolve(ROOT, '..', 'backend', 'main.py'), 'utf8');
        const gated = /Confirm your email address before sending invoices/.test(backend);
        const app = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const hasDoor = /verify-email-modal/.test(app) && /verify-code/.test(app);
        check('sending is held back until the address is proved', gated);
        check('and there is somewhere to prove it', hasDoor);
    }

    // --- unproved ---------------------------------------------------------------
    {
        const { w } = boot({ verified: false });
        await wait(80);
        await w.checkEmailVerified();

        const bar = el(w, 'verify-email-bar');
        check('an unproved account is told, on every screen',
            bar.style.display === 'flex');
        check('and the address is named',
            /owner@acme\.test/.test(el(w, 'verify-bar-text').textContent),
            el(w, 'verify-bar-text').textContent);
        check('the code box is out of the way until asked for',
            el(w, 'verify-email-modal').style.display === 'none');

        w.openVerifyEmail();
        check('and opens from the bar',
            el(w, 'verify-email-modal').style.display === 'flex');
        check('expecting a one time code, so a phone can fill it',
            el(w, 'verify-code').getAttribute('autocomplete') === 'one-time-code');
    }

    {
        const { w } = boot({ verified: true });
        await wait(80);
        await w.checkEmailVerified();
        check('a proved account is not nagged',
            el(w, 'verify-email-bar').style.display === 'none');
    }

    // --- using the code -----------------------------------------------------------
    {
        const { w, sent } = boot({ verified: false });
        await wait(80);
        await w.checkEmailVerified();
        w.openVerifyEmail();
        el(w, 'verify-code').value = '123456';
        sent.length = 0;
        await w.confirmVerifyEmail();
        await wait(40);

        const post = sent.find(s => s.url === '/api/client/verify-email');
        check('the code is sent to be checked', !!post);
        check('as it was typed', post && JSON.parse(post.body).code === '123456');
        check('the box closes when it works',
            el(w, 'verify-email-modal').style.display === 'none');
        check('and the bar goes with it',
            el(w, 'verify-email-bar').style.display === 'none');
    }

    {
        const { w } = boot({ verified: false, badCode: true });
        await wait(80);
        await w.checkEmailVerified();
        w.openVerifyEmail();
        el(w, 'verify-code').value = '000000';
        await w.confirmVerifyEmail();
        await wait(40);

        check('a refused code says so',
            /not valid/i.test(el(w, 'verify-email-error').textContent),
            el(w, 'verify-email-error').textContent);
        check('and is cleared, so the next try is a fresh one',
            el(w, 'verify-code').value === '');
        check('the box stays open to try again',
            el(w, 'verify-email-modal').style.display === 'flex');
    }

    // --- asking for another -----------------------------------------------------------
    {
        const { w, sent } = boot({ verified: false });
        await wait(80);
        await w.checkEmailVerified();
        w.openVerifyEmail();
        sent.length = 0;
        await w.resendVerification();
        await wait(40);
        check('another code can be asked for',
            sent.some(s => s.url === '/api/client/resend-verification'));
        check('and it says one is coming',
            /on its way/i.test(el(w, 'verify-email-note').textContent),
            el(w, 'verify-email-note').textContent);
    }

    {
        const { w } = boot({ verified: false, resendFails: true });
        await wait(80);
        await w.checkEmailVerified();
        w.openVerifyEmail();
        await w.resendVerification();
        await wait(40);
        check('a server that cannot send says so, rather than promising one',
            /cannot send email/i.test(el(w, 'verify-email-error').textContent),
            el(w, 'verify-email-error').textContent);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
