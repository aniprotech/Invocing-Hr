/**
 * Six things the staff portal could already answer and never showed anybody.
 *
 * Every endpoint here existed, worked, and was called by nothing in the
 * browser. A task assigned to somebody by name was visible to everyone except
 * them. The holidays the office closes for could not be looked up by the
 * people booking leave around them. The attendance rows were listed but never
 * added up, so the one question anyone has about their own attendance had no
 * answer on the page that shows it.
 *
 * And the heartbeat: the server closes a shift that has overrun, but only
 * when something asks. Nothing asked, so a forgotten clock-out stayed open
 * until the person next signed in - which is how a ten-hour day lands on the
 * record as a thirty-hour one.
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

const TASKS = [
    { id: 3, title: 'Return the old laptop', notes: 'Hand to IT', due_date: '2026-08-01',
      done: false, overdue: true },
    { id: 4, title: 'Read the security policy', notes: '', due_date: '2026-12-31',
      done: false, overdue: false },
    { id: 5, title: 'Sign your contract', notes: '', due_date: '', done: true,
      overdue: false },
];
const HOLIDAYS = [
    { date: '2026-01-01', name: "New Year's Day", optional: false, recurring: true,
      office_closed: true },
    { date: '2026-03-14', name: 'Founders Day', optional: true, recurring: false,
      office_closed: false },
];
const ASSETS = [
    { tag: 'LAP-014', name: 'MacBook Pro 14', category: 'Laptop',
      issued_at: '2026-02-01', condition_out: 'good' },
];
const ANALYTICS = {
    daily: [], total_hours: 141.5, days_present: 19, avg_hours: 7.4,
    late_days: 2, period_days: 30,
};

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
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const query = String(url).split('?')[1] || '';
                sent.push({ url: p, query, method: (init && init.method) || 'GET',
                            body: init && init.body });
                const give = b => Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(b) });
                if (p === '/api/employee/tasks') return give(opts.tasks || TASKS);
                if (p === '/api/employee/holidays') return give(opts.holidays || HOLIDAYS);
                if (p === '/api/employee/assets') return give(opts.assets || ASSETS);
                if (p === '/api/employee/analytics') return give(ANALYTICS);
                if (p === '/api/employee/heartbeat') return give({ status: 'ok' });
                if (/\/done$/.test(p)) {
                    return opts.doneError
                        ? Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({}) })
                        : give({ ok: true });
                }
                return give(p.endsWith('s') ? [] : {});
            };
            w.alert = m => alerts.push(m);
            w.confirm = () => true;
        },
    });
    const w = dom.window;
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    return { w, sent, alerts };
}

const text = (w, id) => (w.document.getElementById(id) || {}).textContent || '';
const called = (sent, p) => sent.filter(s => s.url === p);

(async () => {
    // --- the tasks addressed to this person -------------------------------------
    {
        const { w } = boot();
        await w.loadMyTasks();
        await wait(40);
        const out = text(w, 'myTasks');
        check('the portal shows tasks assigned to this person',
            /Return the old laptop/.test(out), out.slice(0, 100));
        check('with the notes that came with them', /Hand to IT/.test(out));
        check('and says which one is late rather than leaving it to be worked out',
            /Overdue/.test(out), out.slice(0, 160));
        // Asked of that task's own row. Across the whole list the word
        // "Overdue" is present either way, so a blob match proves nothing.
        const rows = [...w.document.querySelectorAll('#myTasks label')];
        const onTime = rows.find(r => /security policy/.test(r.textContent));
        check('a task that is not late is not called late',
            onTime && !/Overdue/.test(onTime.textContent),
            onTime && onTime.textContent);
        const late = rows.find(r => /old laptop/.test(r.textContent));
        check('and the late one is marked on its own row',
            late && /Overdue/.test(late.textContent));
    }

    {
        const { w, sent } = boot();
        await w.loadMyTasks();
        await wait(40);
        const box = w.document.querySelector('#myTasks input[type="checkbox"]');
        check('each task can be ticked off', !!box);
        box.checked = true;
        box.onchange();
        await wait(40);
        const done = called(sent, '/api/employee/tasks/3/done');
        check('ticking one records it against that task', done.length === 1,
            sent.map(s => s.url).join(', '));
        check('and says it is done rather than guessing',
            done.length && JSON.parse(done[0].body).done === true, done[0] && done[0].body);
    }

    {
        // A tick that silently did not save is worse than one that refuses:
        // the box stays ticked and the task stays open.
        const { w, alerts } = boot({ doneError: true });
        await w.loadMyTasks();
        await wait(40);
        const box = w.document.querySelector('#myTasks input[type="checkbox"]');
        box.checked = true;
        box.onchange();
        await wait(60);
        check('a tick that did not save says so', alerts.length === 1,
            alerts.join(' | '));
    }

    {
        const { w } = boot({ tasks: [] });
        await w.loadMyTasks();
        await wait(40);
        check('nothing outstanding says so plainly',
            /Nothing outstanding/.test(text(w, 'myTasks')));
    }

    // --- what the attendance rows add up to ------------------------------------------
    {
        const { w, sent } = boot();
        await w.loadAttendanceStats();
        await wait(40);
        const out = text(w, 'attendanceStats');
        check('the attendance screen adds the hours up', /141\.5/.test(out), out);
        check('and counts the days present', /19/.test(out));
        check('and the average day', /7\.4h/.test(out));
        check('and late arrivals, which is the one people check',
            /Late arrivals/.test(out));
        check('over a period it names rather than an unstated one',
            /last 30 days/.test(out), out);
        check('asked of the endpoint that was never called',
            called(sent, '/api/employee/analytics').length === 1);
    }

    // --- when the office is closed -------------------------------------------------------
    {
        const { w, sent } = boot();
        await w.loadHolidays();
        await wait(40);
        const out = text(w, 'holidayList');
        check('the holidays are listed', /New Year/.test(out), out.slice(0, 120));
        check('marked as the office being closed', /Office closed/.test(out));
        // An optional day is one you may work, so it still costs leave to take.
        check('and an optional day is not passed off as a closure',
            /Optional/.test(out), out);
        check('for a year that can be chosen',
            /year=/.test((called(sent, '/api/employee/holidays')[0] || {}).query || ''),
            (called(sent, '/api/employee/holidays')[0] || {}).query);

        const pick = w.document.getElementById('holidayYear');
        check('with the year picker filled in', pick && pick.options.length >= 2,
            pick && pick.options.length);
    }

    {
        const { w } = boot({ holidays: [] });
        await w.loadHolidays();
        await wait(40);
        check('a year with none listed says so',
            /No holidays listed/.test(text(w, 'holidayList')));
    }

    // --- what you are holding -------------------------------------------------------------
    {
        const { w } = boot();
        await w.loadMyAssets();
        await wait(40);
        const out = text(w, 'myAssets');
        check('the equipment assigned to somebody is on their own record',
            /MacBook Pro 14/.test(out), out.slice(0, 120));
        check('with the tag written on the thing itself', /LAP-014/.test(out));
        check('and when they got it', /2026-02-01/.test(out));
    }

    {
        const { w } = boot({ assets: [] });
        await w.loadMyAssets();
        await wait(40);
        check('nothing assigned says so',
            /Nothing is assigned/.test(text(w, 'myAssets')));
    }

    // --- the shift nobody closed ------------------------------------------------------------
    {
        const { sent } = boot();
        await wait(120);
        check('the portal tells the server it is still open',
            called(sent, '/api/employee/heartbeat').length >= 1,
            sent.map(s => s.url).join(', '));
        check('by posting, since it can change the record',
            (called(sent, '/api/employee/heartbeat')[0] || {}).method === 'POST');
    }

    // --- each one loads where somebody would look --------------------------------------------
    {
        const page = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        [['overview', 'loadMyTasks'], ['attendance', 'loadAttendanceStats'],
         ['calendar', 'loadHolidays'], ['profile', 'loadMyAssets']].forEach(pair => {
            const line = new RegExp("tab === '" + pair[0] + "'[^\\n]*" + pair[1]);
            check(`${pair[1]} runs when the ${pair[0]} tab is opened`, line.test(page));
        });
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
