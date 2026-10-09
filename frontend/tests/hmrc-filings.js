/**
 * HMRC payroll filings (RTI) on the Payroll screen.
 *
 * A panel that shows on UK payroll only: what stands between the business and
 * its first filing (and whose job each thing is), each pay day with Check and
 * Send, what has been sent, and the windows for the business's HMRC details
 * and the Employer Payment Summary. Plus the three employee fields HMRC needs.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const READY = [
    { key: 'regime', owner: 'you', ok: true, label: 'UK payroll is switched on', detail: '' },
    { key: 'year', owner: 'platform', ok: true, label: "HMRC's 2026-27 filing definitions are installed", detail: '' },
    { key: 'refs', owner: 'you', ok: true, label: 'Your PAYE and Accounts Office references', detail: '' },
    { key: 'gateway', owner: 'you', ok: true, label: 'Your Government Gateway user ID and password', detail: '' },
    { key: 'vendor', owner: 'platform', ok: true, label: 'HMRC has recognised this software (Vendor ID)', detail: '' },
    { key: 'endpoint', owner: 'platform', ok: true, label: "The address of HMRC's Gateway", detail: '' },
    { key: 'encryption', owner: 'platform', ok: true, label: 'A key to keep Gateway passwords safe', detail: '' },
];
const NOT_READY = READY.map(r => ['refs', 'gateway', 'vendor', 'endpoint', 'encryption'].includes(r.key)
    ? { ...r, ok: false, detail: r.key === 'vendor' ? 'HMRC_VENDOR_ID is not set.' : 'Not yet.' } : r);

const STATUS = (o) => Object.assign({
    employer: { office_no: '123', paye_ref: 'AB456', ao_ref: '123PA00012345', contact_name: 'Jane', contact_email: 'j@x.co', contact_phone: '0207', gateway_user: 'GW1' },
    has_gateway_password: true, readiness: READY, can_check: true, can_send: true, mode: 'test', irmark: false,
    pay_dates: [{ pay_date: '2026-04-30', people: 3, state: 'not_sent' }, { pay_date: '2026-03-31', people: 3, state: 'sent' }],
    submissions: [{ id: 7, kind: 'FPS', tax_year: 2025, pay_date: '2026-03-31', status: 'accepted', mode: 'live', people: 3, summary: '3 paid', correlation_id: 'C', problems: [], hmrc_errors: [], created_at: '2026-03-31 09:00:00', created_by: 'me' }],
    not_built: ['Statutory pay on the payslip', 'Payrolled benefits'],
}, o || {});

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/payroll' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (p === '/api/payroll/settings') return give({ regime: opts.regime || 'uk', tax_year: '2026-27', rates_ready: true, ni_categories: ['A', 'H'] });
        if (p === '/api/hmrc/rti' && method === 'GET') return give(opts.status || STATUS());
        if (p === '/api/hmrc/rti/settings') return give(opts.status || STATUS());
        if (opts.reply && opts.reply[p]) { const r = opts.reply[p](init); return give(r.body, r.status); }
        if (p === '/api/hmrc/rti/fps/check') return give({ ok: true, status: 'checked', people: 3, pay_date: '2026-04-30', problems: [], hmrc_errors: [], starters: ['Ann Lee'], mode: 'test', xml: '<IRenvelope/>' });
        if (p === '/api/hmrc/rti/fps/send') return give({ ok: true, sent: true, status: 'accepted', people: 3, pay_date: '2026-04-30', problems: [], hmrc_errors: [], mode: 'test' });
        if (p === '/api/hmrc/rti/eps/check' || p === '/api/hmrc/rti/eps/send') return give({ ok: true, sent: p.endsWith('send'), status: p.endsWith('send') ? 'accepted' : 'checked', people: 0, problems: [], hmrc_errors: [], mode: 'test' });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m, t) => { w._toasts = (w._toasts || []).concat([[m, t]]); };
    w._asked = [];
    w.uiConfirm = (m, o) => { w._asked.push(String(m)); return Promise.resolve(opts.confirm !== false); };
    w.formatCurrency = (v) => '£' + Number(v || 0).toFixed(2);
    return { w, doc: w.document, sent };
}

(async () => {
    // --- only on UK payroll ----------------------------------------------------------
    {
        const { w, doc, sent } = boot({ regime: 'simple' });
        await w.loadHmrcPanel();
        check('on the simple payroll there is no HMRC panel', doc.getElementById('hmrc-panel').style.display === 'none');
        check('  and it does not ask the server for anything', !sent.some(s => s.url === '/api/hmrc/rti'));
    }

    // --- an answer that is not what was expected ------------------------------------------
    {
        const { w, doc } = boot({ status: {} });
        await w.loadHmrcPanel();
        check('a server answer without the expected parts says so instead of breaking the Payroll screen', /not available right now/.test(doc.getElementById('hmrc-content').textContent));
    }
    {
        const { w, doc } = boot({ status: STATUS({ pay_dates: undefined, submissions: undefined, not_built: undefined }) });
        await w.loadHmrcPanel();
        check('missing lists are treated as empty', /No UK payslips yet/.test(doc.getElementById('hmrc-content').textContent));
    }

    // --- a business that has not set up ----------------------------------------------------
    {
        const { w, doc } = boot({ status: STATUS({ readiness: NOT_READY, can_check: false, can_send: false, has_gateway_password: false }) });
        await w.loadHmrcPanel();
        const text = doc.getElementById('hmrc-content').textContent;
        check('the panel shows on UK payroll', doc.getElementById('hmrc-panel').style.display !== 'none');
        check('it lists what is missing, in the words of the server', /Before the first filing/.test(text) && /HMRC_VENDOR_ID is not set/.test(text));
        check('  and says whose job each one is', /you/.test(text) && /platform admin/.test(text));
        check('  and the ones already done are marked done', /Done\s*UK payroll is switched on/.test(text.replace(/\s+/g, ' ')), text.slice(0, 160));
        const checks = [...doc.querySelectorAll('[data-hmrc-check]')], sends = [...doc.querySelectorAll('[data-hmrc-send]')];
        check('Check and Send are both off until the references are in / everything is', checks.every(b => b.disabled) && sends.every(b => b.disabled));
        check('  the disabled Send says why', /Finish the list above/.test(sends[0].getAttribute('title')));
    }

    // --- references in but the platform not ready: check yes, send no ------------------------
    {
        const { w, doc } = boot({ status: STATUS({ readiness: NOT_READY.map(r => r.key === 'refs' ? { ...r, ok: true } : r), can_check: true, can_send: false }) });
        await w.loadHmrcPanel();
        check('with the references in, Check is on and Send is not',
            [...doc.querySelectorAll('[data-hmrc-check]')].every(b => !b.disabled) && [...doc.querySelectorAll('[data-hmrc-send]')].every(b => b.disabled));
    }

    // --- ready ---------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadHmrcPanel();
        const text = doc.getElementById('hmrc-content').textContent;
        check('when everything is in place it says so, without the list', /Everything needed to send is in place/.test(text) && !/Before the first filing/.test(text));
        check('test mode is stated plainly', /Test mode/.test(text) && /records nothing/.test(text));
        const rows = doc.querySelectorAll('#hmrc-content [data-hmrc-day]');
        check('each pay day has a row with people and status', rows.length === 2 && /2026-04-30/.test(rows[0].textContent) && /3 people/.test(rows[0].textContent) && /Not reported/.test(rows[0].textContent) && /Sent to HMRC/.test(rows[1].textContent));
        check('  a day already sent offers "Send again"', /Send again/.test(rows[1].textContent) && /^Send$/.test(rows[0].querySelector('[data-hmrc-send]').textContent));
        check('what has been sent is listed', /Full Payment/.test(text) && /Accepted/.test(text));
        check('what is not covered is stated', /Not covered yet/.test(text) && /payrolled benefits/.test(text));
    }
    {
        const { w, doc } = boot({ status: STATUS({ mode: 'live' }) });
        await w.loadHmrcPanel();
        check('live mode is stated plainly too', /Live - what you send is recorded at HMRC/.test(doc.getElementById('hmrc-content').textContent));
    }

    // --- checking a day -------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadHmrcPanel();
        doc.querySelector('[data-hmrc-check="2026-04-30"]').dispatchEvent(new w.Event('click'));
        await new Promise(r => setTimeout(r, 30));
        const post = sent.find(s => s.url === '/api/hmrc/rti/fps/check');
        check('Check posts the pay date', post && bodyOf(post).pay_date === '2026-04-30');
        const modal = doc.getElementById('hmrc-result-modal');
        check('the result opens in a window and says nothing was sent', modal.style.display === 'flex' && /Passes HMRC's own rules/.test(modal.textContent) && /Nothing has been sent/.test(modal.textContent));
        check('  with the starters named', /New starters in this filing: Ann Lee/.test(modal.textContent));
        check('  and the message available to read', /<IRenvelope\/>/.test(modal.querySelector('pre').textContent));
    }
    {
        const { w, doc } = boot({ reply: { '/api/hmrc/rti/fps/check': () => ({ body: { ok: false, status: 'rejected', people: 1, pay_date: '2026-04-30', sent: false, problems: ['Ann Lee: HMRC needs their gender <img src=x onerror=alert(1)>', 'Element NINO: bad'], hmrc_errors: [], starters: [] } }) } });
        await w.loadHmrcPanel();
        await w.hmrcCheck('2026-04-30');
        const modal = doc.getElementById('hmrc-result-modal');
        check('a failed check lists each thing to put right', /To put right/.test(modal.textContent) && modal.querySelectorAll('li').length === 2);
        check('  says it would be refused', /would be refused/.test(modal.textContent));
        check('  and what the server sent cannot inject markup', !modal.querySelector('img') && /<img src=x/.test(modal.textContent));
    }
    {
        const { w, doc } = boot({ reply: { '/api/hmrc/rti/fps/check': () => ({ status: 404, body: { detail: 'There are no UK payslips with the pay date 2026-04-30' } }) } });
        await w.loadHmrcPanel();
        await w.hmrcCheck('2026-04-30');
        check('an error from the server is shown as an error, not as a result', (w._toasts || []).some(t => /no UK payslips/.test(t[0]) && t[1] === 'error') && doc.getElementById('hmrc-result-modal').style.display !== 'flex');
    }

    // --- sending ---------------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        check('sending asks first, and in test mode says nothing is recorded', w._asked.length === 1 && /test service/.test(w._asked[0]) && /not record/.test(w._asked[0]), w._asked[0]);
        check('  then posts the pay date', sent.some(s => s.url === '/api/hmrc/rti/fps/send' && bodyOf(s).pay_date === '2026-04-30'));
        check('  and shows HMRC\'s answer, noting that a test records nothing', /Accepted/.test(doc.getElementById('hmrc-result-modal').textContent) && /nothing was recorded/.test(doc.getElementById('hmrc-result-modal').textContent));
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        check('saying no to the question sends nothing', !sent.some(s => s.url === '/api/hmrc/rti/fps/send'));
    }
    {
        const { w, sent } = boot({ status: STATUS({ mode: 'live' }) });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        check('in live mode the question says it is recorded at HMRC', /recorded at HMRC/.test(w._asked[0]), w._asked[0]);
    }
    {
        let calls = 0;
        const { w, sent } = boot({ status: STATUS({ mode: 'live' }), reply: { '/api/hmrc/rti/fps/send': (init) => (++calls === 1
            ? { status: 409, body: { detail: 'HMRC already accepted a Full Payment Submission for 2026-04-30 on 2026-04-30. Send again only to correct it - confirm to go ahead.' } }
            : { body: { ok: true, sent: true, status: 'accepted', people: 3, pay_date: '2026-04-30', problems: [], hmrc_errors: [], mode: 'live' } }) } });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        const posts = sent.filter(s => s.url === '/api/hmrc/rti/fps/send');
        check('a day already sent is asked about again, and resent only on a second yes', posts.length === 2 && !bodyOf(posts[0]).confirm_resend && bodyOf(posts[1]).confirm_resend === true && w._asked.length === 2 && /already accepted/.test(w._asked[1]));
    }
    {
        const { w, doc } = boot({ reply: { '/api/hmrc/rti/fps/send': () => ({ body: { ok: false, status: 'refused', sent: true, people: 3, pay_date: '2026-04-30', problems: [], hmrc_errors: [{ number: '1046', text: 'Authentication Failure.' }], mode: 'test' } }) } });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        const t = doc.getElementById('hmrc-result-modal').textContent;
        check('a refusal shows HMRC\'s own number and words', /HMRC refused it/.test(t) && /1046: Authentication Failure/.test(t));
    }
    {
        const { w, doc } = boot({ reply: { '/api/hmrc/rti/fps/send': () => ({ body: { ok: false, status: 'sent', sent: true, people: 3, pay_date: '2026-04-30', problems: [], hmrc_errors: [], mode: 'test' } }) } });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        check('an answer still awaited is said to be awaited, not failed', /HMRC has not answered yet/.test(doc.getElementById('hmrc-result-modal').textContent));
    }
    {
        const { w } = boot({ reply: { '/api/hmrc/rti/fps/send': () => ({ status: 503, body: { detail: 'Not ready to send to HMRC yet: HMRC has recognised this software (Vendor ID) (the platform)' } }) } });
        await w.loadHmrcPanel();
        await w.hmrcSend('2026-04-30');
        check('a send the server will not take says why', (w._toasts || []).some(t => /Vendor ID/.test(t[0]) && t[1] === 'error'));
    }

    // --- viewing what was sent ----------------------------------------------------------------------------------
    {
        const { w, doc } = boot({ reply: { '/api/hmrc/rti/submissions/7': () => ({ body: { id: 7, kind: 'FPS', pay_date: '2026-03-31', status: 'accepted', mode: 'live', people: 3, problems: [], hmrc_errors: [], body_xml: '<IRenvelope>sent</IRenvelope>' } }) } });
        await w.loadHmrcPanel();
        doc.querySelector('[data-hmrc-view="7"]').dispatchEvent(new w.Event('click'));
        await new Promise(r => setTimeout(r, 30));
        const m = doc.getElementById('hmrc-result-modal');
        check('View opens what was sent, with the message', m.style.display === 'flex' && /Full Payment Submission - 2026-03-31/.test(m.textContent) && /<IRenvelope>sent/.test(m.querySelector('pre').textContent));
    }

    // --- the business's details -------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadHmrcPanel();
        w.openHmrcSettings();
        const v = id => doc.getElementById(id).value;
        check('the details window opens filled in', v('hmrc-office-no') === '123' && v('hmrc-paye-ref') === 'AB456' && v('hmrc-ao-ref') === '123PA00012345' && v('hmrc-gateway-user') === 'GW1');
        check('  the password is never filled in, and says one is saved', v('hmrc-gateway-password') === '' && /Saved/.test(doc.getElementById('hmrc-gateway-password').placeholder));
        check('  and the password box is a password box that browsers will not autofill', doc.getElementById('hmrc-gateway-password').type === 'password' && doc.getElementById('hmrc-gateway-password').getAttribute('autocomplete') === 'new-password');
        doc.getElementById('hmrc-paye-ref').value = 'ZZ999';
        await w.saveHmrcSettings();
        const put = sent.find(s => s.url === '/api/hmrc/rti/settings' && s.method === 'PUT');
        check('saving sends the references', put && bodyOf(put).paye_ref === 'ZZ999' && bodyOf(put).office_no === '123');
        check('  but not the password when none was typed', !('gateway_password' in bodyOf(put)));
        doc.getElementById('hmrc-gateway-password').value = 'S3cret!';
        await w.saveHmrcSettings();
        const puts = sent.filter(s => s.url === '/api/hmrc/rti/settings' && s.method === 'PUT');
        check('  and sends it when one was', bodyOf(puts[1]).gateway_password === 'S3cret!');
        check('  the window closes and the panel is refreshed', doc.getElementById('hmrc-settings-modal').style.display === 'none');
    }
    {
        const { w, doc } = boot({ status: STATUS({ has_gateway_password: false }) });
        await w.loadHmrcPanel();
        w.openHmrcSettings();
        check('with no password saved the box asks for it', /Your Government Gateway password/.test(doc.getElementById('hmrc-gateway-password').placeholder));
    }

    // --- Employer Payment Summary ---------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadHmrcPanel();
        w.openHmrcEps();
        check('the summary window offers twelve tax months', doc.getElementById('hmrc-eps-month').options.length === 13);
        doc.getElementById('hmrc-eps-from').value = '2026-05-06';
        doc.getElementById('hmrc-eps-to').value = '2026-06-05';
        await w.hmrcEps(false);
        const post = sent.find(s => s.url === '/api/hmrc/rti/eps/check');
        check('a quiet month is sent as its two dates and nothing else', post && bodyOf(post).no_payment_from === '2026-05-06' && bodyOf(post).no_payment_to === '2026-06-05' && !('recoverable' in bodyOf(post)) && !('employment_allowance' in bodyOf(post)), JSON.stringify(bodyOf(post)));
        check('  Check does not ask whether to send, and shows the result', w._asked.length === 0 && doc.getElementById('hmrc-result-modal').style.display === 'flex');
    }
    {
        const { w, doc, sent } = boot();
        await w.loadHmrcPanel();
        w.openHmrcEps();
        doc.getElementById('hmrc-eps-allowance').value = 'yes';
        doc.getElementById('hmrc-eps-month').value = '3';
        doc.getElementById('hmrc-eps-smp').value = '250.5';
        doc.getElementById('hmrc-eps-nic-smp').value = '6.5';
        await w.hmrcEps(true);
        const post = sent.find(s => s.url === '/api/hmrc/rti/eps/send');
        const b = bodyOf(post);
        check('the allowance and amounts to recover are sent with the month', b.employment_allowance === true && b.recoverable.smp === 250.5 && b.recoverable.nic_smp === 6.5 && b.recoverable_month === 3, JSON.stringify(b));
        check('  and sending asks first', w._asked.length === 1);
    }
    {
        const { w, doc } = boot({ status: STATUS({ can_send: false }) });
        await w.loadHmrcPanel();
        w.openHmrcEps();
        check('the summary cannot be sent until the panel is ready, but can be checked', doc.getElementById('hmrc-eps-send').disabled === true);
    }

    // --- the employee fields HMRC needs -----------------------------------------------------------------------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        for (const p of ['emp', 'ukp']) {
            check(`the ${p === 'emp' ? 'new employee form' : 'UK payroll window'} asks for gender, postcode and usual hours`,
                new RegExp(`id="${p}-gender"`).test(html) && new RegExp(`id="${p}-postcode"`).test(html) && new RegExp(`id="${p}-hours-band"`).test(html));
        }
        const { w, doc, sent } = boot();
        await w.loadPayrollSettings();
        w._ukEmployee = { id: 5, gender: 'F', postcode: 'LS1 4AB', hours_band: 'D', ni_category: 'A' };
        w.openUkPayroll();
        check('the UK payroll window opens with them filled in', doc.getElementById('ukp-gender').value === 'F' && doc.getElementById('ukp-postcode').value === 'LS1 4AB' && doc.getElementById('ukp-hours-band').value === 'D');
        doc.getElementById('ukp-gender').value = 'M';
        doc.getElementById('ukp-hours-band').value = 'B';
        await w.saveUkPayroll();
        const put = sent.find(s => s.url === '/api/employees/5' && s.method === 'PUT');
        check('and saves them', put && bodyOf(put).gender === 'M' && bodyOf(put).postcode === 'LS1 4AB' && bodyOf(put).hours_band === 'B', put && put.body);
        await w.renderEmployeeUk({ id: 5, ni_number: 'AB123456C', tax_code: '1257L', gender: '', postcode: '', hours_band: '' });
        check('an employee with no gender is told it is still needed', /a gender for HMRC/.test(doc.getElementById('emp-uk-summary').textContent) && /No gender/.test(doc.getElementById('emp-uk-summary').textContent));
    }

    // --- reached from the Payroll screen, and from adding someone -------------------------------------------------------------
    {
        const { w, sent } = boot();
        await w.loadPayrollSettings();
        w.showView('payroll-view');
        await new Promise(r => setTimeout(r, 60));
        check('opening the Payroll screen loads the HMRC panel', sent.some(s => s.url === '/api/hmrc/rti' && s.method === 'GET'));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadPayrollSettings();
        const set = (id, v) => { doc.getElementById(id).value = v; };
        set('emp-first-name', 'Ann'); set('emp-last-name', 'Lee'); set('emp-email', 'ann@example.com'); set('emp-password', 'Passw0rdTest');
        set('emp-gender', 'F'); set('emp-postcode', 'LS1 4AB'); set('emp-hours-band', 'D');
        try { await w.submitNewEmployee(); } catch (e) { /* what follows the save is not under test */ }
        const post = sent.find(s => s.url === '/api/employees' && s.method === 'POST');
        check('a new employee is created with the three fields HMRC needs', post && bodyOf(post).gender === 'F' && bodyOf(post).postcode === 'LS1 4AB' && bodyOf(post).hours_band === 'D', post && post.body);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
