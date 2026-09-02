/**
 * Signing in to the operator account with an emailed code.
 *
 * A password was the only way in, so losing it locked the operator out of
 * their own platform.
 *
 * The page must not undo what the server is careful about. It asks for the
 * code against the address already typed, it never claims the address was
 * recognised, and it clears a rejected code so the next attempt is a fresh
 * one rather than resending the same wrong digits into a five-try limit.
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

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin-login.html'), 'utf8');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin-login.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.__sent = sent;
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET',
                            body: init && init.body });
                if (p === '/api/superadmin/me') {
                    return Promise.resolve({ ok: false, status: 401,
                        json: () => Promise.resolve({}) });
                }
                if (p === '/api/superadmin/request-otp') {
                    if (opts.requestFails) {
                        return Promise.resolve({ ok: false, status: 429,
                            json: () => Promise.resolve({ detail: 'Too many codes requested.' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({
                            sent: true,
                            message: 'If that account exists, a code has been sent to it.',
                        }) });
                }
                if (p === '/api/superadmin/verify-otp') {
                    if (opts.badCode) {
                        return Promise.resolve({ ok: false, status: 401,
                            json: () => Promise.resolve({ detail: 'That code is not valid' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ ok: true }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve({}) });
            };
        },
    });
    return dom.window;
}

const el = (w, id) => w.document.getElementById(id);

(async () => {
    // --- the offer ---------------------------------------------------------------
    {
        const w = boot();
        await wait(80);
        check('a code is offered as a way in', !!el(w, 'otp-start'));
        check('and the code box is out of the way until asked for',
            el(w, 'otp-form').style.display === 'none');
        check('the box expects a one time code, so a phone can fill it',
            el(w, 'otp-code').getAttribute('autocomplete') === 'one-time-code');
        check('and is limited to the six digits that are sent',
            el(w, 'otp-code').getAttribute('maxlength') === '6');
    }

    // --- asking without saying who you are ------------------------------------------
    {
        const w = boot();
        await wait(80);
        w.__sent.length = 0;
        await w.startOtp();
        await wait(30);
        check('asking with no address sends nothing',
            !w.__sent.some(s => s.url === '/api/superadmin/request-otp'));
        check('and says what is missing',
            /email or username/i.test(el(w, 'error-msg').textContent),
            el(w, 'error-msg').textContent);
    }

    // --- asking properly --------------------------------------------------------------
    {
        const w = boot();
        await wait(80);
        el(w, 'login-id').value = 'operator@example.test';
        w.__sent.length = 0;
        await w.startOtp();
        await wait(40);

        const ask = w.__sent.find(s => s.url === '/api/superadmin/request-otp');
        check('the code is asked for', !!ask);
        check('against the address that was typed',
            ask && JSON.parse(ask.body).identifier === 'operator@example.test',
            ask && ask.body);
        check('the code box appears', el(w, 'otp-form').style.display === 'block');

        const hint = el(w, 'otp-hint').textContent;
        check('and the page does not claim the address was recognised',
            /if that account exists/i.test(hint), hint);
        check('while saying the code runs out',
            /ten minutes|once/i.test(hint), hint);
    }

    // --- using the code ------------------------------------------------------------------
    {
        const w = boot();
        await wait(80);
        el(w, 'login-id').value = 'operator@example.test';
        await w.startOtp();
        await wait(40);
        el(w, 'otp-code').value = '123456';
        w.__sent.length = 0;
        await w.finishOtp({ preventDefault() { }, target: el(w, 'otp-form') });
        await wait(40);

        const use = w.__sent.find(s => s.url === '/api/superadmin/verify-otp');
        check('the code is sent to be checked', !!use);
        const body = use && JSON.parse(use.body);
        check('with the code', body && body.code === '123456');
        check('and the account it belongs to',
            body && body.identifier === 'operator@example.test');
    }

    {
        const w = boot({ badCode: true });
        await wait(80);
        el(w, 'login-id').value = 'operator@example.test';
        await w.startOtp();
        await wait(40);
        el(w, 'otp-code').value = '000000';
        await w.finishOtp({ preventDefault() { }, target: el(w, 'otp-form') });
        await wait(40);

        check('a refused code is reported', /not valid/i.test(el(w, 'error-msg').textContent),
            el(w, 'error-msg').textContent);
        check('and cleared, so the next try is a fresh one',
            el(w, 'otp-code').value === '', el(w, 'otp-code').value);
        check('the form stays open to try again',
            el(w, 'otp-form').style.display === 'block');
    }

    {
        const w = boot({ requestFails: true });
        await wait(80);
        el(w, 'login-id').value = 'operator@example.test';
        await w.startOtp();
        await wait(40);
        check('being refused a code is reported',
            /too many/i.test(el(w, 'error-msg').textContent),
            el(w, 'error-msg').textContent);
        check('and the code box is not opened on a code that never went',
            el(w, 'otp-form').style.display === 'none');
    }

    // --- going back ----------------------------------------------------------------------
    {
        const w = boot();
        await wait(80);
        el(w, 'login-id').value = 'operator@example.test';
        await w.startOtp();
        await wait(40);
        el(w, 'otp-code').value = '123456';
        w.cancelOtp();
        check('a password is still an option', el(w, 'otp-form').style.display === 'none');
        check('and the typed code is not left lying in the box',
            el(w, 'otp-code').value === '');
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
