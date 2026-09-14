/**
 * The dialogs, and the guard that keeps the raw ones out.
 *
 * alert(), confirm() and prompt() freeze the tab, cannot be styled, and on
 * a phone put the page's origin above the message. dialogs.js replaced them
 * and every page loads it - and then thirty-one call sites used the raw ones
 * anyway, and a text prompt was being used as a picker: "1. Dana  2. Sam,
 * type the number".
 *
 * Two things here. The new pieces work: a chooser that is a select, a form
 * that is a form, a toast that goes away on its own, and a palette that
 * follows the page rather than assuming it is dark. And a guard: no file
 * that is not dialogs.js itself, and not a test, calls the raw ones.
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

function boot(bodyBg) {
    const dom = new JSDOM(
        `<body style="background:${bodyBg || '#0b1220'}"><button id="opener">open</button></body>`,
        { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/x.html' });
    const w = dom.window;
    w.requestAnimationFrame = fn => setTimeout(fn, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    return { w, doc: w.document };
}

(async () => {
    // --- the file itself is clean -------------------------------------------------
    {
        // CRLF is what git gives a Windows checkout and is fine. The corruption
        // that was here was a doubled carriage return - CR CR LF - inside the
        // CSS template literal, which put stray characters into the stylesheet.
        const raw = fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8');
        check('dialogs.js carries no doubled carriage returns',
            !/\r\r/.test(raw), 'the CSS template literal would contain them at runtime');
    }

    // --- choosing -------------------------------------------------------------------
    {
        const { w, doc } = boot();
        const p = w.uiChoose('Issue LAP-014 to which person?',
            [{ value: 7, label: 'Dana Boss' }, { value: 9, label: 'Sam Staff' }],
            { title: 'Issue equipment' });
        await wait(20);
        const sel = doc.querySelector('.ui-dialog select');
        check('a chooser is a select, not a text box', !!sel && !doc.querySelector('.ui-dialog input'));
        check('  with the options given', sel && [...sel.options].map(o => o.textContent).join('|') === 'Dana Boss|Sam Staff');
        sel.value = '9';
        doc.querySelector('.ui-dialog-btn.is-go').click();
        check('  and resolves to the chosen value', String(await p) === '9');
    }
    {
        const { w, doc } = boot();
        const p = w.uiChoose('Condition?', ['good', 'fair', 'poor'], { placeholder: 'Pick one' });
        await wait(20);
        doc.querySelector('.ui-dialog-btn.is-go').click();
        await wait(20);
        check('choosing nothing is stopped in the dialog',
            doc.querySelector('.ui-dialog-error').classList.contains('is-shown') && !!doc.querySelector('.ui-dialog'));
        doc.querySelector('.ui-dialog-btn.is-cancel').click();
        check('  and backing out resolves null', (await p) === null);
    }

    // --- a form -----------------------------------------------------------------------
    {
        const { w, doc } = boot();
        const p = w.uiForm([
            { name: 'title', label: 'Task', type: 'text', required: true },
            { name: 'category', label: 'Category', type: 'select', options: ['Legal', 'IT'], value: 'IT' },
            { name: 'due', label: 'Due', type: 'date' },
            { name: 'notes', label: 'Notes', type: 'textarea' },
        ], { title: 'New task' });
        await wait(20);
        const fields = doc.querySelectorAll('.ui-dialog-field');
        check('a form draws every field, labelled', fields.length === 4 &&
            [...fields].every(f => f.querySelector('label')));
        check('  a date field is a date input', doc.querySelector('.ui-dialog input[type=date]') !== null);
        check('  a select keeps its preset value', doc.querySelector('.ui-dialog select').value === 'IT');

        doc.querySelector('.ui-dialog-btn.is-go').click();
        await wait(20);
        check('a required field left empty is said in the dialog',
            /Task is needed/.test(doc.querySelector('.ui-dialog-error').textContent),
            doc.querySelector('.ui-dialog-error').textContent);
        check('  and focus goes to it', doc.activeElement === doc.querySelector('#ui-dialog-f0'));

        doc.querySelector('#ui-dialog-f0').value = 'Sign the contract';
        doc.querySelector('#ui-dialog-f2').value = '2026-10-01';
        doc.querySelector('#ui-dialog-f3').value = 'Two copies';
        doc.querySelector('.ui-dialog-btn.is-go').click();
        const out = await p;
        check('  and resolves to an object with every answer',
            out && out.title === 'Sign the contract' && out.category === 'IT' &&
            out.due === '2026-10-01' && out.notes === 'Two copies', JSON.stringify(out));
    }
    {
        const { w, doc } = boot();
        w.uiForm([{ name: 'notes', label: 'Notes', type: 'textarea' }]);
        await wait(20);
        const ta = doc.querySelector('.ui-dialog textarea');
        ta.focus();
        const ev = new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
        doc.dispatchEvent(ev);
        await wait(20);
        check('Enter in a textarea is a new line, not Send', !!doc.querySelector('.ui-dialog'));
    }

    // --- the old ones still work the old way ----------------------------------------------
    {
        const { w, doc } = boot();
        const p = w.uiPrompt('Name?', 'Dana');
        await wait(20);
        check('a prompt still has one text box preset', doc.querySelector('.ui-dialog input').value === 'Dana');
        doc.querySelector('.ui-dialog input').value = 'Sam';
        doc.querySelector('.ui-dialog-btn.is-go').click();
        check('  and still resolves to the string', (await p) === 'Sam');
    }
    {
        const { w, doc } = boot();
        const p = w.uiConfirm('Sure?');
        await wait(20);
        doc.querySelector('.ui-dialog-btn.is-cancel').click();
        check('a confirm still resolves false on cancel', (await p) === false);
    }

    // --- the palette follows the page -----------------------------------------------------
    {
        const { w, doc } = boot('#ffffff');
        w.uiAlert('Hello');
        await wait(20);
        check('on a light page the dialog is light', doc.querySelector('.ui-dialog-scrim').classList.contains('is-light'));
    }
    {
        const { w, doc } = boot('#0b1220');
        w.uiAlert('Hello');
        await wait(20);
        check('on a dark page it is not', !doc.querySelector('.ui-dialog-scrim').classList.contains('is-light'));
    }

    // --- a toast ------------------------------------------------------------------------------
    {
        const { w, doc } = boot('#ffffff');
        w.uiToast('Saved.', 'success', 200);
        await wait(20);
        const t = doc.querySelector('.ui-toast');
        check('a toast appears', !!t && t.textContent === 'Saved.');
        check('  with its kind', t.classList.contains('is-success'));
        check('  matching the page', t.classList.contains('is-light'));
        check('  and blocks nothing', !doc.querySelector('.ui-dialog-scrim'));
        await wait(500);
        check('  and goes away on its own', !doc.querySelector('.ui-toast'));
    }

    // --- the guard: nothing outside dialogs.js uses the raw ones -----------------------------
    {
        const RAW = /(^|[^.\w$])(alert|confirm|prompt)\s*\(/;
        const offenders = [];
        const scan = (file) => {
            const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
            // Split on either line ending: "." does not match a carriage return,
            // so on a CRLF file the comment stripper below would miss the end of
            // the line and flag the word prompt() inside a comment.
            src.split(/\r?\n/).forEach((line, i) => {
                const code = line.replace(/\/\/.*$/, '');      // not comments
                if (RAW.test(code) && !/uiAlert|uiConfirm|uiPrompt|window\.(alert|confirm|prompt)\s*=|\bw\.(alert|confirm|prompt)/.test(code)) {
                    offenders.push(`${file}:${i + 1}`);
                }
            });
        };
        fs.readdirSync(ROOT).filter(f => /\.(js|html)$/.test(f) && f !== 'dialogs.js' && f !== 'tailwind.css')
            .forEach(scan);
        check('no page or script calls the browser\'s alert, confirm or prompt',
            offenders.length === 0, offenders.slice(0, 12).join(', ') + (offenders.length > 12 ? ` (+${offenders.length - 12})` : ''));
    }

    console.log(failures === 0
        ? '\nAll dialog checks passed.'
        : `\n${failures} dialog check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
