/**
 * The calendar reads back what /api/hr/calendar sends and lets HR add what
 * has no home elsewhere.
 *
 * These check the grid actually reflects the data - a dot for each event on
 * the right day, in the colour that says what kind it is - and that only the
 * entries HR typed in directly can be edited from here. The rest are read
 * from wherever they actually live and link back to it.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

function boot(events) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.confirm = () => true;
    w.console.error = () => { };   // expected noise from the loaders this test does not stub

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
        if (p === '/api/auth/me') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'me@x' }, client_id: 1 }),
            });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }),
            });
        }
        if (p === '/api/hr/calendar') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ events: events || [] }),
            });
        }
        const body = p.endsWith('s') ? [] : {};
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };

    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

// A fixed "today" so the grid's shape does not depend on which day the suite
// happens to run.
function withFixedToday(w, iso) {
    const RealDate = w.Date;
    class FixedDate extends RealDate {
        constructor(...args) {
            if (args.length === 0) return new RealDate(iso);
            return new RealDate(...args);
        }
        static now() { return new RealDate(iso).getTime(); }
    }
    w.Date = FixedDate;
}

(async () => {
    // --- the markup is there, before app.js runs -----------------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const dom = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, ''));
        const doc = dom.window.document;
        check('the app ships a Calendar link', !!doc.getElementById('nav-calendar'));
        check('it points at #/calendar',
            doc.getElementById('nav-calendar').getAttribute('href') === '#/calendar');
        check('the calendar view exists', !!doc.getElementById('calendar-view'));
        check('and the add-entry modal', !!doc.getElementById('calendar-event-modal'));
    }

    // --- navigating there loads it -------------------------------------------
    {
        const { w, sent } = boot([
            { id: 'holiday-1', date: '2026-06-15', time: '', title: 'Founders Day',
              subtitle: 'Office closed', kind: 'holiday', source_type: 'holiday',
              source_id: 1, editable: false, view: '' },
        ]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);

        check('opening the view asks the calendar endpoint',
            sent.some(s => s.url === '/api/hr/calendar'));
        check('the month label is drawn',
            w.document.getElementById('calendar-month-label').textContent.trim().length > 0);

        const cells = [...w.document.querySelectorAll('.calendar-cell')];
        check('the grid draws six full weeks', cells.length === 42, cells.length);

        const holidayCell = cells.find(c => c.getAttribute('onclick').includes('2026-06-15'));
        check('the day with an event has a dot on it',
            !!holidayCell && holidayCell.querySelector('.calendar-dot'),
            holidayCell && holidayCell.outerHTML.slice(0, 120));
        check('the dot is the holiday colour',
            holidayCell.querySelector('.calendar-dot').getAttribute('style').includes('#f43f5e'));

        const emptyCell = cells.find(c => c.getAttribute('onclick').includes('2026-06-16'));
        check('a day with nothing on it has no dot',
            !!emptyCell && !emptyCell.querySelector('.calendar-dot'));
    }

    // --- clicking a day shows what is on it -----------------------------------
    {
        const { w } = boot([
            { id: 'goal-9', date: '2026-06-20', time: '', title: 'Ship the report',
              subtitle: 'Ada Reid - 40/100 %', kind: 'goal', source_type: 'goal',
              source_id: 9, editable: false, view: 'goals-view' },
        ]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);

        w.selectCalendarDay('2026-06-20');
        const list = w.document.getElementById('calendar-day-list');
        check('the day list names the event', /Ship the report/.test(list.textContent), list.textContent);
        check('and who it is for', /Ada Reid/.test(list.textContent), list.textContent);

        const heading = w.document.getElementById('calendar-day-heading');
        check('the heading names the date chosen', /20/.test(heading.textContent) && /June/.test(heading.textContent),
            heading.textContent);
    }

    // --- only HR's own entries can be edited from here -------------------------
    {
        const { w } = boot([
            { id: 'holiday-1', date: '2026-06-15', time: '', title: 'Founders Day',
              subtitle: '', kind: 'holiday', source_type: 'holiday', source_id: 1,
              editable: false, view: '' },
            { id: 'calendar_event-4', date: '2026-06-15', time: '14:00',
              title: 'Board meeting', subtitle: 'Quarterly review', kind: 'meeting',
              source_type: 'calendar_event', source_id: 4, editable: true, view: '' },
        ]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);
        w.selectCalendarDay('2026-06-15');

        const rows = [...w.document.getElementById('calendar-day-list').children];
        check('two entries on the same day both show', rows.length === 2, rows.length);

        const editableRow = rows.find(r => /Board meeting/.test(r.textContent));
        const holidayRow = rows.find(r => /Founders Day/.test(r.textContent));
        check('the entry HR added says it can be edited', /Edit/.test(editableRow.textContent));
        check('the holiday does not', !/Edit/.test(holidayRow.textContent));
        check('the holiday is not clickable into the edit modal',
            !editableRow.isSameNode(holidayRow) && holidayRow.getAttribute('onclick') === null,
            holidayRow.getAttribute('onclick'));
    }

    // --- adding an entry ------------------------------------------------------
    {
        const { w, sent } = boot([]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);

        w.selectCalendarDay('2026-06-18');
        w.openCalendarEventModal();
        check('the date field is pre-filled from the day selected',
            w.document.getElementById('cal-ev-date').value === '2026-06-18');
        check('a new entry has no delete button',
            w.document.getElementById('cal-ev-delete-btn').style.display === 'none');

        w.document.getElementById('cal-ev-title').value = 'Renew fire extinguisher contract';
        w.document.getElementById('cal-ev-kind').value = 'reminder';
        sent.length = 0;
        await w.saveCalendarEvent();

        const post = sent.find(s => s.url === '/api/hr/calendar-events' && s.method === 'POST');
        check('saving posts the new entry', !!post, JSON.stringify(sent.map(s => s.url)));
        const body = JSON.parse(post.body);
        check('with the title and date from the form',
            body.title === 'Renew fire extinguisher contract' && body.date === '2026-06-18',
            JSON.stringify(body));
    }

    // --- editing and deleting one of HR's own entries --------------------------
    {
        const { w, sent } = boot([]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);

        w.openCalendarEventModal({
            id: 'calendar_event-4', date: '2026-06-15', time: '14:00',
            title: 'Board meeting', subtitle: 'Quarterly review', kind: 'meeting',
            source_type: 'calendar_event', source_id: 4, editable: true, view: '',
        });
        check('editing shows the delete button',
            w.document.getElementById('cal-ev-delete-btn').style.display !== 'none');
        check('the form is filled from the entry',
            w.document.getElementById('cal-ev-title').value === 'Board meeting');

        sent.length = 0;
        await w.deleteCalendarEventFromModal();
        const del = sent.find(s => s.method === 'DELETE');
        check('deleting calls the right id', !!del && del.url === '/api/hr/calendar-events/4',
            del && del.url);
    }

    // --- a goal change refreshes an open calendar -------------------------------
    {
        const { w } = boot([]);
        withFixedToday(w, '2026-06-10T09:00:00');
        await wait(80);
        w.showView('calendar-view');
        await wait(80);
        check('calendar-view is registered to refresh when goals change',
            (w.HR_REFRESH_MAP.goals || []).includes('calendar-view'));
        check('and when leave changes',
            (w.HR_REFRESH_MAP.leave || []).includes('calendar-view'));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
