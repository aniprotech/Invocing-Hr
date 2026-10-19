/**
 * Payroll and staff money on screen: what is owed to HMRC and the pension,
 * recording those payments, marking payslips and expense claims paid with the
 * day, the account and the bank line, undoing a mistaken "paid", and the
 * reports showing staff costs and what is owed.
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
const text = el => (el ? el.textContent.replace(/\s+/g, ' ') : '');

const blank = { tax: 0, employee_ni: 0, employer_ni: 0, student_loan: 0, postgrad_loan: 0, total: 0, paid: 0, left: 0, status: 'nothing' };
const pblank = { employee: 0, employer: 0, total: 0, paid: 0, left: 0, status: 'nothing' };
const OWED = {
    tax_year: 2026, label: '2026-27', note: 'Employment Allowance claimed on an Employer Payment Summary is not taken off what is shown as owed to HMRC.',
    totals: { paye_left: 650.5, pension_left: 0, overdue: 1 },
    months: [
        { month: 1, from: '2026-04-06', to: '2026-05-05', due: '2026-05-22', payslips: 2, paye: { ...blank, total: 650.5, left: 650.5, status: 'overdue' }, pension: { ...pblank, total: 200, paid: 200, left: 0, status: 'paid' } },
        { month: 2, from: '2026-05-06', to: '2026-06-05', due: '2026-06-22', payslips: 0, paye: blank, pension: pblank },
    ].concat(Array.from({ length: 10 }, (_, i) => ({ month: i + 3, from: '', to: '', due: '', payslips: 0, paye: blank, pension: pblank }))),
    remittances: [{ id: 5, kind: 'pension', tax_month: 1, amount: 200, paid_on: '2026-05-15', reference: 'NEST-1', account: '', from_bank: false },
                  { id: 6, kind: 'hmrc', tax_month: 1, amount: 0.01, paid_on: '2026-05-16', reference: '', account: '', from_bank: true }],
};
const LINES = { lines: [{ id: 41, date: '2026-05-20', description: 'HMRC NDDS', amount: -650.5 }, { id: 42, date: '2026-05-21', description: 'RENT', amount: -900 },
                        { id: 43, date: '2026-04-30', description: 'PAYROLL', amount: -4321.09 }] };

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
        if (opts.reply) { const k = Object.keys(opts.reply).find(k => k === method + ' ' + p || k === p); if (k) { const r = opts.reply[k](init); return give(r.body, r.status); } }
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/payroll/settings') return give({ regime: opts.regime || 'uk', ni_categories: ['A'] });
        if (p === '/api/payroll/liabilities') return give(OWED);
        if (p === '/api/bank/lines') return give(LINES);
        if (p === '/api/accounts') return give({ accounts: [{ id: 3, name: 'Current', active: true }] });
        if (p === '/api/payslips' && method === 'GET') return give([
            { id: 1, number: 'PS-1', pay_date: '2026-04-30', net_pay: 2000.5, status: 'Draft' }, { id: 2, number: 'PS-2', pay_date: '2026-04-30', net_pay: 2320.59, status: 'Sent' },
            { id: 3, number: 'PS-3', pay_date: '2026-03-31', net_pay: 1800, status: 'Draft' }, { id: 4, number: 'PS-4', pay_date: '2026-04-30', net_pay: 999, status: 'Paid' }]);
        if (p === '/api/payslips/9') return give({ id: 9, number: 'PS-9', net_pay: 4321.09, status: 'Draft' });
        if (p === '/api/payroll/pay') return give({ paid: 2, net_pay: 4321.09 });
        if (p === '/api/payroll/remittances') return give({ id: 7, paid_on: '2026-05-20' });
        if (p === '/api/expenses') return give({ currency: 'GBP', totals: { pending_count: 0, pending: 0, owed: 45, paid_this_month: 0 },
            claims: [{ id: 21, amount: 45, currency: 'GBP', status: 'approved', employee: 'Ann', description: 'Train', category: 'travel', spent_on: '2026-05-10', can_mark_paid: true },
                     { id: 22, amount: 12, currency: 'GBP', status: 'paid', employee: 'Ben', description: 'Taxi', category: 'travel', spent_on: '2026-05-09', paid_at: '2026-05-12 10:00:00' }] });
        if (p === '/api/reports/balance-sheet') return give({ currency: 'GBP', assets: { cash_collected: 1000, accounts_receivable: 500 },
            liabilities: { accounts_payable: 300, wages_owed: 2000.5, paye_owed: 650.5, pension_owed: 0, expense_claims_owed: 45 }, equity: { retained_earnings: 10 },
            total_assets: 1500, total_liabilities: 2996, total_equity: 10, other_currencies: [] });
        if (p === '/api/reports/profit-loss') return give({ currency: 'GBP', months: ['2026-04'], revenue: [1000], expenses: [3800], profit: [-2800], total_revenue: 1000, total_expenses: 3800,
            net_profit: -2800, expense_parts: { bills: 300, payroll: 3455, staff_expenses: 45 }, other_currencies: [] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m, t) => { w._toasts = (w._toasts || []).concat([[m, t]]); };
    w._asked = [];
    w.uiConfirm = (m) => { w._asked.push(String(m)); return Promise.resolve(opts.confirm !== false); };
    w._forms = [];
    w.uiForm = (fields, o) => {
        w._forms.push({ fields, o });
        const answer = Array.isArray(opts.forms) ? opts.forms.shift() : opts.form;
        return Promise.resolve(answer === undefined ? Object.fromEntries(fields.map(f => [f.name, f.value === undefined ? '' : f.value])) : answer);
    };
    w.formatCurrency = (v) => '£' + Number(v || 0).toFixed(2);
    return { w, doc: w.document, sent };
}
const click = (w, el) => el.dispatchEvent(new w.Event('click', { bubbles: true }));

(async () => {
    // --- what is owed -----------------------------------------------------------------------
    {
        const { w, doc } = boot({ regime: 'simple' });
        await w.loadPayrollOwed();
        check('on the simple payroll there is no HMRC and pension panel', doc.getElementById('payroll-owed-panel').style.display === 'none');
    }
    {
        const { w, doc, sent } = boot();
        await w.loadPayrollOwed();
        const host = doc.getElementById('payroll-owed-content');
        const t = text(host);
        check('the panel shows what is owed to HMRC and the pension, and that one payment is overdue', /Owed to HMRC\s*£650\.50/.test(t) && /Owed to the pension\s*£0\.00/.test(t) && /1 payment is overdue/.test(t), t.slice(0, 200));
        check('  a row only for months something was taken, with its due date and state', host.querySelectorAll('tbody tr').length >= 1 && /Month 1/.test(t) && /2026-05-22/.test(t) && /Overdue/.test(t) && /Paid/.test(t) && !/Month 2/.test(t));
        check('  a paid month offers no payment button; an owed one does', !!host.querySelector('[data-owed-pay="hmrc"][data-month="1"]') && !host.querySelector('[data-owed-pay="pension"]'));
        check('  payments made are listed, and one from a bank line cannot be removed here', /NEST-1/.test(t) && !!host.querySelector('[data-owed-remove="5"]') && !host.querySelector('[data-owed-remove="6"]'));
        check('  the Employment Allowance caveat is stated', /Employment Allowance/.test(t));
        check('  and the tax year is labelled', text(doc.getElementById('payroll-owed-year')) === '2026-27');
        click(w, host.querySelector('[data-owed-pay="hmrc"]'));
        await wait(80);
        const f = w._forms[0];
        check('recording a payment asks the amount (what is left), the reference, the day and the bank line',
            f && f.fields.map(x => x.name).join() === 'amount,reference,paid_on,bank_line_id,account_id' && f.fields[0].value === 650.5 && /tax month 1/.test(f.o.title));
        check('  only bank lines of exactly that amount are offered', f.fields[3].options.length === 2 && f.fields[3].options[1].value === 41);
        const post = sent.find(x => x.url === '/api/payroll/remittances' && x.method === 'POST');
        check('  and it is recorded for that kind, year and month', post && bodyOf(post).kind === 'hmrc' && bodyOf(post).tax_year === 2026 && bodyOf(post).tax_month === 1 && bodyOf(post).amount === 650.5);
        click(w, host.querySelector('[data-owed-remove="5"]'));
        await wait(80);
        check('removing a payment asks first, then removes it', /Remove this payment/.test(w._asked[0]) && sent.some(x => x.url === '/api/payroll/remittances/5' && x.method === 'DELETE'));
    }
    {
        const { w, doc } = boot({ form: { amount: '650.50', reference: 'X', paid_on: '2026-05-20', bank_line_id: '41', account_id: '' }, reply: { 'POST /api/payroll/remittances': () => ({ status: 400, body: { detail: 'That is more than is owed for that month (650.50)' } }) } });
        await w.loadPayrollOwed();
        click(w, doc.querySelector('[data-owed-pay="hmrc"]'));
        await wait(80);
        check('a payment the server refuses says why', (w._toasts || []).some(t => /more than is owed/.test(t[0]) && t[1] === 'error'));
    }

    {
        const { w, doc } = boot({ reply: { '/api/payroll/liabilities': () => ({ body: {} }) } });
        await w.loadPayrollOwed();
        check('an answer without the expected parts says so instead of breaking the Payroll screen', /Not available right now/.test(text(doc.getElementById('payroll-owed-content'))));
    }

    // --- net pay for a run ------------------------------------------------------------------------
    {
        const { w, sent } = boot({ forms: [{ day: '2026-04-30' }, { paid_on: '2026-04-30', bank_line_id: '43', account_id: '' }] });
        await w.payPayrollRun();
        const first = w._forms[0].fields[0];
        check('recording net pay offers each pay day with its unpaid payslips and total', first.options.length === 2 && /2026-04-30 - 2 payslips, £4321\.09 net/.test(first.options[0].label));
        check('  then offers the bank line of exactly that total', w._forms[1].fields[1].options.some(o => o.value === 43) && !w._forms[1].fields[1].options.some(o => o.value === 42));
        const post = sent.find(x => x.url === '/api/payroll/pay');
        check('  and marks those payslips paid against that line', post && JSON.stringify(bodyOf(post).payslip_ids) === '[1,2]' && bodyOf(post).bank_line_id === 43);
    }
    {
        const { w, sent } = boot({ reply: { '/api/payslips': () => ({ body: [{ id: 4, status: 'Paid', net_pay: 1 }] }) } });
        await w.payPayrollRun();
        check('with everything paid, nothing is asked', w._forms.length === 0 && (w._toasts || []).some(t => /already paid/.test(t[0])));
    }

    // --- one payslip ---------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ form: { paid_on: '2026-04-30', bank_line_id: '', account_id: '3' } });
        w.currentPayslipId = 9;
        w.viewPayslip = () => { };
        doc.getElementById('ps-detail-status').textContent = 'Draft';
        await w.markPayslipPaid();
        const post = sent.find(x => x.url === '/api/payslips/9/mark-paid');
        check('marking a payslip paid asks the day and the account and sends them', post && bodyOf(post).paid_on === '2026-04-30' && bodyOf(post).account_id === 3 && bodyOf(post).bank_line_id === null);
        w.syncPayslipPaidButton('Paid');
        check('a paid payslip offers Mark unpaid', doc.getElementById('ps-paid-btn').textContent === 'Mark unpaid');
        doc.getElementById('ps-detail-status').textContent = 'Paid';
        await w.markPayslipPaid();
        check('  which asks first and reopens it', /Mark this payslip as not paid/.test(w._asked[0]) && sent.some(x => x.url === '/api/payslips/9/unmark-paid'));
        w.syncPayslipPaidButton('Draft');
        check('  and an unpaid one offers Mark paid', doc.getElementById('ps-paid-btn').textContent === 'Mark paid');
    }
    {
        const { w, doc, sent } = boot({ reply: { 'POST /api/payslips/9/unmark-paid': () => ({ status: 400, body: { detail: 'This payslip was paid by a bank line. Take that line\'s coding back in Bank instead.' } }) } });
        w.currentPayslipId = 9;
        doc.getElementById('ps-detail-status').textContent = 'Paid';
        await w.markPayslipPaid();
        check('a payslip paid by a bank line says to undo it in Bank', (w._toasts || []).some(t => /coding back in Bank/.test(t[0])));
    }

    // --- expense claims -----------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ form: { paid_on: '2026-05-12', bank_line_id: '', account_id: '3' } });
        await w.loadExpensesView();
        await w.markExpensePaid(21);
        const f = w._forms[0];
        const post = sent.find(x => x.url === '/api/expenses/21/paid');
        check('repaying a claim asks the day and the account and sends them', post && bodyOf(post).paid_on === '2026-05-12' && bodyOf(post).account_id === 3);
        check('  offering bank lines of the claim\'s amount only', f.fields[1].options.length === 1);
        check('a paid claim offers Mark unpaid', /markExpenseUnpaid\(22\)/.test(doc.getElementById('exp-rows').innerHTML) && !/markExpenseUnpaid\(21\)/.test(doc.getElementById('exp-rows').innerHTML));
        await w.markExpenseUnpaid(22);
        check('  which asks first and sends it', /not paid/.test(w._asked[0]) && sent.some(x => x.url === '/api/expenses/22/unpaid' && x.method === 'POST'));
    }

    // --- the reports -------------------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadBalanceSheet();
        const t = text(doc.getElementById('bs-report-body'));
        check('the balance sheet owes suppliers, wages, HMRC and expense claims, and leaves out what is zero',
            /Owed to suppliers\s*£300\.00/.test(t) && /Wages not yet paid\s*£2000\.50/.test(t) && /Owed to HMRC from payroll\s*£650\.50/.test(t) && /Expense claims to repay\s*£45\.00/.test(t) && !/pension provider/.test(t), t.slice(0, 400));
        await w.loadProfitLoss();
        check('the profit and loss says what the expenses are made of', /Bills £300\.00 · Payroll £3455\.00 · Staff expenses £45\.00/.test(text(doc.getElementById('pl-expense-parts'))), text(doc.getElementById('pl-expense-parts')));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
