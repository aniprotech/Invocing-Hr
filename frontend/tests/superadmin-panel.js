/**
 * The operator panel: what it fetches, and when.
 *
 * Every one of its eleven loaders fired on page load, before the page knew
 * whether there was a session at all - so a signed-out operator produced
 * eleven 401s on the way to the login redirect, and a signed-in one paid for
 * five panels to reach the one they wanted. It was also a single scroll, with
 * both tables printing every row they had.
 *
 * These check the three things that changed: nothing is fetched before the
 * session is confirmed, a panel is fetched on first visit and not again, and
 * the tables page rather than printing everything.
 *
 * It also covers the plan control, which is newer and load-bearing: invoicing
 * and HR are one app now, so what a business sees is decided by the plan and
 * this panel is the only place it can be set.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');

// Enough rows that paging has something to do.
const CLIENTS = Array.from({ length: 60 }, (_, i) => ({
    id: i + 1, company_name: 'Tenant ' + (i + 1), contact_name: 'C', email: `t${i + 1}@example.com`,
    is_active: true, is_onboarded: true, invoice_count: 0, outstanding: 0,
    created_at: '2026-01-01', login_count: 1,
    // A spread of plans, including one written back to front: the server
    // stores a list, not an ordered pair, so the control has to recognise
    // ['hr','invoicing'] as the same plan as ['invoicing','hr'].
    modules: i % 3 === 0 ? ['invoicing', 'hr']
        : i % 3 === 1 ? ['hr']
            : ['hr', 'invoicing'],
}));
const LOGS = Array.from({ length: 140 }, (_, i) => ({
    id: i + 1, email: `u${i + 1}@example.com`, user_type: 'client', login_type: 'password',
    ip_address: '10.0.0.' + (i % 255), status: 'success', created_at: '2026-01-01 09:00:00',
}));

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const calls = [];

    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html' + (opts.hash || ''),
        beforeParse(w) {
            // Installed before the inline script runs, so the very first
            // fetch the page makes is recorded.
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                calls.push(p);
                if (p === '/api/superadmin/me') {
                    return opts.signedOut
                        ? Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) })
                        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ username: 'op', email: 'op@x' }) });
                }
                // Shaped like the real responses. A bare {} would have every
                // panel throw on a missing field, and a genuine break could
                // then hide in the noise.
                const body = p === '/api/superadmin/clients' ? CLIENTS
                    : p === '/api/superadmin/login-logs' ? LOGS
                        : p === '/api/superadmin/insights' ? {
                            total_clients: 60, active_clients: 58,
                            total_invoices: 0, total_outstanding: 0,
                        }
                            : (p.endsWith('s') ? [] : {});
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
            };
        },
    });
    // jsdom does not navigate, so the signed-out redirect shows up only as
    // its "Not implemented: navigation" notice. What matters here is what was
    // fetched, which is asserted directly.
    return { w: dom.window, calls };
}

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const rows = (w, id) => w.document.querySelectorAll('#' + id + ' tr').length;

(async () => {
    // --- Nothing loads before the session is known ------------------------
    {
        const { calls } = boot({ signedOut: true });
        await wait(60);
        const panelCalls = calls.filter(c => c !== '/api/superadmin/me');
        check('signed out, the panel asks who you are and nothing else',
            panelCalls.length === 0, 'also called: ' + panelCalls.join(', '));
        check('and it does ask',
            calls.includes('/api/superadmin/me'), calls.join(', '));
    }

    // --- One panel loads, not all five ------------------------------------
    {
        const { w, calls } = boot();
        await wait(60);
        check('signed in, the first panel is shown',
            w.document.querySelector('#panel-overview').classList.contains('active'));
        check('and only its own data is fetched',
            !calls.includes('/api/superadmin/clients') && !calls.includes('/api/superadmin/wallets'),
            calls.join(', '));

        w.showTab('clients');
        await wait(60);
        check('opening Clients fetches the client list',
            calls.includes('/api/superadmin/clients'), calls.join(', '));

        const before = calls.length;
        w.showTab('overview');
        w.showTab('clients');
        await wait(60);
        check('going back to a panel already loaded fetches nothing again',
            calls.length === before, 'grew by ' + (calls.length - before));
    }

    // --- The panel you are on survives a refresh ---------------------------
    {
        const { w } = boot({ hash: '#billing' });
        await wait(60);
        check('a link to one panel opens that panel',
            w.document.querySelector('#panel-billing').classList.contains('active'));
    }

    // --- Tables page --------------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        w.showTab('clients');
        await wait(60);
        check('sixty tenants are not all printed at once',
            rows(w, 'clients-tbody') === 25, rows(w, 'clients-tbody') + ' rows');
        check('and the pager says where you are',
            /Page 1 of 3/.test(w.document.getElementById('clients-pager').textContent),
            w.document.getElementById('clients-pager').textContent);

        w.showPage('clients', 2);
        check('the last page holds the remainder',
            rows(w, 'clients-tbody') === 10, rows(w, 'clients-tbody') + ' rows');

        // Paging must not outrun the data.
        w.showPage('clients', 99);
        check('asking past the end stays on the last page',
            /Page 3 of 3/.test(w.document.getElementById('clients-pager').textContent),
            w.document.getElementById('clients-pager').textContent);

        w.showTab('activity');
        await wait(60);
        check('the log table pages too',
            rows(w, 'login-logs-tbody') === 25, rows(w, 'login-logs-tbody') + ' rows');

        // Filtering re-pages from the top rather than leaving you on a page
        // that no longer exists.
        w.filterLogs('u1@example.com');
        check('searching the logs pages the results, not the whole set',
            rows(w, 'login-logs-tbody') === 1, rows(w, 'login-logs-tbody') + ' rows');
    }

    // --- The plan, which is the whole basis of the merged app --------------
    {
        const { w } = boot();
        await wait(60);
        w.showTab('clients');
        await wait(60);
        const d = w.document;

        const selects = d.querySelectorAll('#clients-tbody .plan-select');
        check('every tenant row offers a plan',
            selects.length === rows(w, 'clients-tbody'),
            `${selects.length} controls for ${rows(w, 'clients-tbody')} rows`);

        // A row whose cells do not match the header shifts every column after
        // it, which is how a plan control silently lands under "Status".
        const headers = d.querySelectorAll('#panel-clients thead th').length
            || d.querySelectorAll('table.clients-table thead th').length;
        const cells = d.querySelectorAll('#clients-tbody tr')[0].children.length;
        check('the row has a cell for every column', headers === cells,
            `${headers} headers, ${cells} cells`);

        // The plan shown has to be the plan held, whichever order it arrived in.
        const first = d.querySelectorAll('#clients-tbody tr')[0]
            .querySelector('.plan-select');
        check('a tenant on both modules shows as being on both',
            first.value === 'invoicing,hr', first.value);

        const reversed = [...selects].find((sel, i) => {
            const tr = sel.closest('tr');
            return tr && /Tenant 3$/.test(tr.querySelector('.client-name').textContent);
        });
        check('a plan stored back to front is still recognised',
            reversed && reversed.value === 'invoicing,hr',
            reversed && reversed.value);

        const hrOnly = [...selects].find(sel =>
            /Tenant 2$/.test(sel.closest('tr').querySelector('.client-name').textContent));
        check('an HR-only tenant shows as HR only',
            hrOnly && hrOnly.value === 'hr', hrOnly && hrOnly.value);

        // Every option has to be one the server will take. The panel offering
        // a plan the API rejects is a control that only ever fails.
        const api = fs.readFileSync(path.join(ROOT, '..', 'backend', 'main.py'), 'utf8');
        const known = (api.match(/ALL_MODULES = \(([^)]*)\)/) || [, ''])[1]
            .split(',').map(x => x.trim().replace(/['"]/g, '')).filter(Boolean);
        const offered = [...first.options].map(o => o.value);
        check('every plan offered is one the server accepts',
            offered.every(v => v.split(',').every(m => known.includes(m))),
            `offered ${offered.join(' | ')}; server knows ${known.join(', ')}`);

        // --- changing one ---------------------------------------------------
        const sent = [];
        const realFetch = w.fetch;
        w.fetch = (url, init) => {
            if (String(url).includes('/modules')) {
                sent.push({ url: String(url), body: JSON.parse(init.body), method: init.method });
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
            }
            return realFetch(url, init);
        };

        hrOnly.value = 'invoicing,hr';
        await w.setClientPlan(Number(hrOnly.getAttribute('onchange').match(/\d+/)[0]), hrOnly);

        check('changing the plan calls the endpoint that sets it',
            sent.length === 1 && /\/api\/superadmin\/clients\/\d+\/modules$/.test(sent[0].url),
            sent[0] && sent[0].url);
        check('and sends it as a list, which is what the API takes',
            sent[0] && Array.isArray(sent[0].body.modules)
            && sent[0].body.modules.sort().join(',') === 'hr,invoicing',
            sent[0] && JSON.stringify(sent[0].body));
        check('with PUT', sent[0] && sent[0].method === 'PUT', sent[0] && sent[0].method);

        // --- and a refusal must not leave a plan on screen that is not set ---
        w.fetch = (url, init) => {
            if (String(url).includes('/modules')) {
                return Promise.resolve({
                    ok: false, status: 400,
                    json: () => Promise.resolve({ detail: 'nope' }),
                });
            }
            return realFetch(url, init);
        };
        w.alert = () => { };   // jsdom has no dialogs

        const before = hrOnly.value;
        hrOnly.value = 'invoicing';
        await w.setClientPlan(Number(hrOnly.getAttribute('onchange').match(/\d+/)[0]), hrOnly);
        check('a refused change puts the control back rather than lying about it',
            hrOnly.value === before, `${hrOnly.value}, was ${before}`);
        check('and the control is usable again', hrOnly.disabled === false);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
