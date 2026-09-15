/**
 * Recognition, on screen: the portal's shout-out card and its give
 * dialog; the HR page with its values, tiles and the one lever (remove);
 * the profile widget; the analytics block. Names and messages are
 * people's own words and are always rendered as text.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const RECENT = [
    { id: 5, from_id: 1, from: 'Ann <b>Lee</b>', to_id: 2, to: 'Bo Ray', message: 'Shipped <i>it</i>', value: 'Craft', created_at: '2026-09-15 10:00:00', mine: true },
    { id: 6, from_id: 2, from: 'Bo Ray', to_id: 1, to: 'Ann Lee', message: 'Thanks', value: '', created_at: '2026-09-14 10:00:00', mine: false },
];

function bootPortal(kudos, opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [], forms = [];
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/employee-dashboard.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.uiToast = () => { }; w.uiAlert = () => Promise.resolve(true); w.uiConfirm = () => Promise.resolve(true); w.uiPrompt = () => Promise.resolve('');
            w.uiForm = (fields) => { forms.push(fields); return Promise.resolve(opts.form === undefined ? null : opts.form); };
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                const method = (init && init.method) || 'GET';
                sent.push({ url: p, method, body: init && init.body });
                const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                if (p === '/api/employee/kudos' && method === 'GET') return give(kudos);
                if (p === '/api/employee/kudos' && method === 'POST') return give({ id: 9 });
                if (p.startsWith('/api/employee/kudos/') && method === 'DELETE') return give({ message: 'Withdrawn' });
                return give(p.endsWith('s') ? [] : {});
            };
        } });
    return { w: dom.window, doc: dom.window.document, sent, forms };
}

function bootHr(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/kudos' && method === 'GET') return give(opts.kudos || { kudos: RECENT, summary: {
            this_month: 2, last_month: 1, total_90d: 2, people_recognised_pct: 50, never_recognised: ['Cy <u>Dee</u>'],
            top_recognised: [{ employee_id: 2, name: 'Bo Ray', count: 1 }], top_givers: [{ employee_id: 1, name: 'Ann <b>Lee</b>', count: 1 }],
            by_value: [{ value: 'Craft', count: 1 }], values: ['Craft', 'Care'] } });
        if (p === '/api/kudos/values' && method === 'PUT') return give({ values: ['Grit', 'Care'] });
        if (p.startsWith('/api/kudos/') && method === 'DELETE') return give({ message: 'Removed' });
        if (p === '/api/employees/7/kudos') return give({ received: [RECENT[0]], received_count: 3, given_count: 1 });
        if (p === '/api/employees/7' && method === 'GET') return give({ id: 7, full_name: 'Bo Ray', first_name: 'Bo', last_name: 'Ray', status: 'active', probation: { status: '' },
            custom_fields: [], payslips: [], onboarding_items: [], leave_requests: [], goals: [], documents: [], attendance_summary: {}, leave_balance: {} });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    w.loadHRStats = () => { };
    return { w, doc: w.document, sent };
}

(async () => {
    // --- portal ---
    {
        const { w, doc } = bootPortal({ recent: RECENT, received: 1, given: 1, values: ['Craft'], people: [{ id: 2, name: 'Bo Ray' }] });
        await w.loadKudos();
        await wait(30);
        const host = doc.getElementById('kudosList');
        const text = host.textContent;
        check('the card lists who thanked whom, the value as a tag, and the words as text',
            /Ann <b>Lee<\/b>/.test(text) && /Shipped <i>it<\/i>/.test(text) && !host.querySelector('b, i') && /Craft/.test(text) && host.children.length === 2, text.slice(0, 200));
        check('  my own carries a withdraw button and the other does not', host.children[0].querySelector('button') && !host.children[1].querySelector('button'));
        check('  and the header carries my tallies', /1 received, 1 given/.test(doc.getElementById('kudosMine').textContent));
        check('the card is always shown, so the button is the invitation', !doc.getElementById('kudosCard').hidden && doc.getElementById('kudosGiveBtn'));
    }
    {
        const { w, doc } = bootPortal({ recent: [], received: 0, given: 0, values: [], people: [] });
        await w.loadKudos();
        await wait(30);
        check('with none yet the card says so and asks for one', /Nobody has been thanked yet/.test(doc.getElementById('kudosList').textContent) && doc.getElementById('kudosMine').textContent === '');
    }
    {
        const { w, sent, forms } = bootPortal({ recent: [], received: 0, given: 0, values: ['Craft', 'Care'], people: [{ id: 2, name: 'Bo Ray' }, { id: 3, name: 'Cy Dee' }] },
            { form: { to: '3', value: 'Care', message: 'Held the fort.' } });
        await w.giveKudos();
        await wait(30);
        const f = forms[0];
        check('giving opens a form: who (everyone but me), which value, what they did',
            f && f.length === 3 && f[0].name === 'to' && f[0].options.length === 2 && f[1].name === 'value' && f[1].options.length === 3 && f[2].type === 'textarea', f && JSON.stringify(f.map(x => x.name)));
        const post = sent.find(s => s.url === '/api/employee/kudos' && s.method === 'POST');
        check('  and posts the person as a number with the value and the words', post && JSON.stringify(bodyOf(post)) === '{"to_employee_id":3,"message":"Held the fort.","value":"Care"}', post && post.body);
        check('  then reloads the card', sent.filter(s => s.url === '/api/employee/kudos' && s.method === 'GET').length >= 2);
    }
    {
        const { w, forms } = bootPortal({ recent: [], received: 0, given: 0, values: [], people: [{ id: 2, name: 'Bo Ray' }] }, { form: null });
        await w.giveKudos();
        await wait(20);
        check('with no company values the form has no value question', forms[0] && forms[0].length === 2 && forms[0].every(x => x.name !== 'value'));
    }
    {
        const { w, sent } = bootPortal({ recent: RECENT, received: 0, given: 1, values: [], people: [] });
        await w.withdrawKudos(5);
        await wait(20);
        check('withdrawing asks, then deletes mine', sent.some(s => s.url === '/api/employee/kudos/5' && s.method === 'DELETE'));
    }
    {
        const src = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        check('the overview tab loads the card', /if \(tab === 'overview'\) \{[^\n]*loadKudos\(\);/.test(src));
    }

    // --- HR app ---
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the People menu has a Recognition entry and the page exists', /id="nav-recognition"[^\n]*mega-label">Recognition</.test(src) && /id="recognition-view"/.test(src) && /id="emp-kudos-list"/.test(src));
    }
    {
        const { w, doc, sent } = bootHr();
        check('the route and nav maps know the page', w.ROUTE_SLUGS['recognition-view'] === 'recognition' && w.VIEW_FOR_SLUG.recognition === 'recognition-view');
        await w.loadRecognitionView();
        await wait(40);
        const tiles = doc.getElementById('kudos-tiles').textContent;
        check('the tiles say this month against last, the share thanked, the most thanked and the most generous',
            /This month/.test(tiles) && /up from 1 last month/.test(tiles) && /50%/.test(tiles) && /Bo Ray/.test(tiles) && /Ann <b>Lee<\/b>/.test(tiles) && !doc.getElementById('kudos-tiles').querySelector('b'), tiles);
        check('the values box carries the business\'s words', doc.getElementById('kudos-values').value === 'Craft, Care');
        check('  and a bar per value named', /Craft/.test(doc.getElementById('kudos-values-chart').textContent));
        const sm = doc.getElementById('kudos-summary');
        check('the summary names the most thanked, most generous, and who has not been thanked, as text', /Bo Ray/.test(sm.textContent) && /Cy <u>Dee<\/u>/.test(sm.textContent) && !sm.querySelector('u'));
        const list = doc.getElementById('kudos-list');
        check('every shout-out is listed with words as text and a remove button', list.querySelectorAll('[data-kudos-remove]').length === 2 && /Shipped <i>it<\/i>/.test(list.textContent) && !list.querySelector('i'));
        list.querySelector('[data-kudos-remove="5"]').click();
        await wait(40);
        check('  removing asks, deletes, and reloads', sent.some(s => s.url === '/api/kudos/5' && s.method === 'DELETE') && sent.filter(s => s.url === '/api/kudos' && s.method === 'GET').length === 2);
    }
    {
        const { w, doc, sent } = bootHr({ confirm: false });
        await w.loadRecognitionView();
        await wait(30);
        doc.querySelector('[data-kudos-remove="5"]').click();
        await wait(30);
        check('backing out of the removal deletes nothing', !sent.some(s => s.method === 'DELETE'));
        doc.getElementById('kudos-values').value = 'Grit, Care';
        await w.saveCompanyValues();
        await wait(20);
        const put = sent.find(s => s.url === '/api/kudos/values' && s.method === 'PUT');
        check('saving the values sends the box as typed and shows them back as kept', put && bodyOf(put).values === 'Grit, Care' && doc.getElementById('kudos-values').value === 'Grit, Care');
    }
    {
        const { w, doc } = bootHr();
        w.currentEmployeeId = 7;
        await w.viewEmployee(7);
        await wait(80);
        const host = doc.getElementById('emp-kudos-list');
        check('the profile shows what colleagues said, as text, with the tallies', /Ann <b>Lee<\/b>/.test(host.textContent) && !host.querySelector('b') && /Shipped/.test(host.textContent) && /3 received · 1 given/.test(doc.getElementById('emp-kudos-count').textContent));
    }
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        check('analytics carries a Recognition block from the same numbers', /block\('Recognition', \[[^\]]*a\.recognition\.this_month/.test(src) && /people_recognised_pct \+ '%'/.test(src));
    }
    console.log(failures === 0 ? '\nAll recognition checks passed.' : `\n${failures} recognition check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
