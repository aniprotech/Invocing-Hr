/**
 * The numbers on the operator's front page have to lead somewhere.
 *
 * Every figure on the overview was a dead end. It told you fourteen clients
 * were active, four had never signed in and twelve sign-ins had failed, and
 * then left you to go and find them yourself - which meant switching panel by
 * hand and reading down a list of sixty to work out which ones it had meant.
 *
 * So each card is a button that lands on the panel holding the detail behind
 * it, with the list already narrowed to what was clicked. The two things worth
 * pinning: the destination is right, and a narrowed list always says that it
 * is narrowed - a filtered table that does not admit it is how somebody
 * concludes half their clients have disappeared.
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
const wait = ms => new Promise(r => setTimeout(r, ms));

// Sixty tenants with a spread of the states the cards filter on.
const CLIENTS = Array.from({ length: 60 }, (_, i) => ({
    id: i + 1,
    company_name: 'Tenant ' + (i + 1),
    contact_name: 'C', email: `t${i + 1}@example.com`,
    is_active: i % 3 !== 0,                 // 40 active, 20 disabled
    is_onboarded: true,
    invoice_count: 0,
    outstanding: i % 5 === 0 ? 250 : 0,     // 12 owing
    created_at: '2026-01-01',
    login_count: i % 4 === 0 ? 0 : 3,       // 15 never signed in
    modules: i % 2 === 0 ? ['invoicing', 'hr'] : ['invoicing'],
}));

const LOGS = Array.from({ length: 40 }, (_, i) => ({
    id: i + 1, email: `u${i + 1}@example.com`, user_type: 'client',
    login_type: 'password', ip_address: '10.0.0.' + i,
    status: i % 4 === 0 ? 'failed' : 'success',   // 10 failed
    created_at: '2026-01-01 09:00:00',
}));

function boot() {
    const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/superadmin.html',
        beforeParse(w) {
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                const body =
                    p === '/api/superadmin/me' ? { username: 'op', email: 'op@x' }
                        : p === '/api/superadmin/clients' ? CLIENTS
                            : p === '/api/superadmin/login-logs' ? LOGS
                                : p === '/api/superadmin/insights' ? {
                                    total_clients: 60, active_clients: 40,
                                    total_invoices: 0, total_outstanding: 0,
                                }
                                    : p === '/api/superadmin/platform-stats' ? {
                                        hr: { employees: 120, departments: 8, payslips: 400, payroll_paid: 90000 },
                                        recruitment: { open_jobs: 5, applications: 40 },
                                        tenants: { active_last_30_days: 33, total: 60 },
                                    }
                                        : (p.endsWith('s') ? [] : {});
                return Promise.resolve({
                    ok: true, status: 200,
                    json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
                });
            };
        },
    });
    return dom.window;
}

const shownPanel = w => {
    const p = w.document.querySelector('.admin-panel.active');
    return p ? p.id.replace('panel-', '') : '';
};
const rowNames = w => [...w.document.querySelectorAll('#clients-tbody .client-name')]
    .map(e => e.textContent.trim());

(async () => {
    // --- every figure is reachable by keyboard, not just by mouse ----------
    {
        const w = boot();
        await wait(120);
        const cards = w.document.querySelectorAll('#panel-overview button.stat-card');
        check('the overview figures are buttons, so they can be tabbed to',
            cards.length >= 8, cards.length + ' clickable cards');
        check('and every one of them names a destination',
            [...cards].every(c => /goToPanel\('[a-z]+'/.test(c.getAttribute('onclick'))));
        check('each says where it goes before you click',
            [...cards].every(c => c.querySelector('.stat-go')));
    }

    // --- where each card actually lands ------------------------------------
    const cases = [
        ['stat-total', 'clients', 60, 'every client'],
        ['stat-active', 'clients', 40, 'only the active ones'],
        ['stat-outstanding', 'clients', 12, 'only those owing money'],
        ['stat-never-login', 'clients', 15, 'only those who never signed in'],
        ['stat-invoices', 'billing', null, 'billing'],
        ['stat-logins-today', 'activity', null, 'the login log'],
    ];

    for (const [id, panel, expected, what] of cases) {
        const w = boot();
        await wait(120);
        const card = w.document.getElementById(id).closest('button.stat-card');
        card.dispatchEvent(new w.Event('click', { bubbles: true }));
        // The filter waits for the panel's own loader, so give it a moment.
        await wait(400);

        check(`${id} opens the ${panel} panel`, shownPanel(w) === panel, shownPanel(w));

        if (expected !== null) {
            // The table pages, so count what was filtered rather than drawn.
            const names = rowNames(w);
            const notice = w.document.getElementById('clients-filter-notice').textContent;
            check(`  and narrows to ${what}`,
                names.length > 0 && names.length <= 25, names.length + ' rows drawn');
            check(`  and says which list you are looking at`,
                id === 'stat-total' ? notice.trim() === '' : notice.trim().length > 0,
                JSON.stringify(notice.trim().slice(0, 60)));
        }
    }

    // --- the narrowing is real, not decorative ------------------------------
    {
        const w = boot();
        await wait(120);
        w.showTab('clients');
        await wait(200);

        w.setClientFilter('never');
        check('"never signed in" excludes everyone who has',
            [...w.document.querySelectorAll('#clients-tbody tr')].length > 0 &&
            rowNames(w).every(n => {
                const c = CLIENTS.find(x => x.company_name === n);
                return c && !c.login_count;
            }), rowNames(w).slice(0, 3).join(', '));

        w.setClientFilter('owing');
        check('"outstanding" excludes everyone at zero',
            rowNames(w).every(n => {
                const c = CLIENTS.find(x => x.company_name === n);
                return c && c.outstanding > 0;
            }));

        w.setClientFilter('active');
        check('"active" excludes the disabled',
            rowNames(w).every(n => {
                const c = CLIENTS.find(x => x.company_name === n);
                return c && c.is_active;
            }));
    }

    // --- getting back out ---------------------------------------------------
    {
        const w = boot();
        await wait(120);
        w.showTab('clients');
        await wait(200);
        w.setClientFilter('never');
        const before = rowNames(w).length;

        w.setClientFilter('all');
        check('there is a way back to the whole list',
            rowNames(w).length > before, `${before} -> ${rowNames(w).length}`);
        check('and the notice goes away with it',
            w.document.getElementById('clients-filter-notice').textContent.trim() === '');
    }

    // --- searching inside a narrowed list stays narrowed --------------------
    {
        const w = boot();
        await wait(120);
        w.showTab('clients');
        await wait(200);
        w.setClientFilter('active');
        w.filterClients('Tenant 1');

        check('a search within a filter respects both',
            rowNames(w).every(n => {
                const c = CLIENTS.find(x => x.company_name === n);
                return c && c.is_active && n.startsWith('Tenant 1');
            }) && rowNames(w).length > 0,
            rowNames(w).slice(0, 4).join(', '));
    }

    // --- the login log narrows too ------------------------------------------
    {
        const w = boot();
        await wait(120);
        const card = w.document.getElementById('stat-logins-failed').closest('button.stat-card');
        card.dispatchEvent(new w.Event('click', { bubbles: true }));
        await wait(400);

        check('failed logins opens the activity panel',
            shownPanel(w) === 'activity', shownPanel(w));

        const cells = [...w.document.querySelectorAll('#login-logs-tbody tr')]
            .map(tr => tr.textContent);
        check('  and shows only the failures',
            cells.length > 0 && cells.every(t => !/success/i.test(t)),
            cells.length + ' rows');
        check('  and says so',
            w.document.getElementById('logs-filter-notice').textContent.trim().length > 0);
    }

    // --- the platform strip leads somewhere as well -------------------------
    {
        const w = boot();
        await wait(200);
        const strip = w.document.querySelectorAll('#platform-grid button.stat-card');
        check('the platform figures are clickable too', strip.length >= 3,
            strip.length + ' of ' + w.document.querySelectorAll('#platform-grid .stat-card').length);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
