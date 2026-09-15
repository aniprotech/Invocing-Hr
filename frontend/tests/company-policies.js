/**
 * Policies, on screen: coverage per policy with a reminder for those who
 * have not read it, a form whose "new version" choice republishes, and a
 * portal card with the unread ones first and an acknowledge button.
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
const POLICIES = { outstanding_total: 2, policies: [
    { id: 1, title: 'Expenses <b>policy</b>', body: 'Keep receipts.', url: '', version: 2, requires_ack: true, active: true, department_id: null, department_name: '', published_at: '2026-09-01 10:00:00',
      coverage: { audience: 4, acknowledged: 2, outstanding: 2, pct: 50, outstanding_people: [{ employee_id: 3, name: 'Lena' }, { employee_id: 4, name: 'Mo' }] } },
    { id: 2, title: 'Office map', body: 'x', url: 'https://docs.example/map', version: 1, requires_ack: false, active: true, department_id: null, department_name: '', published_at: '2026-09-01 10:00:00', coverage: null } ] };

function bootHr(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/policies' && method === 'GET') return give(POLICIES);
        if (p === '/api/policies' && method === 'POST') return give({ id: 3 });
        if (/\/api\/policies\/\d+$/.test(p) && method === 'PUT') return give({ id: 1, version: 3 });
        if (/\/remind$/.test(p)) return give({ reminded: 2 });
        if (p === '/api/departments') return give([{ id: 5, name: 'Ops' }]);
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiAlert = () => Promise.resolve(true);
    w.uiForm = () => Promise.resolve(opts.form === undefined ? null : opts.form);
    return { w, doc: w.document, sent };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('People has Policies', /href="#\/policies"/.test(src) && /id="policies-view"/.test(src));
    }
    {
        const { w, doc, sent } = bootHr();
        await w.loadPoliciesView();
        await wait(40);
        const host = doc.getElementById('policies-list');
        check('each policy shows its version and how many have read it, title as text', /Expenses <b>policy<\/b>/.test(host.textContent) && !host.querySelector('b') && /2 of 4 have read v2/.test(host.textContent) && /2 have not/.test(host.textContent));
        check('  one that needs no acknowledgement says so and has no reminder', /No acknowledgement needed/.test(host.textContent) && (host.innerHTML.match(/remindPolicy\(/g) || []).length === 1);
        await w.remindPolicy(1);
        await wait(30);
        check('  Remind posts to the reminder route', sent.some(s => s.url === '/api/policies/1/remind' && s.method === 'POST'));
    }
    {
        const { w, sent } = bootHr({ form: { title: 'Expenses policy', body: 'New words', url: '', department_id: '', requires_ack: 'yes', republish: 'new' } });
        await w.loadPoliciesView();
        await wait(40);
        await w.editPolicy(1);
        await wait(40);
        const put = sent.find(s => s.url === '/api/policies/1' && s.method === 'PUT');
        check('choosing "a new version" republishes', put && bodyOf(put).republish === true && bodyOf(put).requires_ack === true, put && put.body);
    }
    {
        const { w, sent } = bootHr({ form: { title: 'Code of conduct', body: 'Be kind', url: '', department_id: '5', requires_ack: 'no' } });
        await w.editPolicy();
        await wait(40);
        const post = sent.find(s => s.url === '/api/policies' && s.method === 'POST');
        check('a new policy posts its audience and whether it needs acknowledging', post && bodyOf(post).department_id === '5' && bodyOf(post).requires_ack === false, post && post.body);
    }
    // --- portal ---
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const sent = [];
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url, init) => {
                    const p = String(url).split('?')[0];
                    const method = (init && init.method) || 'GET';
                    sent.push({ url: p, method });
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/policies') return give({ to_read: 1, policies: [
                        { id: 1, title: 'Expenses <i>policy</i>', body: 'Keep <b>receipts</b>.', url: '', version: 2, requires_ack: true, to_read: true, acknowledged: false, acknowledged_at: '' },
                        { id: 2, title: 'Handbook', body: '', url: 'https://docs.example/h', version: 1, requires_ack: true, to_read: false, acknowledged: true, acknowledged_at: '2026-09-02 09:00:00' } ] });
                    if (/\/acknowledge$/.test(p)) return give({ acknowledged_at: 'now', version: 2 });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadMyPolicies();
        await wait(30);
        const host = doc.getElementById('policies');
        check('the portal lists policies with the unread one first and the words as text', host.children.length === 2 && /Expenses <i>policy<\/i>/.test(host.children[0].textContent) && !host.querySelector('b') && /Keep <b>receipts<\/b>/.test(host.textContent));
        check('  the read one says when, and a linked one links out', /Acknowledged 2026-09-02/.test(host.children[1].textContent) && !!host.children[1].querySelector('a[href="https://docs.example/h"]'));
        const btn = [...host.querySelectorAll('button')].find(b => /I have read/.test(b.textContent));
        check('  only the unread one has the acknowledge button', !!btn && host.querySelectorAll('button').length === 1);
        btn.click();
        await wait(30);
        check('  pressing it acknowledges', sent.some(s => s.url === '/api/employee/policies/1/acknowledge' && s.method === 'POST'));
    }
    console.log(failures === 0 ? '\nAll policy checks passed.' : `\n${failures} policy check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
