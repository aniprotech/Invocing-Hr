/**
 * Custom fields, on screen: defined under Settings, filled on the profile
 * with a control that fits the kind, and shown to the person when the
 * field says so.
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
const FIELDS = { kinds: [], fields: [
    { id: 1, key: 'locker', label: 'Locker <b>no</b>', kind: 'number', choices: [], required: false, shown_to_staff: true, position: 0 },
    { id: 2, key: 'shirt', label: 'Shirt size', kind: 'choice', choices: ['S', 'M', 'L'], required: true, shown_to_staff: false, position: 1 } ] };
const EMP = { id: 7, full_name: 'Ann', first_name: 'Ann', last_name: 'Lee', status: 'active', probation: { status: '' },
    custom_fields: [{ key: 'locker', label: 'Locker <b>no</b>', kind: 'number', choices: [], required: false, shown_to_staff: true, value: '12' },
                    { key: 'shirt', label: 'Shirt size', kind: 'choice', choices: ['S', 'M', 'L'], required: true, shown_to_staff: false, value: '' }],
    payslips: [], onboarding_items: [], leave_requests: [], goals: [], documents: [], attendance_summary: {}, leave_balance: {} };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], forms = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/custom-fields' && method === 'GET') return give(FIELDS);
        if (p === '/api/custom-fields' && method === 'POST') return give({ id: 3 });
        if (p === '/api/employees/7' && method === 'GET') return give(EMP);
        if (p === '/api/employees/7' && method === 'PUT') return give({ message: 'ok' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiForm = (fields) => { forms.push(fields); return Promise.resolve(opts.form === undefined ? null : opts.form); };
    w.loadHRStats = () => { };
    return { w, doc: w.document, sent, forms };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Settings has an Employee fields section and the profile a More details widget', /data-settings-section="employee-fields"/.test(src) && /id="emp-custom-list"/.test(src));
    }
    {
        const { w, doc } = boot();
        await w.loadCustomFields();
        await wait(30);
        const host = doc.getElementById('custom-fields-list');
        check('fields are listed with kind, choices, required and visibility, labels as text', /Locker <b>no<\/b>/.test(host.textContent) && !host.querySelector('b') && /S \/ M \/ L/.test(host.textContent) && /choice/.test(host.textContent));
    }
    {
        const { w, sent } = boot({ form: { label: 'Clearance', kind: 'choice', choices: 'SC, DV', required: 'yes', shown_to_staff: 'no' } });
        await w.addCustomField();
        await wait(30);
        const post = sent.find(s => s.url === '/api/custom-fields' && s.method === 'POST');
        check('adding posts the kind, choices and flags', post && bodyOf(post).kind === 'choice' && bodyOf(post).choices === 'SC, DV' && bodyOf(post).required === true && bodyOf(post).shown_to_staff === false, post && post.body);
    }
    {
        const { w, doc, sent, forms } = boot({ form: { locker: '14', shirt: 'M' } });
        w.currentEmployeeId = 7;
        await w.viewEmployee(7);
        await wait(80);
        const host = doc.getElementById('emp-custom-list');
        check('the profile shows the values, labels as text, empty ones as a dash', /Locker <b>no<\/b>/.test(host.textContent) && !host.querySelector('b') && /12/.test(host.textContent) && /Shirt size: -/.test(host.textContent.replace(/\s+/g, ' ')));
        await w.editCustomValues(7);
        await wait(40);
        const f = forms[forms.length - 1];
        check('editing opens a control per field that fits its kind', f.length === 2 && f[0].type === 'number' && f[1].type === 'select' && f[1].options.length === 4);
        const put = sent.find(s => s.url === '/api/employees/7' && s.method === 'PUT');
        check('  and saves them under custom', put && JSON.stringify(bodyOf(put).custom) === '{"locker":"14","shirt":"M"}', put && put.body);
    }
    // --- portal ---
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url) => {
                    const p = String(url).split('?')[0];
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/profile') return give({ first_name: 'A', full_name: 'Ann', job_title: 'Dev', probation: { status: '' },
                        custom_fields: [{ key: 'locker', label: 'Locker <i>no</i>', kind: 'number', value: '12', shown_to_staff: true }, { key: 'empty', label: 'Empty', kind: 'text', value: '', shown_to_staff: true }] });
                    if (p === '/api/employee/pay-band') return give({ visible: false });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadProfileTab();
        await wait(40);
        const text = doc.getElementById('profileDetails').textContent;
        check('the portal profile shows the fields shown to staff with a value, labels as text', /Locker <i>no<\/i>/.test(text) && !doc.getElementById('profileDetails').querySelector('i') && /12/.test(text) && !/Empty/.test(text));
    }
    console.log(failures === 0 ? '\nAll custom-field checks passed.' : `\n${failures} custom-field check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
