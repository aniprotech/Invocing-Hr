/**
 * Pay bands and the pay review, on screen.
 *
 * The bands table shows each level with its band or "No band yet"; the
 * review lists everybody with where they sit, and a new pay typed against
 * a person becomes a proposal, several of which are applied with one
 * effective date after a confirmation that names each change. In the
 * portal the band appears on the profile only when the business shows it.
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

const BANDS = { currency: 'GBP', visible_to_staff: false, no_level: 1, levels: [
    { level: 'L2', label: 'L2 - Junior', band: null, headcount: 0, average_compa_ratio: null, below: 0, within: 0, above: 0 },
    { level: 'L3', label: 'L3 - Mid', band: { level: 'L3', min: 30000, mid: 40000, max: 50000, currency: 'GBP', notes: '' }, headcount: 2, average_compa_ratio: 0.9, below: 1, within: 1, above: 0 },
] };
const REVIEW = { currency: 'GBP', rating_cycle: 'H1', totals: { annual_payroll: 66000, people: 2, below_band: 1, above_band: 0, no_band: 0, average_compa_ratio: 0.9, not_moved_in_a_year: 1 },
    people: [
        { employee_id: 1, name: "Low O'Neil", job_title: 'Analyst', department: 'Ops', level: 'L3', pay_frequency: 'monthly', salary: 2000, hourly_rate: 0, annual: 24000,
          band: { min: 30000, mid: 40000, max: 50000 }, compa_ratio: 0.6, position: 'below', pct_through_band: -30, last_pay_change: '', months_since_change: 20, rating: 4 },
        { employee_id: 2, name: 'Fair Day', job_title: '', department: '', level: 'L3', pay_frequency: 'monthly', salary: 3500, hourly_rate: 0, annual: 42000,
          band: { min: 30000, mid: 40000, max: 50000 }, compa_ratio: 1.05, position: 'within', pct_through_band: 60, last_pay_change: '2026-06-01', months_since_change: 3, rating: null },
    ] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    const confirms = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (p === '/api/pay-bands' && method === 'GET') return give(BANDS);
        if (/\/api\/pay-bands\/L\d$/.test(p)) return give(opts.bandFails ? { detail: 'The minimum is above the maximum' } : { level: 'L2' }, opts.bandFails ? 400 : 200);
        if (p === '/api/pay-review' && method === 'GET') return give(REVIEW);
        if (p === '/api/pay-review' && method === 'POST') return give({ applied: 1, effective_on: '2026-10-01', changes: [] });
        if (p === '/api/pay-bands-visibility') return give({ visible_to_staff: true });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    const toasts = [];
    w.showToast = (m) => toasts.push(String(m));
    w.uiConfirm = (m) => { confirms.push(String(m)); return Promise.resolve(opts.confirm !== false); };
    w.uiForm = () => Promise.resolve(opts.form === undefined ? null : opts.form);
    return { w, doc: w.document, sent, toasts, confirms };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('People has Pay bands', /href="#\/pay"/.test(src) && /id="compensation-view"/.test(src));
        const { w } = boot();
        check('  and the hash opens the view', w.VIEW_FOR_SLUG['pay'] === 'compensation-view');
    }
    {
        const { w, doc, sent, confirms, toasts } = boot();
        await w.loadPayView();
        await wait(60);
        const tiles = doc.getElementById('pay-tiles').textContent;
        check('the tiles lead with payroll, ratio, below band and stale pay', /£66,000/.test(tiles) && /0\.9/.test(tiles) && /No pay change in a year/.test(tiles));
        const bands = doc.getElementById('pay-bands');
        check('the bands table shows a band per level or says there is none', /No band yet/.test(bands.textContent) && /£30,000/.test(bands.textContent) && /£50,000/.test(bands.textContent));
        check('  a level with a band offers Edit and Remove; one without offers Set band', /Set band/.test(bands.textContent) && /Remove/.test(bands.textContent));
        check('  people without a level are mentioned', /1 people have no level/.test(bands.textContent));
        const rev = doc.getElementById('pay-review');
        check('the review lists everybody with position and ratio, names as text', /Low O'Neil/.test(rev.textContent) && /Below band/.test(rev.textContent) && /In band/.test(rev.textContent) && /0\.6/.test(rev.textContent));
        check('  says when pay last moved, in months, and flags a year', /20 months ago/.test(rev.textContent) && /3 months ago/.test(rev.textContent));
        check('  the apply bar is hidden until something is typed', doc.getElementById('pay-apply').style.display === 'none');
        w.proposePay(1, '2400');
        w.proposePay(2, '3500');           // the same as now: not a change
        check('a new figure is a proposal; the same figure is not', doc.getElementById('pay-apply').style.display === '' && /Apply 1 change$/.test(doc.getElementById('pay-apply-btn').textContent));
        doc.getElementById('pay-effective').value = '2026-10-01';
        doc.getElementById('pay-note').value = 'Annual review';
        await w.applyPayChanges();
        await wait(60);
        check('applying asks, naming each change', confirms.length === 1 && /Low O'Neil: £2,000 → £2,400/.test(confirms[0]), confirms[0]);
        const post = sent.find(s => s.url === '/api/pay-review' && s.method === 'POST');
        const b = bodyOf(post);
        check('  and posts the changes with the date and note', post && b.effective_on === '2026-10-01' && b.note === 'Annual review' && b.changes.length === 1 && b.changes[0].salary === 2400, post && post.body);
        check('  then says how many applied', toasts.some(t => /1 change applied/.test(t)));
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.loadPayView();
        await wait(60);
        w.proposePay(1, '2400');
        await w.applyPayChanges();
        check('backing out of the confirmation applies nothing', !sent.some(s => s.url === '/api/pay-review' && s.method === 'POST'));
    }
    {
        const { w, sent } = boot({ form: { min: '28000', mid: '', max: '48000', notes: '' } });
        await w.editPayBand('L2');
        await wait(60);
        const put = sent.find(s => /\/api\/pay-bands\/L2$/.test(s.url) && s.method === 'PUT');
        check('setting a band puts min and max, leaving the middle to the server', put && bodyOf(put).min === '28000' && bodyOf(put).max === '48000', put && put.body);
    }
    {
        const { w, sent } = boot();
        await w.setBandVisibility(true);
        await wait(30);
        const put = sent.find(s => s.url === '/api/pay-bands-visibility');
        check('the staff-visibility switch is sent', put && bodyOf(put).visible === true);
    }

    // --- portal --------------------------------------------------------------------------
    for (const visible of [true, false]) {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url) => {
                    const p = String(url).split('?')[0];
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/profile') return give({ first_name: 'F', full_name: 'Fair Day', job_title: 'Analyst', probation: { status: '' } });
                    if (p === '/api/employee/pay-band') return give(visible ? { visible: true, level: 'L3', band: { min: 30000, max: 50000, mid: 40000, currency: 'GBP' }, annual: 42000, position: 'within', pct_through_band: 60 } : { visible: false });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadProfileTab();
        await wait(40);
        const text = doc.getElementById('profileDetails').textContent;
        if (visible) check('the portal profile shows the band and where I sit when the business shows it', /Pay band \(L3\)/.test(text) && /£30,000 to £50,000 a year/.test(text) && /60% of the way/.test(text), text);
        else check('  and nothing about pay bands when it does not', !/Pay band/.test(text));
    }

    console.log(failures === 0 ? '\nAll pay-band checks passed.' : `\n${failures} pay-band check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
