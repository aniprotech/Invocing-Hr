/**
 * Workplace pension screens.
 *
 * A panel on the Payroll screen that shows only on UK payroll: the scheme,
 * who is in and who has to be, and the things the law leaves to a person -
 * joining, opting out, the letter. Plus the pension on the payslip itself.
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

const SCHEME = (enabled) => ({
    scheme: { enabled, provider: 'NEST', basis: 'qualifying', method: 'net_pay', employer_pct: 3, employee_pct: 5, postponement_months: 0, duties_start: '2024-03-01' },
    regime: 'uk', next_reenrolment: '2027-03-01',
    bases: [{ key: 'qualifying', label: 'Qualifying earnings (the band between the lower and upper limits)', min_employer: 3, min_total: 8 },
            { key: 'basic', label: 'Basic pay', min_employer: 4, min_total: 9 }, { key: 'total', label: 'All pay', min_employer: 3, min_total: 7 }],
    methods: [{ key: 'net_pay', label: 'Net pay arrangement' }, { key: 'relief_at_source', label: 'Relief at source' }],
    thresholds: { year: '2026-27', source: 'The Pensions Regulator', lower: 6240, trigger: 10000, upper: 50270 },
    not_built: ['Salary sacrifice', 'Provider-specific upload files'],
});
const STAFF = { scheme_enabled: true, counts: { member: 1, postponed: 0, opted_out: 0, not_in: 2 }, staff: [
    { id: 1, name: 'Ann Lee', age: 31, has_dob: true, group: 'eligible_jobholder', group_label: 'Eligible jobholder - must be enrolled', status: 'member', joined_on: '2026-04-30', letter_due: 'enrolment', next: 'Contributing' },
    { id: 2, name: 'Ben <b>Ode</b>', age: 20, has_dob: true, group: 'non_eligible_jobholder', group_label: 'Non-eligible jobholder - may opt in', status: '', joined_on: '', letter_due: '', next: 'Not enrolled - may opt in' },
    { id: 3, name: 'Cat Dee', age: null, has_dob: false, group: '', group_label: '', status: '', joined_on: '', letter_due: '', next: 'Needs a date of birth before they can be assessed' },
] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/payroll' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    let enabled = opts.enabled !== false;
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/payroll/settings') return give({ regime: opts.regime || 'uk', tax_year: '2026-27', rates_ready: true, ni_categories: ['A'] });
        if (p === '/api/pension/scheme' && method === 'PUT') { enabled = bodyOf({ body: init.body }).enabled; return give(SCHEME(enabled)); }
        if (p === '/api/pension/scheme') return give(SCHEME(enabled));
        if (p === '/api/pension/staff') return give(STAFF);
        if (p.endsWith('/join')) return give({});
        if (p.endsWith('/opt-out')) return give({ within_refund_window: true, refund_due: 124, message: 'Within a month of joining: treated as never having joined.' });
        if (p.endsWith('/letter')) return give({ kind: 'enrolment', subject: 'You have been enrolled in a workplace pension', body: 'Hello Ann,\n\nNEST ... opt out ... one month', to: 'ann@example.com' });
        if (p.endsWith('/letter-sent')) return give({ ok: true });
        if (p === '/api/pension/reenrol') return give({ count: 1, re_enrolled: [{ id: 2, name: 'Ben' }], skipped: [{ id: 3, name: 'Cat Dee', reason: 'no date of birth' }] });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiForm = (fields) => { w._asked = fields; return Promise.resolve({ date: '2026-05-10' }); };
    const alerts = [];
    w.uiAlert = (m, o) => { alerts.push(String(m)); return Promise.resolve(); };
    w.formatCurrency = (v) => '£' + Number(v || 0).toFixed(2);
    return { w, doc: w.document, sent, alerts };
}

(async () => {
    // --- only on UK payroll -----------------------------------------------------
    {
        const { w, doc } = boot({ regime: 'simple' });
        await w.loadPensionPanel();
        check('on the simple payroll there is no pension panel', doc.getElementById('pension-panel').style.display === 'none');
    }

    // --- the scheme is not on yet ------------------------------------------------------
    {
        const { w, doc, sent } = boot({ enabled: false });
        await w.loadPensionPanel();
        const host = doc.getElementById('pension-content');
        check('with the scheme off the panel explains and offers to set it up', /Set up the scheme/.test(host.textContent) && /eligible staff/.test(host.textContent));
        check('  and does not list staff or fetch them', !sent.some(s => s.url === '/api/pension/staff'));
        check('  nor offer re-enrolment or the CSV', doc.getElementById('pension-reenrol-btn').style.display === 'none' && doc.getElementById('pension-csv').style.display === 'none');
    }

    // --- the panel --------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadPensionPanel();
        const text = doc.getElementById('pension-content').textContent;
        check('the panel names the provider, the split and who is in', /NEST/.test(text) && /3% you \+ 5% them/.test(text) && /In the scheme/.test(text), text.slice(0, 200));
        check('  says when re-enrolment is next due', /Next re-enrolment/.test(text) && /2027-03-01/.test(text));
        const rows = doc.querySelectorAll('#pension-content tbody tr');
        check('  one row per person, with what happens to them next', rows.length === 3 && /Contributing/.test(rows[0].textContent) && /may opt in/.test(rows[1].textContent));
        check('  a person without a date of birth is asked for one, with no Join button',
            /Needs a date of birth/.test(rows[2].textContent) && !rows[2].querySelector('[data-pen-join]'));
        check('  a member can be recorded as opted out; somebody else can join',
            !!rows[0].querySelector('[data-pen-optout]') && !!rows[1].querySelector('[data-pen-join]') && !rows[0].querySelector('[data-pen-join]'));
        check('  a letter that is due is offered by name', /Enrolment letter/.test(rows[0].textContent));
        check('  a name is text, not markup', !doc.querySelector('#pension-content b') && /Ben <b>Ode<\/b>/.test(rows[1].textContent));
    }

    // --- joining, opting out, re-enrolling ------------------------------------------------------
    {
        const { w, doc, sent, alerts } = boot();
        await w.loadPensionPanel();
        doc.querySelector('[data-pen-join="2"]').click();
        await wait(20);
        check('Join asks, then joins that person', sent.some(s => s.url === '/api/pension/staff/2/join' && s.method === 'POST'));
        doc.querySelector('[data-pen-optout="1"]').click();
        await wait(20);
        const oo = sent.find(s => s.url === '/api/pension/staff/1/opt-out');
        check('an opt-out asks the day it happened, and sends that day, not today',
            w._asked && w._asked[0].name === 'date' && oo && bodyOf(oo).date === '2026-05-10', oo && oo.body);
        check('recording an opt-out says what to repay', !!oo && /Repay them: £124\.00/.test(alerts[alerts.length - 1]), alerts.join('|'));
        await w.reEnrolPensions();
        await wait(20);
        check('re-enrolment says who it did and who it could not, and why', /1 re-enrolled/.test(alerts[alerts.length - 1]) && /Cat Dee: no date of birth/.test(alerts[alerts.length - 1]), alerts[alerts.length - 1]);
    }

    // --- the letter ---------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadPensionPanel();
        doc.querySelector('[data-pen-letter="1"]').click();
        await wait(20);
        check('the letter opens, to the right person, as read-only text',
            doc.getElementById('pension-letter-modal').style.display === 'flex' && /ann@example.com/.test(doc.getElementById('pen-letter-to').textContent)
            && /opt out/.test(doc.getElementById('pen-letter-body').value) && doc.getElementById('pen-letter-body').readOnly);
        check('  and says it is a template, not legal advice', /not legal advice/.test(doc.getElementById('pension-letter-modal').textContent));
        await w.markPensionLetterSent();
        await wait(20);
        check('Mark as sent clears it and closes', sent.some(s => s.url === '/api/pension/staff/1/letter-sent' && s.method === 'POST') && doc.getElementById('pension-letter-modal').style.display === 'none');
    }

    // --- the scheme form --------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadPensionPanel();
        await w.openPensionScheme();
        check('the form opens with the scheme in it and the law’s minimum beside it',
            doc.getElementById('pen-provider').value === 'NEST' && doc.getElementById('pen-employer').value === '3'
            && /8% in total, at least 3%/.test(doc.getElementById('pen-minimum').textContent));
        check('  with the Regulator’s thresholds, sourced, and what is not built',
            /The Pensions Regulator/.test(doc.getElementById('pen-thresholds').textContent) && /£6240/.test(doc.getElementById('pen-thresholds').textContent)
            && /salary sacrifice/i.test(doc.getElementById('pen-not-built').textContent));
        doc.getElementById('pen-basis').value = 'basic'; w.penBasisChanged();
        check('  choosing basic pay changes the minimum shown', /9% in total, at least 4%/.test(doc.getElementById('pen-minimum').textContent));
        doc.getElementById('pen-postpone').value = '3';
        await w.savePensionScheme();
        await wait(20);
        const put = sent.find(s => s.url === '/api/pension/scheme' && s.method === 'PUT');
        const b = bodyOf(put || {});
        check('Save sends every field', put && b.enabled === true && b.basis === 'basic' && b.postponement_months === 3 && b.employer_pct === 3 && b.duties_start === '2024-03-01', put && put.body);
    }

    // --- the payslip itself ------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        w.showView = () => { };
        w.fetch = (u) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
            id: 3, number: 'PS-0003', status: 'Draft', employee: { full_name: 'Ann Lee' }, period_start: '2026-04-01', period_end: '2026-04-30',
            pay_date: '2026-04-30', basic_salary: 3000, gross_pay: 3000, tax_amount: 365.4, total_deductions: 645.56, net_pay: 2354.44,
            company: { name: 'Northwind' }, regime: 'uk', standing_deduction: 0,
            uk: { tax_code: '1257L', ni_category: 'A', ni_number: 'AB123456C', tax_year: '2026-27', tax_period: 1, employee_ni: 156.16, employer_ni: 387.45,
                student_loan: 0, postgrad_loan: 0, pension: { pensionable: 2480, employee: 124, employer: 74.4, relief: 0 },
                year_to_date: { tax_year: '2026-27', payslips: 1, gross_pay: 3000, taxable_pay: 2876, tax: 365.4, employee_ni: 156.16, net_pay: 2354.44 } } }) });
        await w.viewPayslip(3);
        await wait(20);
        const hidden = id => doc.getElementById(id).style.display === 'none';
        check('a payslip with a pension has its own line, with the employee’s share', !hidden('ps-detail-pension-row') && doc.getElementById('ps-detail-pension').textContent === '124.00');
        check('  and says what the employer paid in on top', /Employer.s pension contribution: £74\.40/.test(doc.getElementById('ps-detail-ytd').textContent), doc.getElementById('ps-detail-ytd').textContent);
    }
    {
        const { w, doc } = boot();
        w.showView = () => { };
        w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
            id: 3, number: 'PS-0003', status: 'Draft', employee: { full_name: 'Ann Lee' }, period_start: '2026-04-01', period_end: '2026-04-30',
            pay_date: '2026-04-30', basic_salary: 3000, gross_pay: 3000, tax_amount: 390.2, total_deductions: 546.36, net_pay: 2453.64,
            company: { name: 'Northwind' }, regime: 'uk', standing_deduction: 0,
            uk: { tax_code: '1257L', ni_category: 'A', tax_year: '2026-27', tax_period: 1, employee_ni: 156.16, employer_ni: 387.45, pension: null,
                year_to_date: { tax_year: '2026-27', payslips: 1, gross_pay: 3000, taxable_pay: 3000, tax: 390.2, employee_ni: 156.16, net_pay: 2453.64 } } }) });
        await w.viewPayslip(3);
        await wait(20);
        check('a payslip with no pension has no pension line', doc.getElementById('ps-detail-pension-row').style.display === 'none');
    }

    console.log(failures ? `\n${failures} check(s) failed.` : '\nAll pension screen checks passed.');
    process.exit(failures ? 1 : 0);
})();
