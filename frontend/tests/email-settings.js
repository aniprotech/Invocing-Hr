/**
 * A business choosing how its own email goes out.
 *
 * Everything left through the operator's account, so a customer received an
 * invoice from them rather than from the business that raised it.
 *
 * The screen has one habit that is easy to get wrong and expensive when it is:
 * the password field is blank because the password is never sent back, not
 * because there isn't one. So saving any other change must not send an empty
 * password and wipe it, and the screen has to say a password is saved rather
 * than leave somebody guessing at an empty box.
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

const SAVED = {
    transport: 'smtp', smtp_host: 'smtp.acme.test', smtp_port: 587,
    smtp_user: 'billing', smtp_password: '****ter2', has_password: true,
    smtp_starttls: true, from_email: 'billing@acme.test', from_name: 'Acme Ltd',
    updated_at: '2026-09-02 10:00:00', allowed_ports: [25, 465, 587, 2525],
};

const FRESH = {
    transport: '', smtp_host: '', smtp_port: 587, smtp_user: '',
    smtp_password: '', has_password: false, smtp_starttls: true,
    from_email: '', from_name: 'Acme Ltd', updated_at: '',
    allowed_ports: [25, 465, 587, 2525],
};

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
        if (p === '/api/email-settings') {
            if (init && init.method === 'PUT' && opts.saveError) {
                return Promise.resolve({ ok: false, status: 400,
                    json: () => Promise.resolve({ detail: opts.saveError }) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve(opts.settings || FRESH) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    w.confirm = () => true;
    return { w, sent };
}

const el = (w, id) => w.document.getElementById(id);
const putBody = sent => {
    const put = sent.filter(s => s.url === '/api/email-settings' && s.method === 'PUT').pop();
    return put ? JSON.parse(put.body) : null;
};

(async () => {
    // --- the choice -------------------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        await w.loadEmailSettings();

        const pick = el(w, 'email-transport');
        check('a business can choose how its mail goes out', !!pick);
        check('between the platform, Google and its own server',
            pick.options.length === 3, pick.options.length);
        check('and starts out following the platform', pick.value === '', pick.value);
        check('so the server fields stay out of the way',
            el(w, 'email-smtp-fields').style.display === 'none');
        check('the company name is offered as the sender name',
            el(w, 'email-from-name').value === 'Acme Ltd');
    }

    {
        const { w } = boot();
        await wait(60);
        await w.loadEmailSettings();
        el(w, 'email-transport').value = 'smtp';
        w.onEmailTransportChange();
        check('choosing your own server asks for its details',
            el(w, 'email-smtp-fields').style.display === 'block');
        check('offering only the ports mail actually uses',
            el(w, 'email-smtp-port').options.length === 4);
    }

    // --- the password, which is never sent back ------------------------------------
    {
        const { w } = boot({ settings: SAVED });
        await wait(60);
        await w.loadEmailSettings();

        check('a saved password is not put back in the box',
            el(w, 'email-smtp-password').value === '',
            el(w, 'email-smtp-password').value);
        check('but the screen says there is one',
            /password is saved/i.test(el(w, 'email-password-note').textContent),
            el(w, 'email-password-note').textContent);
        check('and offers to forget it',
            el(w, 'email-clear-password').style.display !== 'none');
    }

    {
        const { w, sent } = boot({ settings: SAVED });
        await wait(60);
        await w.loadEmailSettings();
        el(w, 'email-smtp-user').value = 'someone-else';
        sent.length = 0;
        await w.saveEmailSettings();
        await wait(40);

        const body = putBody(sent);
        check('changing something else sends no password at all',
            body && body.smtp_password === undefined, body && Object.keys(body).join(','));
        check('while sending the thing that did change',
            body && body.smtp_user === 'someone-else');
    }

    {
        const { w, sent } = boot({ settings: SAVED });
        await wait(60);
        await w.loadEmailSettings();
        el(w, 'email-smtp-password').value = 'a new one';
        sent.length = 0;
        await w.saveEmailSettings();
        await wait(40);
        check('a password that was typed is sent',
            putBody(sent).smtp_password === 'a new one');
    }

    {
        const { w, sent } = boot({ settings: SAVED });
        await wait(60);
        await w.loadEmailSettings();
        sent.length = 0;
        await w.clearEmailPassword();
        await wait(40);
        check('forgetting it is asked for on purpose',
            putBody(sent).clear_password === true);
    }

    // --- what gets sent ---------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        await w.loadEmailSettings();
        el(w, 'email-transport').value = 'smtp';
        el(w, 'email-smtp-host').value = 'smtp.acme.test';
        el(w, 'email-smtp-port').value = '465';
        el(w, 'email-from-address').value = 'billing@acme.test';
        el(w, 'email-smtp-starttls').checked = false;
        sent.length = 0;
        await w.saveEmailSettings();
        await wait(40);

        const body = putBody(sent);
        check('the server details are sent', body.smtp_host === 'smtp.acme.test');
        check('the port as a number, not as text', body.smtp_port === 465);
        check('the address it should come from',
            body.from_email === 'billing@acme.test');
        check('and whether to use STARTTLS', body.smtp_starttls === false);
    }

    // --- refusals ------------------------------------------------------------------------
    {
        const { w } = boot({ saveError: 'smtp.acme.test is not a public mail server' });
        await wait(60);
        await w.loadEmailSettings();
        await w.saveEmailSettings();
        await wait(40);
        check('a refusal from the server is shown, not swallowed',
            /not a public mail server/.test(el(w, 'email-settings-error').textContent),
            el(w, 'email-settings-error').textContent);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
