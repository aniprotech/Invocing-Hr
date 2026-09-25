/**
 * Training partners and importing training.
 *
 * The panel on the Training screen names the platforms a business uses and
 * what each actually offers; choosing them saves; importing reads
 * certificates or a report, shows every row to be checked and corrected,
 * and files only what is ticked and complete. Nothing read is filed first.
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

const PARTNERS = [
    { key: 'caretutor', name: 'CareTutor', site: 'https://caretutor.org/', sign_in: 'https://caretutor.org/', api: 'available',
      api_note: 'API connectivity on their Pathway LMS plans.', export: 'Certificates can be downloaded in bulk.' },
    { key: 'florence', name: 'Florence Academy', site: 'https://www.florence.co.uk/florence-academy', sign_in: 'https://www.florence.co.uk/florence-academy',
      api: 'none published', api_note: 'No API published.', export: 'One-click Excel export.' },
    { key: 'custoris', name: 'Custoris Academy', site: '', sign_in: '', api: 'unknown',
      api_note: 'No public presence could be found - check them before relying on them.', export: 'Ask them.' },
];

const STAFF = [{ id: 1, first_name: 'Ann', last_name: 'Lee', status: 'active' }, { id: 2, first_name: 'Joann', last_name: 'Lee', status: 'active' },
               { id: 9, first_name: 'Gone', last_name: 'Away', status: 'terminated' }];

function boot(opts) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html#/training' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    let chosen = (opts && opts.chosen) || [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/training/partners' && method === 'PUT') { chosen = bodyOf({ body: init.body }).chosen; }
        if (p === '/api/training/partners') return give({ partners: PARTNERS.map(x => Object.assign({}, x, { chosen: chosen.includes(x.key) })), chosen });
        if (p === '/api/employees') return give(STAFF);
        if (p === '/api/training/certificates/read') return give({ certificates: [
            { file_name: 'ann.pdf', employee_id: 1, employee_name: 'Ann Lee', name: 'Moving and Handling', issuer: 'Florence Academy',
              issued_on: '2026-09-14', expires_on: '2027-09-14', reference: 'FA-1', missing: [], readable: true },
            { file_name: 'scan.pdf', employee_id: null, employee_name: '', name: '', issuer: '', issued_on: '', expires_on: '', reference: '',
              missing: ['who it belongs to', 'the course', 'the date it was completed'], readable: false, note: 'This PDF is a scanned picture - fill it in below.' },
            { file_name: 'notes.txt', problem: 'That certificate is not a PDF', readable: false }] });
        if (p === '/api/training/report/read') return give({ file_name: 'm.xlsx', shape: 'training matrix', skipped: 2, partner: 'florence',
            unmatched: [{ name: 'Zed <b>Nobody</b>', courses: 3 }],
            rows: [{ row: 2, employee_id: 2, employee_name: 'Joann Lee', name: 'Fire Safety', issuer: 'Florence Academy', issued_on: '2026-04-02', expires_on: '', reference: '' }] });
        if (p === '/api/training/import') return give({ created: bodyOf({ body: init.body }).items.length, courses_completed: 1, skipped: [], certificates: [] });
        if (p === '/api/certifications') return give({ certifications: [], counts: { valid: 0, expiring: 0, expired: 0, unverified: 0, total: 0 }, warn_days: 30 });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.uiAlert = () => Promise.resolve();
    // jsdom has no FileReader output for fake files; hand the reader what a browser would.
    w.FileReader = function () { this.readAsDataURL = (f) => { this.result = 'data:application/pdf;base64,JVBERi0x'; setTimeout(() => this.onload(), 0); }; };
    return { w, doc: w.document, sent };
}

const fakeFiles = names => names.map(n => ({ name: n }));

(async () => {
    // --- the panel ------------------------------------------------------------
    {
        const { w, doc } = boot({ chosen: [] });
        await w.loadTrainingPartners();
        const text = doc.getElementById('training-partners-list').textContent;
        check('with none chosen the panel asks which platforms staff train on', /Say which platforms your staff train on/.test(text), text);
    }
    {
        const { w, doc } = boot({ chosen: ['caretutor', 'florence'] });
        await w.loadTrainingPartners();
        const cards = doc.querySelectorAll('#training-partners-list [data-partner]');
        check('each chosen platform has a card', cards.length === 2, String(cards.length));
        check('  saying honestly what it offers', /API available/.test(cards[0].textContent) && /No API/.test(cards[1].textContent) && /Excel export/.test(cards[1].textContent));
        check('  with a way to sign in to it, opening in a new tab',
            cards[0].querySelector('a[href="https://caretutor.org/"][target="_blank"][rel="noopener"]'));
    }

    // --- choosing ------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ chosen: ['caretutor'] });
        await w.loadTrainingPartners();
        await w.openTrainingPartners();
        const boxes = doc.querySelectorAll('#training-partners-choices input[type="checkbox"]');
        check('the chooser lists every platform with what it offers', boxes.length === 3 && /check them before relying/.test(doc.getElementById('training-partners-choices').textContent));
        check('  with the ones in use already ticked', boxes[0].checked && !boxes[1].checked);
        boxes[1].checked = true;
        await w.saveTrainingPartners();
        await wait(10);
        const put = sent.find(s => s.url === '/api/training/partners' && s.method === 'PUT');
        check('Save sends the ticked platforms', put && JSON.stringify(bodyOf(put).chosen) === '["caretutor","florence"]', put && put.body);
        check('  and the panel then shows them', doc.querySelectorAll('#training-partners-list [data-partner]').length === 2);
    }

    // --- importing certificates ---------------------------------------------------------
    {
        const { w, doc, sent } = boot({});
        await w.openTrainingImport();
        await wait(10);
        check('import opens on certificates, taking several PDFs', doc.getElementById('training-import-file').multiple && /\.pdf/.test(doc.getElementById('training-import-file').accept));
        await w.readTrainingFiles(fakeFiles(['ann.pdf', 'scan.pdf', 'notes.txt']));
        await wait(20);
        const rows = doc.querySelectorAll('#training-import-preview tr[data-row]');
        check('every certificate is shown to be checked', rows.length === 3, String(rows.length));
        check('  a fully read one is ticked, with its person chosen', rows[0].querySelector('[data-f="include"]').checked && rows[0].querySelector('[data-f="employee_id"]').value === '1');
        check('  one that could not be read is not ticked, and says what to fill in',
            !rows[1].querySelector('[data-f="include"]').checked && /scanned picture/.test(rows[1].textContent));
        check('  one that is not a certificate cannot be ticked', rows[2].querySelector('[data-f="include"]').disabled && /not a PDF/.test(rows[2].textContent));
        check('  leavers are not offered as the person', ![...rows[1].querySelectorAll('option')].some(o => /Gone Away/.test(o.textContent)));
        check('the button counts what will be filed', doc.getElementById('training-import-go').textContent === 'Import 1');
        check('  and nothing is filed yet', !sent.some(s => s.url === '/api/training/import'));

        // Fill in the scanned one.
        const r = rows[1];
        const sel = r.querySelector('[data-f="employee_id"]'); sel.value = '2'; sel.dispatchEvent(new w.Event('change'));
        const nm = r.querySelector('[data-f="name"]'); nm.value = 'First Aid'; nm.dispatchEvent(new w.Event('change'));
        check('filling in who and what ticks it', r.querySelector('[data-f="include"]').checked && doc.getElementById('training-import-go').textContent === 'Import 2');
        const ed = rows[0].querySelector('[data-f="expires_on"]'); ed.value = '2028-01-01'; ed.dispatchEvent(new w.Event('change'));
        // Untick a complete row: it must stay behind.
        const inc = rows[1].querySelector('[data-f="include"]'); inc.checked = false; inc.dispatchEvent(new w.Event('change'));
        check('unticking a complete row leaves it out of the count', doc.getElementById('training-import-go').textContent === 'Import 1');
        inc.checked = true; inc.dispatchEvent(new w.Event('change'));

        await w.importTraining();
        await wait(20);
        const post = sent.find(s => s.url === '/api/training/import');
        const items = bodyOf(post || {}).items || [];
        check('Import sends only the ticked, complete rows', items.length === 2, items.length);
        check('  with the corrections made', items[0].expires_on === '2028-01-01' && items[1].employee_id === 2 && items[1].name === 'First Aid');
        check('  and the certificate itself', /^data:application\/pdf/.test(items[0].document_data));
        check('  then closes', doc.getElementById('training-import-modal').style.display === 'none');
    }

    // --- importing a report ------------------------------------------------------------------
    {
        const { w, doc } = boot({});
        await w.openTrainingImport();
        w.switchTrainingImport('report', doc.querySelector('#training-import-tabs [data-mode="report"]'));
        check('the report tab takes one Excel or CSV file', !doc.getElementById('training-import-file').multiple && /\.xlsx/.test(doc.getElementById('training-import-file').accept));
        await w.readTrainingFiles(fakeFiles(['m.xlsx']));
        await wait(20);
        const status = doc.getElementById('training-import-status');
        check('it says how the report was read and what was left out',
            /training matrix/.test(status.textContent) && /2 not completed/.test(status.textContent) && /Zed <b>Nobody<\/b> \(3\)/.test(status.textContent), status.textContent);
        check('  a name from the file is shown as text', !status.querySelector('b'));
        check('  and the completions are listed to check', doc.querySelectorAll('#training-import-preview tr[data-row]').length === 1);
    }

    // --- names are text ----------------------------------------------------------------
    {
        const { w, doc } = boot({});
        await w.openTrainingImport();
        await w.readTrainingFiles(fakeFiles(['ann.pdf']));
        await wait(20);
        const input = doc.querySelector('#training-import-preview [data-f="name"]');
        check('read values sit in inputs, never as markup', input && input.value === 'Moving and Handling' && !doc.querySelector('#training-import-preview script'));
    }

    console.log(failures ? `\n${failures} check(s) failed.` : '\nAll training partner checks passed.');
    process.exit(failures ? 1 : 0);
})();
