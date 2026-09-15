/** The morning digest switch and preview under Settings. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const ROOT = path.resolve(__dirname, '..');
let failures = 0;
const check = (label, ok, detail) => { if (ok) console.log(`ok    ${label}`); else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window, sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0]; const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/hr/digest-preview') return give({ enabled: true, to: 'hr@acme.example', digest: { text: 'Good morning. <b>x</b>\n- 2 probations to decide' } });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    await w.loadDigestPreview();
    await wait(30);
    const d = w.document;
    check('the switch reflects the setting and the preview shows the words as text', d.getElementById('digest-on').checked && /2 probations to decide/.test(d.getElementById('digest-preview').textContent) && !d.getElementById('digest-preview').querySelector('b') && d.getElementById('digest-to').textContent === 'hr@acme.example');
    await w.setDigest(false);
    await wait(30);
    const post = sent.find(s => s.url === '/api/settings' && s.method === 'POST');
    check('switching it off saves the setting', post && JSON.parse(post.body).hr_digest === '0');
    console.log(failures === 0 ? '\nAll digest checks passed.' : `\n${failures} digest check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
