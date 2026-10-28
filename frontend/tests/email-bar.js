/**
 * While this business's email cannot go out - a Google connection that has
 * been revoked, no mail server set - every screen says so, with a way to fix
 * it, until it is fixed.
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

function boot(mine) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/client/account-status') return give({ email: 'a@x.test', mine: mine, trial: { active: true } });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return w;
}

(async () => {
    {
        const w = boot({ can_send: false, blocked_reason: 'the Google account connected for sending is no longer authorised <b>x</b>' });
        await w.checkAccountStatus();
        const bar = w.document.getElementById('email-bar');
        check('a dead connection puts a bar on the screen', bar.style.display === 'flex' && /Your emails are not going out: the Google account connected for sending is no longer authorised/.test(bar.textContent));
        check('  the reason stays text', !bar.querySelector('b'));
        let went = false;
        w.goToEmailSetup = () => { went = true; };
        bar.querySelector('button').click();
        check('  and Fix it goes to the email settings', went);
    }
    {
        const w = boot({ can_send: true, blocked_reason: '' });
        await w.checkAccountStatus();
        check('working email shows no bar', w.document.getElementById('email-bar').style.display === 'none');
    }
    {
        const w = boot({ can_send: false, blocked_reason: 'x' });
        await w.checkAccountStatus();
        w.fetch = (url) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(String(url).includes('account-status') ? { mine: { can_send: true }, trial: { active: true } } : {}) });
        await w.checkAccountStatus();
        check('once it is fixed the bar goes on the next screen', w.document.getElementById('email-bar').style.display === 'none');
    }
    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
