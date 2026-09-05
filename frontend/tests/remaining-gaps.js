/**
 * The last four endpoints nothing in the browser called.
 *
 * Aged receivables was described in its own docstring as the report every
 * finance team asks for first, and the reports screen did not have it - so
 * the only way to see who was ninety days late was to sort the invoice list
 * and count. Sign-ins were recorded for every account and readable only by
 * the operator, so a business could not answer "was that me?" about its own.
 *
 * The two operator ones both answer a question that has no other answer.
 * Environment: did that variable actually take effect? Scheduled work: are
 * the recurring invoices and overdue chases going out at all - because a
 * scheduler that has stopped looks exactly like a quiet week.
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

const AGED = {
    currency: 'GBP',
    buckets: { current: 400, '1_30': 250, '31_60': 0, '61_90': 0, over_90: 1800 },
    total_outstanding: 2450,
    invoices: [
        { number: 'INV-0007', contact: 'Late Co', due_date: '2026-01-05',
          outstanding: 1800, days_overdue: 210, bucket: 'over_90', currency: 'GBP' },
        { number: 'INV-0031', contact: 'Slow Ltd', due_date: '2026-08-20',
          outstanding: 250, days_overdue: 12, bucket: '1_30', currency: 'GBP' },
        { number: 'INV-0044', contact: 'Fine Plc', due_date: '2026-10-01',
          outstanding: 400, days_overdue: 0, bucket: 'current', currency: 'GBP' },
    ],
    other_currencies: [],
};
const LOGINS = [
    { id: 2, email: 'a@b.com', login_type: 'password', ip_address: '10.0.0.9',
      device_info: '', status: 'success', created_at: '2026-09-04 10:00:00' },
    { id: 1, email: 'a@b.com', login_type: 'password', ip_address: '203.0.113.7',
      device_info: '', status: 'failed', created_at: '2026-09-03 22:14:00' },
];
const ENVIRONMENT = {
    ready: false, outstanding: ['GROQ_API_KEY'],
    checks: [
        { name: 'SECRET_KEY', ok: true, detail: 'Sessions survive a redeploy.', fix: '' },
        { name: 'GROQ_API_KEY', ok: false,
          detail: 'Not set, so every AI feature fails at the point of use.',
          fix: 'Set GROQ_API_KEY in the host environment.' },
    ],
};
const JOB_RUNS = [
    { id: 4, job: 'recurring_invoices', period: '2026-09-05', status: 'ok',
      detail: '2 raised', started_at: '2026-09-05 06:00:00', finished_at: '2026-09-05 06:00:04' },
    { id: 3, job: 'overdue_reminders', period: '2026-09-04', status: 'failed',
      detail: 'SMTP error', started_at: '2026-09-04 06:00:00', finished_at: '' },
];

// --- the business app ---------------------------------------------------------
function bootApp(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, query: String(url).split('?')[1] || '',
                    method: (init && init.method) || 'GET' });
        const give = b => Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(b) });
        if (p === '/api/auth/me') return give({ user: { email: 'a@b' }, client_id: 1 });
        if (p === '/api/client/me') return give({ id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/reports/aged-receivables') return give(opts.aged || AGED);
        if (p === '/api/my/login-history') return give(opts.logins || LOGINS);
        return give(p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

// --- the operator panel ---------------------------------------------------------
function bootOps(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const sent = [];
    const alerts = [];
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET' });
                const give = b => Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(b) });
                if (p === '/api/superadmin/me') return give({ username: 'op', email: 'op@x' });
                if (p === '/api/superadmin/environment') return give(opts.env || ENVIRONMENT);
                if (p === '/api/superadmin/job-runs') return give(opts.runs || JOB_RUNS);
                if (p === '/api/superadmin/run-jobs') {
                    return opts.runError
                        ? Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({ detail: opts.runError }) })
                        : give({ results: opts.results || { recurring_invoices: '1 raised' } });
                }
                return give(p.endsWith('s') ? [] : {});
            };
            w.alert = m => alerts.push(m);
            w.confirm = () => true;
        },
    });
    const w = dom.window;
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    return { w, sent, alerts };
}

const text = (w, id) => (w.document.getElementById(id) || {}).textContent || '';

(async () => {
    // --- aged receivables ------------------------------------------------------
    {
        const { w, sent } = bootApp();
        await wait(50);
        await w.loadAgedReceivables();
        await wait(40);
        const buckets = text(w, 'aged-buckets');
        const rows = text(w, 'aged-rows');

        check('the reports screen has aged receivables',
            !!w.document.getElementById('rpt-aged-btn'));
        check('and asks the endpoint that was never called',
            sent.some(s => s.url === '/api/reports/aged-receivables'));
        check('bucketed by how late it is',
            /1-30 days/.test(buckets) && /Over 90 days/.test(buckets),
            buckets.slice(0, 120));
        check('with a total', /2,450|2450/.test(buckets), buckets.slice(-80));
        check('every unpaid invoice listed', /INV-0007/.test(rows) && /Late Co/.test(rows));
        check('worst first, which is the order it is read in',
            rows.indexOf('INV-0007') < rows.indexOf('INV-0044'));
        check('saying how late each one is', /210 days/.test(rows), rows.slice(0, 160));
        check('and one that is not late is not called late',
            /Not due/.test(rows));

        // Colouring "not yet due" as a problem makes an account in perfectly
        // good order read as one in trouble.
        // The label div, then its own cell. Matching any div containing the
        // text also matches the grid that wraps every bucket, which carries
        // the overdue colours - so that would pass or fail for the wrong cell.
        const cellFor = label => {
            const tag = [...w.document.querySelectorAll('#aged-buckets div')]
                .find(d => d.textContent.trim() === label);
            return tag && tag.parentElement;
        };
        const notDue = cellFor('Not yet due');
        const late = cellFor('Over 90 days');
        check('money that is not yet due is not painted as overdue',
            notDue && !/danger/.test(notDue.innerHTML), notDue && notDue.innerHTML);
        check('while money that is overdue is',
            late && /danger/.test(late.innerHTML), late && late.innerHTML);

        // Only the panel it belongs to is on show.
        check('it takes over the reports area rather than stacking',
            w.document.getElementById('reports-aged-content').style.display === 'block' &&
            w.document.getElementById('reports-content').style.display === 'none');
    }

    {
        const { w } = bootApp({ aged: Object.assign({}, AGED,
            { invoices: [], buckets: {}, total_outstanding: 0 }) });
        await wait(50);
        await w.loadAgedReceivables();
        await wait(40);
        check('nothing outstanding says so',
            /Nothing is outstanding/.test(text(w, 'aged-rows')));
    }

    // --- sign-ins -----------------------------------------------------------------
    {
        const { w } = bootApp();
        await wait(50);
        await w.loadLoginHistory();
        await wait(40);
        const out = text(w, 'login-history');
        check('a business can see its own sign-ins', /2026-09-04/.test(out),
            out.slice(0, 120));
        check('with where from', /10\.0\.0\.9/.test(out));
        // A list of successes says nothing about somebody trying and failing.
        check('and a failed attempt, which is the one worth seeing',
            /failed/.test(out), out);
    }

    {
        const { w } = bootApp({ logins: [] });
        await wait(50);
        await w.loadLoginHistory();
        await wait(40);
        check('no history says so rather than showing an empty box',
            /Nothing recorded/.test(text(w, 'login-history')));
    }

    // --- environment ------------------------------------------------------------------
    {
        const { w } = bootOps();
        await w.loadEnvironment();
        const out = text(w, 'environment-body');
        check('the operator can see which variables are set',
            /SECRET_KEY/.test(out) && /GROQ_API_KEY/.test(out), out.slice(0, 120));
        check('with what each one being missing costs',
            /every AI feature fails/.test(out));
        check('and what to do about it, not only that it is wrong',
            /Set GROQ_API_KEY in the host environment/.test(out), out);

        // The whole reason this endpoint never returns values.
        const page = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
        const block = page.slice(page.indexOf('function renderEnvironment'),
                                 page.indexOf('async function loadJobRuns'));
        check('and the screen never asks for or prints a value',
            !/\.value\b/.test(block));
    }

    // --- scheduled work -----------------------------------------------------------------
    {
        const { w } = bootOps();
        await w.loadJobRuns();
        const out = text(w, 'jobruns-body');
        check('the operator can see the work that runs on its own',
            /recurring_invoices/.test(out), out.slice(0, 120));
        check('when it ran', /2026-09-05/.test(out));
        check('and one that failed, with the reason',
            /failed/.test(out) && /SMTP error/.test(out), out);
    }

    {
        // An empty list is the alarming case, not the calm one: it means the
        // scheduler is not running and neither are the invoices.
        const { w } = bootOps({ runs: [] });
        await w.loadJobRuns();
        const out = text(w, 'jobruns-body');
        check('nothing having run is called out rather than shown as empty',
            /scheduler is not running/.test(out), out.slice(0, 200));
    }

    {
        const { w, sent, alerts } = bootOps();
        await w.loadJobRuns();
        await w.runJobsNow();
        await wait(40);
        check('the work can be run now instead of waiting for the tick',
            sent.some(s => s.url === '/api/superadmin/run-jobs' && s.method === 'POST'));
        check('and says what it did', /1 raised/.test(alerts.join(' ')),
            alerts.join(' | '));
    }

    {
        const { w, alerts } = bootOps({ results: {} });
        await w.loadJobRuns();
        await w.runJobsNow();
        await wait(40);
        check('nothing due says so rather than looking like a failure',
            /Nothing was due/.test(alerts.join(' ')), alerts.join(' | '));
    }

    {
        const { w, alerts } = bootOps({ runError: 'Scheduler is disabled' });
        await w.loadJobRuns();
        await w.runJobsNow();
        await wait(40);
        check('a refusal is shown rather than swallowed',
            /Scheduler is disabled/.test(alerts.join(' ')), alerts.join(' | '));
    }

    // --- each loads where it belongs ------------------------------------------------------
    {
        const ops = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
        ['loadEnvironment', 'loadJobRuns'].forEach(fn => {
            check(`${fn} loads with the settings tab`,
                new RegExp('control:\\s*\\[[^\\]]*' + fn).test(ops));
        });
        const app = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const block = app.slice(app.indexOf('async function loadWallet()'),
                                app.indexOf('window.loadWallet'));
        check('loadLoginHistory loads with the wallet',
            block.includes('loadLoginHistory()'));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
