/** Search reaches pages by name and the HR kinds, and each result opens where it belongs. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const ROOT = path.resolve(__dirname, '..');
let failures = 0;
const check = (label, ok, detail) => { if (ok) console.log(`ok    ${label}`); else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window, shown = [];
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/search') return give({ results: [
            { type: 'skill', label: 'Payroll run', sub: '1 person has it', number: '', id: 3 },
            { type: 'policy', label: 'Expenses <b>policy</b>', sub: 'policy, v2', number: '', id: 4 } ] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showView = (id) => { shown.push(id); };
    w.searchSkills = (q) => { shown.push('skills:' + q); };
    await w.runGlobalSearch('pay');
    await wait(40);
    const d = w.document, dd = d.getElementById('search-results-dropdown');
    check('typing "pay" offers the Pay bands and Payroll pages under Go to', dd && /Go to/.test(dd.textContent) && /Pay bands/.test(dd.textContent) && /Payroll/.test(dd.textContent));
    check('  and the skill and policy hits, labels as text', /Payroll run/.test(dd.textContent) && /Expenses <b>policy<\/b>/.test(dd.textContent) && !dd.querySelector('.search-result-item b'));
    w.openSearchResult('page', encodeURIComponent('compensation-view'), 0);
    check('a page hit opens the page', shown[shown.length - 1] === 'compensation-view');
    w.openSearchResult('skill', encodeURIComponent('Payroll run'), 3);
    await wait(350);
    check('a skill hit opens Skills and searches for it', shown.includes('skills-view') && shown.includes('skills:Payroll run'), JSON.stringify(shown));
    w.openSearchResult('policy', '', 4);
    check('a policy hit opens Policies', shown[shown.length - 1] === 'policies-view');
    console.log(failures === 0 ? '\nAll search checks passed.' : `\n${failures} search check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
