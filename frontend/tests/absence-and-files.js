/**
 * Absence and people-as-a-file, on screen.
 *
 * The analytics page lists the Bradford scores with their band and draws
 * the weekday pattern; the employees page exports a CSV and imports one
 * after a dry run that names the problems; a profile links to the
 * person's whole record; the portal links to the person's own.
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

const ABSENCE = { people: [{ employee_id: 7, name: "Often O'Neil", spells: 4, days: 4, bradford: 64, band: 'Watch', last_spell: '2026-09-01' }],
    totals: { sick_days: 4, spells: 4, people_off_sick: 1, people: 3, absence_rate_pct: 0.51, concern_or_worse: 0 },
    spells_by_weekday: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => ({ day: d, spells: i === 0 ? 3 : 0 })), bands: [] };
const DRY = { dry_run: true, summary: { rows: 3, create: 1, update: 1, skip: 1 }, rows: [
    { row: 2, email: 'a@x', name: 'A', action: 'create', problems: [], new_department: true },
    { row: 3, email: 'b@x', name: 'B', action: 'update', problems: [], new_department: false },
    { row: 4, email: '', name: 'C', action: 'skip', problems: ['no email'], new_department: false } ] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], confirms = [], alerts = [], charts = [];
    w.console.error = () => { };
    w.Chart = function (el, config) { charts.push({ id: el.id, config }); this.destroy = () => { }; };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, q: String(url).split('?')[1] || '', method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/absence') return give(ABSENCE);
        if (p === '/api/people/import') return give(/dry_run=1/.test(String(url)) ? DRY : { dry_run: false, summary: DRY.summary, rows: DRY.rows });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = (m) => { confirms.push(String(m)); return Promise.resolve(opts.confirm !== false); };
    w.uiAlert = (m) => { alerts.push(String(m)); return Promise.resolve(true); };
    w.fetchEmployees = () => { };
    w.loadHRStats = () => { };
    return { w, doc: w.document, sent, confirms, alerts, charts };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the employees page has Export CSV and Import CSV', /href="\/api\/people\/export\.csv"/.test(src) && /id="people-csv-file"/.test(src));
        check('a profile links to the person\'s whole record', /id="emp-export-link"/.test(src));
        const portal = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the portal links to the person\'s own data', /href="\/api\/employee\/my-data"/.test(portal));
    }
    {
        const { w, doc, charts } = boot();
        await w.loadAbsencePanel();
        await wait(40);
        const host = doc.getElementById('pa-absence-list');
        check('the sickness panel lists people with spells, days, score and band', /Often O'Neil/.test(host.textContent) && /64/.test(host.textContent) && /Watch/.test(host.textContent));
        check('  with the totals in the header', /4 days in 4 spells/.test(doc.getElementById('pa-absence-note').textContent));
        check('  and the weekday chart drawn on one axis', charts.length === 1 && charts[0].id === 'pa-weekday' && charts[0].config.data.datasets[0].data[0] === 3);
    }
    {
        const { w, sent, confirms } = boot();
        await w.previewPeopleCsv('first_name,last_name,email\nA,B,a@x\n');
        await wait(60);
        const dry = sent.find(s => s.url === '/api/people/import' && /dry_run=1/.test(s.q));
        const real = sent.filter(s => s.url === '/api/people/import' && !/dry_run/.test(s.q));
        check('an import is dry-run first and then confirmed with the summary and the problems', !!dry && confirms.length === 1 && /1 to create, 1 to update, 1 skipped/.test(confirms[0]) && /Row 4: no email/.test(confirms[0]) && /department that does not exist/.test(confirms[0]), confirms[0]);
        check('  and only then sent for real', real.length === 1);
    }
    {
        const { w, sent } = boot({ confirm: false });
        await w.previewPeopleCsv('first_name,last_name,email\nA,B,a@x\n');
        await wait(60);
        check('backing out of the confirmation imports nothing', !sent.some(s => s.url === '/api/people/import' && !/dry_run/.test(s.q)));
    }
    console.log(failures === 0 ? '\nAll absence-and-files checks passed.' : `\n${failures} absence-and-files check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
