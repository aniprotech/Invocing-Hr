/**
 * Nobody is asked to confirm their address.
 *
 * Signing up used to send a code, and the app showed a bar on every screen
 * until it was typed back - including to people who had just signed in with
 * Google. The code often never arrived, so new people were stuck at the first
 * step. There is no bar and no code window now.
 *
 * What is worth pinning is that it stays gone, and that the two things that
 * shared the old status check still work: the free-trial bar, and the prompt
 * for a business whose own mail cannot send.
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

function boot(status) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    const sent = [];
    const reply = body => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body), text: () => Promise.resolve('{}') });
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET' });
        if (p === '/api/auth/me') return reply({ user: { email: 'a@b' }, client_id: 1 });
        if (p === '/api/client/me') return reply({ id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/client/account-status') return reply(status);
        return reply(p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

const el = (w, id) => w.document.getElementById(id);

(async () => {
    // --- gone from the page ------------------------------------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const js = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        check('the app has no confirm-your-address bar', !/id="verify-email-bar"/.test(html));
        check('and no window to type a code into', !/id="verify-email-modal"/.test(html) && !/id="verify-code"/.test(html));
        check('and nothing in the script that would open one or send a code to be checked',
            !/openVerifyEmail|confirmVerifyEmail|resendVerification/.test(js) && !/verify-email|resend-verification/.test(js));
        check('and it no longer asks the old status address', !/verification-status/.test(js));
        const server = fs.readFileSync(path.resolve(ROOT, '..', 'backend', 'main.py'), 'utf8');
        check('and the server holds nothing back until an address is proved',
            !/Confirm your email address before/.test(server));
    }

    // --- an account that was never confirmed is not nagged ---------------------------------
    {
        const { w, sent } = boot({ email: 'owner@acme.test', mine: { can_send: true }, trial: { active: true, ending_soon: false, days_left: 25 } });
        await wait(100);
        await w.checkAccountStatus();
        check('asking the status is one request, to the address that says what it is',
            sent.filter(s => s.url === '/api/client/account-status').length >= 1
            && !sent.some(s => /verification-status|verify-email|resend-verification/.test(s.url)), JSON.stringify(sent.map(s => s.url)));
        check('with nothing proved, no bar appears', !el(w, 'verify-email-bar'));
        check('and the trial bar stays out of the way early in the month', el(w, 'trial-bar').style.display === 'none');
    }

    // --- the old answer, from a server not yet updated, changes nothing ------------------------
    {
        const { w } = boot({ verified: false, can_send: false, blocked_reason: 'email is sent through a connected Google account and none is connected', email: 'x@y.test', mine: { can_send: true }, trial: {} });
        await wait(100);
        await w.checkAccountStatus();
        check('even an answer that still says "not verified" puts nothing on the screen',
            !el(w, 'verify-email-bar') && !/confirm|code/i.test(el(w, 'trial-bar').textContent));
    }

    // --- what shared the old check still works ---------------------------------------------------
    {
        const { w } = boot({ email: 'o@a.test', mine: { can_send: true }, trial: { active: true, ending_soon: true, days_left: 3 } });
        await wait(100);
        await w.checkAccountStatus();
        check('the trial bar still says when the free month is nearly over',
            el(w, 'trial-bar').style.display === 'flex' && /ends in 3 days/.test(el(w, 'trial-bar-text').textContent), el(w, 'trial-bar-text').textContent);
    }
    {
        const { w } = boot({ email: 'o@a.test', mine: { can_send: true }, trial: { active: false, needs_credit: true } });
        await wait(100);
        await w.checkAccountStatus();
        check('and after it, when there is no credit behind the account', /free trial has ended/.test(el(w, 'trial-bar-text').textContent));
    }
    {
        const { w } = boot({ email: 'o@a.test', mine: { can_send: false, blocked_reason: 'the SMTP password was refused' }, trial: {} });
        await wait(100);
        await w.checkEmailSending();
        check('a business whose own mail cannot send is still told, once, and why',
            el(w, 'email-setup-modal').style.display === 'flex' && /SMTP password was refused/.test(el(w, 'email-setup-why').textContent),
            el(w, 'email-setup-why').textContent);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
