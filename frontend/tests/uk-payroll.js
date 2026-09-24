/**
 * UK payroll screens.
 *
 * The switch on the Payroll screen; the UK card and form on an employee;
 * the add-employee form's UK fields; and a UK payslip showing Income Tax,
 * National Insurance, the loans, the codes and the tax year to date. None
 * of it shows for a business on the simple payroll.
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

const SETTINGS = (regime) => ({ regime, tax_year: '2026-27', rates_ready: true, rates_loaded: ['2026-27'],
    rates_source: 'HMRC rates and thresholds for employers 2026 to 2027', ni_categories: ['A', 'B', 'C', 'H', 'J', 'M', 'V', 'Z'],
    student_loan_plans: ['1', '2', '4', '5'] });

const EMP = { id: 7, first_name: 'Ann', last_name: 'Lee', ni_number: 'AB123456C', tax_code: '1257L', ni_category: 'A',
    student_loan_plan: '2', postgrad_loan: false, is_director: false, director_since: '', starter_declaration: '',
    p45_tax_year: 0, p45_taxable_pay: 0, p45_tax: 0 };

const UK_PAYSLIP = {
    id: 3, number: 'PS-0003', status: 'Draft', employee: { full_name: 'Ann Lee', pay_frequency: 'monthly' },
    period_start: '2026-04-01', period_end: '2026-04-30', pay_date: '2026-04-30',
    basic_salary: 3000, overtime_pay: 0, bonus: 0, allowances: 0, gross_pay: 3000,
    tax_amount: 390.2, insurance: 0, retirement: 0, other_deductions: 0, standing_deduction: 0,
    total_deductions: 595.36, net_pay: 2404.64, company: { name: 'Northwind' }, regime: 'uk',
    uk: { tax_code: '1257L', ni_category: 'A', ni_number: 'AB123456C', tax_year: '2026-27', tax_period: 1,
          employee_ni: 156.16, employer_ni: 387.45, student_loan: 49, postgrad_loan: 0, student_loan_plan: '2',
          year_to_date: { tax_year: '2026-27', payslips: 1, gross_pay: 3000, taxable_pay: 3000, tax: 390.2,
                          employee_ni: 156.16, employer_ni: 387.45, student_loan: 49, postgrad_loan: 0, net_pay: 2404.64 } }
};

function boot(opts) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/payroll' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    let regime = opts.regime || 'simple';
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/payroll/settings' && method === 'PUT') { regime = bodyOf({ body: init.body }).regime; return give(SETTINGS(regime)); }
        if (p === '/api/payroll/settings') return give(SETTINGS(regime));
        if (p === '/api/payslips/3') return give(opts.payslip || UK_PAYSLIP);
        if (p === '/api/employees/7' && method === 'PUT') return give({ message: 'Employee updated' });
        if (p === '/api/employees/7') return give(Object.assign({}, EMP, opts.emp || {}));
        if (p === '/api/payroll/preview') return give({ gross_pay: 3000, tax_amount: 390.2, employee_ni: 156.16, employer_ni: 387.45,
            student_loan: 49, postgrad_loan: 0, net_pay: 2404.64, tax_year_label: '2026-27', tax_period: 6, tax_code: '1257L', notes: [] });
        if (p === '/api/employees' && method === 'POST') return give({ message: 'Employee created', id: 9 });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.getCurrencySymbol = () => '£';
    w.formatCurrency = (v) => '£' + Number(v || 0).toFixed(2);
    return { w, doc: w.document, sent };
}

(async () => {
    // --- the switch ---------------------------------------------------------
    {
        const { w, doc, sent } = boot({ regime: 'simple' });
        await w.renderPayrollRegime();
        await wait(10);
        const sel = doc.getElementById('payroll-regime-select');
        check('the Payroll screen says which payroll this business runs', sel && sel.value === 'simple');
        check('  and says nothing about tax years while it is the simple one', doc.getElementById('payroll-regime-note').textContent === '');
        await w.setPayrollRegime('uk');
        await wait(10);
        const put = sent.find(s => s.url === '/api/payroll/settings' && s.method === 'PUT');
        check('choosing UK PAYE asks first, then saves it', put && bodyOf(put).regime === 'uk');
        check('  and the screen then says which tax year its rates are for',
            /Tax year 2026-27/.test(doc.getElementById('payroll-regime-note').textContent), doc.getElementById('payroll-regime-note').textContent);
    }

    // --- the employee's UK card ---------------------------------------------
    {
        const { w, doc } = boot({ regime: 'simple' });
        await w.renderEmployeeUk(EMP);
        check('on the simple payroll an employee has no UK card', doc.getElementById('emp-uk-card').style.display === 'none');
    }
    {
        const { w, doc } = boot({ regime: 'uk' });
        await w.renderEmployeeUk(EMP);
        const card = doc.getElementById('emp-uk-card');
        const text = card.textContent;
        check('on UK payroll the employee has a UK card', card.style.display !== 'none');
        check('  showing the NI number, code, category and loan', /AB123456C/.test(text) && /1257L/.test(text) && /A - standard/.test(text) && /Plan 2/.test(text), text.slice(0, 300));
        check('  and nothing is flagged as missing', !/Still needed/.test(text));
    }
    {
        const { w, doc } = boot({ regime: 'uk' });
        await w.renderEmployeeUk(Object.assign({}, EMP, { ni_number: '', tax_code: '', starter_declaration: 'B' }));
        const text = doc.getElementById('emp-uk-card').textContent;
        check('a starter with no code says what is being used meanwhile', /using statement B/.test(text), text.slice(0, 300));
        check('  and says what is still needed', /Still needed: an NI number and a tax code/.test(text), text);
    }
    {
        const { w, doc } = boot({ regime: 'uk' });
        await w.renderEmployeeUk(Object.assign({}, EMP, { tax_code: '<img src=x onerror=alert(1)>' }));
        check('whatever is in a code is shown as text', !doc.querySelector('#emp-uk-card img'));
    }

    // --- the form ------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ regime: 'uk' });
        await w.loadPayrollSettings(true);
        await w.renderEmployeeUk(Object.assign({}, EMP, { p45_tax_year: 2026, p45_taxable_pay: 6000, p45_tax: 780.6 }));
        w.openUkPayroll();
        check('the form opens with the employee\'s details in it',
            doc.getElementById('uk-payroll-modal').style.display === 'flex' && doc.getElementById('ukp-ni-number').value === 'AB123456C'
            && doc.getElementById('ukp-student-loan').value === '2' && doc.getElementById('ukp-ni-category').value === 'A');
        check('  and the P45 in the current tax year', doc.getElementById('ukp-p45-year').value === '2026' && doc.getElementById('ukp-p45-pay').value === '6000');
        doc.getElementById('ukp-tax-code').value = 'S1257L';
        doc.getElementById('ukp-is-director').checked = true;
        doc.getElementById('ukp-director-since').value = '2026-07-01';
        await w.saveUkPayroll();
        await wait(10);
        const put = sent.find(s => s.url === '/api/employees/7' && s.method === 'PUT');
        const b = bodyOf(put || {});
        check('Save sends every UK field', put && b.tax_code === 'S1257L' && b.is_director === true && b.director_since === '2026-07-01'
            && b.ni_number === 'AB123456C' && b.student_loan_plan === '2' && b.p45_tax_year === 2026 && b.p45_tax === 780.6, put && put.body);
        check('  and closes', doc.getElementById('uk-payroll-modal').style.display === 'none');
    }

    // --- the preview -----------------------------------------------------------
    {
        const { w, doc, sent } = boot({ regime: 'uk' });
        await w.renderEmployeeUk(EMP);
        await w.previewUkPayslip();
        await wait(10);
        const text = doc.getElementById('emp-uk-preview').textContent;
        check('the preview shows tax, NI, the loan and take-home, and says nothing was saved',
            /Income Tax£390.20/.test(text) && /National Insurance£156.16/.test(text) && /Student loan£49.00/.test(text)
            && /Take-home£2404.64/.test(text) && /Nothing has been saved/.test(text), text);
        check('  without making a payslip', !sent.some(s => s.url === '/api/payslips' && s.method === 'POST'));
    }

    // --- adding an employee --------------------------------------------------------
    {
        const { w, doc, sent } = boot({ regime: 'uk' });
        await w.showAddEmployeeModal();
        await wait(20);
        check('on UK payroll the add form asks for the UK details', doc.getElementById('emp-uk-fields').style.display !== 'none');
        doc.getElementById('emp-first-name').value = 'Ben';
        doc.getElementById('emp-last-name').value = 'Ode';
        doc.getElementById('emp-email').value = 'ben@example.com';
        doc.getElementById('emp-password').value = 'Passw0rdTest';
        doc.getElementById('emp-ni-number').value = 'AB 65 43 21 A';
        doc.getElementById('emp-tax-code').value = '1257L';
        doc.getElementById('emp-ni-category').value = 'M';
        doc.getElementById('emp-starter-declaration').value = 'A';
        doc.getElementById('emp-student-loan').value = '5';
        await w.submitNewEmployee();
        await wait(20);
        const post = sent.find(s => s.url === '/api/employees' && s.method === 'POST');
        const b = bodyOf(post || {});
        check('  and sends them with the rest', post && b.ni_number === 'AB 65 43 21 A' && b.tax_code === '1257L' && b.ni_category === 'M'
            && b.starter_declaration === 'A' && b.student_loan_plan === '5', post && post.body);
    }
    {
        const { w, doc, sent } = boot({ regime: 'simple' });
        await w.showAddEmployeeModal();
        await wait(20);
        check('on the simple payroll the add form does not', doc.getElementById('emp-uk-fields').style.display === 'none');
        doc.getElementById('emp-first-name').value = 'Ben';
        doc.getElementById('emp-last-name').value = 'Ode';
        doc.getElementById('emp-email').value = 'ben@example.com';
        doc.getElementById('emp-password').value = 'Passw0rdTest';
        await w.submitNewEmployee();
        await wait(20);
        const b = bodyOf(sent.find(s => s.url === '/api/employees' && s.method === 'POST') || {});
        check('  nor sends UK fields', !('tax_code' in b) && !('ni_number' in b));
    }

    // --- a UK payslip -----------------------------------------------------------------
    {
        const { w, doc } = boot({ regime: 'uk' });
        w.showView = () => { };
        await w.viewPayslip(3);
        await wait(20);
        const show = id => doc.getElementById(id).style.display !== 'none';
        check('a UK payslip calls the tax Income Tax', doc.getElementById('ps-detail-tax-label').textContent === 'Income Tax');
        check('  shows National Insurance and the student loan on their own lines',
            show('ps-detail-ni-row') && doc.getElementById('ps-detail-ni').textContent === '156.16'
            && show('ps-detail-sl-row') && doc.getElementById('ps-detail-sl').textContent === '49.00'
            && /plan 2/.test(doc.getElementById('ps-detail-sl-label').textContent));
        check('  and no postgraduate line when there is none', !show('ps-detail-pgl-row'));
        check('  and none of the flat-rate rows at zero',
            doc.getElementById('ps-detail-ins').parentElement.style.display === 'none'
            && doc.getElementById('ps-detail-ret').parentElement.style.display === 'none'
            && doc.getElementById('ps-detail-other').parentElement.style.display === 'none');
        const codes = doc.getElementById('ps-detail-uk-codes').textContent;
        check('  shows the codes it was worked on', /Tax code 1257L/.test(codes) && /NI A/.test(codes) && /AB123456C/.test(codes) && /2026-27 period 1/.test(codes), codes);
        const ytd = doc.getElementById('ps-detail-ytd').textContent;
        check('  and the tax year to date, with the employer\'s NI kept apart',
            /This tax year to date \(2026-27\)/.test(ytd) && /Income Tax£390.20/.test(ytd) && /Employer's National Insurance this period: £387.45/.test(ytd), ytd);
    }
    {
        const simple = Object.assign({}, UK_PAYSLIP, { regime: 'simple', uk: null, tax_amount: 600, total_deductions: 600, net_pay: 2400 });
        const { w, doc } = boot({ regime: 'simple', payslip: simple });
        w.showView = () => { };
        await w.viewPayslip(3);
        await wait(20);
        const hidden = id => doc.getElementById(id).style.display === 'none';
        check('a flat-rate payslip is as it was: Tax, no NI line, no tax year block',
            doc.getElementById('ps-detail-tax-label').textContent === 'Tax' && hidden('ps-detail-ni-row') && hidden('ps-detail-sl-row')
            && hidden('ps-detail-ytd') && hidden('ps-detail-uk-codes')
            && doc.getElementById('ps-detail-ret').parentElement.style.display === ''
            && doc.getElementById('ps-detail-ret').previousElementSibling.textContent === 'Retirement');
    }

    // --- four-weekly is a pay frequency -----------------------------------------------
    {
        const { doc } = boot({ regime: 'uk' });
        check('four-weekly can be chosen when adding and editing an employee',
            !!doc.querySelector('#emp-pay-freq option[value="fourweekly"]') && !!doc.querySelector('#emp-detail-payfreq option[value="fourweekly"]'));
    }

    console.log(failures ? `\n${failures} check(s) failed.` : '\nAll UK payroll screen checks passed.');
    process.exit(failures ? 1 : 0);
})();
