/**
 * The org chart, which was overlapping and colliding.
 *
 * Four separate causes, and each one is checked here because they fail in
 * different ways:
 *
 *   - .org-tree was a column, so two people at the top of the company sat one
 *     above the other, reading as though one reported to the other.
 *   - every node carried inline styles, which beat every .org-node rule in the
 *     stylesheet including the narrow-screen ones, so boxes stayed full width
 *     on a phone and ran into each other.
 *   - the connector was a border-top across the whole children row, so the
 *     line ran out past the outermost people and pointed at nobody.
 *   - a single child still got that full-width line.
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

const CHART = {
    total_employees: 5, departments: {},
    roots: [
        { id: 1, name: 'Ada Reid', job_title: 'CEO', children: [
            { id: 2, name: 'Bo Lin', job_title: 'CTO', children: [
                { id: 4, name: 'Cy Ng', job_title: 'Developer', children: [] }] },
            { id: 3, name: 'Di Roy', job_title: 'CFO', children: [] }] },
        { id: 5, name: 'Eve Sol', job_title: 'Chair', children: [] },
    ],
};

function boot() {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF: function () { } };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.fetch = (u) => {
        const p = String(u).split('?')[0];
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['hr', 'invoicing'] }) });
        }
        if (p === '/api/org-chart') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve(CHART) });
        }
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}') });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return w;
}

(async () => {
    const w = boot();
    await w.loadOrgChart();
    await new Promise(r => setTimeout(r, 60));
    const d = w.document;

    const tree = d.querySelector('.org-tree');
    check('the chart renders every person', d.querySelectorAll('.org-node').length === 5,
        d.querySelectorAll('.org-node').length);
    check('two people at the top sit side by side, not stacked',
        tree.children.length === 2, tree.children.length);

    check('a node carries no inline styles, so the stylesheet can size it',
        d.querySelector('.org-node').getAttribute('style') === null,
        d.querySelector('.org-node').getAttribute('style'));

    const rows = [...d.querySelectorAll('.org-children')];
    check('reports are grouped into rows', rows.length === 2, rows.length);
    check('and no row draws a line across its whole width',
        rows.every(r => !r.style.borderTop),
        rows.map(r => r.style.borderTop).join('|'));

    check('every branch under a manager is a branch element',
        rows.every(r => [...r.children].every(c => c.classList.contains('org-branch'))));

    const manager = d.querySelector('.org-branch');
    check('a manager has a stem down to their reports',
        !!manager.querySelector(':scope > .org-stem'));

    const leaf = [...d.querySelectorAll('.org-branch')]
        .find(b => !b.querySelector(':scope > .org-children'));
    check('somebody with no reports has no stem hanging off them',
        !leaf.querySelector(':scope > .org-stem'));

    // --- the stylesheet has to actually describe this ------------------------
    const css = fs.readFileSync(path.join(ROOT, 'styles.css'), 'utf8');
    check('the tree lays out in a row', /\.org-tree\s*{[^}]*flex-direction:\s*row/.test(css));
    check('and is allowed to be wider than the screen',
        /\.org-tree\s*{[^}]*min-width:\s*max-content/.test(css));
    check('an only child draws no connector at all',
        /:only-child::after\s*{\s*display:\s*none/.test(css));
    check('the first and last child stop their line at their own centre',
        /:first-child::after\s*{\s*left:\s*50%/.test(css) &&
        /:last-child::after\s*{\s*right:\s*50%/.test(css));
    check('and the segments reach across the gap so the line is unbroken',
        /left:\s*calc\(var\(--org-gap\)\s*\/\s*-2\)/.test(css));

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
