/**
 * Server features that had no screen: a person updating progress on their
 * goal, a manager confirming a report's skills, and HR seeing which
 * reporting lines have gone quiet on one-to-ones.
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

function portal(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [], toasts = [];
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = (m, t) => toasts.push([m, t]); w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true);
            w.uiPrompt = (m, v) => { w._asked = [m, v]; return Promise.resolve(opts.answer === undefined ? null : opts.answer); };
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body ? JSON.parse(init.body) : null });
                const give = (b, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/goals') return give([
                    { id: 4, title: 'Close <b>deals</b>', description: '', target_value: 10, current_value: 4, unit: 'deals', priority: 'high', due_date: '', status: 'in_progress' },
                    { id: 5, title: 'Done one', description: '', target_value: 1, current_value: 1, unit: '%', priority: 'low', due_date: '', status: 'completed' }]);
                if (/\/api\/employee\/goals\/\d+\/update$/.test(p)) return opts.refuse ? give({ detail: 'Progress is a number' }, 400) : give({ status: 'completed', current_value: 10 });
                if (p === '/api/employee/team-skills') return give({ reports: [{ employee_id: 7, name: 'Ann <i>Lee</i>', skills: [
                    { skill_id: 1, name: 'Excel', level_word: 'Strong', verified: false, verified_by: '' },
                    { skill_id: 2, name: 'SQL', level_word: 'Some', verified: true, verified_by: 'Boss' }] }], levels: {} });
                if (/\/verify$/.test(p)) return give({ verified: true });
                return give(p.endsWith('s') ? [] : {});
            };
        } });
    return { w: dom.window, doc: dom.window.document, sent, toasts };
}

(async () => {
    // --- my goals ----------------------------------------------------------------------------
    {
        const { w, doc, sent, toasts } = portal({ answer: '10' });
        await w.loadGoals();
        const btns = doc.querySelectorAll('#goalsGrid [data-goal-update]');
        check('a goal still open offers Update progress, a completed one does not', btns.length === 1 && btns[0].getAttribute('data-goal-update') === '4');
        check('  the title stays text', !doc.querySelector('#goalsGrid b'));
        btns[0].dispatchEvent(new w.Event('click'));
        await wait(20);
        check('  it asks where it is now, starting from where it was', /out of 10 deals/.test(w._asked[0]) && w._asked[1] === '4');
        const post = sent.find(s => s.method === 'POST' && /goals/.test(s.url));
        check('  and saves the number', post && post.url === '/api/employee/goals/4/update' && post.body.current_value === 10, JSON.stringify(post));
        check('  reaching the target says so', toasts.some(t => /Goal reached/.test(t[0])));
    }
    {
        const { w, doc, sent, toasts } = portal({ answer: 'lots' });
        await w.loadGoals();
        await w.updateGoalProgress({ id: 4, title: 'x', target_value: 10, current_value: 4, unit: '' });
        check('a word is refused before it is sent', !sent.some(s => s.method === 'POST' && /goals/.test(s.url)) && toasts.some(t => /number from zero up/.test(t[0])));
    }
    {
        const { w, sent } = portal({ answer: null });
        await w.updateGoalProgress({ id: 4, title: 'x', target_value: 10, current_value: 4, unit: '' });
        check('cancelling sends nothing', !sent.some(s => s.method === 'POST' && /goals/.test(s.url)));
    }
    {
        const { w, toasts } = portal({ answer: '3', refuse: true });
        await w.updateGoalProgress({ id: 4, title: 'x', target_value: 10, current_value: 4, unit: '' });
        check('a refusal is said', toasts.some(t => /Progress is a number/.test(t[0])));
    }

    // --- a manager confirms a report's skills ------------------------------------------------
    {
        const { w, doc, sent } = portal();
        w.loadTeamOverview = () => { w._reloaded = true; };
        await w.openTeamSkills(7, 'Ann Lee');
        const o = doc.getElementById('teamSkillsOverlay');
        const t = o ? o.textContent : '';
        check('their skills open, names as text', !!o && !o.hidden && /Ann <i>Lee<\/i> - skills/.test(t) && !o.querySelector('i'));
        check('  a confirmed skill says by whom; one not yet confirmed can be', /Confirmed by Boss/.test(t) && o.querySelectorAll('button').length === 2);
        const confirm = Array.from(o.querySelectorAll('button')).find(b => b.textContent === 'Confirm');
        confirm.dispatchEvent(new w.Event('click'));
        await wait(20);
        check('  Confirm confirms it', sent.some(s => s.method === 'POST' && s.url === '/api/employee/team/7/skills/1/verify') && !Array.from(o.querySelectorAll('button')).some(b => b.textContent === 'Confirm') && w._reloaded);
        Array.from(o.querySelectorAll('button')).find(b => b.textContent === 'Close').dispatchEvent(new w.Event('click'));
        check('  Close shuts it', o.hidden === true);
    }
    {
        const { w, toasts } = portal();
        await w.openTeamSkills(99, 'Stranger');
        check('somebody who is not your report is not opened', toasts.some(t => /Not one of your reports/.test(t[0])) && !w.document.getElementById('teamSkillsOverlay'));
    }
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the team card\'s "skills to confirm" opens their skills', /f\[1\] === 'skills'\) openTeamSkills\(r\.employee_id, r\.name\)/.test(src));
    }

    // --- one-to-one coverage, for HR ------------------------------------------------------------
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
        const w = dom.window, doc = w.document;
        w.console.error = () => { };
        let cov = { pairs: 3, recent: 1, quiet: 2, window_days: 30, rows: [
            { manager_id: 1, employee_id: 7, manager_name: 'Bea', employee_name: 'Ann <b>Lee</b>', last_held: '', recent: false },
            { manager_id: 1, employee_id: 8, manager_name: 'Bea', employee_name: 'Cy', last_held: '2026-08-01', recent: false },
            { manager_id: 1, employee_id: 9, manager_name: 'Bea', employee_name: 'Di', last_held: '2026-10-10', recent: true }] };
        w.fetch = (url) => {
            const p = String(url).split('?')[0];
            const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
            if (p === '/api/check-ins/coverage') return give(cov);
            return give(p.endsWith('s') ? [] : {});
        };
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        await w.loadCheckInCoverage();
        const host = doc.getElementById('checkin-coverage');
        const t = host.textContent.replace(/\s+/g, ' ');
        check('Reviews shows how many reporting lines met lately', host.style.display === '' && /1 of 3 reporting lines met in the last 30 days/.test(t), t);
        check('  and names the quiet ones, never or when last', /Ann <b>Lee<\/b> with Bea/.test(t) && /never/.test(t) && /Cy with Bea/.test(t) && /last 2026-08-01/.test(t) && !/Di with/.test(t));
        check('  names as text', !host.querySelector('b'));
        let opened = null;
        w.openEmployee = id => { opened = id; };
        host.querySelector('[data-cov-emp="7"]').dispatchEvent(new w.Event('click', { cancelable: true }));
        check('  a name opens the person', opened === 7);
        cov = { pairs: 0, recent: 0, quiet: 0, window_days: 30, rows: [] };
        await w.loadCheckInCoverage();
        check('with no reporting lines it stays out of the way', host.style.display === 'none');
        const js = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        check('opening Reviews loads it', /if \(viewId === 'reviews-view'\) \{ loadReviewsView\(\); loadCheckInCoverage\(\); \}/.test(js));
    }

    // --- one business on both sides ------------------------------------------------------------
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
        const w = dom.window, doc = w.document;
        w.console.error = () => { };
        const sent = [];
        w.fetch = (url, init) => {
            const p = String(url).split('?')[0];
            const method = (init && init.method) || 'GET';
            sent.push({ url: p, method, body: init && init.body ? JSON.parse(init.body) : null });
            const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
            if (p === '/api/suppliers/3') return give({ id: 3, name: 'Harbour Trading', contact_id: 8, on_hold: false });
            if (p === '/api/contacts') return give([{ id: 8, name: 'Harbour <b>Ltd</b>' }, { id: 9, name: 'Other' }]);
            if (p === '/api/ledger/purchases/3') return give({ supplier: { id: 3, name: 'Harbour Trading' }, start: '2026-01-01', end: '2026-10-20', base: 'GBP', ledgers: [], ageing: [],
                open_bills: [], credits: [], balance: { GBP: 200 }, also_customer: { contact_id: 8, name: 'Harbour <i>Ltd</i>', how: 'linked',
                position: [{ currency: 'GBP', they_owe_us: 500, we_owe_them: 200, net: 300 }] } });
            return give(p.endsWith('s') ? [] : {});
        };
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        w.showToast = () => { };
        await w.openSupplierModal(3);
        const pick = doc.getElementById('supplier-contact');
        check('the supplier form offers your customers to link, the linked one chosen', pick.options.length === 3 && pick.value === '8' && !pick.querySelector('b'));
        pick.value = '';
        await w.saveSupplier();
        const put = sent.find(x => x.method === 'PUT');
        check('  clearing it sends no link', put && put.body.contact_id === null);
        await w.openPurchaseAccount(3);
        const t = doc.getElementById('ledger-detail-body').textContent.replace(/\s+/g, ' ');
        check('a supplier who is also a customer shows both balances and the net', /Also a customer/.test(t) && /they owe you £500\.00, you owe them £200\.00 - net, they owe you £300\.00/.test(t), t.slice(0, 300));
        check('  the name as text', /Harbour <i>Ltd<\/i>/.test(t) && !doc.querySelector('#ledger-detail-body i'));
        let to = null;
        w.openSalesAccount = id => { to = id; };
        w.showView = () => { };
        doc.getElementById('ledger-other-side').dispatchEvent(new w.Event('click', { cancelable: true }));
        check('  and opens their customer account', to === 8);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
