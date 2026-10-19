/**
 * The superadmin email panel lists the platform's own mail that did not go,
 * with the reasons grouped, as text.
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

function boot(fail) {
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                if (p === '/api/superadmin/me') return give({ username: 'op', email: 'op@x' });
                if (p === '/api/superadmin/email-status') return give({ can_send: true, transport: 'smtp', note: '' });
                if (p === '/api/superadmin/email-failures') return fail ? give(fail) : Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) });
                return give(p.endsWith('s') ? [] : {});
            };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true);
        },
    });
    return dom.window;
}

(async () => {
    {
        const w = boot({ sent_7d: 40, failed_7d: 3, reasons: [{ reason: 'SMTP <b>auth</b> failed', count: 3 }],
            failures: [{ when: '2026-10-19 10:00:00', what: 'sign-in code', to: 'a@x.test', error: 'SMTP auth failed <img src=x>' }] });
        await w.loadPlatformEmail();
        await wait(20);
        const box = w.document.getElementById('platform-email-failures');
        const t = box ? box.textContent : '';
        check('failed platform mail is counted against what was sent', /3 platform emails did not go in the last 7 days \(40 sent\)/.test(t), t);
        check('  the reasons are grouped with their count', /3 x SMTP <b>auth<\/b> failed/.test(t));
        check('  each failure says when, what, to whom and why', /sign-in code/.test(t) && /a@x\.test/.test(t) && /2026-10-19 10:00:00/.test(t));
        check('  nothing from the server runs as markup', box && !box.querySelector('b') && !box.querySelector('img'));
        await w.loadPlatformEmail();
        await wait(20);
        check('  reloading the panel shows it once', w.document.querySelectorAll('#platform-email-failures').length === 1);
    }
    {
        const w = boot({ sent_7d: 5, failed_7d: 0, reasons: [], failures: [] });
        await w.loadPlatformEmail();
        await wait(20);
        check('nothing failed says so', /Nothing failed in the last 7 days \(5 sent\)/.test(w.document.getElementById('platform-email-failures').textContent));
    }
    {
        const w = boot(null);
        await w.loadPlatformEmail();
        await wait(20);
        check('if the list cannot be read, the rest of the panel stays', !w.document.getElementById('platform-email-failures') && /can send email/.test(w.document.getElementById('platform-email-body').textContent));
    }
    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
