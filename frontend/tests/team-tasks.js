/**
 * What a manager owes about other people.
 *
 * A workflow step owned by "manager" produced a task, correctly, and then no
 * query in the application returned it. This portal asked for tasks owned by
 * "employee"; HR's list showed everything without saying whose it was; and
 * there was no manager-facing list anywhere. So a joiner checklist aimed at
 * somebody's manager was, in practice, a note in HR's pile.
 *
 * Nothing looked broken. The task existed and the count was right. It was
 * addressed to a role that no screen resolved into a person.
 *
 * Two things this page has to get right. The list is about other people, so
 * each row has to say who - "collect the laptop" about which of four leavers
 * is not an instruction. And most people are not managers, so an empty card
 * has to be absent rather than empty.
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

const TEAM = [
    { id: 11, title: 'Book a first-week catch-up', notes: '', due_date: '2026-01-05',
      done: false, about_id: 2, about: 'Sam New', workflow: 'New starter',
      why: 'their manager', overdue: true },
    { id: 12, title: 'Collect the laptop', notes: 'Hand to IT', due_date: '2026-12-31',
      done: false, about_id: 3, about: 'Lee Gone', workflow: 'Leaver',
      why: 'their manager', overdue: false },
];

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const alerts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET',
                            body: init && init.body });
                const give = b => Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(b) });
                if (p === '/api/employee/team-tasks') {
                    if (opts.teamFails) {
                        return Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({}) });
                    }
                    return give(opts.team === undefined ? TEAM : opts.team);
                }
                if (/team-tasks\/\d+\/done$/.test(p)) {
                    return opts.doneError
                        ? Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({}) })
                        : give({ ok: true });
                }
                if (p === '/api/employee/tasks') return give([]);
                return give(p.endsWith('s') ? [] : {});
            };
            w.alert = m => alerts.push(m);
        },
    });
    return { w: dom.window, doc: dom.window.document, sent, alerts };
}

(async () => {
    // --- a manager with things to do ------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadTeamTasks();
        await wait(30);

        const card = doc.getElementById('teamTasksCard');
        check('the portal asks for the manager list at all',
            sent.some(s => s.url === '/api/employee/team-tasks'),
            'the endpoint would stay unreachable');
        check('and shows the card when there is something in it', card.hidden === false);

        const rows = [...doc.querySelectorAll('#teamTasks label')];
        check('every task is listed', rows.length === 2, rows.length);

        // The whole difference between this list and the personal one.
        check('each row says who it is about',
            /Sam New/.test(rows[0].textContent) && /Lee Gone/.test(rows[1].textContent),
            rows.map(r => r.textContent).join(' | '));
        check('  and which workflow asked for it',
            /New starter/.test(rows[0].textContent));
        check('a late one is called out rather than left to be worked out',
            /Overdue/.test(rows[0].textContent), rows[0].textContent);
        check('  and is marked on the row itself',
            /border-rose/.test(rows[0].className), rows[0].className);
        check('one that is not late is not',
            !/Overdue/.test(rows[1].textContent));
    }

    // --- most people are not managers -------------------------------------------
    {
        const { w, doc } = boot({ team: [] });
        await w.loadTeamTasks();
        await wait(30);
        // An empty card that says nothing is worse than no card: it implies a
        // responsibility that is not theirs.
        check('somebody with no team sees no card at all',
            doc.getElementById('teamTasksCard').hidden === true);
    }

    // --- ticking one off ----------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadTeamTasks();
        await wait(30);
        doc.querySelector('#teamTasks input[type=checkbox]').click();
        await wait(30);

        const call = sent.find(s => /team-tasks\/\d+\/done$/.test(s.url));
        check('ticking a row sends it to the team endpoint', !!call,
            sent.map(s => s.url).join(', '));
        // Not the personal one. That endpoint refuses anything not about the
        // person signed in, so this would 404 on every task in the list.
        check('  and not to the personal one',
            !!call && !/\/api\/employee\/tasks\//.test(call.url), call && call.url);
        check('  for the task that was clicked',
            !!call && call.url.indexOf('/11/') !== -1, call && call.url);
        check('  saying it is done',
            !!call && /"done":true/.test(String(call.body)), call && call.body);
    }

    {
        const { w, doc, alerts } = boot({ doneError: true });
        await w.loadTeamTasks();
        await wait(30);
        doc.querySelector('#teamTasks input[type=checkbox]').click();
        await wait(30);
        // A tick that silently did not save is worse than an error: the
        // manager believes the thing is handled.
        check('a save that fails says so', alerts.length === 1, alerts.join(' | '));
    }

    // --- when the request fails ----------------------------------------------------
    {
        const { w, doc } = boot({ teamFails: true });
        await w.loadTeamTasks();
        await wait(30);
        check('a failed load hides the card rather than showing a broken one',
            doc.getElementById('teamTasksCard').hidden === true);
    }

    // --- and it is actually wired into the page ------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the overview tab loads it', /overview'\)\s*\{[^}]*loadTeamTasks\(\)/.test(src)
            || /loadTeamTasks\(\);/.test(src));
        check('the card is in the markup', /id="teamTasksCard"/.test(src));
    }

    console.log(failures === 0
        ? '\nAll team-task checks passed.'
        : `\n${failures} team-task check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
