/**
 * Schema updates that failed on the way up.
 *
 * They are applied non-fatally on purpose: a partial failure must not stop the
 * app booting. The cost of that is a migration which never ran being
 * indistinguishable from one that worked - the app starts, the screen loads,
 * and the column simply is not there until something touches it.
 *
 * The endpoint recording all of this existed and nothing called it. /api/health
 * reports only a count, deliberately, because the messages carry table and
 * column names and health is public. So the messages themselves - the only
 * thing that tells an expected failure from a real one - were readable
 * nowhere.
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

const CLEAN = { count: 0, warnings: [] };
const BROKEN = {
    count: 2,
    warnings: [
        'migration step 1: column "email_verified_at" of relation "clients" already exists',
        'migration step 7: relation "settlements" does not exist',
    ],
};

function boot(report) {
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                if (p === '/api/superadmin/me') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ username: 'op', email: 'op@x' }) });
                }
                if (p === '/api/superadmin/migration-warnings') {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve(report || CLEAN) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(p.endsWith('s') ? [] : {}) });
            };
            w.alert = () => { };
            w.confirm = () => true;
        },
    });
    const w = dom.window;
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    return w;
}

const body = w => w.document.getElementById('migration-body');

(async () => {
    {
        const w = boot();
        check('the operator panel reports on schema updates', !!body(w));
        check('and it loads with the settings tab',
            /control:\s*\[[^\]]*loadMigrationWarnings/.test(
                fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8')));
    }

    // --- when something did not run -------------------------------------------
    {
        const w = boot(BROKEN);
        await w.loadMigrationWarnings();
        const text = body(w).textContent;
        check('a failed step is reported', /did not complete/.test(text),
            text.slice(0, 90));
        check('with how many', /2 schema steps/.test(text), text.slice(0, 90));

        // Paraphrasing loses the table and column names, which are the whole
        // message - they are what says which migration to go and check.
        check('and the database\'s own words, not a summary of them',
            /email_verified_at/.test(text) && /relation "settlements"/.test(text),
            text.slice(0, 200));
        check('every one of them, not just the first',
            BROKEN.warnings.every(wn => text.includes(wn)));
        check('saying which of these are expected, since some always are',
            /already dropped|expected/i.test(text), text.slice(0, 260));
    }

    // --- when nothing did ---------------------------------------------------------
    {
        const w = boot(CLEAN);
        await w.loadMigrationWarnings();
        const text = body(w).textContent;
        check('a clean boot says so rather than showing an empty box',
            /Every schema update applied/.test(text), text.slice(0, 90));
        check('and does not imply something failed',
            !/did not complete/.test(text));
    }

    // --- one warning reads as one -------------------------------------------------
    {
        const w = boot({ count: 1, warnings: ['migration step 3: nope'] });
        await w.loadMigrationWarnings();
        check('a single failure is not called "1 schema steps"',
            /1 schema step did not complete/.test(body(w).textContent),
            body(w).textContent.slice(0, 80));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
