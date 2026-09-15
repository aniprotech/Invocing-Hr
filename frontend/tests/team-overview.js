/**
 * A manager's Team tab: a card per report with today's state and what is
 * owed them, a row of counts that jump to the right tab, and nothing at
 * all for somebody who manages nobody.
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

const OVERVIEW = { is_manager: true, summary: { reports: 2, in: 1, off: 1, not_in: 0 },
    waiting: [{ key: 'reviews', label: 'Reviews to write', count: 1, tab: 'reviews' }, { key: 'one_to_ones', label: 'Nobody met in 30 days', count: 2, tab: 'checkins' }],
    reports: [
        { employee_id: 1, name: "Ann <b>O'Neil</b>", job_title: 'Analyst', today: 'off', today_detail: 'annual until 2026-09-20', review_to_write: true, last_one_to_one: '', one_to_one_quiet: true, probation: { status: 'on_probation', end: '2026-09-25', due: true, overdue: false }, skills_to_confirm: 2, goals_overdue: 1 },
        { employee_id: 2, name: 'Bob', job_title: '', today: 'in', today_detail: 'since 09:02', review_to_write: false, last_one_to_one: '2026-09-10', one_to_one_quiet: false, probation: null, skills_to_confirm: 0, goals_overdue: 0 } ] };

function boot(overview) {
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/team-overview') return give(overview);
                return give(p.endsWith('s') ? [] : {});
            };
        } });
    return { w: dom.window, doc: dom.window.document };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the Team tab loads the overview', /tab === 'team'\)\s*\{\s*loadTeamPresence\(\);\s*loadTeamOverview\(\)/.test(src));
    }
    {
        const { w, doc } = boot(OVERVIEW);
        await w.loadTeamOverview();
        await wait(30);
        const card = doc.getElementById('myTeamCard');
        check('a manager gets the card with the summary', !card.hidden && /2 reports · 1 in, 1 off/.test(doc.getElementById('myTeamSummary').textContent));
        const waiting = doc.getElementById('myTeamWaiting');
        check('  the counts are buttons', waiting.querySelectorAll('button').length === 2 && /1 reviews to write/.test(waiting.textContent));
        const team = doc.getElementById('myTeam');
        check('  a card per report, names as text, with today\'s state', team.children.length === 2 && /Ann <b>O'Neil<\/b>/.test(team.textContent) && !team.querySelector('b') && /Off/.test(team.children[0].textContent) && /In/.test(team.children[1].textContent));
        check('  what is owed appears as chips', /Review to write/.test(team.children[0].textContent) && /No one-to-one yet/.test(team.children[0].textContent) && /Probation ends 2026-09-25/.test(team.children[0].textContent) && /2 skills to confirm/.test(team.children[0].textContent) && /1 goal overdue/.test(team.children[0].textContent));
        check('  and a report with nothing owed says so', /Nothing waiting/.test(team.children[1].textContent));
        let switched = null;
        w.switchTab = (t) => { switched = t; };
        waiting.querySelector('button').click();
        check('  a count jumps to its tab', switched === 'reviews');
    }
    {
        const { w, doc } = boot({ is_manager: false, reports: [], waiting: [], summary: {} });
        await w.loadTeamOverview();
        await wait(30);
        check('somebody who manages nobody sees no card', doc.getElementById('myTeamCard').hidden);
    }
    console.log(failures === 0 ? '\nAll team-overview checks passed.' : `\n${failures} team-overview check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
