/**
 * The assets screen.
 *
 * A list of equipment is a spreadsheet. The reason anybody opens this page is
 * that somebody has left and nobody knows what they still have - so what is
 * out with a leaver is the thing the page has to lead with, and the rest is
 * inventory.
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

const ASSETS = [
    { id: 1, tag: 'LAP-001', name: 'MacBook Air 13', category: 'laptop',
      serial_number: 'C02X', status: 'available', state: 'available',
      condition: 'good', held_by: null },
    { id: 2, tag: 'LAP-002', name: 'ThinkPad X1', category: 'laptop',
      serial_number: '', status: 'assigned', state: 'available',
      condition: 'good',
      held_by: { employee_id: 7, name: 'Ada Reid', since: '2026-06-01', assignment_id: 3 } },
    { id: 3, tag: 'MON-001', name: 'Dell 27"', category: 'monitor',
      serial_number: '', status: 'retired', state: 'retired',
      condition: 'poor', held_by: null },
];

const SUMMARY = {
    counts: { total: 3, available: 1, assigned: 1, repair: 0, retired: 1 },
    still_out_with_leavers: [
        { asset_id: 2, tag: 'LAP-002', name: 'ThinkPad X1', employee_id: 7,
          employee: 'Ada Reid', employee_status: 'terminated', since: '2026-06-01' },
    ],
    value: 2400, currency: 'GBP',
};

function boot(overrides) {
    const bodies = Object.assign({
        '/api/assets': ASSETS,
        '/api/assets/summary': SUMMARY,
        '/api/employees': [
            { id: 7, first_name: 'Ada', last_name: 'Reid', full_name: 'Ada Reid', status: 'active' },
            { id: 8, first_name: 'Sam', last_name: 'Ali', full_name: 'Sam Ali', status: 'active' },
            { id: 9, first_name: 'Old', last_name: 'Hand', full_name: 'Old Hand', status: 'terminated' },
        ],
        '/api/client/me': { id: 1, email: 'me@example.com', modules: ['invoicing', 'hr'] },
        '/api/auth/me': { user: { email: 'me@example.com' }, client_id: 1 },
    }, overrides || {});

    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
        const body = Object.prototype.hasOwnProperty.call(bodies, p)
            ? bodies[p] : (p.endsWith('s') ? [] : {});
        const status = (body && body.__status) || 200;
        return Promise.resolve({
            ok: status < 400, status,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

(async () => {
    // --- the link is in the markup, before any script runs -------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const doc = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
        const link = doc.getElementById('nav-assets');
        check('the app ships an Assets link', !!link);
        check('it routes to #/assets',
            !!link && link.getAttribute('href') === '#/assets',
            link && link.getAttribute('href'));
        check('and the view it names exists', !!doc.getElementById('assets-view'));
    }

    // --- the list ------------------------------------------------------------
    {
        const { w } = boot();
        w.showView('assets-view');
        await wait(120);

        const list = w.document.getElementById('assets-list').textContent;
        check('equipment is listed', /LAP-001/.test(list) && /ThinkPad X1/.test(list));
        check('what is out says who has it', /Ada Reid/.test(list), list.slice(0, 140));
        check('and since when', /2026-06-01/.test(list));

        const stats = w.document.getElementById('asset-stats').textContent;
        check('the counts are shown', /3/.test(stats) && /Total/.test(stats), stats);
    }

    {
        // The headline: something out with somebody who has left.
        const { w } = boot();
        w.showView('assets-view');
        await wait(120);
        const chase = w.document.getElementById('asset-chase');
        check('a leaver still holding something is called out',
            chase.style.display !== 'none' && /LAP-002/.test(chase.textContent),
            chase.textContent.slice(0, 120));
        check('and it names who and for how long',
            /Ada Reid/.test(chase.textContent) && /2026-06-01/.test(chase.textContent));
        check('with a way to close it off',
            /takeAssetBack\(2/.test(chase.innerHTML));
    }

    {
        const { w } = boot({ '/api/assets/summary': {
            counts: { total: 1, available: 1, assigned: 0, repair: 0, retired: 0 },
            still_out_with_leavers: [], value: 0, currency: 'GBP' } });
        w.showView('assets-view');
        await wait(120);
        check('nothing outstanding hides the banner entirely',
            w.document.getElementById('asset-chase').style.display === 'none');
    }

    {
        const { w } = boot({ '/api/assets': [] });
        w.showView('assets-view');
        await wait(120);
        check('an empty inventory reads as empty, not broken',
            /no equipment/i.test(w.document.getElementById('assets-list').textContent),
            w.document.getElementById('assets-list').textContent.slice(0, 80));
    }

    {
        const { w } = boot({ '/api/assets': { __status: 500 } });
        w.showView('assets-view');
        await wait(120);
        check('a failed load says so rather than going blank',
            /could not load/i.test(w.document.getElementById('assets-list').textContent));
    }

    // --- what each row offers ------------------------------------------------
    {
        const { w } = boot();
        w.showView('assets-view');
        await wait(120);
        const html = w.document.getElementById('assets-list').innerHTML;
        check('something available can be issued', /issueAsset\(1/.test(html));
        check('something out can be taken back', /takeAssetBack\(2/.test(html));
        check('something retired offers neither',
            !/issueAsset\(3/.test(html) && !/takeAssetBack\(3/.test(html));
    }

    // --- issuing -------------------------------------------------------------
    {
        const { w, sent } = boot();
        w.showView('assets-view');
        await wait(120);

        // The dialog is ours now, so it is answered rather than stubbed away.
        const p = w.issueAsset(1, 'LAP-001');
        await wait(40);
        const scrim = w.document.querySelector('.ui-dialog-scrim');
        check('issuing asks who, in our own dialog', !!scrim);
        check('and lists the people it could go to',
            !!scrim && /Ada Reid/.test(scrim.textContent), scrim && scrim.textContent.slice(0, 90));
        check('somebody who has left is not offered',
            !!scrim && !/Old Hand/.test(scrim.textContent));

        scrim.querySelector('#ui-dialog-input').value = '1';
        scrim.querySelector('.ui-dialog-btn.is-go').click();
        await p;
        await wait(60);

        const post = sent.find(r => r.url === '/api/assets/1/assign');
        check('issuing posts to the right asset', !!post);
        check('naming the person chosen',
            !!post && JSON.parse(post.body).employee_id === 7,
            post && post.body);
    }

    {
        const { w, sent } = boot();
        w.showView('assets-view');
        await wait(120);
        const p = w.issueAsset(1, 'LAP-001');
        await wait(40);
        w.document.querySelector('.ui-dialog-scrim .ui-dialog-btn.is-cancel').click();
        await p;
        await wait(40);
        check('backing out of issuing sends nothing',
            !sent.some(r => r.url === '/api/assets/1/assign'));
    }

    // --- taking it back ------------------------------------------------------
    {
        const { w, sent } = boot();
        w.showView('assets-view');
        await wait(120);

        const p = w.takeAssetBack(2, 'LAP-002');
        await wait(40);
        const scrim = w.document.querySelector('.ui-dialog-scrim');
        check('taking something back asks what condition it is in',
            !!scrim && /condition/i.test(scrim.textContent), scrim && scrim.textContent.slice(0, 80));
        check('and it is pre-filled with the usual answer',
            !!scrim && scrim.querySelector('#ui-dialog-input').value === 'good');

        scrim.querySelector('#ui-dialog-input').value = 'damaged';
        scrim.querySelector('.ui-dialog-btn.is-go').click();
        await p;
        await wait(60);

        const post = sent.find(r => r.url === '/api/assets/2/return');
        check('it posts the condition it came back in',
            !!post && JSON.parse(post.body).condition === 'damaged', post && post.body);
    }

    {
        const { w, sent } = boot();
        w.showView('assets-view');
        await wait(120);
        const p = w.takeAssetBack(2, 'LAP-002');
        await wait(40);
        let scrim = w.document.querySelector('.ui-dialog-scrim');
        scrim.querySelector('#ui-dialog-input').value = 'fine';   // not a condition
        scrim.querySelector('.ui-dialog-btn.is-go').click();
        // Past the 160ms the closing dialog takes to leave the DOM, or the
        // outgoing prompt is picked up instead of the complaint.
        await wait(300);

        // The complaint is itself a dialog, so it has to be dismissed - and
        // there may briefly be two, so the live one is the last.
        var all = w.document.querySelectorAll('.ui-dialog-scrim');
        var complaint = all[all.length - 1];
        check('a condition that is not one of the four is refused',
            !!complaint && /good, fair, poor/i.test(complaint.textContent),
            complaint ? complaint.textContent.slice(0, 60) : 'no complaint shown');
        if (complaint) complaint.querySelector('.ui-dialog-btn.is-go').click();
        await p;
        await wait(60);
        check('and nothing is sent', !sent.some(r => r.url === '/api/assets/2/return'));
    }

    // --- adding one ----------------------------------------------------------
    {
        const { w, sent } = boot();
        w.showView('assets-view');
        await wait(120);

        w.openAssetModal();
        check('the add form opens',
            w.document.getElementById('asset-modal').style.display === 'flex');

        await w.saveAsset();
        await wait(40);
        check('a nameless, tagless asset never reaches the server',
            !sent.some(r => r.url === '/api/assets' && r.method === 'POST'));
        check('and the form says what is missing',
            /tag/i.test(w.document.getElementById('asset-error').textContent),
            w.document.getElementById('asset-error').textContent);

        w.document.getElementById('asset-tag').value = 'LAP-099';
        w.document.getElementById('asset-name').value = 'MacBook Pro';
        await w.saveAsset();
        await wait(60);
        const post = sent.find(r => r.url === '/api/assets' && r.method === 'POST');
        check('a complete one is saved', !!post);
        check('with what was typed',
            !!post && JSON.parse(post.body).tag === 'LAP-099', post && post.body);
        check('and the form closes',
            w.document.getElementById('asset-modal').style.display === 'none');
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
