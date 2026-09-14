/**
 * One-to-ones, on the person's side.
 *
 * Book one with your manager or with a report; add talking points; write
 * up the notes; tick the actions that carried over from last time. The
 * manager's private note is a box only the manager gets - the report's
 * page has no element for it, so there is nothing to hide. Nothing here is
 * innerHTML, so a name is text however it is spelled.
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

const LISTS = {
    with_my_manager: [{ id: 1, manager_id: 2, employee_id: 1, manager_name: 'Bea <b>Boss</b>', employee_name: 'Me', scheduled_for: '2026-09-20',
        status: 'planned', talking_points: [{ text: 'Pay', by: 1, done: false }], actions: [], notes: '' }],
    with_my_reports: [{ id: 3, manager_id: 1, employee_id: 4, manager_name: 'Me', employee_name: "Mo O'Salah", scheduled_for: '2026-09-01',
        status: 'done', talking_points: [], actions: [{ text: 'Laptop', owner: 4, done: false }], notes: 'Went well' }],
    open_actions_on_me: 2, manager: { id: 2, name: 'Bea Boss' }, reports: [{ id: 4, name: "Mo O'Salah" }],
};
const AS_REPORT = { id: 1, manager_id: 2, employee_id: 1, manager_name: 'Bea Boss', employee_name: 'Me', scheduled_for: '2026-09-20', status: 'planned',
    talking_points: [{ text: 'Pay', by: 1, done: false }], actions: [], notes: '', my_role: 'employee',
    carried_actions: [{ text: 'Send the draft', owner: 1, done: false, check_in_id: 0, index: 0, from_date: '2026-08-20' }] };
const AS_MANAGER = { id: 3, manager_id: 1, employee_id: 4, manager_name: 'Me', employee_name: "Mo O'Salah", scheduled_for: '2026-09-25', status: 'planned',
    talking_points: [], actions: [], notes: '', private_note: 'Watch the hours', my_role: 'manager', carried_actions: [] };
const HELD = Object.assign({}, AS_MANAGER, { id: 5, status: 'done', completed_at: '2026-09-02 10:00:00', notes: 'Went well <i>x</i>' });

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const toasts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
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
                const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/check-ins' && method === 'GET') return give(opts.lists || LISTS);
                if (p === '/api/employee/check-ins' && method === 'POST') {
                    if (opts.bookFails) return give({ detail: 'Not one of your reports' }, 404);
                    return give(Object.assign({}, AS_REPORT, { id: 9 }));
                }
                if (p === '/api/employee/check-ins/1') return give(AS_REPORT);
                if (p === '/api/employee/check-ins/3') return give(AS_MANAGER);
                if (p === '/api/employee/check-ins/5') return give(HELD);
                if (p === '/api/employee/check-ins/9') return give(Object.assign({}, AS_REPORT, { id: 9 }));
                if (/\/api\/employee\/check-ins\/\d+\/complete$/.test(p)) return give(Object.assign({}, AS_MANAGER, { status: 'done' }));
                if (/\/api\/employee\/check-ins\/\d+$/.test(p) && method === 'PUT') return give(AS_MANAGER);
                if (/\/api\/employee\/check-ins\/\d+$/.test(p) && method === 'DELETE') return give({ deleted: true });
                if (/\/actions\/\d+\/\d+\/done$/.test(p)) return give({ done: true, carried_actions: [] });
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
        check('there is a 1:1s tab', /data-tab="checkins"/.test(src) && /id="tab-checkins"/.test(src));
        check('  switching to it loads the lists', /tab === 'checkins'\)\s*loadCheckIns\(\)/.test(src));
    }
    {
        const { w, doc } = boot();
        await w.loadCheckIns();
        await wait(30);
        const up = doc.getElementById('ci-up'), down = doc.getElementById('ci-down');
        check('one-to-ones with my manager and with my reports are listed', up.children.length === 1 && down.children.length === 1);
        check('  names are text, not markup', !up.querySelector('b') && /Bea <b>Boss<\/b>/.test(up.textContent) && /Mo O'Salah/.test(down.textContent));
        check('  a held one says so and counts its open actions', /Held/.test(down.textContent) && /1 open action/.test(down.textContent));
        check('  the actions on me from earlier meetings are the first thing said', /2 actions on you/.test(doc.getElementById('ci-open-actions').textContent));
        const opts = [...doc.querySelectorAll('#ci-with option')].map(o => o.textContent);
        check('  I can book with my manager or any report', opts[0] === 'Bea Boss (your manager)' && opts[1] === "Mo O'Salah");
    }
    {
        const { w, doc } = boot({ lists: { with_my_manager: [], with_my_reports: [], open_actions_on_me: 0, manager: null, reports: [] } });
        await w.loadCheckIns();
        await wait(30);
        check('with nobody to meet the booking form is hidden and it says why',
            doc.getElementById('ci-book-form').classList.contains('hidden') && /Nobody to meet/.test(doc.getElementById('ci-open-actions').textContent));
        check('  and the reports card is hidden', doc.getElementById('ci-down-card').classList.contains('hidden'));
    }
    {
        const { w, doc, sent, toasts } = boot();
        await w.loadCheckIns();
        await wait(30);
        doc.getElementById('ci-date').value = '2026-10-01';
        doc.getElementById('ci-with').value = '4';
        await w.bookCheckIn();
        await wait(40);
        const post = sent.find(s => s.url === '/api/employee/check-ins' && s.method === 'POST');
        check('booking posts the date and the report', post && bodyOf(post).scheduled_for === '2026-10-01' && bodyOf(post).employee_id === 4, post && post.body);
        check('  says they have been told, and opens it', toasts.some(t => /they have been told/.test(t)) && !doc.getElementById('ci-detail').classList.contains('hidden'));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadCheckIns();
        await wait(30);
        doc.getElementById('ci-with').value = '';
        await w.bookCheckIn();
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/check-ins' && s.method === 'POST');
        check('booking with my manager sends no employee id', post && bodyOf(post).employee_id === null, post && post.body);
    }
    {
        const { w, doc, sent } = boot();
        await w.openCheckIn(1);
        await wait(30);
        const d = doc.getElementById('ci-detail');
        check('as the report I see the talking points and the carried actions', /Pay/.test(d.textContent) && /Still open from last time/.test(d.textContent) && /Send the draft/.test(d.textContent));
        check('  and no private note box', !doc.getElementById('ci-private'));
        const carried = [...d.querySelectorAll('input[type="checkbox"]')].find(b => b.closest('label').textContent.includes('Send the draft'));
        carried.checked = true;
        carried.dispatchEvent(new w.Event('change'));
        await wait(30);
        check('ticking a carried action ticks it where it was written', sent.some(s => s.url === '/api/employee/check-ins/1/actions/0/0/done' && s.method === 'POST'));
        const form = doc.querySelector('#ci-points form');
        form.querySelector('input').value = 'The laptop';
        form.dispatchEvent(new w.Event('submit'));
        doc.getElementById('ci-notes').value = 'We talked';
        await w.saveCheckIn(false);
        await wait(30);
        const put = sent.find(s => s.url === '/api/employee/check-ins/1' && s.method === 'PUT');
        const b = bodyOf(put);
        check('saving sends the talking points including the new one, and the notes',
            b.talking_points.length === 2 && b.talking_points[1].text === 'The laptop' && b.notes === 'We talked' && !('private_note' in b), put && put.body);
    }
    {
        const { w, doc, sent, toasts } = boot();
        await w.openCheckIn(3);
        await wait(30);
        check('as the manager I get the private note box with what I wrote', doc.getElementById('ci-private') && doc.getElementById('ci-private').value === 'Watch the hours');
        const form = doc.querySelector('#ci-actions form');
        form.querySelector('input').value = 'Order the laptop';
        form.querySelector('select').value = '4';
        form.dispatchEvent(new w.Event('submit'));
        doc.getElementById('ci-private').value = 'Still watching';
        await w.saveCheckIn(true);
        await wait(30);
        const post = sent.find(s => s.url === '/api/employee/check-ins/3/complete');
        const b = bodyOf(post);
        check('marking it held posts the actions with their owner and the private note',
            b.actions.length === 1 && b.actions[0].owner === 4 && b.private_note === 'Still watching', post && post.body);
        check('  and says they have been told', toasts.some(t => /Written up/.test(t)));
    }
    {
        const { w, doc } = boot();
        await w.openCheckIn(5);
        await wait(30);
        const d = doc.getElementById('ci-detail');
        check('a held one is read: notes locked, no Mark as held', doc.getElementById('ci-notes').readOnly && ![...d.querySelectorAll('button')].some(b => b.textContent === 'Mark as held'));
        check('  the notes are text', doc.getElementById('ci-notes').value === 'Went well <i>x</i>' && !d.querySelector('i'));
        check('  the manager can still save the private note', [...d.querySelectorAll('button')].some(b => b.textContent === 'Save private note'));
    }
    {
        const { w, doc, sent } = boot();
        await w.openCheckIn(1);
        await w.cancelCheckIn();
        await wait(30);
        check('cancelling asks and deletes', sent.some(s => s.url === '/api/employee/check-ins/1' && s.method === 'DELETE') && doc.getElementById('ci-detail').classList.contains('hidden'));
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.openCheckIn(1);
        await w.cancelCheckIn();
        check('backing out deletes nothing', !sent.some(s => s.method === 'DELETE'));
    }

    console.log(failures === 0 ? '\nAll one-to-one checks passed.' : `\n${failures} one-to-one check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
