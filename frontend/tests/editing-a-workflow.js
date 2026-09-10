/**
 * Changing a checklist after you have written it.
 *
 * There was no way to. A workflow could be created, switched on and off, and
 * deleted - and deleting is refused once it has run for somebody, because the
 * tasks it made are still theirs. So the first version anybody wrote was the
 * one they kept: a typo in a step meant leaving it wrong or turning the whole
 * thing off.
 *
 * Two things this form was quietly losing on the way to the server, both
 * found while wiring the edit path:
 *
 *   - owner_employee_id. The step builder collected it and the payload did
 *     not carry it, so picking "a named person" sent a step with nobody named
 *     and the server stored it as HR's. The dropdown looked like it worked.
 *   - notes. There is no field for them on this form, and the reader rebuilt
 *     every step from the inputs it could see - so renaming a workflow would
 *     have blanked the notes on all of its steps.
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

const EMPLOYEES = [
    { id: 7, first_name: 'Jo', last_name: 'Tech' },
    { id: 8, first_name: 'Ada', last_name: 'Chief' },
];

function aWorkflow(over) {
    return Object.assign({
        id: 3, name: 'New starter', description: '', trigger: 'employee_joins',
        trigger_label: 'When somebody joins', active: true,
        step_count: 2, run_count: 0,
        steps: [
            { id: 1, position: 0, title: 'Order a laptop', owner: 'hr',
              owner_employee_id: null, due_offset_days: -3, notes: '16GB, not 8' },
            { id: 2, position: 1, title: 'Book an induction', owner: 'manager',
              owner_employee_id: null, due_offset_days: 1, notes: '' },
        ],
    }, over || {});
}

function boot(workflow) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET',
                    body: init && init.body });
        const give = b => Promise.resolve({ ok: true, status: 200,
                                            json: () => Promise.resolve(b) });
        if (/^\/api\/workflows\/\d+$/.test(p) && (!init || !init.method || init.method === 'GET')) {
            return give(workflow);
        }
        return give({ ok: true, id: 3 });
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.allEmployees = EMPLOYEES;
    w.showToast = () => { };
    return { w, doc: w.document, sent };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- there is a way in at all ---------------------------------------------
    {
        const { w } = boot(aWorkflow());
        const row = w.workflowRow(aWorkflow({ run_count: 4 }));
        check('a workflow that has run offers Edit', /editWorkflow\(3\)/.test(row),
            'without it a typo in a step is permanent');
        // Deleting is refused once it has run, which is what made this the
        // only way to correct one.
        check('  and still does not offer Delete', !/removeWorkflow/.test(row));
        check('one that has never run offers both',
            /editWorkflow\(3\)/.test(w.workflowRow(aWorkflow())) &&
            /removeWorkflow/.test(w.workflowRow(aWorkflow())));
    }

    // --- it opens filled in -----------------------------------------------------
    {
        const { w, doc, sent } = boot(aWorkflow());
        await w.editWorkflow(3);
        await wait(30);

        check('opening it reads the workflow back',
            sent.some(s => s.url === '/api/workflows/3'),
            'the row carries a step count, not the steps');
        check('the modal says it is an edit',
            doc.getElementById('wf-modal-title').textContent === 'Edit workflow');
        check('the save button says so too',
            doc.getElementById('wf-save-btn').textContent === 'Save changes');
        check('the name is filled in',
            doc.getElementById('wf-name').value === 'New starter');
        check('the trigger is filled in',
            doc.getElementById('wf-trigger').value === 'employee_joins');

        check('both steps are there',
            doc.getElementById('wf-title-0').value === 'Order a laptop' &&
            doc.getElementById('wf-title-1').value === 'Book an induction');
        check('  with the owner each was given',
            doc.getElementById('wf-owner-1').value === 'manager');
        check('  and the days, negative ones included',
            doc.getElementById('wf-days-0').value === '-3');
    }

    // --- what the form was dropping ----------------------------------------------
    {
        const { w, doc, sent } = boot(aWorkflow());
        await w.editWorkflow(3);
        await wait(30);
        await w.saveWorkflow();
        await wait(30);

        const put = sent.find(s => s.method === 'PUT');
        check('saving an edit goes to the workflow itself', !!put && put.url === '/api/workflows/3',
            sent.map(s => s.method + ' ' + s.url).join(', '));
        check('  as a PUT, not a second POST',
            !sent.some(s => s.method === 'POST'));

        const steps = (bodyOf(put).steps) || [];
        check('the steps go back unchanged', steps.length === 2, JSON.stringify(steps));
        // The reader rebuilds each step from the inputs on the form, and there
        // is no input for notes.
        check('  carrying notes there is no field for',
            steps[0] && steps[0].notes === '16GB, not 8', JSON.stringify(steps[0]));
    }

    {
        const { w, doc, sent } = boot(aWorkflow());
        await w.editWorkflow(3);
        await wait(30);
        // Aim the first step at a named person, the way the dropdown does.
        doc.getElementById('wf-owner-0').value = 'person';
        w.onWorkflowOwnerChange(0);
        await wait(20);
        doc.getElementById('wf-person-0').value = '7';
        await w.saveWorkflow();
        await wait(30);

        const step = ((bodyOf(sent.find(s => s.method === 'PUT')).steps) || [])[0];
        check('a named person reaches the server',
            step && step.owner === 'person' && step.owner_employee_id === 7,
            JSON.stringify(step));
    }

    // --- the trigger, once it has run ---------------------------------------------
    {
        const { w, doc, sent } = boot(aWorkflow({ run_count: 4 }));
        await w.editWorkflow(3);
        await wait(30);

        // It fires once per person ever, so moving it would leave it
        // permanently dead for everybody it has run for.
        check('a workflow that has run cannot be re-pointed',
            doc.getElementById('wf-trigger').disabled === true);
        check('  and the reason is on screen',
            doc.getElementById('wf-trigger-locked').style.display === 'block');
        check('  which says what to do instead',
            // The note wraps in the markup, so whitespace is collapsed before
            // looking for the sentence in it.
            /new workflow/i.test(
                doc.getElementById('wf-trigger-locked').textContent.replace(/\s+/g, ' ')),
            doc.getElementById('wf-trigger-locked').textContent);

        await w.saveWorkflow();
        await wait(30);
        const body = bodyOf(sent.find(s => s.method === 'PUT'));
        // A disabled select still has a value, and sending it back would be
        // refused by the server as a trigger change.
        check('  and the trigger is left out of the save',
            !('trigger' in body), JSON.stringify(body));
    }

    {
        const { w, doc, sent } = boot(aWorkflow({ run_count: 0 }));
        await w.editWorkflow(3);
        await wait(30);
        check('one that has never run can still be re-pointed',
            doc.getElementById('wf-trigger').disabled === false);
        check('  with nothing to explain away',
            doc.getElementById('wf-trigger-locked').style.display === 'none');

        await w.saveWorkflow();
        await wait(30);
        check('  and the trigger is sent',
            bodyOf(sent.find(s => s.method === 'PUT')).trigger === 'employee_joins');
    }

    // --- creating still creates ------------------------------------------------------
    {
        const { w, doc, sent } = boot(aWorkflow());
        // Opened for editing first, so the form is dirty - this is the case
        // that leaves a New button silently saving over an existing workflow.
        await w.editWorkflow(3);
        await wait(30);
        w.openWorkflowModal();
        await wait(20);

        check('opening New after an edit clears the name',
            doc.getElementById('wf-name').value === '');
        check('  and the title goes back',
            doc.getElementById('wf-modal-title').textContent === 'New workflow');
        check('  and the trigger is usable again',
            doc.getElementById('wf-trigger').disabled === false);

        doc.getElementById('wf-name').value = 'Leaver';
        doc.getElementById('wf-title-0').value = 'Collect the laptop';
        await w.saveWorkflow();
        await wait(30);

        // Saving reloads the list, so the last call is that GET rather than
        // the save itself.
        const saved = sent.filter(s => s.method === 'POST' || s.method === 'PUT');
        check('and it creates rather than overwriting what was open',
            saved.length === 1 && saved[0].method === 'POST' &&
            saved[0].url === '/api/workflows',
            saved.map(s => s.method + ' ' + s.url).join(', '));
    }

    console.log(failures === 0
        ? '\nAll workflow-editing checks passed.'
        : `\n${failures} workflow-editing check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
