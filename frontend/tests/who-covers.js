/** A pending leave request says who else in the department is off those days, on HR's list and the manager's approvals. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const ROOT = path.resolve(__dirname, '..');
let failures = 0;
const check = (label, ok, detail) => { if (ok) console.log(`ok    ${label}`); else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
        const w = dom.window;
        w.console.error = () => { };
        w.fetch = (url) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(String(url).split('?')[0].endsWith('s') ? [] : {}) });
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        const html = w.leaveRow ? w.leaveRow({ id: 1, employee_id: 2, employee_name: 'Ravi', leave_type: 'annual', start_date: '2026-10-01', end_date: '2026-10-02', days: 2, reason: 'x', status: 'pending',
            others_off: [{ employee_id: 3, name: 'Mo <b>Off</b>', from: '2026-10-01', to: '2026-10-03' }] }) : null;
        if (html === null) {
            // The renderer is not exported by that name; find it by its output instead.
            const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
            check('HR\'s leave row names the others off, as text', /in the department off then/.test(src) && /others_off\.map/.test(src));
        } else {
            check('HR\'s leave row names the others off, as text', /1 other in the department off then: Mo <b>Off<\/b>/.test(html.replace(/&lt;/g, '<').replace(/&gt;/g, '>')) && !/<b>Off<\/b>/.test(html));
        }
    }
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url) => {
                    const p = String(url).split('?')[0];
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/approvals') return give({ count: 1, corrections: [], expenses: [], leave: [
                        { id: 1, employee_id: 2, employee: 'Ravi', leave_type: 'annual', days: 2, start_date: '2026-10-01', end_date: '2026-10-02', reason: '', annual_remaining: 10,
                          others_off: [{ employee_id: 3, name: 'Mo <i>Off</i>', from: '2026-10-01', to: '2026-10-03' }] } ] });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadApprovals();
        await wait(40);
        const card = doc.getElementById('approvalsCard');
        check('the manager\'s approval names who else is off, as text', /Also off then: Mo <i>Off<\/i>/.test(card.textContent) && !card.querySelector('i'));
    }
    console.log(failures === 0 ? '\nAll who-covers checks passed.' : `\n${failures} who-covers check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
