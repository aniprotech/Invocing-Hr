/**
 * Somebody leaving, on screen: the offboarding checklist says whether they
 * have been paid, whether they are in the pension, and offers their P45; the
 * P45 shows what the next employer needs and prints.
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
const text = el => (el ? el.textContent.replace(/\s+/g, ' ') : '');

const CHECK = (o) => Object.assign({
    employee_id: 7, name: 'Ann Lee', status: 'offboarding', end_date: '', assets_out: [], leave_owed_days: 2, expenses_owed: 0, currency: 'GBP',
    open_tasks: [], direct_reports: [], decisions_waiting_on_them: 0, portal_access: true, blocking: [], ready: true,
    final_pay: { last_payslip: { id: 3, number: 'PS-3', pay_date: '2026-05-29', status: 'Draft' }, unpaid_payslips: 1, unpaid_net: 2453.64 },
    pension: { member: true, status: 'member', provider: 'NEST <b>x</b>' }, uk_payroll: true, p45_ready: true,
}, o || {});

const P45 = {
    tax_year: '2026-27', leaving_date: '2026-05-31',
    employer: { name: 'Northwind <i>Care</i>', address: '1 Mill Lane\nLeeds', paye_reference: '123/AB456' },
    employee: { name: 'Ann Lee', ni_number: 'AB123456C', date_of_birth: '1990-01-01', address_lines: ['1 High Street', 'Leeds'], postcode: 'LS1 4AB', payroll_id: 'EMP-0007' },
    tax_code: 'S1257L', week1_month1: true, last_period: { type: 'month', number: 2 }, student_loan: true, student_loan_plan: '2', postgrad_loan: false,
    pay_this_employment: 5400, tax_this_employment: 700.4, total_pay_to_date: 6400, total_tax_to_date: 850.4, payslips: 2,
    missing: ['their address'], notes: ['Parts 1A, 2 and 3 go to the employee.'],
};

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/dashboard' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url), p = full.split('?')[0], method = (init && init.method) || 'GET';
        sent.push({ url: p, full, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (opts.reply && opts.reply[p]) { const r = opts.reply[p](init); return give(r.body, r.status); }
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/employees/7/p45') return give(P45);
        if (p === '/api/employees/7/complete-offboard') return give({ message: 'Employee offboarded', end_date: '2026-05-31', reports_moved: 0, pension_ended: true, pension_provider: 'NEST' });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m, t) => { w._toasts = (w._toasts || []).concat([[m, t]]); };
    w.uiConfirm = () => Promise.resolve(true);
    w.formatCurrency = (v) => '£' + Number(v || 0).toFixed(2);
    w.allEmployees = [];
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const { w, doc } = boot();
        w.renderOffboarding(CHECK());
        const t = text(doc.getElementById('offb-checklist'));
        check('the checklist says what is not yet paid and the last payslip', /1 payslip\(s\) not yet paid/.test(t) && /2,?453\.64/.test(t) && /Last payslip PS-3, paid on 2026-05-29/.test(t), t);
        check('  and that the final payslip should cover their last day and leave owed', /final payslip should include pay up to their last day and any leave owed/.test(t));
        check('  that their pension ends and the provider must be told, the provider named as text', /In the workplace pension with NEST <b>x<\/b>/.test(t) && /Tell the provider/.test(t) && !doc.querySelector('#offb-checklist b'));
        check('  and that their P45 is ready', /P45 ready to give them/.test(t) && !!doc.getElementById('offb-p45'));
        w.showGeneratePayslipModal = () => { w._finalPayslip = true; };
        doc.getElementById('offb-final-payslip').dispatchEvent(new w.Event('click', { bubbles: true, cancelable: true }));
        check('"Make their final payslip" opens the payslip form', w._finalPayslip === true);
        w.openP45 = (id, leaving) => { w._p45 = [id, leaving]; };
        doc.getElementById('offb-end').value = '2026-05-31';
        doc.getElementById('offb-p45').dispatchEvent(new w.Event('click', { bubbles: true, cancelable: true }));
        check('"Open their P45" uses the last day entered', JSON.stringify(w._p45) === JSON.stringify([7, '2026-05-31']));
    }
    {
        const { w, doc } = boot();
        w.renderOffboarding(CHECK({ final_pay: { last_payslip: null, unpaid_payslips: 0, unpaid_net: 0 }, pension: { member: false, status: '', provider: '' }, uk_payroll: false, p45_ready: false }));
        const t = text(doc.getElementById('offb-checklist'));
        check('somebody never paid, not in the pension, on the simple payroll: no pension or P45 lines', /No payslips yet/.test(t) && !/workplace pension/.test(t) && !/P45/.test(t));
    }
    {
        const { w, doc } = boot();
        w.renderOffboarding(CHECK({ p45_ready: false }));
        check('on UK payroll with nothing paid yet, the P45 waits', /P45 - once they have been paid/.test(text(doc.getElementById('offb-checklist'))) && !doc.getElementById('offb-p45'));
    }
    {
        const { w, doc } = boot();
        w.currentEmployeeId = 7;
        w.hrDataChanged = () => { };
        w.renderOffboarding(CHECK());
        doc.getElementById('offb-end').value = '2026-05-31';
        await w.completeOffboarding();
        check('closing the account says to tell the pension provider, with the day', (w._toasts || []).some(t => /tell NEST they left on 2026-05-31/.test(t[0])));
    }

    // --- the P45 --------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.openP45(7, '2026-05-31');
        const t = text(doc.getElementById('p45-body'));
        check('the P45 asks for the leaving day given', sent.some(x => x.full === '/api/employees/7/p45?leaving=2026-05-31'));
        check('it opens with the employer, their PAYE reference and the employee', doc.getElementById('p45-modal').style.display === 'flex' &&
            /123\/AB456/.test(t) && /AB123456C/.test(t) && /1 High Street, Leeds, LS1 4AB/.test(t) && /EMP-0007/.test(t));
        check('  the code they were on, week 1 / month 1, and the last period', /S1257L \(week 1 \/ month 1\)/.test(t) && /Month 2/.test(t));
        check('  student loan carries on, postgraduate does not', /Student loan deductions to continue\s*Yes \(plan 2\)/.test(t) && /Postgraduate loan deductions to continue\s*No/.test(t));
        check('  total pay and tax to date, and in this job', /Total pay to date \(2026-27\)\s*£6400\.00/.test(t) && /Total tax to date\s*£850\.40/.test(t) && /Pay in this employment\s*£5400\.00/.test(t) && /Tax in this employment\s*£700\.40/.test(t));
        check('  what is missing is said first', /Still missing: their address/.test(t));
        check('  nothing from the server runs as markup', !doc.querySelector('#p45-body i'));
        let printed = null;
        w.open = () => ({ document: { write: h => { printed = h; }, close: () => { } }, focus: () => { }, print: () => { printed = printed + '[printed]'; } });
        doc.getElementById('p45-print').onclick();
        check('Print writes the P45 to a page of its own and prints it', /P45 - details of employee leaving work/.test(printed) && /AB123456C/.test(printed) && /\[printed\]$/.test(printed));
        doc.getElementById('p45-done').onclick();
        check('Close shuts it', doc.getElementById('p45-modal').style.display === 'none');
    }
    {
        const { w, doc } = boot({ reply: { '/api/employees/7/p45': () => ({ status: 400, body: { detail: 'Set their last day first - the P45 is for the day they leave' } }) } });
        await w.openP45(7, '');
        check('a P45 that cannot be made says why', (w._toasts || []).some(t => /Set their last day first/.test(t[0])) && doc.getElementById('p45-modal').style.display !== 'flex');
    }
    {
        const { w, doc } = boot();
        w.open = () => null;
        await w.openP45(7, '2026-05-31');
        doc.getElementById('p45-print').onclick();
        check('with pop-ups blocked, printing says so', (w._toasts || []).some(t => /Allow pop-ups/.test(t[0])));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
