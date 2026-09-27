/**
 * Job boards.
 *
 * The Recruitment screen shows the feed URL every self-serve board takes,
 * and is honest about which boards are self-serve (a feed URL), automatic
 * (Google for Jobs needs nothing) and which are still posted by hand
 * (LinkedIn) - never claiming a live connection that isn't real. The
 * public careers page carries Google for Jobs' structured data per role.
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

const SETTINGS = {
    feed_url: 'https://www.aniprotech.com/api/public/jobs/7/feed.xml',
    board_url: 'https://www.aniprotech.com/jobs.html?c=7', open_jobs: 2,
    boards: [
        { key: 'indeed', name: 'Indeed', method: 'feed', note: 'Add the feed URL under Employer settings. Posting through Indeed’s own API needs Indeed to approve this product as a partner first.', add_url: 'https://employers.indeed.com/' },
        { key: 'google', name: 'Google for Jobs', method: 'automatic', note: 'Nothing to add.', add_url: '' },
        { key: 'linkedin', name: 'LinkedIn Jobs', method: 'manual', note: 'LinkedIn does not accept a self-serve XML feed.', add_url: 'https://www.linkedin.com/talent/post-a-job' },
    ],
};

function boot() {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/recruitment' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/job-board/settings') return give(SETTINGS);
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    return { w, doc: w.document };
}

(async () => {
    // --- the panel -------------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadJobBoards();
        const host = doc.getElementById('job-boards-content');
        check('the feed URL is shown, with how many roles it carries', host.textContent.includes(SETTINGS.feed_url) && /2 open roles published/.test(host.textContent));
        check('  with a Copy button', !!host.querySelector('button'));
        const rows = host.textContent;
        check('Indeed is offered as a feed, honest about needing a partner agreement for its own API',
            /Add the feed URL/.test(rows) && /approve/.test(rows) && /partner/.test(rows));
        check('Google for Jobs needs nothing added', /Nothing to add/.test(rows));
        check('LinkedIn is honest about being posted by hand', /Posted by hand/.test(rows) && /does not accept a self-serve/.test(rows));
        check('every board with an add_url gets an Open link, opening in a new tab',
            doc.querySelectorAll('#job-boards-content a[target="_blank"][rel="noopener"]').length === 2);
    }

    // --- copying the feed URL --------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadJobBoards();
        let copied = '';
        Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: (t) => { copied = t; return Promise.resolve(); } }, configurable: true });
        const btn = doc.querySelector('#job-boards-content [data-copy-feed]');
        btn.click();
        await wait(20);
        check('Copy puts the exact feed URL on the clipboard', copied === SETTINGS.feed_url, copied);
    }

    // --- names are text, not markup ---------------------------------------------------
    {
        const nasty = Object.assign({}, SETTINGS, { boards: [{ key: 'x', name: '<b>Evil</b> Board', method: 'feed',
            note: '<img src=x onerror=alert(1)>', add_url: '' }] });
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/recruitment' });
        const w = dom.window;
        w.console.error = () => { };
        w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(nasty) });
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        await w.loadJobBoards();
        const host = w.document.getElementById('job-boards-content');
        check('a board name and note are text, never rendered', !host.querySelector('b') && !host.querySelector('img'));
    }

    // --- a failed load says so rather than breaking the page ----------------------------------
    {
        const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/recruitment' });
        const w = dom.window;
        w.console.error = () => { };
        w.fetch = () => Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({ detail: 'Not authenticated' }) });
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        await w.loadJobBoards();
        check('a failed load leaves a message, not a blank panel', /Not authenticated/.test(w.document.getElementById('job-boards-content').textContent));
    }

    // --- opening the Recruitment screen loads it --------------------------------------------
    {
        const { w, doc } = boot();
        w.loadRecAnalytics = () => { };
        w.switchRecTab = () => { };
        w.showView('recruitment-view');
        await wait(20);
        check('opening Recruitment loads the job boards panel on its own', doc.getElementById('job-boards-content').textContent.includes(SETTINGS.feed_url));
    }

    // --- the public careers page: Google for Jobs structured data ---------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'jobs.html'), 'utf8');
        const DATA = {
            company: 'Northwind Care', logo_url: '', jobs: [{
                id: 42, reference: 'JOB-0001', title: 'Support Worker', department: 'Care', location: 'Leeds',
                work_mode: 'onsite', employment_type: 'full_time', level: '', description: 'Help at home.',
                requirements: '', salary_min: 24000, salary_max: 27000, salary_currency: 'GBP',
                closing_date: '2027-01-01', posted_on: '2026-09-01', apply_token: 'tok-1',
            }],
        };
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/jobs.html?c=7',
            beforeParse(w) { w.console.error = () => { }; w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(DATA) }); } });
        const w = dom.window;
        await wait(300);
        const article = w.document.getElementById('job-42');
        check('the published job has a stable id on the page for the feed to link to', !!article);
        const ld = article && article.querySelector('script[type="application/ld+json"]');
        check('it carries one Google for Jobs JobPosting script', !!ld);
        if (ld) {
            const data = JSON.parse(ld.textContent);
            check('  with the required fields Google validates', data['@type'] === 'JobPosting' && data.title === 'Support Worker'
                && data.datePosted === '2026-09-01' && data.hiringOrganization.name === 'Northwind Care');
            check('  the salary as a MonetaryAmount range', data.baseSalary.value.minValue === 24000 && data.baseSalary.value.maxValue === 27000);
            check('  and the employment type in schema.org’s own vocabulary', data.employmentType === 'FULL_TIME');
        }
    }
    {
        const html = fs.readFileSync(path.join(ROOT, 'jobs.html'), 'utf8');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/jobs.html?c=7',
            beforeParse(w) {
                w.console.error = () => { };
                w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
                    company: 'Northwind', jobs: [{ id: 9, reference: 'JOB-0002', title: 'Remote Coordinator', work_mode: 'remote',
                        employment_type: 'contract', posted_on: '2026-09-01', location: 'Anywhere' }] }) });
            } });
        const w = dom.window;
        await wait(300);
        const ld = JSON.parse(w.document.getElementById('job-9').querySelector('script[type="application/ld+json"]').textContent);
        check('a remote role is marked TELECOMMUTE, not a physical place', ld.jobLocationType === 'TELECOMMUTE' && !ld.jobLocation);
        check('a role with no salary carries no baseSalary field at all', !('baseSalary' in ld));
    }

    console.log(failures ? `\n${failures} check(s) failed.` : '\nAll job board checks passed.');
    process.exit(failures ? 1 : 0);
})();
