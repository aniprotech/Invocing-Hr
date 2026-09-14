/**
 * The operator's mail-server screen.
 *
 * There was none. The mail server lived in environment variables, the screen
 * that chose "smtp" said so in its help text, and an operator who wanted
 * sign-in codes going out through a Gmail address had nowhere to put the app
 * password. Which they reported, accurately, as there being no place for it.
 *
 * Three things this screen has to get right: the password box never shows
 * what is saved and an empty one means "keep it"; the Gmail instructions are
 * on the page, because an app password is not the normal one and nobody
 * finds that out by guessing; and the test button says exactly what the
 * server said, because "not working" is what they already knew.
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

const SETTINGS = {
    groups: ['Email'],
    settings: [
        { key: 'email.transport', label: 'Send email through', group: 'Email', kind: 'choice',
          choices: ['gmail', 'smtp'], value: 'smtp', help: '', is_set: true, from_env: false, env: '' },
        { key: 'email.smtp_host', label: 'SMTP server', group: 'Email', kind: 'text',
          value: 'smtp.gmail.com', help: 'For Gmail: smtp.gmail.com', is_set: true, from_env: false, env: 'SMTP_HOST' },
        { key: 'email.smtp_password', label: 'SMTP password', group: 'Email', kind: 'secret',
          value: '', help: 'For Gmail this must be an App Password', is_set: true, from_env: false, env: 'SMTP_PASSWORD' },
    ],
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true);
            w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body });
                const give = (b, status) => Promise.resolve({
                    ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b),
                    text: () => Promise.resolve(JSON.stringify(b)) });
                if (p === '/api/superadmin/me') return give({ username: 'op', email: 'op@example.com' });
                if (p === '/api/superadmin/platform-settings' && method === 'GET') return give(SETTINGS);
                if (p === '/api/superadmin/platform-settings' && method === 'PUT') return give({ changed: {} });
                if (p === '/api/superadmin/send-test-email') {
                    return give(opts.testResult || { sent: false, to: 'op@example.com', transport: 'smtp',
                        reason: "SMTP error: (535, b'5.7.8 Username and Password not accepted')" });
                }
                return give(p.endsWith('s') ? [] : {});
            };
        },
    });
    return { w: dom.window, doc: dom.window.document, sent };
}

(async () => {
    // --- the fields, and the password box --------------------------------------
    {
        const { w, doc } = boot();
        await w.loadPlatformSettings();
        await wait(40);
        const pw = doc.querySelector('[data-key="email.smtp_password"]');
        check('the password is a password box', !!pw && pw.type === 'password');
        check('  that never carries the saved value', pw && pw.value === '');
        check('  and says one is saved without saying what', pw && /Saved/.test(pw.placeholder), pw && pw.placeholder);
        check('  with autocomplete off, so the browser does not offer somebody else\'s',
            pw && pw.getAttribute('autocomplete') === 'new-password');
    }

    // --- the Gmail steps are on the page ----------------------------------------
    {
        const { w, doc } = boot();
        await w.loadPlatformSettings();
        await wait(40);
        const text = doc.getElementById('platform-settings-body').textContent;
        check('the page says what Gmail needs', /smtp\.gmail\.com/.test(text) && /587/.test(text));
        check('  and that it is an App Password, not the normal one',
            /App Password/.test(text) && /not your normal one/.test(text));
        check('  and where to make one', /2-Step Verification/.test(text) && /App passwords/.test(text));
        check('there is a test button', !!doc.getElementById('email-test-btn'));
    }

    // --- saving with the password box empty keeps the password --------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadPlatformSettings();
        await wait(40);
        await w.savePlatformSettings();
        await wait(40);
        const put = sent.find(s => s.method === 'PUT');
        const body = JSON.parse(put.body).settings;
        check('an untouched password box is sent empty, which the server reads as "keep it"',
            body['email.smtp_password'] === '');
        check('  alongside the fields that were shown', body['email.smtp_host'] === 'smtp.gmail.com');
    }

    // --- the test button ---------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadPlatformSettings();
        await wait(40);
        await w.sendTestEmail();
        await wait(40);
        check('pressing it asks the server to send', sent.some(s => s.url === '/api/superadmin/send-test-email' && s.method === 'POST'));
        const out = doc.getElementById('email-test-result').textContent;
        check('a failure shows the exact reason the server gave', /535/.test(out) && /not accepted/.test(out), out);
    }
    {
        const { w, doc } = boot({ testResult: { sent: true, to: 'op@example.com', transport: 'smtp', reason: '' } });
        await w.loadPlatformSettings();
        await wait(40);
        await w.sendTestEmail();
        await wait(40);
        const out = doc.getElementById('email-test-result').textContent;
        check('a success says where it went and how', /op@example\.com/.test(out) && /smtp/.test(out), out);
        check('  and mentions the spam folder, which is where a first one lands', /spam/.test(out));
    }
    {
        // The usual mistake: testing a password that was typed and never saved.
        const { w, doc, sent } = boot();
        await w.loadPlatformSettings();
        await wait(40);
        doc.querySelector('[data-key="email.smtp_password"]').value = 'typed but not saved';
        await w.sendTestEmail();
        await wait(40);
        check('unsaved changes stop the test and say why',
            !sent.some(s => s.url === '/api/superadmin/send-test-email') &&
            /Save your changes first/.test(doc.getElementById('email-test-result').textContent),
            doc.getElementById('email-test-result').textContent);
    }

    console.log(failures === 0
        ? '\nAll SMTP-screen checks passed.'
        : `\n${failures} SMTP-screen check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
