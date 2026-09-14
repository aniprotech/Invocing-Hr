/**
 * Peer feedback and the talent grid, on screen.
 *
 * HR's review modal shows what colleagues said with names, offers a picker
 * to ask more, and a potential select on the half HR writes; the cycle
 * page draws nine boxes with the unplaced counted beside them. In the
 * portal, feedback asked of me is a short form; a reviewer gets the
 * potential select and the picker; the person reads colleagues' words
 * with no names.
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

const Q = [{ text: 'Quality of work', kind: 'rating' }];
const REVIEW = { id: 12, cycle_id: 1, cycle_name: 'H1', cycle_status: 'open', due_on: '', questions: Q,
    employee_id: 3, employee_name: 'Lena', reviewer_id: null, reviewer_name: 'HR', reviewer_how: 'hr', status: 'awaiting_manager',
    self: { answers: [{ rating: 4 }], rating: 3, comment: '' }, manager: { answers: [], rating: null, summary: '', potential: null }, goals: [],
    peer_feedback: { asked: 2, submitted: 1, declined: 0, average: 4.0, items: [
        { id: 1, peer_id: 5, peer_name: 'Ann <b>Peer</b>', status: 'submitted', strengths: 'Calm', improvements: 'Louder', rating: 4 },
        { id: 2, peer_id: 6, peer_name: 'Bob', status: 'requested', strengths: '', improvements: '', rating: null } ] } };
const GRID = { cycle: { id: 1, name: 'H1', status: 'open' }, placed: 2, unplaced: 1, pending: 3, potential_words: { 1: 'Best where they are', 2: 'Could grow', 3: 'Could go a long way' },
    boxes: [3, 2, 1].flatMap(perf => [1, 2, 3].map(pot => ({ performance: perf, potential: pot,
        label: perf === 3 && pot === 3 ? 'Future leaders' : perf === 1 && pot === 1 ? 'At risk' : 'Box',
        people: perf === 3 && pot === 3 ? [{ employee_id: 3, name: "Lena O'Hara", rating: 5, potential: 3 }] : perf === 1 && pot === 1 ? [{ employee_id: 9, name: 'Zed', rating: 1, potential: 1 }] : [] }))) };
const DETAIL = { cycle: { id: 1, name: 'H1', status: 'open', questions: Q, department_name: '', counts: { total: 1, complete: 0 } },
    reviews: [{ id: 12, employee_id: 3, employee_name: 'Lena', reviewer_id: null, reviewer_name: 'HR', reviewer_how: 'hr', status: 'awaiting_manager', self_rating: 3, manager_rating: null, potential: 2 }],
    summary: { rated: 0, average: null, distribution: {} } };

function bootHr(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/reviews/12') return give(REVIEW);
        if (p === '/api/reviews/12/peers') return give({ asked: 1 });
        if (p === '/api/reviews/12/manager') return give({ id: 12, status: 'complete' });
        if (p === '/api/employees') return give([{ id: 3, full_name: 'Lena', status: 'active' }, { id: 5, full_name: 'Ann', status: 'active' }, { id: 7, full_name: 'Cy', status: 'active' }, { id: 8, full_name: 'Gone', status: 'terminated' }]);
        if (p === '/api/review-cycles/1') return give(DETAIL);
        if (p === '/api/talent-grid') return give(GRID);
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    return { w, doc: w.document, sent };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const { w, doc, sent } = bootHr();
        await w.readReview(12);
        await wait(40);
        const body = doc.getElementById('rr-body');
        check('HR sees what colleagues said, with names, as text', /Ann <b>Peer<\/b>/.test(body.textContent) && !body.querySelector('b') && /Calm/.test(body.textContent) && /Louder/.test(body.textContent));
        check('  and who has not answered', /Bob - not answered yet/.test(body.textContent));
        check('  with the count', /1 of 2 answered/.test(body.textContent) && /average 4/.test(body.textContent));
        check('  the HR half has a potential select', !!doc.getElementById('rr-potential'));
        await w.showPeerPicker();
        await wait(40);
        const boxes = [...doc.querySelectorAll('.rr-peer')];
        check('the picker lists colleagues but not the subject or leavers', boxes.map(b => b.value).join(',') === '5,7');
        check('  the one already asked is ticked and locked', boxes[0].checked && boxes[0].disabled);
        boxes[1].checked = true;
        await w.askPeers();
        await wait(40);
        const post = sent.find(s => s.url === '/api/reviews/12/peers');
        check('asking posts only the newly ticked ids', post && JSON.stringify(bodyOf(post).peer_ids) === '[7]', post && post.body);
        await w.readReview(12);
        await wait(40);
        doc.querySelector('.rr-rating[data-i="0"]').value = '5';
        doc.getElementById('rr-overall').value = '5';
        doc.getElementById('rr-potential').value = '3';
        doc.getElementById('rr-summary').value = 'Top';
        await w.hrWriteReview(false);
        await wait(40);
        const half = sent.find(s => s.url === '/api/reviews/12/manager');
        check('submitting the half carries potential', half && bodyOf(half).potential === 3, half && half.body);
    }
    {
        const { w, doc } = bootHr();
        await w.viewCycle(1);
        await wait(60);
        const detail = doc.getElementById('review-cycle-detail');
        check('the cycle table has a potential column', /Could grow/.test(detail.textContent));
        const grid = doc.getElementById('talent-grid');
        check('the talent grid draws nine boxes', grid && (grid.innerHTML.match(/min-height:96px/g) || []).length === 9);
        check('  with people in the right boxes', /Future leaders/.test(grid.textContent) && /Lena O'Hara/.test(grid.textContent) && /At risk/.test(grid.textContent) && /Zed/.test(grid.textContent));
        check('  and the unplaced counted beside it', /2 placed/.test(grid.textContent) && /1 rated with no view of potential/.test(grid.textContent) && /3 not yet reviewed/.test(grid.textContent));
    }

    // --- the portal ----------------------------------------------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const sent = [];
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.HTMLElement.prototype.scrollIntoView = function () { };
                w.fetch = (url, init) => {
                    const p = String(url).split('?')[0];
                    const method = (init && init.method) || 'GET';
                    sent.push({ url: p, method, body: init && init.body });
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/feedback-requests' && method === 'GET') return give({ open: 1, requests: [
                        { id: 4, status: 'requested', employee_id: 3, employee_name: 'Lena <i>x</i>', cycle_name: 'H1', due_on: '2026-07-15', cycle_open: true },
                        { id: 5, status: 'submitted', employee_id: 6, employee_name: 'Old', cycle_name: 'H1', due_on: '', cycle_open: true } ] });
                    if (p === '/api/employee/feedback-requests/4') return give({ status: 'submitted' });
                    if (p === '/api/employee/colleagues') return give({ colleagues: [{ id: 5, name: 'Ann', job_title: 'Dev' }, { id: 3, name: 'Lena', job_title: '' }] });
                    if (p === '/api/employee/reviews/13') return give({ id: 13, cycle_name: 'H1', cycle_status: 'open', questions: Q, employee_id: 3, employee_name: 'Lena', reviewer_name: 'Me', status: 'awaiting_manager', my_role: 'reviewer',
                        self: { answers: [{ rating: 4 }], rating: 4, comment: '' }, manager: { answers: [], rating: null, summary: '', potential: null }, goals: [],
                        peer_feedback: { asked: 1, submitted: 1, items: [{ peer_id: 5, peer_name: 'Ann', status: 'submitted', strengths: 'Kind', improvements: '', rating: 5 }] } });
                    if (p === '/api/employee/reviews/13/peers') return give({ asked: 1 });
                    if (p === '/api/employee/reviews/13/manager') return give({ id: 13, status: 'complete' });
                    if (p === '/api/employee/reviews/9') return give({ id: 9, cycle_name: 'H2', cycle_status: 'closed', questions: Q, employee_id: 1, employee_name: 'Me', reviewer_name: 'Bea', status: 'complete', my_role: 'subject',
                        self: { answers: [{ rating: 3 }], rating: 3, comment: '' }, manager: { answers: [{ rating: 4 }], rating: 4, summary: 'Good', potential: null }, goals: [],
                        peer_feedback: { asked: 2, submitted: 2, items: [{ strengths: 'Accurate', improvements: 'Slower', rating: 4 }, { strengths: 'Zeal', improvements: '', rating: null }] } });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadFeedbackRequests();
        await wait(30);
        const list = doc.getElementById('fb-list');
        check('the portal lists only the open requests, with the name as text', list.children.length === 1 && /Lena <i>x<\/i>/.test(list.textContent) && !list.querySelector('i'));
        list.querySelector('.fb-strengths').value = 'Calm';
        list.querySelector('.fb-rating').value = '4';
        list.querySelector('button').click();
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/feedback-requests/4');
        check('sending posts strengths, improvements and the rating', post && bodyOf(post).strengths === 'Calm' && bodyOf(post).rating === 4, post && post.body);

        await w.openReview(13);
        await wait(30);
        const d = doc.getElementById('rv-detail');
        check('as the reviewer I see the feedback with the name and get a potential select', /Ann/.test(d.textContent) && /Kind/.test(d.textContent) && !!doc.getElementById('rv-potential'));
        [...d.querySelectorAll('button')].find(b => b.textContent === 'Ask colleagues').click();
        await wait(40);
        const boxes = [...d.querySelectorAll('.rv-peer')];
        check('  the picker leaves out the person being reviewed and locks the one already asked', boxes.length === 1 && boxes[0].value === '5' && boxes[0].disabled);
        doc.querySelector('#rv-detail .rv-rating[data-i="0"]').value = '4';
        doc.getElementById('rv-overall').value = '4';
        doc.getElementById('rv-potential').value = '2';
        doc.getElementById('rv-words').value = 'Solid';
        await w.submitReview(false);
        await wait(30);
        const half = sent.find(s => s.url === '/api/employee/reviews/13/manager');
        check('  submitting my half carries potential', half && bodyOf(half).potential === 2, half && half.body);

        await w.openReview(9);
        await wait(30);
        const mine = doc.getElementById('rv-detail');
        check('as the person I read colleagues\' words with no names', /Accurate/.test(mine.textContent) && /Zeal/.test(mine.textContent) && /A colleague/.test(mine.textContent) && !/Ann/.test(mine.textContent));
        check('  and no potential is shown to me', !/Could grow|Best where|long way/.test(mine.textContent));
    }

    console.log(failures === 0 ? '\nAll peer-feedback checks passed.' : `\n${failures} peer-feedback check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
