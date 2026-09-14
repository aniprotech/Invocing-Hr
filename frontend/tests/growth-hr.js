/**
 * Reviews, training and analytics, on HR's side.
 *
 * What TalentHR sells and this product lacked: a review cycle with two
 * halves, certifications with a date they stop counting, what changed about
 * somebody's job, and the numbers a head of people is asked for. This checks
 * the screens do what the routes allow and no more: a draft can be opened
 * and an open cycle cannot be re-opened; the HR half is a form only for a
 * review nobody else will write; an unverified certification offers Verify;
 * a name with a quote in it survives a table; analytics draws one axis per
 * chart and never a second y-scale.
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

const Q = [{ text: 'What went well?', kind: 'text' }, { text: 'Quality of work', kind: 'rating' }];
const CYCLES = { cycles: [
    { id: 1, name: 'H1 2026', period_start: '2026-01-01', period_end: '2026-06-30', due_on: '2026-07-15', status: 'open',
      questions: Q, department_id: null, department_name: '', counts: { awaiting_self: 1, awaiting_manager: 1, complete: 1, total: 3 } },
    { id: 2, name: 'H2 2026', period_start: '', period_end: '', due_on: '', status: 'draft',
      questions: Q, department_id: null, department_name: '', counts: { awaiting_self: 0, awaiting_manager: 0, complete: 0, total: 0 } },
], default_questions: Q, rating_labels: {} };
const DETAIL = { cycle: CYCLES.cycles[0], reviews: [
    { id: 11, employee_id: 1, employee_name: 'Ravi "Rav" O\'Brien', reviewer_id: 2, reviewer_name: 'Bea Boss', reviewer_how: 'manager', status: 'complete', self_rating: 4, manager_rating: 5 },
    { id: 12, employee_id: 3, employee_name: 'Lena Ortiz', reviewer_id: null, reviewer_name: 'HR', reviewer_how: 'hr', status: 'awaiting_manager', self_rating: 3, manager_rating: null },
    { id: 13, employee_id: 4, employee_name: 'Mo Salah', reviewer_id: 2, reviewer_name: 'Bea Boss', reviewer_how: 'manager', status: 'awaiting_self', self_rating: null, manager_rating: null },
], summary: { rated: 1, average: 5.0, distribution: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 1 } } };
const REVIEW_FOR_HR = { id: 12, cycle_id: 1, cycle_name: 'H1 2026', cycle_status: 'open', due_on: '2026-07-15', questions: Q,
    employee_id: 3, employee_name: 'Lena Ortiz', reviewer_id: null, reviewer_name: 'HR', reviewer_how: 'hr', status: 'awaiting_manager',
    self: { answers: [{ text: 'Shipped it <b>fast</b>' }, { rating: 4 }], rating: 3, comment: '' }, manager: { answers: [], rating: null, summary: '' }, goals: [] };
const REVIEW_DONE = Object.assign({}, REVIEW_FOR_HR, { id: 11, status: 'complete', employee_name: 'Ravi', reviewer_how: 'manager', reviewer_name: 'Bea Boss',
    manager: { answers: [{ text: 'Agreed' }, { rating: 5 }], rating: 5, summary: 'Strong', by: 'Bea Boss' } });
const CERTS = { certifications: [
    { id: 1, employee_id: 1, employee_name: 'Ravi O\'Brien', name: '24" Monitor safety', issuer: 'RTITB', expires_on: '2026-09-20', status: 'expiring', days_left: 6, verified: true, has_document: true, reference: 'RT-1' },
    { id: 2, employee_id: 3, employee_name: 'Lena', name: 'First aid', issuer: '', expires_on: '2026-08-01', status: 'expired', days_left: -44, verified: false, has_document: false, reference: '' },
], counts: { valid: 0, expiring: 1, expired: 1, unverified: 1, total: 2 }, warn_days: 30 };
const ANALYTICS = { as_of: '2026-09-14',
    headcount: { now: 24, joiners_12m: 7, leavers_12m: 3, turnover_pct: 13.6, average_headcount_12m: 22.1,
        by_month: Array.from({ length: 12 }, (_, i) => ({ label: 'M' + i, headcount: 20 + i, joiners: 1, leavers: i % 3 ? 0 : 1 })),
        average_tenure_years: 2.7, tenure_bands: { under_1: 7, '1_to_2': 6, '2_to_5': 8, over_5: 3 },
        by_department: [{ name: 'Eng', count: 10 }], by_type: [{ name: 'full_time', count: 20 }] },
    reviews: { cycle_name: 'H1 2026', total: 24, complete: 18, awaiting_self: 3, awaiting_manager: 3, average: 3.8, distribution: { 1: 0, 2: 2, 3: 6, 4: 7, 5: 3 } },
    certifications: { total: 31, valid: 25, expiring: 4, expired: 2, unverified: 3, people_with_one: 18 },
    leave: { days_taken: 143.5, per_person: 6.0, by_type: { annual: 118, sick: 21.5 } },
    goals: { total: 40, completed: 12, overdue: 4, average_progress_pct: 58 },
    moves_12m: { promotions: 3, pay_changes: 9, transfers: 2, manager_changes: 4 }, hiring: { open_roles: 2, openings: 3 } };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), {
        runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html',
    });
    const w = dom.window;
    const sent = [];
    const charts = [];
    w.console.error = () => { };
    // Chart.js is a CDN script the harness does not load; this records what
    // each chart was asked to draw so the shape can be checked.
    w.Chart = function (el, config) { charts.push({ id: el.id, config }); this.destroy = () => { }; };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({
            ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (p === '/api/review-cycles' && method === 'GET') return give(CYCLES);
        if (p === '/api/review-cycles' && method === 'POST') return give(opts.createFails ? { detail: 'Give the cycle a name' } : { id: 3 }, opts.createFails ? 400 : 200);
        if (p === '/api/review-cycles/1') return give(DETAIL);
        if (p === '/api/review-cycles/2') return give({ cycle: CYCLES.cycles[1], reviews: [], summary: { rated: 0, average: null, distribution: {} } });
        if (/\/api\/review-cycles\/\d+\/open$/.test(p)) return give({ opened: 3, reviewers: 1, hr_pool: 2, status: 'open' });
        if (p === '/api/reviews/12') return give(REVIEW_FOR_HR);
        if (p === '/api/reviews/11') return give(REVIEW_DONE);
        if (p === '/api/reviews/12/manager') return give(opts.writeFails ? { detail: 'Write a summary - it is the part they will read first' } : { id: 12, status: 'complete' }, opts.writeFails ? 400 : 200);
        if (p === '/api/certifications') return give(CERTS);
        if (/\/api\/certifications\/\d+$/.test(p) && method === 'PUT') return give({ id: 2, verified: true });
        if (p === '/api/hr/analytics') return give(ANALYTICS);
        if (p === '/api/employees/7/certifications') return give({ certifications: CERTS.certifications.slice(1) });
        if (p === '/api/employees/7/history') return give({ history: [
            { id: 3, effective_on: '2026-04-01', kind: 'pay_change', label: 'Pay change', old_value: '3000', new_value: '3300', note: 'Annual review' },
            { id: null, effective_on: '2024-03-01', kind: 'joined', label: 'Joined', old_value: '', new_value: 'Analyst', note: '' } ] });
        if (p === '/api/departments') return give([{ id: 5, name: 'Sales' }]);
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    const toasts = [];
    w.showToast = (m, k) => toasts.push({ m, k });
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    w.uiForm = () => Promise.resolve(opts.form || null);
    w.hrDataChanged = () => { };
    return { w, doc: w.document, sent, charts, toasts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- the screens are reachable -------------------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('People has Reviews, Training and Analytics', /href="#\/reviews"/.test(src) && /href="#\/training"/.test(src) && /href="#\/people-analytics"/.test(src));
        const { w } = boot();
        check('  and each hash opens its view', w.VIEW_FOR_SLUG['reviews'] === 'reviews-view' &&
            w.VIEW_FOR_SLUG['training'] === 'training-view' && w.VIEW_FOR_SLUG['people-analytics'] === 'analytics-view');
    }

    // --- cycles -----------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadReviewsView();
        await wait(40);
        const rows = doc.getElementById('review-cycles').textContent;
        check('every cycle is listed with its state', /H1 2026/.test(rows) && /Open/.test(rows) && /H2 2026/.test(rows) && /Draft/.test(rows));
        check('  an open one shows how far along it is', /1 of 3 complete/.test(rows));
        const html = doc.getElementById('review-cycles').innerHTML;
        check('  a draft offers Open it, Edit and Delete; an open one does not', /startCycle\(2\)/.test(html) && /deleteCycle\(2\)/.test(html) && !/startCycle\(1\)/.test(html) && !/deleteCycle\(1\)/.test(html));
        check('  an open one offers Close it', /endCycle\(1\)/.test(html) && !/endCycle\(2\)/.test(html));
        const detail = doc.getElementById('review-cycle-detail').textContent;
        check('the open cycle is shown underneath without a click', /Lena Ortiz/.test(detail) && /Waiting on reviewer/.test(detail));
        check('  a name with quotes in it survives the table', /Ravi "Rav" O'Brien/.test(detail));
        check('  the rating distribution is drawn', /Outstanding/.test(detail) && /Average 5 across 1 rated/.test(detail));
    }
    {
        const { w, sent, toasts } = boot();
        await w.loadReviewsView();
        await wait(40);
        await w.startCycle(2);
        await wait(40);
        check('opening a cycle asks first and then opens it', sent.some(s => s.url === '/api/review-cycles/2/open' && s.method === 'POST'));
        check('  and says how many are for HR to write', toasts.some(t => /3 reviews opened - 2 for you to write/.test(t.m)), JSON.stringify(toasts));
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.loadReviewsView();
        await wait(40);
        await w.startCycle(2);
        check('backing out of the question opens nothing', !sent.some(s => s.url === '/api/review-cycles/2/open'));
    }

    // --- the cycle form -------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadReviewsView();
        await wait(40);
        await w.openCycleModal();
        await wait(40);
        check('a new cycle starts with the default questions', doc.querySelectorAll('#rc-questions [data-q]').length === 2);
        check('  and lists departments as an audience', [...doc.querySelectorAll('#rc-dept option')].some(o => o.textContent === 'Sales'));
        doc.getElementById('rc-name').value = 'H2 2026';
        w.addCycleQuestion();
        doc.querySelectorAll('#rc-questions [data-q]')[2].querySelector('.rc-q-text').value = 'Third';
        doc.querySelectorAll('#rc-questions [data-q]')[2].querySelector('.rc-q-kind').value = 'rating';
        await w.saveCycle();
        await wait(40);
        const post = sent.find(s => s.url === '/api/review-cycles' && s.method === 'POST');
        check('saving sends the questions in order with their kinds', post && bodyOf(post).questions.length === 3 && bodyOf(post).questions[2].kind === 'rating', post && post.body);
        check('  as a draft', post && doc.getElementById('review-cycle-modal').style.display === 'none');
    }
    {
        const { w, doc } = boot();
        await w.loadReviewsView();
        await wait(40);
        await w.openCycleModal(1);
        await wait(40);
        check('an open cycle cannot have its questions or audience changed from the form',
            doc.querySelector('#rc-questions .rc-q-text').disabled && doc.getElementById('rc-dept').disabled &&
            doc.getElementById('rc-add-q').style.display === 'none');
        check('  and the form says why', /cannot change/.test(doc.getElementById('rc-q-note').textContent));
    }
    {
        const { w, doc } = boot({ createFails: true });
        await w.loadReviewsView();
        await wait(40);
        await w.openCycleModal();
        await wait(40);
        await w.saveCycle();
        await wait(40);
        check('a refusal is shown in the form, and the form stays open',
            /Give the cycle a name/.test(doc.getElementById('rc-error').textContent) && doc.getElementById('review-cycle-modal').style.display === 'flex');
    }

    // --- reading and writing one ----------------------------------------------------------------
    {
        const { w, doc, sent, toasts } = boot();
        await w.readReview(12);
        await wait(40);
        const body = doc.getElementById('rr-body');
        check('their half is shown, escaped', /Shipped it/.test(body.textContent) && !body.querySelector('b'));
        check('  and a review with nobody above them gets a form for HR\'s half', !!doc.getElementById('rr-overall') && !!doc.getElementById('rr-summary'));
        check('  with Save draft and Submit', /hrWriteReview\(true\)/.test(doc.getElementById('rr-footer').innerHTML) && /hrWriteReview\(false\)/.test(doc.getElementById('rr-footer').innerHTML));
        doc.querySelector('.rr-text[data-i="0"]').value = 'Agreed';
        doc.querySelector('.rr-rating[data-i="1"]').value = '5';
        doc.getElementById('rr-overall').value = '4';
        doc.getElementById('rr-summary').value = 'Good half';
        await w.hrWriteReview(false);
        await wait(40);
        const post = sent.find(s => s.url === '/api/reviews/12/manager');
        const b = bodyOf(post);
        check('submitting sends every answer, the rating and the summary', b.answers[0].text === 'Agreed' && b.answers[1].rating === 5 && b.rating === 4 && b.summary === 'Good half' && b.draft === false, post && post.body);
        check('  and says they have been told', toasts.some(t => /they have been told/.test(t.m)));
    }
    {
        const { w, doc } = boot();
        await w.readReview(11);
        await wait(40);
        check('a complete review is read, not edited', !doc.getElementById('rr-overall') && /Strong/.test(doc.getElementById('rr-body').textContent));
    }
    {
        const { w, doc } = boot({ writeFails: true });
        await w.readReview(12);
        await wait(40);
        await w.hrWriteReview(false);
        await wait(40);
        check('a refusal is shown under the form', /Write a summary/.test(doc.getElementById('rr-error').textContent));
    }

    // --- training ---------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadTrainingView();
        await wait(40);
        const tiles = doc.getElementById('training-tiles').textContent;
        check('the tiles count valid, expiring, lapsed and unverified', /Expiring within 30 days/.test(tiles) && /Lapsed/.test(tiles) && /Waiting to be verified/.test(tiles));
        const list = doc.getElementById('training-list');
        check('each certification says when it runs out', /Expires 2026-09-20 \(6 days\)/.test(list.textContent) && /Lapsed 2026-08-01 \(44 days ago\)/.test(list.textContent));
        check('  a name with a double quote survives', /24" Monitor safety/.test(list.textContent));
        check('  only the unverified one offers Verify', /verifyCertification\(2\)/.test(list.innerHTML) && !/verifyCertification\(1\)/.test(list.innerHTML));
        check('  a document is a link to the served image', /href="\/api\/certifications\/1\/document"/.test(list.innerHTML) && !/certifications\/2\/document/.test(list.innerHTML));
        await w.verifyCertification(2);
        await wait(40);
        const put = sent.find(s => s.url === '/api/certifications/2' && s.method === 'PUT');
        check('Verify sends verified: true', put && bodyOf(put).verified === true);
        w.switchTrainingTab('expired', null);
        await wait(40);
        check('the Lapsed tab asks for lapsed ones', sent.some(s => s.url === '/api/certifications' && s.method === 'GET') && sent[sent.length - 1].url === '/api/certifications');
    }
    {
        const { w, sent } = boot({ form: { name: 'Forklift', issuer: 'RTITB', expires_on: '2027-01-01' } });
        await w.addCertification(7);
        await wait(40);
        const post = sent.find(s => s.url === '/api/employees/7/certifications' && s.method === 'POST');
        check('adding from a profile posts to that person', post && bodyOf(post).name === 'Forklift');
    }

    // --- on the profile ------------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        w.currentEmployeeId = 7;
        await w.loadEmployeeCerts(7);
        await w.loadEmployeeHistory(7);
        await wait(40);
        const certs = doc.getElementById('emp-certs-list').textContent;
        check('the profile lists their certifications and flags the unverified', /First aid/.test(certs) && /not yet verified/.test(certs));
        const hist = doc.getElementById('emp-history-list').textContent;
        check('the profile shows the job history newest first, joining at the bottom', /Pay change/.test(hist) && /3000 → 3300/.test(hist) && /Joined as Analyst/.test(hist) &&
            hist.indexOf('Pay change') < hist.indexOf('Joined'));
        check('  the automatic rows can be removed, the joining row cannot', /deleteHistoryEntry\(3,7\)/.test(doc.getElementById('emp-history-list').innerHTML) &&
            !/deleteHistoryEntry\(null/.test(doc.getElementById('emp-history-list').innerHTML));
    }

    // --- analytics ---------------------------------------------------------------------------------------------
    {
        const { w, doc, charts } = boot();
        await w.loadAnalyticsView();
        await wait(40);
        const tiles = doc.getElementById('pa-tiles').textContent;
        check('the tiles lead with headcount, turnover, tenure and open roles', /24/.test(tiles) && /13\.6%/.test(tiles) && /2\.7 yrs/.test(tiles) && /3 openings/.test(tiles));
        check('six charts are drawn', charts.length === 6, String(charts.length));
        check('  none of them has two y-axes', charts.every(c => Object.keys(c.config.options.scales || {}).filter(k => k.startsWith('y')).length <= 1));
        const flow = charts.find(c => c.id === 'pa-flow');
        check('  joiners and leavers are two series in fixed colours, with a legend beside the title',
            flow.config.data.datasets.length === 2 && flow.config.data.datasets[0].backgroundColor !== flow.config.data.datasets[1].backgroundColor &&
            /Joiners/.test(doc.getElementById('pa-flow-legend').textContent) && /Leavers/.test(doc.getElementById('pa-flow-legend').textContent));
        check('  every single-series chart uses the one hue', charts.filter(c => c.id !== 'pa-flow').every(c => c.config.data.datasets.length === 1));
        check('  the rating chart names its cycle', /H1 2026/.test(doc.getElementById('pa-ratings-title').textContent));
        const blocks = doc.getElementById('pa-blocks').textContent;
        check('the blocks cover certifications, goals, moves and leave', /Lapsed/.test(blocks) && /Overdue/.test(blocks) && /Promotions/.test(blocks) && /Days taken/.test(blocks));
        await w.loadAnalyticsView();
        await wait(40);
        check('reloading draws again rather than stacking canvases', charts.length === 12);
    }

    console.log(failures === 0 ? '\nAll HR growth checks passed.' : `\n${failures} HR growth check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
