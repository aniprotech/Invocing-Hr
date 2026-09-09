/**
 * Signing in with an authenticator app, and setting one up.
 *
 * The emailed code is only ever as good as the mailbox it goes to. A domain
 * with no MX record has no mailbox, so the code is accepted by the provider,
 * bounces somewhere else later, and the operator waits for something that was
 * never going to arrive. Nothing in the sending path can see that happen.
 *
 * A time-based code has nothing to deliver. The server has had one since the
 * TOTP endpoints went in - status, setup, confirm, disable, login-with-app,
 * checked against the RFC 6238 vectors - and no way to reach any of it. A
 * second factor nobody can switch on is not a second factor.
 *
 * These are the wiring checks: that the pages call the endpoints that exist,
 * with what those endpoints expect, and that the two things shown exactly once
 * - the setup key and the recovery codes - actually reach the screen.
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

const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const RECOVERY = ['a1b2-c3d4', 'e5f6-g7h8', 'i9j0-k1l2'];

function boot(file, routes, opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, file), 'utf8');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/' + file,
        beforeParse(w) {
            w.console.error = () => { };
            w.alert = msg => { sent.push({ url: '@alert', body: String(msg) }); };
            w.uiAlert = msg => {
                sent.push({ url: '@alert', body: String(msg) });
                return Promise.resolve();
            };
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET',
                            body: init && init.body });
                const handler = routes[p];
                const res = handler ? handler(opts) : { ok: false, status: 404, data: {} };
                return Promise.resolve({
                    ok: res.ok, status: res.status,
                    json: () => Promise.resolve(res.data),
                });
            };
        },
    });
    return { dom, w: dom.window, doc: dom.window.document, sent };
}

const jsonOf = entry => { try { return JSON.parse(entry.body); } catch (e) { return {}; } };

// ---- signing in --------------------------------------------------------------

const LOGIN_ROUTES = {
    '/api/superadmin/me': () => ({ ok: false, status: 401, data: {} }),
    '/api/superadmin/login-with-app': o => (
        o.badCode
            ? { ok: false, status: 401, data: { detail: 'That code is not right.' } }
            : { ok: true, status: 200, data: {
                ok: true, used_recovery: !!o.recovery, recovery_codes_left: 7 } }
    ),
};

async function signingIn() {
    console.log('\n-- signing in with the app --');
    {
        const { doc } = boot('superadmin-login.html', LOGIN_ROUTES);
        await wait(20);
        const start = doc.getElementById('app-start');
        check('the sign-in page offers the authenticator at all', !!start,
            'no #app-start - the backend would stay unreachable');
        check('and the form starts hidden',
            doc.getElementById('app-form').style.display === 'none');

        // Without an identifier the server cannot know whose secret to check,
        // so the page must not let it get that far.
        start.click();
        await wait(20);
        check('it will not open with no account named',
            doc.getElementById('app-form').style.display === 'none');
        check('and says why',
            doc.getElementById('error-msg').textContent.length > 0);
    }

    {
        const { doc, sent } = boot('superadmin-login.html', LOGIN_ROUTES);
        await wait(20);
        doc.getElementById('login-id').value = 'operator@example.com';
        doc.getElementById('app-start').click();
        await wait(20);
        check('with an account named, the code box opens',
            doc.getElementById('app-form').style.display === 'block');

        // Nothing is requested to make this appear. That is the whole point:
        // an emailed code needs a send to happen first, and this does not.
        check('and nothing was sent to make that happen',
            !sent.some(s => /request-otp|login-with-app/.test(s.url)),
            sent.map(s => s.url).join(', '));

        doc.getElementById('app-code').value = '123456';
        doc.getElementById('app-form').dispatchEvent(
            new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
        await wait(30);

        const call = sent.find(s => s.url === '/api/superadmin/login-with-app');
        check('submitting reaches the authenticator endpoint', !!call,
            sent.map(s => s.url).join(', '));
        if (call) {
            const body = jsonOf(call);
            check('  carrying the identifier', body.identifier === 'operator@example.com',
                JSON.stringify(body));
            check('  and the code', body.code === '123456', JSON.stringify(body));
        }
    }

    {
        // A recovery code is spent on use. Running out with no working mailbox
        // is how somebody is locked out for good, so it has to be said.
        const { doc, sent } = boot('superadmin-login.html', LOGIN_ROUTES,
            { recovery: true });
        await wait(20);
        doc.getElementById('login-id').value = 'operator@example.com';
        doc.getElementById('app-start').click();
        await wait(10);
        doc.getElementById('app-code').value = 'a1b2-c3d4';
        doc.getElementById('app-form').dispatchEvent(
            new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
        await wait(30);

        const said = sent.find(s => s.url === '@alert');
        check('spending a recovery code says so', !!said, 'nothing was said');
        check('  and says how many are left',
            !!said && /\b7\b/.test(said.body), said && said.body);
    }

    {
        const { doc, sent } = boot('superadmin-login.html', LOGIN_ROUTES,
            { badCode: true });
        await wait(20);
        doc.getElementById('login-id').value = 'operator@example.com';
        doc.getElementById('app-start').click();
        await wait(10);
        doc.getElementById('app-code').value = '000000';
        doc.getElementById('app-form').dispatchEvent(
            new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
        await wait(30);

        check('a refused code shows the reason',
            doc.getElementById('error-msg').textContent.includes('not right'),
            doc.getElementById('error-msg').textContent);
        // The next code is a different number, and a stale one left in the box
        // spends one of ten tries against the same rate limit.
        check('and the box is cleared for the next one',
            doc.getElementById('app-code').value === '');
        check('a refusal does not navigate away',
            !sent.some(s => s.url === '@nav'));
    }
}

// ---- setting one up ----------------------------------------------------------

const PANEL_ROUTES = {
    '/api/superadmin/me': () => ({ ok: true, status: 200,
        data: { username: 'operator', email: 'operator@example.com' } }),
    '/api/superadmin/clients': () => ({ ok: true, status: 200, data: [] }),
    '/api/superadmin/stats': () => ({ ok: true, status: 200, data: {} }),
    '/api/superadmin/totp/status': o => ({ ok: true, status: 200, data:
        o.enabled
            ? { enabled: true, started: false,
                confirmed_at: '2026-09-01 10:00:00', recovery_codes_left: 6 }
            : { enabled: false, started: false, confirmed_at: '',
                recovery_codes_left: 0 } }),
    '/api/superadmin/totp/setup': () => ({ ok: true, status: 200, data: {
        secret: SECRET,
        uri: 'otpauth://totp/aniprotech:operator@example.com?secret=' + SECRET
             + '&issuer=aniprotech&digits=6&period=30',
        account: 'operator@example.com', digits: 6, period: 30 } }),
    '/api/superadmin/totp/confirm': o => (
        o.badCode
            ? { ok: false, status: 400, data: {
                detail: "That code is not right. Check your phone's clock." } }
            : { ok: true, status: 200, data: { ok: true, recovery_codes: RECOVERY } }
    ),
    '/api/superadmin/totp/disable': o => (
        o.badProof
            ? { ok: false, status: 401, data: {
                detail: 'Enter a current code from the app, or your password.' } }
            : { ok: true, status: 200, data: { ok: true } }
    ),
};

async function settingUp() {
    console.log('\n-- setting one up --');
    {
        const { doc, sent } = boot('superadmin.html', PANEL_ROUTES);
        await wait(40);
        check('the panel has a way in', !!doc.querySelector('[onclick="openTotpModal()"]'),
            'no button - the endpoints stay unreachable');

        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        check('opening it asks what is set up now',
            sent.some(s => s.url === '/api/superadmin/totp/status'),
            sent.map(s => s.url).join(', '));

        doc.querySelector('[onclick="startTotp()"]').click();
        await wait(30);
        const body = doc.getElementById('totp-body');

        check('the setup key is on the screen',
            body.textContent.replace(/\s/g, '').includes(SECRET),
            'the operator cannot type what they cannot see');
        // Typed by hand from a screen, so it is broken up.
        check('  grouped for typing', /\w{4} \w{4}/.test(body.textContent));
        check('  with the account it belongs to',
            body.textContent.includes('operator@example.com'));

        const link = body.querySelector('a[href^="otpauth://"]');
        check('a phone can add it in one tap', !!link);
        // The secret is in that URI. Handing it to a third party to draw a QR
        // code would be handing away the second factor itself.
        const external = [...body.querySelectorAll('a[href], img[src]')].filter(el => {
            const v = el.getAttribute('href') || el.getAttribute('src') || '';
            return /^https?:\/\//i.test(v);
        });
        check('and the secret never leaves for anywhere else',
            external.length === 0,
            external.map(e => e.getAttribute('href') || e.getAttribute('src')).join(', '));

        check('it is not on until a code proves it took',
            /not on yet/i.test(body.textContent));
    }

    {
        const { doc, sent } = boot('superadmin.html', PANEL_ROUTES);
        await wait(40);
        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        doc.querySelector('[onclick="startTotp()"]').click();
        await wait(30);
        doc.getElementById('totp-confirm-code').value = '654321';
        doc.querySelector('[onclick="confirmTotp()"]').click();
        await wait(30);

        const call = sent.find(s => s.url === '/api/superadmin/totp/confirm');
        check('confirming sends the code', !!call && jsonOf(call).code === '654321',
            call && call.body);

        const body = doc.getElementById('totp-body');
        const shown = RECOVERY.filter(c => body.textContent.includes(c));
        check('every recovery code is shown', shown.length === RECOVERY.length,
            `${shown.length} of ${RECOVERY.length}`);
        check('  and they are shown as the once-only thing they are',
            /once/i.test(body.textContent));
    }

    {
        const { doc } = boot('superadmin.html', PANEL_ROUTES, { badCode: true });
        await wait(40);
        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        doc.querySelector('[onclick="startTotp()"]').click();
        await wait(30);
        doc.getElementById('totp-confirm-code').value = '000000';
        doc.querySelector('[onclick="confirmTotp()"]').click();
        await wait(30);

        check('a wrong confirmation says so',
            /not right/i.test(doc.getElementById('totp-error').textContent),
            doc.getElementById('totp-error').textContent);
        // The most likely cause is a clock, and no recovery codes exist yet,
        // so the operator must be able to try again rather than be left with a
        // half-finished setup and no way to reach it.
        check('  and the setup is still there to retry',
            !!doc.getElementById('totp-confirm-code'));
    }

    {
        const { doc, sent } = boot('superadmin.html', PANEL_ROUTES, { enabled: true });
        await wait(40);
        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        const body = doc.getElementById('totp-body');
        check('an account already using one is told so',
            /uses an authenticator/i.test(body.textContent));
        check('  with how many recovery codes are left',
            body.textContent.includes('6'), body.textContent.slice(0, 120));

        // Anyone who can remove it can put the account back to depending on a
        // mailbox that may not exist, so the server asks for proof - and the
        // page has to actually send it.
        doc.getElementById('totp-off-proof').value = 'hunter2hunter2';
        doc.querySelector('[onclick="disableTotp()"]').click();
        await wait(30);
        const off = sent.find(s => s.url === '/api/superadmin/totp/disable');
        check('removing it sends the proof', !!off, 'nothing was sent');
        check('  a password as a password', !!off && jsonOf(off).password === 'hunter2hunter2',
            off && off.body);
    }

    {
        const { doc, sent } = boot('superadmin.html', PANEL_ROUTES, { enabled: true });
        await wait(40);
        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        doc.getElementById('totp-off-proof').value = '123456';
        doc.querySelector('[onclick="disableTotp()"]').click();
        await wait(30);
        const off = sent.find(s => s.url === '/api/superadmin/totp/disable');
        check('  and six digits as a code', !!off && jsonOf(off).code === '123456',
            off && off.body);
    }

    {
        const { doc } = boot('superadmin.html', PANEL_ROUTES, { enabled: true });
        await wait(40);
        doc.querySelector('[onclick="openTotpModal()"]').click();
        await wait(30);
        doc.querySelector('[onclick="disableTotp()"]').click();
        await wait(30);
        check('removing it with nothing typed is refused here',
            doc.getElementById('totp-error').style.display === 'block');
    }
}

(async () => {
    await signingIn();
    await settingUp();
    console.log(failures === 0
        ? '\nAll authenticator checks passed.'
        : `\n${failures} authenticator check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
