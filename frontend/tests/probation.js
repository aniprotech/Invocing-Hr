/**
 * Probation and celebrations, on screen.
 *
 * The profile says where a trial period stands and offers the decision;
 * the onboarding hub lists everybody still on one, due first; the HR
 * dashboard's "what lands soon" carries probations ending and birthdays.
 * In the portal, a birthday is a day and a month and never a year.
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

const PROBATIONS = { probations: [
    { employee_id: 7, employee_name: "Nia O'Neil", job_title: 'Analyst', status: 'on_probation', end: '2026-09-10', days_left: -5, due: true, overdue: true, manager_name: 'Bea Boss' },
    { employee_id: 8, employee_name: 'Sam Low', job_title: '', status: 'extended', end: '2026-09-25', days_left: 10, due: true, overdue: false, manager_name: '' },
    { employee_id: 9, employee_name: 'Zed Far', job_title: '', status: 'on_probation', end: '2026-12-01', days_left: 77, due: false, overdue: false, manager_name: '' },
], due: 2, overdue: 1, default_months: 3, warn_days: 14 };
const EMP = { id: 7, full_name: "Nia O'Neil", first_name: 'Nia', last_name: "O'Neil", status: 'active', date_of_birth: '1990-05-05',
    probation: { status: 'on_probation', end: '2026-09-10', days_left: -5, due: true, overdue: true, note: '', decided_by: '', decided_at: '' },
    payslips: [], onboarding_items: [], leave_requests: [], goals: [], documents: [], attendance_summary: {}, leave_balance: {} };
const DASH = { headcount: { total: 3 }, today: { expected: 0 }, waiting_on_you: [], waiting_total: 0,
    coming_up: { starting: [], interviews: [], expiring_documents: [],
        probations: [{ name: "Nia O'Neil", ends_on: '2026-09-10', employee_id: 7, days_left: -5 }],
        celebrations: [{ kind: 'birthday', name: 'Bea Boss', on: '2026-09-20', in_days: 5, years: null },
                       { kind: 'anniversary', name: 'Mo Salah', on: '2026-09-16', in_days: 1, years: 3 }] } };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), {
        runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html',
    });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (p === '/api/probations') return give(PROBATIONS);
        if (p === '/api/employees/7' && method === 'GET') return give(EMP);
        if (/\/api\/employees\/\d+\/probation$/.test(p)) return give({ status: 'confirmed' });
        if (p === '/api/hr/dashboard') return give(DASH);
        if (p === '/api/employees/7/history') return give({ history: [] });
        if (p === '/api/employees/7/certifications') return give({ certifications: [] });
        if (p === '/api/employees/7/check-ins') return give({ check_ins: [] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    const toasts = [];
    w.showToast = (m) => toasts.push(String(m));
    w.uiConfirm = () => Promise.resolve(true);
    w.uiForm = () => Promise.resolve(opts.form === undefined ? null : opts.form);
    w.hrDataChanged = () => { };
    w.loadHRStats = () => { };
    return { w, doc: w.document, sent, toasts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the add-employee form asks for a date of birth and probation length', /id="emp-dob"/.test(src) && /id="emp-probation-months"/.test(src));
        check('  with "Company default" as the first choice', /<option value="">Company default<\/option>/.test(src));
        check('the profile has a probation line with a decide button', /id="emp-detail-probation"/.test(src) && /id="emp-probation-btn"/.test(src));
        check('the onboarding hub has a Probations panel', /id="probations-list"/.test(src));
    }
    {
        const { w, doc } = boot();
        await w.loadProbations();
        await wait(40);
        const host = doc.getElementById('probations-list');
        const names = [...host.querySelectorAll('a')].map(a => a.textContent);
        check('the hub lists everybody on probation, due first', names.join('|') === "Nia O'Neil|Sam Low|Zed Far", names.join('|'));
        check('  an overdue one says so', /Ended 2026-09-10 - no decision yet/.test(host.textContent));
        check('  an extended one says when it now ends', /Extended, ends 2026-09-25 \(10 days\)/.test(host.textContent));
        check('  the due ones get the primary button', host.innerHTML.split('btn-primary').length - 1 === 2);
        check('  the summary counts', /2 to decide/.test(doc.getElementById('probations-summary').textContent));
    }
    {
        const { w, doc, sent, toasts } = boot({ form: { decision: 'confirm', until: '', note: 'Solid' } });
        await w.viewEmployee(7);
        await wait(60);
        check('the profile shows where the probation stands', /no decision yet/.test(doc.getElementById('emp-detail-probation').textContent));
        check('  and the date of birth', doc.getElementById('emp-detail-dob-ro').textContent === '1990-05-05');
        check('  the button says Decide for somebody on probation', doc.getElementById('emp-probation-btn').textContent === 'Decide');
        await w.decideProbation(7);
        await wait(40);
        const post = sent.find(s => /\/api\/employees\/7\/probation$/.test(s.url));
        check('deciding posts the decision and the note', post && bodyOf(post).decision === 'confirm' && bodyOf(post).note === 'Solid', post && post.body);
    }
    {
        const { w, doc, sent } = boot({ form: { months: '6', note: '' } });
        w._currentEmployee = { full_name: 'X', probation: { status: '' } };
        await w.decideProbation(7);
        await wait(40);
        const post = sent.find(s => /\/api\/employees\/7\/probation$/.test(s.url));
        check('somebody not on probation can be put on one for a number of months', post && bodyOf(post).decision === 'start' && bodyOf(post).months === 6, post && post.body);
    }
    {
        const { w, doc } = boot();
        await w.loadHrDashboard();
        await wait(40);
        const up = doc.getElementById('hr-dash-upcoming').textContent;
        check('the dashboard says whose probation ended without a decision', /Nia O'Neil.s probation ended 2026-09-10 with no decision/.test(up), up);
        check('  and lists birthdays and anniversaries', /Bea Boss.s birthday on 2026-09-20/.test(up) && /Mo Salah: 3 years here tomorrow/.test(up), up);
    }

    // --- the portal --------------------------------------------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url) => {
                    const p = String(url).split('?')[0];
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/celebrations') return give({ celebrations: [
                        { kind: 'birthday', name: 'Bea <b>Boss</b>', on: '2026-09-20', in_days: 0, years: null },
                        { kind: 'anniversary', name: 'Mo', on: '2026-09-21', in_days: 1, years: 1 } ] });
                    if (p === '/api/employee/profile') return give({ first_name: 'N', full_name: 'Nia', job_title: 'Analyst', probation: { status: 'extended', end: '2026-10-01' } });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadCelebrations();
        await wait(30);
        const host = doc.getElementById('celebrations');
        check('the portal shows birthdays and anniversaries as text, with Today and Tomorrow', !doc.getElementById('celebrationsCard').hidden &&
            /Bea <b>Boss<\/b>.s birthday/.test(host.textContent) && !host.querySelector('b') && /Today/.test(host.textContent) && /Tomorrow/.test(host.textContent) && /1 year here/.test(host.textContent));
        await w.loadProfileTab();
        await wait(30);
        check('the portal profile says the probation has been extended and until when', /Extended to 2026-10-01/.test(doc.getElementById('profileDetails').textContent));
    }

    console.log(failures === 0 ? '\nAll probation checks passed.' : `\n${failures} probation check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
