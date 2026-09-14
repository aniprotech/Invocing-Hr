/**
 * Reviews, certifications and job history, on the person's side.
 *
 * Two lists on the Reviews tab: about you, and the people you review - the
 * second stays out of the way for the many who review nobody. Your half is a
 * form until it is sent and words afterwards; the reviewer's half is words
 * once it exists and a placeholder before. Certifications you add yourself
 * wait for HR and can be removed until HR has confirmed them. Nothing here
 * is built with innerHTML, so a name is text however it is spelled.
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
const LISTS = { mine: [
    { id: 11, cycle_id: 1, cycle_name: 'H1 2026', due_on: '2026-07-15', cycle_status: 'open', status: 'awaiting_self', employee_id: 1, employee_name: 'Me', reviewer_name: 'Bea <b>Boss</b>' },
    { id: 9, cycle_id: 0, cycle_name: 'H2 2025', due_on: '', cycle_status: 'closed', status: 'complete', employee_id: 1, employee_name: 'Me', reviewer_name: 'Bea', manager_rating: 4, rating_label: 'Exceeds expectations' },
], to_write: [
    { id: 13, cycle_id: 1, cycle_name: 'H1 2026', due_on: '2026-07-15', cycle_status: 'open', status: 'awaiting_manager', employee_id: 4, employee_name: 'Mo O\'Salah', reviewer_name: 'Me' },
] };
const MINE_OPEN = { id: 11, cycle_name: 'H1 2026', period_start: '2026-01-01', period_end: '2026-06-30', due_on: '2026-07-15', cycle_status: 'open',
    questions: Q, employee_id: 1, employee_name: 'Me', reviewer_name: 'Bea Boss', reviewer_how: 'manager', status: 'awaiting_self', my_role: 'subject',
    self: { answers: [{ text: 'A draft' }, { rating: 3 }], rating: null, comment: '' }, goals: [] };
const MINE_DONE = Object.assign({}, MINE_OPEN, { id: 9, status: 'complete', cycle_status: 'closed',
    self: { answers: [{ text: 'Mine' }, { rating: 3 }], rating: 3, comment: 'ok' },
    manager: { answers: [{ text: 'Theirs' }, { rating: 5 }], rating: 4, rating_label: 'Exceeds expectations', summary: 'Well done <i>you</i>', by: 'Bea Boss' } });
const TO_WRITE = { id: 13, cycle_name: 'H1 2026', due_on: '2026-07-15', cycle_status: 'open', questions: Q,
    employee_id: 4, employee_name: 'Mo O\'Salah', reviewer_name: 'Me', reviewer_how: 'manager', status: 'awaiting_manager', my_role: 'reviewer',
    self: { answers: [{ text: 'I did things' }, { rating: 4 }], rating: 4, comment: '' }, manager: { answers: [], rating: null, summary: '' },
    goals: [{ id: 1, title: 'Close five deals', status: 'in_progress', progress_pct: 40 }] };
const CERTS = { certifications: [
    { id: 1, name: 'Forklift licence', issuer: 'RTITB', expires_on: '2026-09-20', status: 'expiring', days_left: 6, verified: true, has_document: true },
    { id: 5, name: '24" <b>Monitor</b>', issuer: '', expires_on: '', status: 'valid', days_left: null, verified: false, has_document: false },
], expiring: 1, warn_days: 30 };
const HISTORY = { history: [
    { id: 3, effective_on: '2026-04-01', kind: 'pay_change', label: 'Pay change', old_value: '3000', new_value: '3300', note: 'Annual review' },
    { id: null, effective_on: '2024-03-01', kind: 'joined', label: 'Joined', old_value: '', new_value: 'Analyst', note: '' } ] };

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const toasts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = (m) => toasts.push(String(m));
            w.uiAlert = () => Promise.resolve(true);
            w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
            w.uiPrompt = () => Promise.resolve('');
            w.HTMLElement.prototype.scrollIntoView = function () { };
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body });
                const give = (b, status) => Promise.resolve({
                    ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/reviews') return give(opts.lists || LISTS);
                if (p === '/api/employee/reviews/11') return give(MINE_OPEN);
                if (p === '/api/employee/reviews/9') return give(MINE_DONE);
                if (p === '/api/employee/reviews/13') return give(TO_WRITE);
                if (/\/api\/employee\/reviews\/\d+\/(self|manager)$/.test(p)) {
                    if (opts.refused) return give({ detail: "Rate 'Quality of work' before submitting" }, 400);
                    return give({ id: 11, status: 'awaiting_manager', saved: 'submitted' });
                }
                if (p === '/api/employee/certifications' && method === 'GET') return give(CERTS);
                if (p === '/api/employee/certifications' && method === 'POST') return give({ id: 6 });
                if (/\/api\/employee\/certifications\/\d+$/.test(p) && method === 'DELETE') {
                    if (opts.deleteRefused) return give({ detail: 'HR has verified this one - ask them to remove it' }, 409);
                    return give({ deleted: true });
                }
                if (p === '/api/employee/history') return give(HISTORY);
                return give(p.endsWith('s') ? [] : {});
            };
        },
    });
    return { w: dom.window, doc: dom.window.document, sent, toasts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('there is a Reviews tab', /data-tab="reviews"/.test(src) && /id="tab-reviews"/.test(src));
        check('  switching to it loads the lists', /tab === 'reviews'\)\s*loadMyReviews\(\)/.test(src));
        check('the profile tab loads certifications and history', /loadMyCerts\(\); loadMyHistory\(\)/.test(src));
    }

    // --- the two lists ------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadMyReviews();
        await wait(30);
        const mine = doc.getElementById('rv-mine');
        check('reviews about me are listed with their state', mine.children.length === 2 && /Your half to write/.test(mine.textContent) && /Ready to read/.test(mine.textContent));
        check('  a reviewer\'s name is text, not markup', !mine.querySelector('b') && /Bea <b>Boss<\/b>/.test(mine.textContent));
        check('  a finished one shows its stars', /★★★★☆/.test(mine.textContent));
        const todo = doc.getElementById('rv-to-write');
        check('the people I review are listed by name', todo.children.length === 1 && /Mo O'Salah/.test(todo.textContent));
        check('  and the card is shown', !doc.getElementById('rv-to-write-card').classList.contains('hidden'));
    }
    {
        const { w, doc } = boot({ lists: { mine: [], to_write: [] } });
        await w.loadMyReviews();
        await wait(30);
        check('with nobody to review the second card stays hidden', doc.getElementById('rv-to-write-card').classList.contains('hidden'));
        check('  and an empty first list says what will happen', /When HR opens a cycle/.test(doc.getElementById('rv-mine').textContent));
    }

    // --- my half -------------------------------------------------------------------------------------
    {
        const { w, doc, sent, toasts } = boot();
        await w.loadMyReviews();
        await w.openReview(11);
        await wait(30);
        const detail = doc.getElementById('rv-detail');
        check('opening my open review gives me a form with my draft in it',
            detail.querySelector('.rv-text[data-i="0"]').value === 'A draft' && detail.querySelector('.rv-rating[data-i="1"]').value === '3');
        check('  and says the reviewer\'s half comes after mine', /Written after yours/.test(detail.textContent));
        detail.querySelector('.rv-text[data-i="0"]').value = 'Shipped it';
        doc.getElementById('rv-overall').value = '4';
        doc.getElementById('rv-words').value = 'Good half';
        await w.submitReview(false);
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/reviews/11/self');
        const b = bodyOf(post);
        check('sending posts my answers, overall and comment to the self route',
            b.answers[0].text === 'Shipped it' && b.answers[1].rating === 3 && b.rating === 4 && b.comment === 'Good half' && b.draft === false, post && post.body);
        check('  says the reviewer has been told, and closes the form', toasts.some(t => /reviewer has been told/.test(t)) && detail.classList.contains('hidden'));
    }
    {
        const { w, doc, sent } = boot();
        await w.openReview(11);
        await wait(30);
        await w.submitReview(true);
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/reviews/11/self');
        check('a draft is flagged as one and the form stays open', bodyOf(post).draft === true && !doc.getElementById('rv-detail').classList.contains('hidden'));
    }
    {
        const { w, doc } = boot({ refused: true });
        await w.openReview(11);
        await wait(30);
        await w.submitReview(false);
        await wait(30);
        check('a refusal is shown under the form in the server\'s words', /Rate 'Quality of work'/.test(doc.getElementById('rv-error').textContent));
    }
    {
        const { w, doc } = boot();
        await w.openReview(9);
        await wait(30);
        const detail = doc.getElementById('rv-detail');
        check('a finished review is read: both halves, no form', !doc.getElementById('rv-overall') && /Theirs/.test(detail.textContent) && /Mine/.test(detail.textContent));
        check('  the summary is text', /Well done <i>you<\/i>/.test(detail.textContent) && !detail.querySelector('i'));
        check('  with the rating in words', /4 - Exceeds expectations/.test(detail.textContent));
    }

    // --- writing about somebody ----------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.openReview(13);
        await wait(30);
        const detail = doc.getElementById('rv-detail');
        check('as their reviewer I see their half in words', /I did things/.test(detail.textContent));
        check('  their goals for context', /Close five deals/.test(detail.textContent) && /40%/.test(detail.textContent));
        check('  and a form for mine with a summary box', !!doc.getElementById('rv-overall') && /Summary/.test(detail.textContent));
        doc.querySelector('#rv-detail .rv-rating[data-i="1"]').value = '5';
        doc.getElementById('rv-overall').value = '5';
        doc.getElementById('rv-words').value = 'Excellent';
        await w.submitReview(false);
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/reviews/13/manager');
        check('submitting goes to the manager route with a summary', post && bodyOf(post).summary === 'Excellent' && bodyOf(post).rating === 5);
    }

    // --- certifications -------------------------------------------------------------------------------------
    {
        const { w, doc, sent, toasts } = boot();
        await w.loadMyCerts();
        await wait(30);
        const host = doc.getElementById('myCerts');
        check('my certifications are listed with when they run out', /Expires 2026-09-20 \(6 days\)/.test(host.textContent));
        check('  one I added waits for HR, and only that one can be removed', /waiting for HR to confirm/.test(host.textContent) &&
            [...host.querySelectorAll('button')].filter(b => b.textContent === 'Remove').length === 1);
        check('  a name is text however it is spelled', !host.querySelector('b') && /24" <b>Monitor<\/b>/.test(host.textContent));
        check('  a document is a link to my own copy', !!host.querySelector('a[href="/api/employee/certifications/1/document"]'));
        doc.getElementById('cert-name').value = 'First aid';
        doc.getElementById('cert-expires').value = '2027-01-01';
        await w.submitMyCert();
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/certifications' && s.method === 'POST');
        check('adding one posts it and says HR will confirm', post && bodyOf(post).name === 'First aid' && toasts.some(t => /HR will confirm/.test(t)));
    }
    {
        const { w, toasts } = boot({ deleteRefused: true });
        await w.loadMyCerts();
        await w.removeMyCert(1);
        await wait(30);
        check('removing a verified one is refused in the server\'s words', toasts.some(t => /HR has verified this one/.test(t)));
    }

    // --- history --------------------------------------------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadMyHistory();
        await wait(30);
        const host = doc.getElementById('myHistory');
        check('my job history is shown newest first with the pay change and the joining title',
            /3000 → 3300/.test(host.textContent) && /as Analyst/.test(host.textContent) && host.textContent.indexOf('Pay change') < host.textContent.indexOf('Joined'));
    }

    console.log(failures === 0 ? '\nAll portal growth checks passed.' : `\n${failures} portal growth check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
