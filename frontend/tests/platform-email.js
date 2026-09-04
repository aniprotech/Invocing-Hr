/**
 * The operator's view of whether the platform can send anything.
 *
 * Everything the product sends itself - a signup code, an operator's own
 * sign-in code, a password reset - goes out on the platform transport, and
 * there was no screen for it anywhere. When it was not set up, every one of
 * those failed the same quiet way and the answer to "why did no code arrive"
 * was not visible from any page.
 *
 * So the thing being checked here is mostly that the bad state is stated
 * plainly rather than left to be inferred - and that a stored authorisation
 * which has stopped working is not described as working, because that one
 * looks fine right up until somebody needs a code.
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

const WORKING = {
    can_send: true, blocked_reason: '', transport: 'gmail',
    google_connected: true, google_works: true, connected_as: 'ops@aniprotech.com',
    smtp_host_set: false, note: 'Everything the platform sends itself goes out this way.',
};
const BROKEN = {
    can_send: false,
    blocked_reason: 'email is sent through a connected Google account and none is connected',
    transport: 'gmail', google_connected: false, google_works: false,
    connected_as: '', smtp_host_set: false, note: 'Everything the platform sends.',
};
const STALE = Object.assign({}, WORKING, {
    can_send: true, google_works: false, connected_as: '',
});

function boot(status, hash) {
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const alerts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html' + (hash || ''),
        beforeParse(w) {
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                if (p === '/api/superadmin/me') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ username: 'op', email: 'op@x' }) });
                }
                if (p === '/api/superadmin/email-status') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve(status || WORKING) });
                }
                if (p === '/api/superadmin/gmail/disconnect') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ ok: true, can_send: false,
                            message: 'Disconnected. The platform can no longer send anything.' }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(p.endsWith('s') ? [] : {}) });
            };
            w.alert = m => alerts.push(m);
            w.confirm = () => true;
        },
    });
    const w = dom.window;
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    return { w, alerts };
}

const body = w => w.document.getElementById('platform-email-body');

(async () => {
    // --- it is on the screen at all --------------------------------------------
    {
        const { w } = boot();
        check('the operator panel has somewhere to see platform email',
            !!body(w));
        check('and it loads with the rest of the settings tab',
            /control:\s*\[loadPlatformEmail/.test(
                fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8')));
    }

    // --- the bad state, said plainly ---------------------------------------------
    {
        const { w } = boot(BROKEN);
        await w.loadPlatformEmail();
        const text = body(w).textContent;
        check('a platform that cannot send says so first',
            /cannot send email/i.test(text), text.slice(0, 90));
        check('and gives the reason rather than leaving it to be guessed',
            /none is connected/.test(text));
        check('and says what it is costing, since nothing else reports it',
            /verification code|password reset/i.test(text));
        check('with a way to fix it on the same screen',
            !!w.document.querySelector('a[href="/api/superadmin/gmail/connect"]'));
        check('and the alternative spelled out for anyone who prefers SMTP',
            /SMTP_HOST/.test(text));
    }

    // --- the good state -------------------------------------------------------------
    {
        const { w } = boot(WORKING);
        await w.loadPlatformEmail();
        const text = body(w).textContent;
        check('a platform that can send says that instead',
            /can send email/i.test(text));
        check('and names the account it goes out through',
            /ops@aniprotech\.com/.test(text));
        check('offering to disconnect, since it is connected',
            /Disconnect/.test(text));
    }

    // --- the state that looks fine and is not ------------------------------------------
    {
        const { w } = boot(STALE);
        await w.loadPlatformEmail();
        const text = body(w).textContent;
        check('an authorisation that has stopped working is called out',
            /no longer works/i.test(text), text.slice(0, 120));
        check('and says to connect it again', /again/i.test(text));
    }

    // --- disconnecting is not a quiet button ---------------------------------------------
    {
        const { w, alerts } = boot(WORKING);
        await w.loadPlatformEmail();
        let asked = null;
        w.confirm = m => { asked = m; return false; };
        await w.disconnectPlatformGmail();
        check('disconnecting asks first', !!asked);
        check('and says what it will break, which the word does not',
            /stop working|no mail server/i.test(asked || ''), asked);
        check('and nothing happens when the answer is no', alerts.length === 0);
    }

    // --- what came back from Google -------------------------------------------------------
    {
        const { w, alerts } = boot(WORKING, '#email=connected');
        await wait(80);
        check('a connection that worked is reported', alerts.length === 1,
            alerts.join(' | '));
        check('and says the platform can send now, which is the point of it',
            /can send email/i.test(alerts[0] || ''), alerts[0]);
        // Not asserting the hash is cleared: showTab rewrites it on load
        // whatever this does, so such a check would pass either way.
        check('and the page settles on a real tab rather than the raw answer',
            !/email=/.test(w.location.hash), w.location.hash);
    }

    {
        const { w, alerts } = boot(WORKING, '#email=norefresh');
        await wait(80);
        check('access that will not last is reported as a failure',
            alerts.length === 1 && /not grant lasting/i.test(alerts[0]),
            alerts.join(' | '));
    }

    {
        const { w, alerts } = boot(WORKING, '#control');
        await wait(80);
        check('and somebody who just opened the tab is told nothing',
            alerts.length === 0, alerts.join(' | '));
    }

    {
        // Every word the server can send back has to mean something here, or
        // one of them lands somebody on a screen that says nothing at all.
        const server = fs.readFileSync(
            path.resolve(__dirname, '..', '..', 'backend', 'main.py'), 'utf8');
        const block = server.slice(server.indexOf('def superadmin_gmail_callback'),
                                   server.indexOf('def superadmin_gmail_disconnect'));
        const sent = [...block.matchAll(/superadmin\.html#email=([a-z]+)/g)]
            .map(m => m[1]);
        check('the server has outcomes to report', sent.length > 0, sent.join(','));

        for (const word of new Set(sent)) {
            const { alerts } = boot(WORKING, '#email=' + word);
            await wait(80);
            check(`"${word}" is a word the screen understands`,
                alerts.length === 1, alerts.join(' | '));
        }
    }

    // --- the credential never reaches the page -------------------------------------------
    {
        const page = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
        check('the screen never asks for or prints the stored token',
            !/refresh_token|\.token\b/.test(
                page.slice(page.indexOf('function renderPlatformEmail'),
                           page.indexOf('async function disconnectPlatformGmail'))));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
