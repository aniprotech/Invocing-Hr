/**
 * The app must never come up as an empty page.
 *
 * Reported on a reload of /app.html#/hr: the header drew, the body was blank,
 * and the button still said Sign In. Two things had to be true at once.
 *
 * The first: startRouter() - the call that decides what is on screen - ran at
 * the very end of the boot sequence, behind a dozen network calls that had no
 * error handling between them. Any one of them throwing meant it never ran.
 *
 * The second is what the portal merge changed. The invoicing app used to ship
 * dashboard-view marked `active` in its markup, so the browser painted a
 * dashboard before app.js had even parsed; a failed loader could leave you on
 * the wrong screen but never on no screen. app.html was rebuilt from the HR
 * page during the merge, and in that file every view was hidden because it
 * belonged to the other portal - so all 28 arrived hidden with none active,
 * and the floor that had always been there was gone.
 *
 * So this checks the floor rather than any one loader: markup alone puts a
 * screen up, and a boot that throws still leaves one there.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

// The boot handler is an async function, so anything it throws after its
// first await surfaces as an unhandled rejection rather than synchronously.
// That is not a detail of the test - it is why the reported failure was
// silent: a browser prints such a rejection to the console and carries on
// with a half-built page, which is what "blank but no error" was. Node kills
// the process instead, so they are collected here and asserted on.
const rejections = [];
process.on('unhandledRejection', (e) => rejections.push(e));

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log('ok    ' + label);
    else { failures++; console.log('FAIL  ' + label + (detail ? ': ' + detail : '')); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));

// What a reader actually sees. The stylesheet is what hides these -
// .view-section is display:none and .view-section.active is display:block -
// so the class is the signal, not the inline style. jsdom does not load the
// stylesheet, so reading computed style here would answer nothing; this
// applies the same rule the stylesheet does.
const onScreen = d => [...d.querySelectorAll('.view-section')]
    .filter(v => v.classList.contains('active') && v.style.display !== 'none')
    .map(v => v.id);

// --- 1. Before a line of script runs ---------------------------------------
{
    const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
    const d = new JSDOM(raw.replace(/<script[^>]*>[\s\S]*?<\/script>/g, '')).window.document;

    const views = [...d.querySelectorAll('.view-section')];
    const active = views.filter(v => v.classList.contains('active'));
    const painted = views.filter(v => !/display:\s*none/.test(v.getAttribute('style') || ''));

    check('the markup ships a view marked active',
        active.length === 1, `${active.length} active of ${views.length}`);
    check('and that view is not also hidden inline',
        active.length === 1 && painted.includes(active[0]),
        active[0] && active[0].getAttribute('style'));
    check('exactly one view is painted by markup alone',
        painted.length === 1, painted.map(v => v.id).join(', ') || 'none');
}

// --- 2. When the boot throws -----------------------------------------------
// Every network call in the boot is made to fail, which is the state the
// report came from: the page still has to end up on a screen.
function bootWithFetch(fetchImpl, hash) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html' + (hash || ''),
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = fetchImpl(w);
    // The console would otherwise carry a page of expected failures.
    w.console = { log() { }, warn() { }, error() { } };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    // jsdom dispatches synchronously and lets a listener's exception escape,
    // which would end this process with a stack trace instead of a result.
    // A boot that fails is the case under test, so it is caught here and
    // judged by the DOM assertions below.
    try {
        w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    } catch (e) { /* recorded by the DOM assertions below */ }
    return w;
}

// A session that is valid, and nothing else working at all.
const sessionOnly = (body) => () => (url) => {
    const p = String(url).split('?')[0];
    if (p === '/api/auth/me') {
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve({ user: { email: 'me@x' }, client_id: 1 }),
        });
    }
    if (p === '/api/client/me' && body) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    }
    return Promise.reject(new Error('offline'));
};

(async () => {
    {
        const w = bootWithFetch(sessionOnly({ id: 1, modules: ['invoicing', 'hr'] }));
        await wait(80);
        check('a signed-in boot with every loader failing still shows a screen',
            onScreen(w.document).length === 1, onScreen(w.document).join(', ') || 'nothing');
        check('and it is the dashboard',
            onScreen(w.document)[0] === 'dashboard-view', onScreen(w.document)[0]);
    }

    {
        // The exact URL from the report.
        const w = bootWithFetch(sessionOnly({ id: 1, modules: ['invoicing', 'hr'] }), '#/hr');
        await wait(80);
        check('#/hr still lands on the HR dashboard when the loaders fail',
            onScreen(w.document)[0] === 'hr-dashboard-view', onScreen(w.document)[0] || 'nothing');
    }

    {
        // Even the plan call gone, which used to be the last thing before the
        // router and is now before it.
        const w = bootWithFetch(sessionOnly(null), '#/invoices');
        await wait(80);
        check('a boot with no plan at all still shows the asked-for screen',
            onScreen(w.document)[0] === 'invoices-view', onScreen(w.document)[0] || 'nothing');
    }

    // --- 3. The router runs before the loaders, not after -------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const boot = src.slice(src.indexOf("document.addEventListener('DOMContentLoaded'"));
        // Named, not called: it goes through the wrapper now.
        const router = boot.indexOf('startRouter');
        const firstLoader = boot.indexOf('fetchDashboardData');
        check('startRouter runs before the data loaders',
            router !== -1 && firstLoader !== -1 && router < firstLoader,
            `router at ${router}, first loader at ${firstLoader}`);
    }

    // --- 4. A deep link survives the trip through sign-in -------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const gate = src.slice(src.indexOf('async function requireAuth'),
                               src.indexOf('window.requireAuth'));
        check('the address kept for after sign-in includes the hash',
            /location\.hash/.test(gate),
            'every screen is a hash, so without it they come back to the dashboard');
    }

    // --- 5. Nothing in the boot is left unguarded --------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const body = src.slice(src.indexOf("document.addEventListener('DOMContentLoaded'"));
        const end = body.indexOf('\n});');

        // Every step the boot takes, as written. A bare call at this level is
        // a step that can stop the boot on its way past - and stop it quietly,
        // because the handler is async and the throw becomes a rejection that
        // a browser only prints to the console.
        const bare = [];
        body.slice(0, end).split('\n').forEach((line) => {
            const m = line.match(/^ {4}([a-zA-Z_][\w.]*)\(\);\s*$/);
            if (m && m[1] !== 'boot') bare.push(m[1]);
        });
        check('every step of the boot is wrapped, so one failure is not all of them',
            bare.length === 0, bare.join(', '));
    }

    // The runs above deliberately fail every network call, so the wrapper is
    // being exercised. Anything escaping it means a step was missed.
    check('no boot failure escapes as an unhandled rejection',
        rejections.length === 0,
        rejections.map(e => (e && e.message) || String(e)).join('; '));

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
