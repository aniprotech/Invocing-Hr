/**
 * Connecting Gmail from the settings screen.
 *
 * The button here pointed at /api/auth/login - the sign-in route. Somebody who
 * signed up with an email and a password and then pressed it was signed in as
 * whatever Google account their browser happened to be holding, which for a
 * mismatched address meant a brand new empty account with none of their
 * invoices in it. The button has to start a link, not a sign-in.
 *
 * The other half is being told what happened. The server sends the browser
 * back to /app.html#/settings?gmail=..., so the answer arrives in the hash and
 * not in location.search - reading the wrong one means every outcome, success
 * and failure alike, passes in silence.
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

function boot(hash) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html' + (hash || ''),
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };

    const asked = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        asked.push(p);
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        if (p === '/api/gmail/status') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ gmail_ready: false }) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

    const said = [];
    w.showToast = (message, type) => said.push({ message, type });
    return { w, said, asked };
}

(async () => {
    // --- the button ---------------------------------------------------------------
    {
        const { w } = boot();
        const btn = w.document.getElementById('gmail-login-btn');
        check('there is a way to connect Gmail', !!btn);
        check('and it starts a link, not a sign-in',
            btn.getAttribute('href') === '/api/gmail/connect',
            btn.getAttribute('href'));

        // The Google sign-in route creates an account for an address it does
        // not recognise, so nothing inside the app - not even the header's
        // Sign In, which shows when a request drops - may point at it.
        const page = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('nothing inside the app points at the account-creating route',
            !/\/api\/auth\/login/.test(page));
        const header = w.document.getElementById('login-btn');
        check('the header sends people to the login page instead',
            !header || header.getAttribute('href') === '/login.html',
            header && header.getAttribute('href'));
        check('the wording says what it does, rather than offering a login',
            /connect/i.test(btn.textContent) && !/log ?in|sign ?in/i.test(btn.textContent),
            btn.textContent);
    }

    // --- being told what happened -----------------------------------------------
    {
        const { w, said } = boot('#/settings?gmail=connected');
        w.reportGmailConnect();
        check('a connection that worked says so', said.length === 1);
        check('as success, not as a warning',
            said[0] && said[0].type === 'success', said[0] && said[0].type);
        check('and the answer is read out of the hash, where the server puts it',
            said[0] && /connected/i.test(said[0].message), said[0] && said[0].message);
    }

    {
        const { w, said } = boot('#/settings?gmail=norefresh');
        w.reportGmailConnect();
        check('access that will not last is reported as a failure',
            said.length === 1 && said[0].type === 'error',
            said[0] && said[0].type);
        check('and says to try again, since trying again is the fix',
            /again/i.test(said[0].message), said[0].message);
    }

    {
        const { w, said } = boot('#/settings?gmail=failed');
        w.reportGmailConnect();
        check('a refusal at Google is reported as a failure',
            said.length === 1 && said[0].type === 'error');
        check('saying nothing changed, so nobody goes looking for damage',
            /nothing has changed/i.test(said[0].message), said[0].message);
    }

    {
        const { w, said } = boot('#/settings?gmail=notlinked');
        w.reportGmailConnect();
        check('a callback nobody started is reported too',
            said.length === 1 && said[0].type === 'error');
    }

    // --- and only once --------------------------------------------------------------
    {
        const { w, said } = boot('#/settings?gmail=connected');
        w.reportGmailConnect();
        check('the answer is cleared off the address',
            w.location.hash.indexOf('gmail=') === -1, w.location.hash);
        w.reportGmailConnect();
        check('so a refresh does not say it all over again', said.length === 1,
            said.length);
        check('and the screen stays on settings',
            w.location.hash === '#/settings', w.location.hash);
    }

    // --- the rest of the time --------------------------------------------------------
    {
        const { w, said } = boot('#/settings');
        w.reportGmailConnect();
        check('somebody who just opened settings is told nothing',
            said.length === 0);
    }

    {
        const { w, said } = boot('#/settings?tab=email');
        w.reportGmailConnect();
        check('nor is somebody with an unrelated parameter', said.length === 0);
        check('and their parameter is left alone',
            w.location.hash === '#/settings?tab=email', w.location.hash);
    }

    // --- the settings screen still asks -------------------------------------------
    {
        const { w, said, asked } = boot('#/settings?gmail=connected');
        await w.loadGmailStatus();
        await wait(20);
        check('opening the Gmail card is what reports the outcome',
            said.length === 1, said.length);
        check('and it still asks the server where the connection stands',
            asked.indexOf('/api/gmail/status') !== -1);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
