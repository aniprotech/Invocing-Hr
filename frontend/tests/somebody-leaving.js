/**
 * The leaving panel, as drawn.
 *
 * The checklist is the server's; this only draws it and refuses to let the
 * door close while it says not to. Two things it has to get right: the
 * override is only offered when there is something to override, and when it
 * is taken it insists on a reason - because a laptop written off is a
 * decision and goes on the record as one.
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

const BLOCKED = {
    employee_id: 7, name: 'Dana Boss', status: 'offboarding', end_date: '',
    assets_out: [{ asset_id: 1, tag: 'LAP-014', name: 'MacBook Air', issued_at: '2026-01-12' }],
    leave_owed_days: 4.5, expenses_owed: 42.8, currency: 'GBP',
    open_tasks: [{ id: 1, title: 'Collect the door fob', due_date: '2026-09-30', assignee: 'hr' }],
    direct_reports: [{ id: 2, name: 'Sam Mine' }, { id: 3, name: 'Lee Mine' }],
    decisions_waiting_on_them: 1,
    portal_access: true,
    blocking: ['1 item(s) of equipment not returned', '1 decision(s) waiting on them for their team'],
    ready: false,
};
const READY = Object.assign({}, BLOCKED, {
    assets_out: [], decisions_waiting_on_them: 0, open_tasks: [], blocking: [], ready: true,
});

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), {
        runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html',
    });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({
            ok: !status || status < 400, status: status || 200, json: () => Promise.resolve(b) });
        if (/\/offboarding$/.test(p)) return give(opts.checklist || BLOCKED);
        if (/\/complete-offboard$/.test(p)) {
            if (opts.refused) return give({ detail: 'Not ready: 1 item(s) of equipment not returned. Sort these out, or confirm you want to go ahead anyway.' }, 409);
            return give({ message: 'Employee offboarded', reports_moved: 2 });
        }
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.allEmployees = [
        { id: 7, first_name: 'Dana', last_name: 'Boss', status: 'offboarding' },
        { id: 9, first_name: 'New', last_name: 'Boss', status: 'active' },
        { id: 4, first_name: 'Old', last_name: 'Gone', status: 'terminated' },
    ];
    w.currentEmployeeId = 7;
    w.showToast = () => { };
    w.hrDataChanged = () => { };
    w.uiConfirm = () => Promise.resolve(opts.confirm !== false);
    return { w, doc: w.document, sent };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- shown only for somebody on their way out -------------------------------
    {
        const { w, doc } = boot();
        await w.loadOffboarding({ id: 7, status: 'active' });
        await wait(20);
        check('somebody active does not see the leaving panel',
            doc.getElementById('offboarding-widget').style.display === 'none');
        await w.loadOffboarding({ id: 7, status: 'terminated' });
        await wait(20);
        check('nor somebody already gone',
            doc.getElementById('offboarding-widget').style.display === 'none');
    }

    // --- the checklist, drawn -----------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        check('somebody offboarding sees it', doc.getElementById('offboarding-widget').style.display !== 'none');
        check('it asks the server for the checklist', sent.some(s => /\/employees\/7\/offboarding$/.test(s.url)));

        const text = doc.getElementById('offb-checklist').textContent;
        check('it says what is still out, by tag', /LAP-014/.test(text) && /MacBook Air/.test(text), text);
        check('  and what is waiting on them', /1 decision/.test(text));
        check('  and who reports to them', /Sam Mine/.test(text) && /Lee Mine/.test(text));
        check('  and the leave to settle', /4\.5 day/.test(text));
        check('  and the money owed', /£42\.80/.test(text));
        check('  and that they can still sign in', /still sign in/.test(text));
        check('the state says not ready', /Not ready/.test(doc.getElementById('offb-state').textContent));
    }

    // --- the override is only offered when there is something to override -----------
    {
        const { w, doc } = boot();
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        check('with things blocking, the override is offered',
            doc.getElementById('offb-force-box').style.display !== 'none');
        check('  but the reason box stays hidden until it is ticked',
            doc.getElementById('offb-force-note').style.display === 'none');
        doc.getElementById('offb-force').checked = true;
        doc.getElementById('offb-force').onchange.call(doc.getElementById('offb-force'));
        check('  and appears when it is', doc.getElementById('offb-force-note').style.display !== 'none');
    }
    {
        const { w, doc } = boot({ checklist: READY });
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        check('with nothing blocking, there is no override to offer',
            doc.getElementById('offb-force-box').style.display === 'none');
        check('  and the state says ready', /Ready/.test(doc.getElementById('offb-state').textContent));
    }

    // --- who can take their team ----------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        const opts = [...doc.getElementById('offb-reassign').options].map(o => o.textContent);
        check('the successor list has the others', opts.includes('New Boss'));
        check('  not the person leaving', !opts.includes('Dana Boss'));
        check('  and not somebody who has already left', !opts.includes('Old Gone'));
    }

    // --- closing the door -----------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ checklist: READY });
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        doc.getElementById('offb-end').value = '2026-09-30';
        doc.getElementById('offb-reassign').value = '9';
        await w.completeOffboarding();
        await wait(30);
        const call = sent.find(s => /\/complete-offboard$/.test(s.url));
        check('closing sends the last day and the successor', !!call, sent.map(s => s.url).join(', '));
        const b = bodyOf(call || {});
        check('  as typed', b.end_date === '2026-09-30' && b.reassign_to === '9', JSON.stringify(b));
        check('  without forcing when nothing needed it', b.force === false);
    }
    {
        const { w, doc, sent } = boot({ confirm: false, checklist: READY });
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        doc.getElementById('offb-end').value = '2026-09-30';
        await w.completeOffboarding();
        await wait(30);
        check('but not without asking first', !sent.some(s => /\/complete-offboard$/.test(s.url)));
    }
    {
        const { w, doc, sent } = boot();
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        doc.getElementById('offb-end').value = '2026-09-30';
        doc.getElementById('offb-force').checked = true;
        doc.getElementById('offb-force-note').value = 'Laptop written off, insurer told';
        await w.completeOffboarding();
        await wait(30);
        const b = bodyOf(sent.find(s => /\/complete-offboard$/.test(s.url)) || {});
        check('going ahead anyway sends the reason with it',
            b.force === true && b.force_note === 'Laptop written off, insurer told', JSON.stringify(b));
    }
    {
        const { w, doc } = boot({ refused: true });
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        doc.getElementById('offb-end').value = '2026-09-30';
        await w.completeOffboarding();
        await wait(30);
        const err = doc.getElementById('offb-error');
        check('a refusal shows the reason the server gave',
            err.style.display === 'block' && /equipment not returned/.test(err.textContent), err.textContent);
    }
    {
        const { w, doc, sent } = boot({ checklist: READY });
        await w.loadOffboarding({ id: 7, status: 'offboarding' });
        await wait(30);
        doc.getElementById('offb-end').value = '';
        await w.completeOffboarding();
        await wait(20);
        check('no last day is stopped on the page', !sent.some(s => /\/complete-offboard$/.test(s.url)));
    }

    console.log(failures === 0
        ? '\nAll leaving-panel checks passed.'
        : `\n${failures} leaving-panel check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
