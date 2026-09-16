/**
 * The leave year and training courses, on screen: the Leave page reads its
 * policy as one line and edits it in a dialog; the Training page lists
 * courses, assigns them, opens who has them and marks them done; the
 * profile shows a person's training; the portal shows theirs with a
 * button to say it is done, and the balance card says what carried over.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const POLICY = { year_start: '04-01', accrual: 'monthly', carry_over_max: 5, carry_over_expires_months: 3, pro_rata: true,
    current_year_start: '2026-04-01', current_year_end: '2027-03-31', accruals: ['upfront', 'monthly'] };
const COURSES = { courses: [
    { id: 1, title: 'Fire <b>safety</b>', description: '', link: 'https://learn.example/fire', provider: 'Safety Co', duration_hours: 1.5, mandatory: true, due_days: 14, renew_months: 12, self_complete: true, active: true, assigned: 3, done: 1, overdue: 1 },
    { id: 2, title: 'Old course', description: '', link: '', provider: '', duration_hours: 0, mandatory: false, due_days: 30, renew_months: 0, self_complete: false, active: false, assigned: 2, done: 2, overdue: 0 } ] };
const ASSIGNMENTS = { course: COURSES.courses[0], assignments: [
    { id: 1, course_id: 1, employee_id: 7, employee: 'Ann <i>Lee</i>', assigned_on: '2026-09-01', due_on: '2026-09-10', status: 'overdue', completed_on: '', completed_by: '', expires_on: '', note: '' },
    { id: 2, course_id: 1, employee_id: 8, employee: 'Bo Ray', assigned_on: '2026-09-01', due_on: '2026-09-15', status: 'done', completed_on: '2026-09-05', completed_by: 'hr', expires_on: '2027-09-05', note: 'Cert 123' } ] };

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
        if (p === '/api/hr/leave-policy') return give(method === 'PUT' ? Object.assign({}, POLICY, bodyOf({ body: init.body })) : POLICY);
        if (p === '/api/courses' && method === 'GET') return give(COURSES);
        if (p === '/api/courses' && method === 'POST') return give({ id: 3 });
        if (p === '/api/courses/1/assignments') return give(ASSIGNMENTS);
        if (p === '/api/courses/1/assign') return give({ assigned: 2, already: 1 });
        if (p === '/api/courses/1/assignments/7/complete') return give({ status: 'done' });
        if (p === '/api/departments') return give([{ id: 4, name: 'Ops' }]);
        if (p === '/api/employees/7/courses') return give({ courses: [{ id: 1, course_id: 1, status: 'overdue', due_on: '2026-09-10', completed_on: '', expires_on: '', course: { id: 1, title: 'Fire <b>safety</b>' } }] });
        if (p === '/api/employees/7' && method === 'GET') return give({ id: 7, full_name: 'Ann', first_name: 'Ann', last_name: 'Lee', status: 'active', probation: { status: '' }, custom_fields: [], payslips: [], onboarding_items: [], leave_requests: [], goals: [], documents: [], attendance_summary: {}, leave_balance: {} });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiPrompt = () => Promise.resolve(opts.prompt === undefined ? 'Cert 9' : opts.prompt);
    w.uiChoose = () => Promise.resolve(opts.choose === undefined ? '1' : opts.choose);
    w.uiForm = (fields) => { forms.push(fields); return Promise.resolve(opts.form === undefined ? null : opts.form); };
    w.loadHRStats = () => { };
    return { w, doc: w.document, sent, forms };
}

function bootPortal(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body });
                const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/courses') return give(opts.courses || { courses: [] });
                if (p === '/api/employee/courses/1/complete') return give({ status: 'done' });
                if (p === '/api/employee/leave-balance') return give(opts.balance || {});
                return give(p.endsWith('s') ? [] : {});
            };
        } });
    return { w: dom.window, doc: dom.window.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the Leave page has a policy button and line; Training has courses; the profile has a Training widget',
            /editLeavePolicy\(\)/.test(src) && /id="leave-policy-line"/.test(src) && /id="courses-list"/.test(src) && /id="emp-courses-list"/.test(src));
    }
    {
        const { w, doc, forms, sent } = boot({ form: { year_start: '01-01', accrual: 'upfront', pro_rata: 'no', carry_over_max: '10', carry_over_expires_months: '0' } });
        await w.loadLeavePolicyLine();
        await wait(30);
        const line = doc.getElementById('leave-policy-line').textContent;
        check('the policy reads as one line', /Leave year from 1 Apr \(2026-04-01 to 2027-03-31\)/.test(line) && /accrue month by month/.test(line) && /up to 5 days carry over, lapsing after 3 months/.test(line), line);
        await w.editLeavePolicy();
        await wait(30);
        const f = forms[0];
        check('editing asks for the start, accrual, pro-rata, carry-over cap and lapse', f && f.map(x => x.name).join() === 'year_start,accrual,pro_rata,carry_over_max,carry_over_expires_months' && f[0].value === '04-01');
        const put = sent.find(s => s.url === '/api/hr/leave-policy' && s.method === 'PUT');
        check('  and sends numbers and booleans, not strings', put && JSON.stringify(bodyOf(put)) === '{"year_start":"01-01","accrual":"upfront","pro_rata":false,"carry_over_max":10,"carry_over_expires_months":0}', put && put.body);
    }
    {
        const { w, doc, sent, forms } = boot({ form: { who: 'dept:4', people: '' } });
        await w.loadCourses();
        await wait(30);
        const host = doc.getElementById('courses-list');
        const rows = host.querySelectorAll('tbody tr');
        check('courses are listed with counts, mandatory and closed marked, titles as text',
            rows.length === 2 && /Fire <b>safety<\/b>/.test(rows[0].textContent) && !host.querySelector('b') && /mandatory/.test(rows[0].textContent) && /every 12 months/.test(rows[0].textContent) && /closed/.test(rows[1].textContent), host.textContent.slice(0, 200));
        check('  a closed course cannot be assigned', !rows[1].querySelector('[data-course-assign]') && rows[0].querySelector('[data-course-assign]'));
        check('  the note counts what is overdue', /1 overdue/.test(doc.getElementById('courses-note').textContent));
        rows[0].querySelector('[data-course-assign]').click();
        await wait(40);
        const f = forms[forms.length - 1];
        check('assigning offers everybody, each department, or named people', f && f[0].options.length === 3 && f[0].options[1].value === 'dept:4');
        const post = sent.find(s => s.url === '/api/courses/1/assign' && s.method === 'POST');
        check('  and sends the department', post && bodyOf(post).department_id === 4, post && post.body);
        rows[0].querySelector('[data-course-open]').click();
        await wait(40);
        const detail = doc.getElementById('course-detail');
        check('opening a course lists who has it, status and notes, names as text',
            /Ann <i>Lee<\/i>/.test(detail.textContent) && !detail.querySelector('i') && /Overdue/.test(detail.textContent) && /Cert 123/.test(detail.textContent) && /\(HR\)/.test(detail.textContent), detail.textContent.slice(0, 200));
        check('  only the unfinished can be marked done', detail.querySelectorAll('[data-course-done]').length === 1);
        detail.querySelector('[data-course-done]').click();
        await wait(40);
        const done = sent.find(s => s.url === '/api/courses/1/assignments/7/complete');
        check('  marking done asks for a note and posts it', done && bodyOf(done).note === 'Cert 9');
    }
    {
        const { w, doc, sent, forms } = boot({ form: { title: 'GDPR', link: 'https://x', provider: '', duration_hours: '2', due_days: '21', renew_months: '12', mandatory: 'yes', self_complete: 'hr', description: 'Data' } });
        await w.editCourse();
        await wait(30);
        const post = sent.find(s => s.url === '/api/courses' && s.method === 'POST');
        check('a new course posts numbers and booleans', post && JSON.stringify(bodyOf(post)) === '{"title":"GDPR","link":"https://x","provider":"","duration_hours":2,"due_days":21,"renew_months":12,"mandatory":true,"self_complete":false,"description":"Data"}', post && post.body);
    }
    {
        const { w, doc, sent } = boot();
        w.currentEmployeeId = 7;
        await w.viewEmployee(7);
        await wait(80);
        const host = doc.getElementById('emp-courses-list');
        check('the profile lists their training with status, titles as text', /Fire <b>safety<\/b>/.test(host.textContent) && !host.querySelector('b') && /Overdue/.test(host.textContent) && /due 2026-09-10/.test(host.textContent), host.textContent);
        await w.assignCourseTo(7);
        await wait(40);
        const post = sent.find(s => s.url === '/api/courses/1/assign');
        check('  assigning from the profile picks a course and sends this person', post && JSON.stringify(bodyOf(post).employee_ids) === '[7]');
    }
    // --- portal ---
    {
        const { w, doc, sent } = bootPortal({ courses: { courses: [
            { id: 1, course_id: 1, status: 'overdue', due_on: '2026-09-10', completed_on: '', expires_on: '', course: { id: 1, title: 'Fire <b>safety</b>', link: 'https://learn.example/fire', provider: 'Safety Co', duration_hours: 1.5, mandatory: true, self_complete: true, description: '' } },
            { id: 2, course_id: 2, status: 'assigned', due_on: '2026-10-01', completed_on: '', expires_on: '', course: { id: 2, title: 'GDPR', link: '', provider: '', duration_hours: 0, mandatory: false, self_complete: false, description: 'Read <i>it</i>' } },
            { id: 3, course_id: 3, status: 'done', due_on: '2026-08-01', completed_on: '2026-07-20', expires_on: '', course: { id: 3, title: 'Done one', link: '', provider: '', duration_hours: 0, mandatory: false, self_complete: true, description: '' } } ] } });
        await w.loadMyTraining();
        await wait(40);
        const host = doc.getElementById('training');
        check('the portal lists training, overdue first, titles and text as text, with the link and a done button where allowed',
            !doc.getElementById('trainingCard').hidden && host.children.length === 3 && /Fire <b>safety<\/b> · mandatory/.test(host.children[0].textContent) && !host.querySelector('b, i') &&
            /Overdue since 2026-09-10/.test(host.children[0].textContent) && host.children[0].querySelector('a[href="https://learn.example/fire"]') && host.children[0].querySelector('button') &&
            /HR marks this one done/.test(host.children[1].textContent) && !host.children[1].querySelector('button') && /Done 2026-07-20/.test(host.children[2].textContent), host.textContent.slice(0, 300));
        check('  the hint counts what is left', /2 to complete/.test(doc.getElementById('training-hint').textContent));
        host.children[0].querySelector('button').click();
        await wait(40);
        check('  saying it is done posts the completion', sent.some(s => s.url === '/api/employee/courses/1/complete' && s.method === 'POST'));
    }
    {
        const { w, doc } = bootPortal({ balance: { annual_total: 25, annual_entitlement: 20, annual_accrued: 20, annual_carried: 5, carry_expires_on: '2026-03-31', annual_taken: 2, annual_pending: 0, annual_remaining: 23, sick_total: 10, sick_taken: 0, sick_remaining: 10, leave_year_start: '2026-01-01', leave_year_end: '2026-12-31', accrual: 'upfront' } });
        await w.loadLeaveBalance();
        await wait(30);
        const text = doc.getElementById('leaveRemaining').textContent;
        check('the balance card says what carried over, when it lapses, and the leave year', /includes 5 carried over, use by 2026-03-31/.test(text) && /leave year to 2026-12-31/.test(text) && /23/.test(text), text);
    }
    {
        const { w, doc } = bootPortal({ balance: { annual_total: 8, annual_entitlement: 24, annual_accrued: 8, annual_carried: 0, carry_expires_on: '', annual_taken: 0, annual_pending: 0, annual_remaining: 8, sick_total: 10, sick_taken: 0, sick_remaining: 10, leave_year_start: '2026-01-01', leave_year_end: '2026-12-31', accrual: 'monthly' } });
        await w.loadLeaveBalance();
        await wait(30);
        check('with monthly accrual it says how much is earned so far', /8 of 24 earned so far this year/.test(doc.getElementById('leaveRemaining').textContent));
    }
    console.log(failures === 0 ? '\nAll leave-year and training checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
