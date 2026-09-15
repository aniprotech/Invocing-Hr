/** The portal's to-do strip, and the operator's HR adoption table. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const ROOT = path.resolve(__dirname, '..');
let failures = 0;
const check = (label, ok, detail) => { if (ok) console.log(`ok    ${label}`); else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
function bootPortal(todo) {
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
            w.fetch = (url) => { const p = String(url).split('?')[0]; const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/todo') return give(todo); return give(p.endsWith('s') ? [] : {}); };
        } });
    return { w: dom.window, doc: dom.window.document };
}
(async () => {
    {
        const { w, doc } = bootPortal({ total: 4, items: [
            { key: 'self_review', label: 'Your self-assessment to write', count: 1, tab: 'reviews' },
            { key: 'policies', label: 'Policies to read <b>x</b>', count: 3, tab: 'documents' } ] });
        await w.loadTodo();
        await wait(30);
        const strip = doc.getElementById('todoStrip');
        check('the strip shows each thing waiting, with a count when more than one, as text', !strip.hidden && strip.children.length === 2 && /3 · Policies to read <b>x<\/b>/.test(strip.textContent) && !strip.querySelector('b'));
        let switched = null; w.switchTab = (t) => { switched = t; };
        strip.children[1].click();
        check('  and pressing one goes to its tab', switched === 'documents');
    }
    {
        const { w, doc } = bootPortal({ total: 0, items: [] });
        await w.loadTodo();
        await wait(30);
        check('with nothing waiting the strip is hidden', doc.getElementById('todoStrip').hidden);
    }
    {
        const html = fs.readFileSync(path.join(ROOT, 'superadmin.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/superadmin.html',
            beforeParse(w) {
                w.console.error = () => { };
                w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
                w.fetch = (url) => { const p = String(url).split('?')[0]; const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p === '/api/superadmin/hr-adoption') return give({ feature_keys: ['reviews', 'policies'], businesses: [
                        { client_id: 1, company: 'Acme <b>Ltd</b>', email: 'a@x', active: true, employees: 12, features: { reviews: 2, policies: 0 }, features_used: 1 } ] });
                    return give(p.endsWith('s') ? [] : {}); };
            } });
        const w = dom.window, doc = w.document;
        await w.loadHrAdoption();
        await wait(30);
        const host = doc.getElementById('hr-adoption');
        check('the operator sees each business with its people and what it has touched, names as text', /Acme <b>Ltd<\/b>/.test(host.textContent) && !host.querySelector('b') && /12/.test(host.textContent) && /1 of 2/.test(host.textContent));
    }
    console.log(failures === 0 ? '\nAll to-do and adoption checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
