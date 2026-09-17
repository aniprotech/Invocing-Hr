/**
 * Chasing: the settings widget reads the schedule and the late fee, edits
 * and saves them as the API wants (negative days for "before"); the Chasing
 * page lists what is being chased with Chase now / Hold; the invoice page
 * shows what went, what is next, the fees, and lets one off; the contact
 * form carries the two switches. Words are text.
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

const POLICY = { enabled: true,
    steps: [{ days: -3, tone: 'gentle', message: 'Thanks <b>again</b>' }, { days: 7, tone: 'firm', message: '' }, { days: 30, tone: 'final', message: '' }],
    late_fee: { enabled: true, kind: 'percent', value: 2, after_days: 14, repeat: 'monthly' },
    samples: [{ days: -3, tone: 'gentle', label: '3 days before due (gentle)', subject: 'Invoice INV-0042 is due on 2026-03-31', opening: 'A quick note <i>x</i>' },
              { days: 7, tone: 'firm', label: '7 days overdue (firm)', subject: 'Overdue: invoice INV-0042 is 7 days past due', opening: 'Our records show' },
              { days: 30, tone: 'final', label: '30 days overdue (final)', subject: 'Final notice: invoice INV-0042', opening: 'This is a final reminder' }],
    tones: ['gentle', 'firm', 'final'], defaults: [] };

const CHASING = { enabled: true, late_fee: { enabled: true, kind: 'flat', value: 25, after_days: 7, repeat: 'once' }, overdue: 2, paused: 1, owed: 425, rows: [
    { number: 'INV-0001', customer: 'Acme <b>Ltd</b>', email: 'a@example.com', due: 325, currency: 'GBP', due_date: '2026-08-20', days: 29, reminders: 2, last_reminder: '2026-09-03', last_label: '14 days overdue', paused: false, chased: true, why_not: '', late_fees: 25 },
    { number: 'INV-0002', customer: 'Beta', email: 'b@example.com', due: 100, currency: 'GBP', due_date: '2026-09-15', days: 3, reminders: 0, last_reminder: '', last_label: '', paused: true, chased: true, why_not: '', late_fees: 0 },
    { number: 'INV-0003', customer: 'Gamma', email: '', due: 50, currency: 'GBP', due_date: '2026-09-20', days: -2, reminders: 0, last_reminder: '', last_label: '', paused: false, chased: false, why_not: 'customer not chased', late_fees: 0 } ] };

const INVOICE = { number: 'INV-0001', to: 'Acme', email: 'a@example.com', date: '2026-08-06', due_date: '2026-08-20', paid: 0, due: 325, subtotal: 325, tax_total: 0, total: 325,
    is_overdue: true, days_overdue: 29, payments: [], refunds: [], refunded_total: 0, status: 'Awaiting Payment', currency: 'GBP', line_items: [], company: {}, bill_to: {}, bill_from: {},
    chasing: { paused: false, chased: true, why_not: '', fees_allowed: true, fee_why_not: '', customer_id: 4,
        reminders: [{ stage_days: 7, sent_to: 'a@example.com', sent_at: '2026-08-27 09:00:00', label: '7 days overdue' }, { stage_days: 14, sent_to: 'a@example.com', sent_at: '2026-09-03 09:00:00', label: '14 days overdue' }],
        next: { days: 30, tone: 'final', on: '2026-09-19', label: '30 days overdue (final)' },
        late_fees: [{ id: 9, amount: 25, days_overdue: 21, basis: 'flat', applied_on: '2026-09-10', applied_by: 'policy', waived_on: '', waived_by: '', waived_why: '' }],
        late_fee_total: 25, late_fee_next: null, policy: { enabled: true, steps: 3, late_fee: { enabled: true, kind: 'flat', value: 25, after_days: 7, repeat: 'once' } } } };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/dunning') return give(method === 'PUT' ? Object.assign({}, POLICY, bodyOf({ body: init.body }), { samples: [] }) : (opts.policy || POLICY));
        if (p === '/api/chasing') return give(opts.chasing || CHASING);
        if (p === '/api/invoices/INV-0001') return give(opts.invoice || INVOICE);
        if (p.startsWith('/api/invoices/INV-0001/chase')) return give({ message: 'Reminder sent to a@example.com', chasing: INVOICE.chasing });
        if (p.startsWith('/api/invoices/INV-0002/chase')) return give({ message: 'Reminders back on', chasing: {} });
        if (p.startsWith('/api/invoices/INV-0001/late-fee')) return give({ message: 'ok', fee: {}, invoice: {}, chasing: INVOICE.chasing });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        if (p === '/api/client/logo') return give({ logo_url: '' });
        if (p === '/api/settings') return give({});
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiPrompt = () => Promise.resolve(opts.prompt === undefined ? 'Goodwill' : opts.prompt);
    w.uiForm = (fields) => Promise.resolve(opts.form === undefined ? { tone: 'firm', message: 'Call us', amount: '12.50', tell: 'no' } : opts.form);
    w.uiAlert = () => Promise.resolve(true);
    w.fetchInvoices = () => Promise.resolve();
    w.getCurrencySymbol = () => '£';
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('Money has a Chasing page, Settings > Payments the schedule and fee, the invoice page a chasing block, the contact form two switches',
            /id="nav-chasing"/.test(src) && /id="chasing-view"/.test(src) && /id="dunning-widget"/.test(src) && /id="late-fee-enabled"/.test(src) && /id="view-inv-chasing"/.test(src) && /id="contact-chase"/.test(src) && /id="contact-late-fees"/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        check('the route and nav maps know the page', w.ROUTE_SLUGS['chasing-view'] === 'chasing' && w.VIEW_FOR_SLUG.chasing === 'chasing-view' && w.NAV_FOR_VIEW['chasing-view'] === 'nav-chasing');
        await w.loadDunning();
        await wait(30);
        const rows = doc.querySelectorAll('#dunning-steps [data-dunning-step]');
        check('the schedule shows one row per step, before/after and tone as chosen, the message as text',
            rows.length === 3 && rows[0].querySelector('[data-dunning-n]').value === '3' && rows[0].querySelector('[data-dunning-when]').value === 'before' &&
            rows[1].querySelector('[data-dunning-when]').value === 'after' && rows[2].querySelector('[data-dunning-tone]').value === 'final' &&
            rows[0].querySelector('[data-dunning-message]').value === 'Thanks <b>again</b>' && !doc.getElementById('dunning-steps').querySelector('b'), rows.length);
        check('  each step says what it will read like, as text', /Invoice INV-0042 is due on 2026-03-31/.test(rows[0].textContent) && /A quick note <i>x<\/i>/.test(rows[0].textContent) && !rows[0].querySelector('i'));
        check('  the late fee fields are filled', doc.getElementById('late-fee-enabled').checked && doc.getElementById('late-fee-kind').value === 'percent' && doc.getElementById('late-fee-value').value === '2' && doc.getElementById('late-fee-after').value === '14' && doc.getElementById('late-fee-repeat').value === 'monthly');
        w.addDunningStep();
        const rows2 = doc.querySelectorAll('#dunning-steps [data-dunning-step]');
        check('  + Step adds one a week after the last, firm', rows2.length === 4 && rows2[3].querySelector('[data-dunning-n]').value === '37' && rows2[3].querySelector('[data-dunning-tone]').value === 'firm');
        rows2[1].querySelector('[data-dunning-remove]').click();
        await wait(10);
        check('  x takes a step out', doc.querySelectorAll('#dunning-steps [data-dunning-step]').length === 3);
        doc.getElementById('late-fee-kind').value = 'flat';
        doc.getElementById('late-fee-value').value = '25';
        doc.getElementById('late-fee-after').value = '10';
        doc.getElementById('late-fee-repeat').value = 'once';
        doc.getElementById('dunning-enabled').checked = false;
        await w.saveDunning();
        await wait(20);
        const put = sent.find(s => s.url === '/api/dunning' && s.method === 'PUT');
        const b = put && bodyOf(put);
        check('Save puts the steps with negative days for "before", the tones, and the fee as set',
            b && b.enabled === false && JSON.stringify(b.steps.map(s => s.days)) === '[-3,30,37]' && b.steps[0].tone === 'gentle' && b.steps[0].message === 'Thanks <b>again</b>' &&
            b.late_fee.enabled === true && b.late_fee.kind === 'flat' && b.late_fee.value === 25 && b.late_fee.after_days === 10 && b.late_fee.repeat === 'once', put && put.body);
    }
    {
        const { w, doc, sent } = boot();
        doc.getElementById('late-fee-enabled').checked = true;
        doc.getElementById('late-fee-value').value = '';
        await w.saveDunning();
        check('a fee switched on with no amount is refused before it is sent', !sent.some(s => s.url === '/api/dunning' && s.method === 'PUT'));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadChasingView();
        await wait(30);
        const tiles = doc.getElementById('chasing-tiles').textContent.replace(/\s+/g, ' ');
        check('the Chasing page counts the overdue and what they owe, says whether reminders and the fee are on, and how many are held',
            /Overdue\s*2/.test(tiles) && /£425\.00 owed/.test(tiles) && /Reminders\s*On/.test(tiles) && /£25\.00/.test(tiles) && /after 7 days/.test(tiles) && /Held\s*1/.test(tiles), tiles);
        const rows = doc.querySelectorAll('#chasing-list tbody tr');
        check('one row per invoice, names as text, the most overdue first', rows.length === 3 && /Acme <b>Ltd<\/b>/.test(rows[0].textContent) && !doc.getElementById('chasing-list').querySelector('b') && /29 days overdue/.test(rows[0].textContent));
        check('  a row says what has been said so far and the fee on it', /2 reminders/.test(rows[0].textContent) && /last: 14 days overdue on 2026-09-03/.test(rows[0].textContent) && /incl\. £25\.00 late fee/.test(rows[0].textContent));
        check('  a held one says Held and offers Resume; one not chased says why; one with no email cannot be chased',
            /Held/.test(rows[1].textContent) && rows[1].querySelector('[data-chasing-pause]').textContent === 'Resume' && /customer not chased/.test(rows[2].textContent) && !rows[2].querySelector('[data-chasing-chase]') && /no email/.test(rows[2].textContent));
        rows[0].querySelector('[data-chasing-chase]').click();
        await wait(30);
        const chase = sent.find(s => s.url === '/api/invoices/INV-0001/chase');
        check('Chase now asks for a tone and a sentence, then posts them', chase && bodyOf(chase).tone === 'firm' && bodyOf(chase).message === 'Call us', chase && chase.body);
        rows[1].querySelector('[data-chasing-pause]').click();
        await wait(30);
        const resume = sent.find(s => s.url === '/api/invoices/INV-0002/chase/pause');
        check('Resume posts paused=false', resume && bodyOf(resume).paused === false);
    }
    {
        const { w, doc, sent } = boot();
        await w.viewInvoice('INV-0001');
        await wait(40);
        const host = doc.getElementById('view-inv-chasing');
        const text = host.textContent.replace(/\s+/g, ' ');
        check('the invoice page shows what is next, what went, and the fee on it', host.style.display === 'block' && /Next: 30 days overdue \(final\) on 2026-09-19/.test(text) && /2026-08-27 · 7 days overdue → a@example.com/.test(text) && /Late fee · 21 days overdue/.test(text) && /£25\.00/.test(text), text);
        check('  with buttons to send one now, hold, add a fee, and let the fee off', host.querySelector('[data-chase-now]') && host.querySelector('[data-chase-pause]').textContent === 'Hold reminders' && host.querySelector('[data-fee-add]') && host.querySelector('[data-fee-waive="9"]'));
        host.querySelector('[data-fee-waive="9"]').click();
        await wait(30);
        const waive = sent.find(s => s.url === '/api/invoices/INV-0001/late-fees/9/waive');
        check('Let off asks why and posts it', waive && bodyOf(waive).reason === 'Goodwill');
        host.querySelector('[data-fee-add]').click();
        await wait(30);
        const fee = sent.find(s => s.url === '/api/invoices/INV-0001/late-fee');
        check('Add a late fee posts the amount typed and whether to tell the customer', fee && bodyOf(fee).amount === 12.5 && bodyOf(fee).tell_customer === false, fee && fee.body);
        host.querySelector('[data-chase-pause]').click();
        await wait(30);
        const hold = sent.find(s => s.url === '/api/invoices/INV-0001/chase/pause');
        check('Hold posts paused=true', hold && bodyOf(hold).paused === true);
    }
    {
        const paidInv = Object.assign({}, INVOICE, { status: 'Paid', due: 0, is_overdue: false, days_overdue: 0, chasing: Object.assign({}, INVOICE.chasing, { next: null, reminders: [], late_fees: [] }) });
        const { w, doc } = boot({ invoice: paidInv });
        await w.viewInvoice('INV-0001');
        await wait(40);
        check('a paid invoice with nothing said shows no chasing block', doc.getElementById('view-inv-chasing').style.display === 'none');
        const heldInv = Object.assign({}, INVOICE, { chasing: Object.assign({}, INVOICE.chasing, { paused: true, late_fees: [] }) });
        const b2 = boot({ invoice: heldInv });
        await b2.w.viewInvoice('INV-0001');
        await wait(40);
        const t2 = b2.doc.getElementById('view-inv-chasing').textContent;
        check('a held invoice says so and offers Resume', /Held/.test(t2) && b2.doc.querySelector('[data-chase-pause]').textContent === 'Resume reminders');
    }
    {
        const { w, doc, sent } = boot();
        w.allContacts = [{ id: 4, name: 'Acme', email: 'a@example.com', chase: false, late_fees: true }];
        w.editContact(4);
        check('editing a contact shows its switches', doc.getElementById('contact-chase').checked === false && doc.getElementById('contact-late-fees').checked === true);
        doc.getElementById('contact-late-fees').checked = false;
        await w.saveContact();
        await wait(20);
        const put = sent.find(s => s.url === '/api/contacts/4' && s.method === 'PUT');
        check('saving sends both switches', put && bodyOf(put).chase === false && bodyOf(put).late_fees === false, put && put.body);
        w.showAddContactModal();
        check('a new contact starts with both on', doc.getElementById('contact-chase').checked && doc.getElementById('contact-late-fees').checked);
    }
    console.log(failures === 0 ? '\nAll chasing checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
