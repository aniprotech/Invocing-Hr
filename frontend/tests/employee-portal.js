/**
 * The four things the employee portal could not do.
 *
 * A payslip could be seen as a figure but not taken away. Leave was requested
 * without knowing what was left. A phone number could only be corrected by
 * asking HR. And there was no assistant at all - every AI feature pointed at
 * the owner's side.
 *
 * The portal is one page with its script inline, so the script is pulled out
 * and run the way the browser runs it.
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

const PAYSLIP = {
    id: 7, number: 'PS-0007', period_start: '2026-07-01', period_end: '2026-07-31',
    pay_date: '2026-08-01', status: 'Paid', hours_worked: 160, overtime_hours: 4,
    basic_salary: 3000, overtime_pay: 120, bonus: 0, allowances: 50,
    gross_pay: 3170, tax_amount: 634, insurance: 90, retirement: 100,
    other_deductions: 0, total_deductions: 824, net_pay: 2346,
    employee: { name: 'Ada Reid', employee_id: 'E-1', job_title: 'Analyst',
                bank_account: '****5678' },
    company: { name: 'Acme Ltd', address: '1 High Street', email: 'hr@acme.test' },
    currency: 'GBP',
};

function boot(overrides) {
    const bodies = Object.assign({
        '/api/employee/auth/me': { id: 1, full_name: 'Ada Reid', first_name: 'Ada',
                                  job_title: 'Analyst' },
        '/api/employee/profile': {
            full_name: 'Ada Reid', first_name: 'Ada', last_name: 'Reid',
            email: 'ada@acme.test', phone: '07700 900123', address: '12 New Street',
            emergency_contact: 'Jo Reid', emergency_phone: '07700 900999',
            job_title: 'Analyst', department: 'Finance', bank_name: 'Barclays',
            bank_account_masked: '****5678', team: [], goals_count: 0,
        },
        '/api/employee/leave-balance': {
            annual_total: 25, annual_taken: 3, annual_pending: 2, annual_remaining: 20,
            sick_total: 10, sick_taken: 1, sick_remaining: 9,
        },
        '/api/employee/payslips': [{
            id: 7, number: 'PS-0007', period_start: '2026-07-01',
            period_end: '2026-07-31', pay_date: '2026-08-01', net_pay: 2346,
            gross_pay: 3170, status: 'Paid',
        }],
        '/api/employee/payslips/7': PAYSLIP,
        '/api/employee/profile-changes': [],
        // Stubbed far enough to keep the page's own error handling quiet, so a
        // real failure still stands out in the output.
        '/api/employee/weekly-chart': [],
        '/api/employee/dashboard': {
            attendance: [], payslips: [], onboarding: [], overtime: [],
            attendance_summary: {}, employee: {},
        },
        '/api/employee/assistant/suggestions': {
            suggestions: ['How much annual leave do I have left?'],
        },
        '/api/employee/assistant': { answer: 'You have 20 days left.', available: true },
        '/api/employee/calendar': {
            start: '2026-08-01', end: '2026-08-31',
            events: [
                { id: 'holiday-1', date: '2026-08-31', time: '', title: 'Summer Bank Holiday',
                  subtitle: 'Office closed', kind: 'holiday', kind_label: 'Holiday',
                  mine: false, tab: 'leave' },
                { id: 'leave-1', date: '2026-08-10', time: '', title: 'Your annual leave',
                  subtitle: '2026-08-10 to 2026-08-12', kind: 'leave', kind_label: 'Leave',
                  mine: true, tab: 'leave' },
                { id: 'leave-2', date: '2026-08-18', time: '', title: 'Sam Ali is away',
                  subtitle: '2026-08-18 to 2026-08-19', kind: 'leave', kind_label: 'Leave',
                  mine: false, tab: 'leave' },
            ],
        },
        '/api/employee/announcements': [
            { id: 1, title: 'Office closed Friday', message: 'Boiler repairs.',
              sent_by: 'hr@acme.test', is_read: false, created_at: '2026-08-20 09:00' },
        ],
    }, overrides || {});

    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/employee-dashboard.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.URL.createObjectURL = () => 'blob:stub';
    w.alert = () => { };
    // The first inline script is the Tailwind CDN config, which expects the
    // global the CDN script would have defined.
    w.tailwind = { config: {} };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
        const body = Object.prototype.hasOwnProperty.call(bodies, p)
            ? bodies[p] : (p.endsWith('s') ? [] : {});
        const status = (body && body.__status) || 200;
        return Promise.resolve({
            ok: status < 400, status,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));

    const scripts = [...w.document.querySelectorAll('script')]
        .filter(s => !s.src).map(s => s.textContent).join('\n');
    w.eval(scripts);
    return { w, sent };
}

(async () => {
    // --- leave: what is left, not what is spent -----------------------------
    {
        const { w } = boot();
        w.switchTab('leave');
        await wait(60);
        const text = w.document.getElementById('leaveRemaining').textContent;
        check('the leave tab leads with days remaining', /20/.test(text), text);
        check('and names what that is out of', /25/.test(text), text);
        check('a request still awaiting a decision is called out',
            /2 still awaiting/.test(text), text);
    }

    // --- payslips -----------------------------------------------------------
    {
        const { w } = boot();
        w.switchTab('payslips');
        await wait(60);
        const grid = w.document.getElementById('payslipGrid');
        check('payslips are listed', /PS-0007/.test(grid.textContent));
        check('with the net figure', /2346\.00/.test(grid.textContent), grid.textContent);
        check('and a way to take one away',
            /downloadPayslip\(7\)/.test(grid.innerHTML));
    }

    {
        // The document itself: built here, because there is no server-side
        // generator to ask.
        const { w } = boot();
        let saved = null;
        w.jspdf = {
            jsPDF: function () {
                const doc = new jsPDF({ unit: 'pt', format: 'a4' });
                doc.save = name => { saved = name; };
                return doc;
            },
        };
        await w.downloadPayslip(7);
        await wait(80);
        check('a payslip PDF is produced', saved !== null, String(saved));
        check('named after the payslip', /PS-0007/.test(saved || ''), String(saved));
    }

    {
        const { w } = boot({ '/api/employee/payslips': [] });
        w.switchTab('payslips');
        await wait(60);
        check('no payslips reads as empty, not broken',
            /no payslips/i.test(w.document.getElementById('payslipGrid').textContent));
    }

    // --- correcting your own record -----------------------------------------
    {
        const { w, sent } = boot();
        w.switchTab('profile');
        await wait(80);

        check('the form starts from what is on record',
            w.document.getElementById('me-phone').value === '07700 900123',
            w.document.getElementById('me-phone').value);
        check('the account number is never prefilled',
            w.document.getElementById('me-bank_account').value === '');
        check('but what is on file is shown masked',
            w.document.getElementById('me-bank_account').placeholder === '****5678');

        w.document.getElementById('me-phone').value = '07700 900555';
        await w.saveMyDetails();
        await wait(60);
        const put = sent.find(r => r.method === 'PUT');
        check('saving sends the changed details',
            !!put && JSON.parse(put.body).phone === '07700 900555');
    }

    {
        const { w } = boot({
            '/api/employee/profile-changes': [
                { id: 1, field: 'bank_account', status: 'pending', new_value: '9999',
                  note: '', created_at: '2026-08-20' },
                { id: 2, field: 'bank_name', status: 'rejected', new_value: 'X',
                  note: 'Send a statement first', created_at: '2026-08-19' },
            ],
        });
        w.switchTab('profile');
        await wait(80);
        const text = w.document.getElementById('myChanges').textContent;
        check('an outstanding ask says it is with HR', /waiting for HR/.test(text), text);
        check("and a refusal carries HR's reason",
            /Send a statement first/.test(text), text);
    }

    // --- the assistant ------------------------------------------------------
    {
        const { w, sent } = boot();
        w.switchTab('assistant');
        await wait(80);

        const log = w.document.getElementById('asstLog').textContent;
        check('the assistant says what it does and does not know',
            /only know about your own record/i.test(log), log);
        check('openers are offered',
            /annual leave/i.test(w.document.getElementById('asstSuggestions').textContent));

        w.document.getElementById('asstInput').value = 'How much leave do I have?';
        await w.askAssistant();
        await wait(80);

        const asked = sent.find(r => r.url === '/api/employee/assistant' && r.method === 'POST');
        check('the question is sent to the employee endpoint', !!asked);
        check('and never to the owner-side one',
            !sent.some(r => r.url === '/api/ai/assistant'));
        const after = w.document.getElementById('asstLog').textContent;
        check('the answer is shown', /20 days left/.test(after), after);
        check('and "Thinking..." does not linger', !/Thinking/.test(after));
    }

    {
        // The employer pays for this, so there is nothing the employee can do
        // but tell somebody who can.
        const { w } = boot({
            '/api/employee/assistant': { __status: 402, detail: 'Not enough credit' },
        });
        w.switchTab('assistant');
        await wait(60);
        w.document.getElementById('asstInput').value = 'How much leave?';
        await w.askAssistant();
        await wait(80);
        const text = w.document.getElementById('asstLog').textContent;
        check('running out of credit points at the person who can fix it',
            /ask hr/i.test(text) && /credit/i.test(text), text);
    }

    // --- the dial for the working day --------------------------------------
    // "3h 12m" is a fact with nothing to measure it against. HR sets the
    // production hours now, so the same figure can be shown as a proportion of
    // the day - which is the question somebody actually has: am I nearly done.
    {
        const { w } = boot();
        const SWEEP = 240;
        const C = 2 * Math.PI * 54;
        const drawn = () => parseFloat(w.document.getElementById('gaugeArc')
            .getAttribute('stroke-dasharray').split(' ')[0]);
        const swept = () => drawn() / (C * SWEEP / 360);
        const needleAngle = () => parseFloat(w.document.getElementById('gaugeNeedle')
            .getAttribute('transform').match(/-?[\d.]+/)[0]);
        const stateText = () => w.document.getElementById('gaugeState').textContent;

        w.applyShift({ target_hours: 7.5, worked_hours: 3, state: 'working' });

        check('the dial is drawn against the hours HR set, not a fixed eight',
            w.document.getElementById('gaugeTarget').textContent === 'of 7h 30m',
            w.document.getElementById('gaugeTarget').textContent);
        check('the arc covers the fraction of the day worked',
            Math.abs(swept() - 3 / 7.5) < 0.001, swept().toFixed(4));
        check('and the needle agrees with the arc',
            Math.abs(needleAngle() - (-120 + (3 / 7.5) * SWEEP)) < 0.1, needleAngle());
        check('the readout is the same figure in words',
            w.document.getElementById('elapsedTime').textContent === '3h 00m',
            w.document.getElementById('elapsedTime').textContent);
        check('the dial is marked in hours of that day',
            w.document.getElementById('gaugeTicks').children.length === 8,
            w.document.getElementById('gaugeTicks').children.length + ' marks for 7.5h');

        // A needle past the last mark reads as a fault, not as a long day.
        w.applyShift({ target_hours: 8, worked_hours: 12, state: 'complete' });
        check('a long day stops at the end of the dial',
            Math.abs(swept() - 1) < 0.001, swept().toFixed(4));
        check('and the needle stops with it',
            Math.abs(needleAngle() - 120) < 0.1, needleAngle());
        check('with the hours over said in words instead',
            /4h 00m over/.test(stateText()), stateText());

        // Read from the inline style, which is where the colour is now set.
        // Reading the attribute is what let a real bug through: the attribute
        // changed and the painted colour did not, because a CSS transition on
        // stroke swallows presentation-attribute changes - invisible here,
        // where nothing transitions, and plain in a browser.
        const colourFor = (state, worked) => {
            w.applyShift({ target_hours: 8, worked_hours: worked, state });
            return w.document.getElementById('gaugeArc').style.stroke;
        };
        const tones = [colourFor('not_started', 0), colourFor('working', 3),
                       colourFor('on_break', 3), colourFor('complete', 8)];
        check('each state of the day is a different colour',
            new Set(tones).size === 4, tones.join(' '));

        w.applyShift({ target_hours: 8, worked_hours: 0, state: 'not_started' });
        check('an unstarted day shows the target rather than an empty dial',
            w.document.getElementById('gaugeTarget').textContent === 'of 8h 00m' && drawn() === 0,
            w.document.getElementById('gaugeTarget').textContent);
        check('and says so', /not started/i.test(stateText()), stateText());

        // The server said "working" a moment ago. Passing the target while
        // still clocked in has to read as overtime without waiting for a poll.
        w.applyShift({ target_hours: 4, worked_hours: 3.9, state: 'working' });
        w.updateElapsed(4.5);
        check('passing the target mid-shift reads as overtime straight away',
            /over/i.test(stateText()), stateText());
    }

    // --- the target comes from the server, not from the page ----------------
    {
        const { w } = boot({
            '/api/employee/attendance/today': {
                clocked_in: true, clock_in: '09:00:00', clock_out: '',
                is_on_break: false, break_minutes: 0, elapsed_hours: 2,
                status: 'present', is_working_day: true,
                shift: {
                    target_hours: 6, worked_hours: 2, remaining_hours: 4,
                    overtime_hours: 0, fraction: 0.3333, percent: 33,
                    state: 'working', late_minutes: 0, left_early_minutes: 0,
                    expected_in: '09:00', expected_out: '15:00',
                },
            },
        });
        await wait(80);
        check('a six-hour day is a six-hour dial',
            w.document.getElementById('gaugeTarget').textContent === 'of 6h 00m',
            w.document.getElementById('gaugeTarget').textContent);
    }

    // --- the calendar --------------------------------------------------------
    {
        const { w, sent } = boot();
        w.switchTab('calendar');
        await wait(90);

        const asked = sent.find(r => r.url === '/api/employee/calendar');
        check('the calendar asks for a month', !!asked);
        check('and asks the employee endpoint, never HR’s',
            !sent.some(r => r.url === '/api/hr/calendar'));

        const grid = w.document.getElementById('calGrid');
        check('a grid of days is drawn', grid.querySelectorAll('button').length >= 28,
            String(grid.querySelectorAll('button').length));
        check('the month is named',
            /\w+ \d{4}/.test(w.document.getElementById('calTitle').textContent),
            w.document.getElementById('calTitle').textContent);

        const list = w.document.getElementById('calList').textContent;
        check('a company holiday is on it', /Summer Bank Holiday/.test(list));
        check('their own leave is on it', /Your annual leave/.test(list));
        check('a colleague shows as away, with no leave type',
            /Sam Ali is away/.test(list) && !/Sam Ali.*sick/i.test(list), list.slice(0, 120));

        // Clicking a day narrows the list to that day.
        w.showCalendarDay('2026-08-10');
        const narrowed = w.document.getElementById('calList').textContent;
        check('clicking a day shows only that day',
            /Your annual leave/.test(narrowed) && !/Summer Bank Holiday/.test(narrowed),
            narrowed.slice(0, 120));
    }

    {
        const { w } = boot({
            '/api/employee/calendar': { start: '', end: '', events: [] },
        });
        w.switchTab('calendar');
        await wait(90);
        check('an empty month reads as empty, not broken',
            /nothing on/i.test(w.document.getElementById('calList').textContent),
            w.document.getElementById('calList').textContent);
        check('and the grid is still drawn',
            w.document.getElementById('calGrid').querySelectorAll('button').length >= 28);
    }

    {
        // A month that will not load must not leave a blank page behind.
        const { w } = boot({ '/api/employee/calendar': { __status: 500 } });
        w.switchTab('calendar');
        await wait(90);
        check('a failed month still draws the grid',
            w.document.getElementById('calGrid').querySelectorAll('button').length >= 28);
    }

    // --- notices -------------------------------------------------------------
    {
        const { w } = boot();
        w.switchTab('notices');
        await wait(80);
        const text = w.document.getElementById('noticeList').textContent;
        check('an announcement can be read again', /Office closed Friday/.test(text), text);
        check('with what it actually said', /Boiler repairs/.test(text));
        check('and who sent it', /hr@acme\.test/.test(text));
    }

    {
        const { w } = boot({ '/api/employee/announcements': [] });
        w.switchTab('notices');
        await wait(80);
        check('nothing sent yet reads as empty',
            /nothing has been sent/i.test(w.document.getElementById('noticeList').textContent));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
