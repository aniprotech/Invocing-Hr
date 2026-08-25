/**
 * What the service worker is allowed to keep.
 *
 * This is the file where a mistake is quiet and serious. The cache is keyed
 * by URL and shared by everyone who uses the browser, so caching a response
 * from /api/ would hand the next person to sign in on that machine the
 * previous tenant's invoices, payroll or employee records - looking, to them,
 * like their own data. The same applies to the HTML pages, which are only
 * reachable when signed in.
 *
 * So the rule this file exists to hold down is: static assets may be cached,
 * and nothing else may be. It is asserted here rather than left to review,
 * because the failure is invisible in normal use.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

// Run sw.js with just enough of a worker around it to capture its handlers.
function loadWorker() {
    const handlers = {};
    const sandbox = {
        self: {
            addEventListener: (name, fn) => { handlers[name] = fn; },
            location: { origin: 'https://app.example.com' },
            skipWaiting: () => Promise.resolve(),
            clients: { claim: () => Promise.resolve() },
        },
        caches: {
            open: () => Promise.resolve({
                match: () => Promise.resolve(undefined),
                put: () => Promise.resolve(),
                add: () => Promise.resolve(),
            }),
            keys: () => Promise.resolve([]),
            delete: () => Promise.resolve(true),
        },
        fetch: () => Promise.resolve({ ok: true, clone: () => ({}) }),
        URL,
        console,
    };
    sandbox.self.self = sandbox.self;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8'), sandbox);
    return handlers;
}

// Does the worker take over this request, or let it go to the network?
function intercepts(handlers, url, method) {
    let took = false;
    handlers.fetch({
        request: { url, method: method || 'GET' },
        respondWith: () => { took = true; },
    });
    return took;
}

const h = loadWorker();
const ORIGIN = 'https://app.example.com';

check('a worker is installed at all', typeof h.fetch === 'function');

// --- The things that must never be cached ---------------------------------
[
    ['/api/invoices', 'the invoice list'],
    ['/api/hr/employees', 'the employee list'],
    ['/api/payroll/payslips', 'payslips'],
    ['/api/client/me', 'who is signed in'],
    ['/api/superadmin/clients', 'the operator client list'],
    ['/api/settings', 'tenant settings'],
].forEach(([p, what]) => {
    check('never caches ' + what, !intercepts(h, ORIGIN + p), p);
});

[
    ['/app.html', 'the invoicing app page'],
    ['/hr.html', 'the HR app page'],
    ['/superadmin.html', 'the operator panel'],
    ['/', 'the site root'],
].forEach(([p, what]) => {
    check('never caches ' + what, !intercepts(h, ORIGIN + p), p);
});

// A query string must not be a way to dress an API call up as an asset.
check('never caches an API call with an asset-looking query',
    !intercepts(h, ORIGIN + '/api/invoices?export=report.css'));

// Writes go to the network whatever they are.
check('never caches a POST', !intercepts(h, ORIGIN + '/styles.css?v=82', 'POST'));
check('never caches a DELETE', !intercepts(h, ORIGIN + '/styles.css?v=82', 'DELETE'));

// Another origin's responses are not ours to keep.
check('never caches a third-party request',
    !intercepts(h, 'https://fonts.example.net/x.woff2'));

// --- The things that should be cached --------------------------------------
[
    ['/styles.css?v=82', 'the stylesheet'],
    ['/mobile.css?v=82', 'the mobile stylesheet'],
    ['/app.js?v=82', 'the script bundle'],
    ['/icons/icon-192.png', 'an icon'],
    ['/icons/icon.svg', 'the svg icon'],
].forEach(([p, what]) => {
    check('caches ' + what, intercepts(h, ORIGIN + p), p);
});

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
