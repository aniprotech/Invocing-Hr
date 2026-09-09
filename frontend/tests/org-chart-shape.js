/**
 * The chart drew the company twice.
 *
 * The server sent the hierarchy nested under its roots, and then sent every
 * person again - flat, grouped by department - and the page drew both. So
 * under the tree came a second copy of the whole staff list with no reporting
 * lines in it, and everybody with a department appeared twice on one screen.
 *
 * With no departments set up nobody could see that, which is why the existing
 * chart test never caught it: its fixture has departments: {}. With real
 * departments it is most of the page, and it is the reason the chart did not
 * read as a chart.
 *
 * Departments are now what they are - a name, a colour, a head and a count -
 * rather than a second copy of the staff list.
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

// Two departments, everybody in one of them, one clean reporting line.
const CHART = {
    total_employees: 4,
    unmanaged: 1,
    orphaned: 1,
    departments: [
        { id: 1, name: 'Engineering', color: '#38bdf8', head_id: 2,
          head_name: 'Dana Lead', count: 3 },
        { id: 2, name: 'Finance', color: '#34d399', head_id: null,
          head_name: '', count: 1 },
    ],
    roots: [
        {
            id: 1, name: 'Ada Chief', job_title: 'CEO', level: '', role: 'admin',
            department: 'Engineering', department_id: 1, department_color: '#38bdf8',
            heads_department: false, direct_reports: 1, total_reports: 2,
            children: [
                {
                    id: 2, name: 'Dana Lead', job_title: 'Head of Engineering',
                    level: '', role: 'employee', department: 'Engineering',
                    department_id: 1, department_color: '#38bdf8',
                    heads_department: true, direct_reports: 1, total_reports: 1,
                    children: [
                        { id: 3, name: 'Sam Dev', job_title: 'Engineer', level: '',
                          role: 'employee', department: 'Engineering',
                          department_id: 1, department_color: '#38bdf8',
                          heads_department: false, direct_reports: 0,
                          total_reports: 0, children: [] },
                    ],
                },
            ],
        },
        {
            id: 4, name: 'Lee Books', job_title: 'Accountant', level: '',
            role: 'employee', department: 'Finance', department_id: 2,
            department_color: '#34d399', heads_department: false,
            orphaned: true, direct_reports: 0, total_reports: 0, children: [],
        },
    ],
};

function boot(data) {
    const dom = new JSDOM(
        '<div id="orgchart-container"></div>',
        { runScripts: 'outside-only', pretendToBeVisual: true,
          url: 'https://localhost/app.html' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = () => Promise.resolve({ ok: true, status: 200,
                                      json: () => Promise.resolve(data) });
    const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
    w.eval(src);
    return w;
}

(async () => {
    const w = boot(CHART);
    await w.loadOrgChart();
    await new Promise(r => setTimeout(r, 60));
    const d = w.document;

    // --- the duplication, which is the whole bug ----------------------------
    {
        const nodes = [...d.querySelectorAll('.org-node')];
        check('every person is drawn exactly once', nodes.length === 4, nodes.length);

        const names = nodes.map(n => n.querySelector('.org-name').textContent.trim());
        const seen = {};
        const twice = names.filter(n => (seen[n] = (seen[n] || 0) + 1) === 2);
        check('  so nobody appears twice on the same screen',
            twice.length === 0, twice.join(', '));
    }

    // --- one connected tree, not a tree plus a pile --------------------------
    {
        const trees = d.querySelectorAll('.org-tree');
        check('there is one tree, not one per department',
            trees.length === 1, trees.length);
        check('and it is wide enough to scroll rather than crush',
            !!d.querySelector('#orgchart-container div[style*="overflow-x"]'));
    }

    // --- departments are described, not re-listed ----------------------------
    {
        const text = d.getElementById('orgchart-container').textContent;
        check('a department says how many people are in it',
            /Engineering/.test(text) && /3\s*people/.test(text), text.slice(0, 200));
        check('and who heads it', /led by Dana Lead/.test(text));
        // Somebody has to be accountable for a department, and a step aimed at
        // "their department head" silently becomes HR's without one.
        check('a department with no head says so', /no head set/.test(text));
    }

    // --- what a chart cannot show by drawing it ------------------------------
    {
        const text = d.getElementById('orgchart-container').textContent;
        check('the count of people is stated', /4\s*people/.test(text));
        // A reference to somebody who has gone is not the same as no manager,
        // and it is fixable - so it is worth separating.
        check('somebody whose manager has left is called out',
            /report to somebody who has left/.test(text));
        const orphan = [...d.querySelectorAll('.org-node')]
            .find(n => /Lee Books/.test(n.textContent));
        check('  and marked on their own box',
            /manager has left/.test(orphan.textContent));
    }

    // --- reports counts ------------------------------------------------------
    {
        const dana = [...d.querySelectorAll('.org-node')]
            .find(n => /Dana Lead/.test(n.textContent));
        check('a manager shows how many report to them',
            /1/.test(dana.querySelector('.org-toggle').textContent),
            dana.querySelector('.org-toggle') &&
            dana.querySelector('.org-toggle').textContent);
        const ada = [...d.querySelectorAll('.org-node')]
            .find(n => /Ada Chief/.test(n.textContent));
        // Direct reports and everyone underneath are different questions.
        check('  and everyone below them when that is a bigger number',
            /2 below/.test(ada.querySelector('.org-toggle').textContent),
            ada.querySelector('.org-toggle').textContent);
        const leaf = [...d.querySelectorAll('.org-node')]
            .find(n => /Sam Dev/.test(n.textContent));
        check('somebody with no reports has no count to show',
            !leaf.querySelector('.org-toggle'));
    }

    // --- folding a branch away ------------------------------------------------
    {
        w.toggleOrgBranch(2);
        await new Promise(r => setTimeout(r, 20));
        const names = [...d.querySelectorAll('.org-node')]
            .map(n => n.querySelector('.org-name').textContent);
        check('folding a manager away hides their reports',
            !names.some(n => /Sam Dev/.test(n)), names.join(', '));
        check('  but not the manager themselves',
            names.some(n => /Dana Lead/.test(n)));

        w.toggleOrgBranch(2);
        await new Promise(r => setTimeout(r, 20));
        check('  and unfolding brings them back',
            [...d.querySelectorAll('.org-node')].length === 4);
    }

    // --- finding somebody ------------------------------------------------------
    {
        d.getElementById('org-search').value = 'sam';
        w.filterOrgChart();
        const nodes = [...d.querySelectorAll('.org-node')];
        const dimmed = nodes.filter(n => n.style.opacity === '0.25');
        // Dimmed rather than removed: pulling non-matches out would reshape the
        // tree around whoever is left, so the thing being looked for moves while
        // it is being read.
        check('searching dims everyone else rather than removing them',
            dimmed.length === 3 && nodes.length === 4,
            `${dimmed.length} dimmed of ${nodes.length}`);
        check('  and the match is still in the tree',
            nodes.some(n => /Sam Dev/.test(n.textContent) && n.style.opacity !== '0.25'));
    }

    // --- an empty company --------------------------------------------------------
    {
        const w2 = boot({ total_employees: 0, roots: [], departments: [] });
        await w2.loadOrgChart();
        await new Promise(r => setTimeout(r, 40));
        check('a company with nobody in it says so, and does not throw',
            /No employees/.test(w2.document.getElementById('orgchart-container').textContent));
    }

    console.log(failures === 0
        ? '\nAll org chart shape checks passed.'
        : `\n${failures} org chart shape check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
