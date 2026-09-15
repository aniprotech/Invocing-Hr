/**
 * Integrations, on screen: keys made and shown once, webhooks added with a
 * secret shown once, the delivery log, and the reference text an
 * integrator needs without leaving the page.
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
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], alerts = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/api-keys' && method === 'GET') return give({ keys: [{ id: 1, name: 'Payroll <b>sync</b>', prefix: 'ak_abc12345', scopes: 'read', last_used_at: '', revoked_at: '' }, { id: 2, name: 'Old', prefix: 'ak_old', scopes: 'read', last_used_at: '', revoked_at: '2026-01-01' }], events: [] });
        if (p === '/api/api-keys' && method === 'POST') return give({ id: 3, key: 'ak_THE_ONLY_TIME', prefix: 'ak_THE_ONL', scopes: 'read,write' });
        if (p === '/api/webhooks' && method === 'GET') return give({ events: ['employee.created', 'leave.decided'], webhooks: [
            { id: 4, url: 'https://x.example/hook', events: ['employee.created'], active: true, last_status: 200, last_delivered_at: '2026-09-15 09:00:00', failures: 0, secret_prefix: 'whsec_' },
            { id: 5, url: 'https://dead.example/hook', events: ['leave.decided'], active: false, last_status: 503, last_delivered_at: '', failures: 20, secret_prefix: 'whsec_' } ],
            deliveries: [{ id: 9, webhook_id: 5, event: 'leave.decided', ok: false, status_code: 503, attempts: 3, created_at: '2026-09-15 08:00:00', delivered_at: '', error: 'HTTP 503', next_attempt_at: '2026-09-15 08:30:00' }] });
        if (p === '/api/webhooks' && method === 'POST') return give({ id: 6, url: 'https://n.example/h', events: ['employee.created'], secret: 'whsec_SHOWN_ONCE' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiAlert = (m) => { alerts.push(String(m)); return Promise.resolve(true); };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiForm = () => Promise.resolve(opts.form === undefined ? null : opts.form);
    return { w, doc: w.document, sent, alerts };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Settings has an Integrations section', /data-settings-section="integrations"/.test(src));
        check('  that says how to authenticate and how deliveries are signed', /Authorization: Bearer ak_/.test(src) && /X-Aniprotech-Signature/.test(src) && /\/api\/v1\/employees/.test(src));
    }
    {
        const { w, doc } = boot();
        await w.loadIntegrations();
        await wait(60);
        const keys = doc.getElementById('api-keys-list');
        check('live keys are listed by prefix only, names as text, revoked ones left out', /ak_abc12345/.test(keys.textContent) && /Payroll <b>sync<\/b>/.test(keys.textContent) && !keys.querySelector('b') && !/ak_old/.test(keys.textContent));
        const hooks = doc.getElementById('webhooks-list');
        check('webhooks show their events and state', /employee\.created/.test(hooks.textContent) && /Last answer 200/.test(hooks.textContent) && /Switched off after 20 failures/.test(hooks.textContent));
        check('  a switched-off one offers Switch on', /toggleWebhook\(5,true\)/.test(hooks.innerHTML) && /toggleWebhook\(4,false\)/.test(hooks.innerHTML));
        const log = doc.getElementById('webhook-deliveries');
        check('the delivery log shows failures with when they are tried again', /HTTP 503/.test(log.textContent) && /again at 2026-09-15 08:30:00/.test(log.textContent));
    }
    {
        const { w, sent, alerts } = boot({ form: { name: 'BI', write: 'write' } });
        await w.createApiKey();
        await wait(40);
        const post = sent.find(s => s.url === '/api/api-keys' && s.method === 'POST');
        check('creating a key posts its scope and shows the key once', post && bodyOf(post).write === true && alerts.some(a => /ak_THE_ONLY_TIME/.test(a) && /not shown again/.test(a)));
    }
    {
        const { w, sent, alerts } = boot({ form: { url: 'https://n.example/h', events: 'employee.created, leave.decided' } });
        await w.addWebhook();
        await wait(40);
        const post = sent.find(s => s.url === '/api/webhooks' && s.method === 'POST');
        check('adding a webhook posts the URL and parsed events and shows the secret once', post && JSON.stringify(bodyOf(post).events) === '["employee.created","leave.decided"]' && alerts.some(a => /whsec_SHOWN_ONCE/.test(a)), post && post.body);
    }
    {
        const { w, sent } = boot({ form: { url: 'https://n.example/h', events: 'all' } });
        await w.addWebhook();
        await wait(40);
        check('"all" asks for every event', bodyOf(sent.find(s => s.url === '/api/webhooks' && s.method === 'POST')).events === '*');
    }
    console.log(failures === 0 ? '\nAll integration checks passed.' : `\n${failures} integration check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
