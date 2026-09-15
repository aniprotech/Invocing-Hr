/**
 * Skills, on screen.
 *
 * The Skills view names the single points of failure first, lists the
 * catalogue, draws the matrix for a department, and answers "who can do
 * X" as you type. A profile shows chips, greyed until confirmed, with a
 * tick to confirm. In the portal a person edits their own list and sees
 * which ones are confirmed.
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

const SKILLS = { people: 3, people_with_none: 1, levels: {}, skills: [
    { id: 1, name: 'Payroll run', category: 'Finance', people: 1, strong: 1, average_level: 4, single_point_of_failure: true, unverified: 0 },
    { id: 2, name: 'Python <b>3</b>', category: '', people: 2, strong: 1, average_level: 2.5, single_point_of_failure: false, unverified: 1 },
], single_points_of_failure: [{ id: 1, name: 'Payroll run', category: 'Finance', people: 1, strong: 1, average_level: 4, single_point_of_failure: true, unverified: 0 }] };
const MATRIX = { skills: [{ id: 2, name: 'Python' }, { id: 1, name: 'SQL' }], levels: {},
    people: [{ employee_id: 7, name: "Ann O'Neil", job_title: '', levels: [4, 0], verified: [true, false] }, { employee_id: 8, name: 'Bob', job_title: '', levels: [1, 3], verified: [false, false] }],
    coverage: [{ skill_id: 2, name: 'Python', strong: 1, any: 2 }, { skill_id: 1, name: 'SQL', strong: 1, any: 1 }] };

function bootHr(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body, q: String(url).split('?')[1] || '' });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/skills' && method === 'GET') return give(SKILLS);
        if (p === '/api/skills/matrix') return give(MATRIX);
        if (p === '/api/skills/search') return give({ people: [{ employee_id: 7, name: "Ann O'Neil", skill: 'Python', level: 4, level_word: 'Expert', verified: true }] });
        if (p === '/api/employees/7/skills' && method === 'GET') return give({ skills: [
            { skill_id: 2, name: 'Python', level: 4, level_word: 'Expert', verified: true, verified_by: 'HR', added_by: 'hr' },
            { skill_id: 3, name: 'Figma', level: 2, level_word: 'Working', verified: false, verified_by: '', added_by: 'employee' } ] });
        if (p === '/api/employees/7/skills' && method === 'PUT') return give({ skills: [] });
        if (p === '/api/employees/7/skills/3/verify') return give({ verified: true });
        if (p === '/api/departments') return give([{ id: 5, name: 'Data' }]);
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(true);
    w.uiForm = () => Promise.resolve(opts.form === undefined ? null : opts.form);
    return { w, doc: w.document, sent };
}
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('People has Skills', /href="#\/skills"/.test(src) && /id="skills-view"/.test(src));
        const { w } = bootHr();
        check('  and the hash opens the view', w.VIEW_FOR_SLUG['skills'] === 'skills-view');
    }
    {
        const { w, doc, sent } = bootHr();
        await w.loadSkillsView();
        await wait(80);
        const tiles = doc.getElementById('skill-tiles').textContent;
        check('the tiles count the catalogue, the single points of failure, and who has none', /Only one person can do it/.test(tiles) && /1/.test(tiles) && /People with none recorded/.test(tiles));
        check('  the single points of failure are named up top', doc.getElementById('skill-spof-widget').style.display === '' && /Payroll run/.test(doc.getElementById('skill-spof').textContent));
        const cat = doc.getElementById('skill-catalogue');
        check('  the catalogue is a table with names as text', /Python <b>3<\/b>/.test(cat.textContent) && !cat.querySelector('b') && /only one/.test(cat.textContent));
        const m = doc.getElementById('skill-matrix');
        check('  the matrix has a column per skill and a row per person', /Python/.test(m.textContent) && /SQL/.test(m.textContent) && /Ann O'Neil/.test(m.textContent) && /Bob/.test(m.textContent));
        check('  and a cover row that flags one-person cover', /Strong cover/.test(m.textContent) && (m.innerHTML.match(/var\(--warning-color\)/g) || []).length >= 2);
        check('  the department picker was filled', [...doc.querySelectorAll('#skill-matrix-dept option')].some(o => o.textContent === 'Data'));
        w.searchSkills('python');
        await wait(300);
        const res = doc.getElementById('skill-search-results');
        check('typing a skill asks who can do it and lists them strongest first', sent.some(s => s.url === '/api/skills/search' && /q=python/.test(s.q)) && res.style.display === '' && /Ann O'Neil/.test(res.textContent) && /Expert/.test(res.textContent));
    }
    {
        const { w, doc, sent } = bootHr({ form: { list: 'Python:4\nSQL:2\nExcel' } });
        w.currentEmployeeId = 7;
        await w.loadEmployeeSkills(7);
        await wait(40);
        const host = doc.getElementById('emp-skills-list');
        check('the profile shows chips, and a tick only on the unconfirmed one', /Python/.test(host.textContent) && /Figma/.test(host.textContent) && (host.innerHTML.match(/verifyEmployeeSkill\(7,3\)/g) || []).length === 1 && !/verifyEmployeeSkill\(7,2\)/.test(host.innerHTML));
        await w.verifyEmployeeSkill(7, 3);
        await wait(30);
        check('  ticking confirms it', sent.some(s => s.url === '/api/employees/7/skills/3/verify' && s.method === 'POST'));
        await w.editEmployeeSkills(7);
        await wait(40);
        const put = sent.find(s => s.url === '/api/employees/7/skills' && s.method === 'PUT');
        const b = bodyOf(put);
        check('editing parses "name:level" lines, a bare name being a working level', put && b.skills.length === 3 && b.skills[0].level === 4 && b.skills[1].level === 2 && b.skills[2].name === 'Excel' && b.skills[2].level === 2, put && put.body);
    }

    // --- the portal ---------------------------------------------------------------
    {
        const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const sent = [];
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url, init) => {
                    const p = String(url).split('?')[0];
                    const method = (init && init.method) || 'GET';
                    sent.push({ url: p, method, body: init && init.body });
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/employee/skills' && method === 'GET') return give({ skills: [
                        { skill_id: 2, name: 'Python <i>x</i>', level: 3, verified: true }, { skill_id: 3, name: 'Figma', level: 2, verified: false } ], catalogue: ['Figma', 'Python <i>x</i>', 'SQL'], levels: {} });
                    if (p === '/api/employee/skills' && method === 'PUT') return give({ skills: [] });
                    return give(p.endsWith('s') ? [] : {});
                };
            } });
        const w = dom.window, doc = w.document;
        await w.loadMySkills();
        await wait(30);
        const host = doc.getElementById('mySkills');
        check('the portal shows my skills as chips, names as text, confirmed ones ticked', host.children.length === 2 && /Python <i>x<\/i>/.test(host.textContent) && !host.querySelector('i') && /Strong ✓/.test(host.textContent) && /Figma · Working$/.test(host.children[1].textContent));
        check('  the catalogue feeds the suggestions', doc.querySelectorAll('#skill-catalogue option').length === 3);
        w.toggleSkillForm();
        doc.getElementById('skill-new').value = 'SQL';
        doc.getElementById('skill-new-level').value = '4';
        w.addMySkillRow();
        doc.querySelectorAll('#skill-rows .skill-level')[1].value = '3';
        doc.querySelectorAll('#skill-rows .skill-level')[1].dispatchEvent(new w.Event('change'));
        await w.submitMySkills();
        await wait(30);
        const put = sent.find(s => s.url === '/api/employee/skills' && s.method === 'PUT');
        const b = bodyOf(put);
        check('saving sends the whole list with levels, the new one included', put && b.skills.length === 3 && b.skills[2].name === 'SQL' && b.skills[2].level === 4 && b.skills[1].level === 3, put && put.body);
    }

    console.log(failures === 0 ? '\nAll skills checks passed.' : `\n${failures} skills check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
