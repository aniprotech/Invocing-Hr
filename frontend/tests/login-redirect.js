/**
 * The login page and the app have to agree on who is signed in.
 *
 * They stopped agreeing, and the result was a loop: requireAuth was tightened
 * to require client_id, because every endpoint in the app resolves the tenant
 * through it, but the login pages still forwarded anyone holding a Google
 * identity. So a session with a user and no tenant - a superadmin, a member
 * of staff, a half-finished sign-in - went login -> app -> login -> app
 * without stopping, and both pages blinked.
 *
 * The rule: a page may only send somebody into the app for a session the app
 * will actually accept. These check the two sides against each other rather
 * than each on its own, because agreeing is the whole point.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log('ok    ' + label);
    else { failures++; console.log('FAIL  ' + label + (detail ? ': ' + detail : '')); }
};
(async () => {
    // --- the shape that caused the loop -----------------------------------
    for (const page of ['login.html', 'hr-login.html']) {
        const src = fs.readFileSync(path.join(ROOT, page), 'utf8');

        check(`${page} does not forward on a user alone`,
            !/if \(data\.user\)\s*\{/.test(src),
            'a session with no tenant would be sent into the app, which sends it back');

        check(`${page} requires the tenant id before entering the app`,
            /client_id/.test(src),
            'nothing in this page mentions client_id');

        // The app's own gate, for comparison. If these two ever disagree the
        // loop comes back.
        const appJs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const gate = appJs.slice(appJs.indexOf('async function requireAuth'),
                                 appJs.indexOf('window.requireAuth'));
        check(`${page} agrees with requireAuth about what counts as signed in`,
            /client_id/.test(gate) && /client_id/.test(src),
            'one side checks client_id and the other does not');
    }

    // --- an operator still gets where they are going ----------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'login.html'), 'utf8');
        // The superadmin check has to come first: that session has no tenant
        // of its own, so a tenant-first test would strand them here.
        // Measured inside the block that does the deciding: nextTarget's own
        // definition sits above it, so searching the whole file compares the
        // wrong two things.
        const block = src.slice(src.indexOf('(async function () {'));
        const saAt = block.indexOf('/api/superadmin/me');
        const tenantAt = block.indexOf('nextTarget(');
        check('the operator is checked before the tenant',
            saAt !== -1 && saAt < tenantAt,
            'a superadmin has no client_id and would be left on the login page');
        check('and is sent to their own panel',
            /superadmin\.html/.test(src));
    }

    // --- the landing page must not offer a door that refuses them ---------
    {
        const src = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
        check('index.html only points at the app for a real tenant session',
            /data\.user && data\.client_id/.test(src),
            'the portal buttons would send a tenant-less session into a bounce');
    }

    // --- and the gate itself still lets a real tenant in ------------------
    {
        const appJs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const gate = appJs.slice(appJs.indexOf('async function requireAuth'),
                                 appJs.indexOf('window.requireAuth'));
        check('requireAuth admits a session that has both',
            /data\.user && data\.client_id/.test(gate), gate.slice(0, 120));
    }

    console.log(failures ? '\n' + failures + ' failed' : '\nall good');
    process.exit(failures ? 1 : 0);
})();
