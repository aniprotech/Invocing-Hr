/**
 * A dashboard, and a way back to it, in both portals.
 *
 * The invoicing portal opened on its dashboard and had no link to it, so the
 * first click anywhere was a one-way trip until you reloaded. The HR portal had
 * no dashboard at all - it opened on the employee list, which says who exists
 * but not what needs doing, and the one view its markup called dashboard-view
 * was the invoicing one, hidden.
 *
 * The nav link has to be in the markup rather than built at runtime: app.js is
 * half a megabyte, and until it has run the browser paints whatever the HTML
 * says.
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

const EMPTY_BOARD = {
    headcount: { total: 0, active: 0, onboarding: 0, offboarding: 0 },
    today: { expected: 0, clocked_in: 0, on_leave: [], unaccounted_for: [], unaccounted_count: 0 },
    waiting_on_you: [
        { key: 'leave', label: 'Leave requests to decide', count: 0, view: 'leave-view' },
        { key: 'requests', label: 'Staff requests unanswered', count: 0, view: 'staff-requests-view' },
    ],
    waiting_total: 0,
    coming_up: { starting: [], interviews: [], expiring_documents: [] },
};

function boot(page, board) {
    const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/' + page,
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    // Shaped like the real Chart.js: the app sets Chart.defaults before drawing,
    // and a stub without it turns every run into a page of noise that a real
    // error could hide in.
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = p === '/api/hr/dashboard' ? (board || EMPTY_BOARD)
            : p === '/api/client/me' ? { id: 1, email: 'me@example.com' }
                : p === '/api/auth/me' ? { user: { email: 'me@example.com' } }
                    : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return dom.window;
}

(async () => {
    // --- the link exists in the markup, before any script runs ---------------
    for (const [page, id, view] of [
        ['app.html', 'nav-dashboard', 'dashboard-view'],
        ['hr.html', 'nav-hr-dashboard', 'hr-dashboard-view'],
    ]) {
        const raw = fs.readFileSync(path.join(ROOT, page), 'utf8');
        const dom = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, ''));
        const link = dom.window.document.getElementById(id);
        check(`${page} ships a Dashboard link in its markup`, !!link);
        check(`${page} link goes to ${view}`,
            !!link && (link.getAttribute('onclick') || '').includes(view),
            link && link.getAttribute('onclick'));
        check(`${page} link is labelled Dashboard`,
            !!link && link.textContent.trim() === 'Dashboard');
    }

    // --- and survives the portal filter --------------------------------------
    {
        const w = boot('hr.html');
        await wait(30);
        const link = w.document.getElementById('nav-hr-dashboard');
        check('HR keeps its dashboard link after the portal filter runs',
            link.style.display !== 'none', link.style.display);
        check('and does not show the invoicing one',
            w.document.getElementById('nav-dashboard').style.display === 'none');
        check('HR opens on its own dashboard, not the employee list',
            w.document.getElementById('hr-dashboard-view').style.display === 'block',
            w.document.getElementById('hr-dashboard-view').style.display);
        check('the link is marked active',
            link.classList.contains('active'));
    }

    {
        const w = boot('app.html');
        await wait(30);
        check('invoicing keeps its dashboard link',
            w.document.getElementById('nav-dashboard').style.display !== 'none');
        check('and there is a route back after leaving it', (() => {
            w.showView('invoices-view');
            w.showView('dashboard-view');
            return w.document.getElementById('dashboard-view').style.display === 'block';
        })());
    }

    // --- an empty tenant reads as calm, not broken ---------------------------
    {
        const w = boot('hr.html');
        await wait(30);
        check('an empty board says nothing is waiting',
            /nothing is waiting/i.test(w.document.getElementById('hr-dash-subtitle').textContent),
            w.document.getElementById('hr-dash-subtitle').textContent);
        check('a queue at zero is still shown, so it reads as clear rather than absent',
            w.document.getElementById('hr-dash-waiting').querySelectorAll('button').length === 2);
        check('with nobody on the books it says so',
            /nobody on the books/i.test(w.document.getElementById('hr-dash-today').textContent));
    }

    // --- a working day ------------------------------------------------------
    {
        const w = boot('hr.html', {
            headcount: { total: 12, active: 9, onboarding: 2, offboarding: 1 },
            today: {
                expected: 11, clocked_in: 6,
                on_leave: [{ name: 'Ada Reid', type: 'annual', until: '2026-08-25' }],
                unaccounted_for: ['Sam Ali', 'Jo Kerr'], unaccounted_count: 4,
            },
            waiting_on_you: [
                { key: 'leave', label: 'Leave requests to decide', count: 3, view: 'leave-view' },
                { key: 'documents', label: 'Documents to review', count: 0, view: 'onboarding-hub-view' },
            ],
            waiting_total: 3,
            coming_up: {
                starting: [{ name: 'Nia Okoro', date: '2026-08-24', title: 'Analyst' }],
                interviews: [], expiring_documents: [],
            },
        });
        await wait(30);

        const sub = w.document.getElementById('hr-dash-subtitle').textContent;
        check('the subtitle counts what is waiting', sub.includes('3 things are waiting'), sub);

        const today = w.document.getElementById('hr-dash-today').textContent;
        check('it says how many of how many clocked in', /6.*of.*11/.test(today), today);
        check('somebody on leave is named with their return date',
            today.includes('Ada Reid') && today.includes('2026-08-25'));
        check('the rest are "not accounted for", never "absent"',
            /not accounted for/i.test(today) && !/absent/i.test(today), today);
        check('the named few are listed and the remainder counted',
            today.includes('Sam Ali') && /2 more/.test(today), today);

        check('somebody starting soon is flagged',
            /Nia Okoro/.test(w.document.getElementById('hr-dash-upcoming').textContent));

        const cards = w.document.getElementById('hr-dash-waiting').querySelectorAll('button');
        check('every queue card navigates to the page that clears it',
            [...cards].every(b => /showView\("[a-z-]+-view"\)/.test(b.getAttribute('onclick'))),
            cards[0] && cards[0].getAttribute('onclick'));

        // jsdom does not run inline handler attributes under outside-only, so
        // the target is read out of the attribute and followed directly. The
        // thing worth proving is that the view it names is real - a card
        // pointing at nothing is worse than no card.
        const target = cards[0].getAttribute('onclick').match(/showView\("([^"]+)"\)/)[1];
        check('the view a card names actually exists',
            !!w.document.getElementById(target), target);
        w.showView(target);
        check('and going there shows it',
            w.document.getElementById(target).style.display === 'block');

        const head = w.document.getElementById('hr-dash-headcount').textContent;
        check('headcount is on the page', /12/.test(head) && /9/.test(head), head);
    }

    // --- a failed call does not leave it looking loaded ----------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'hr.html'), 'utf8')
            .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, {
            runScripts: 'outside-only', pretendToBeVisual: true,
            url: 'https://localhost/hr.html',
        });
        const w = dom.window;
        // Shaped like the real Chart.js: the app sets Chart.defaults before drawing,
    // and a stub without it turns every run into a page of noise that a real
    // error could hide in.
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
        w.jspdf = { jsPDF };
        w.URL.createObjectURL = () => 'blob:stub';
        w.fetch = () => Promise.reject(new Error('offline'));
        w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
        w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
        await wait(30);
        check('an unreachable server says so rather than showing "Loading..." forever',
            /could not load/i.test(w.document.getElementById('hr-dash-subtitle').textContent),
            w.document.getElementById('hr-dash-subtitle').textContent);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
