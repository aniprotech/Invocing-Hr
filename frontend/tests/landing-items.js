/**
 * Operator-managed entries on the public front page.
 *
 * The section headings were editable while the entries under them were written
 * into the HTML, so the FAQ could be renamed but not added to.
 *
 * Two things are worth checking. An empty section must leave the built-in
 * entries alone - if it blanked the section instead, deleting the last row
 * would empty the front page. And every value comes from a form an operator
 * types into, so it has to land as text: a headline containing a script tag
 * must show up as characters, not run.
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

const EMPTY = { module: [], industry: [], faq: [] };

function boot(items) {
    const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/index.html',
        beforeParse(w) {
            w.console.error = () => { };
            w.fetch = () => Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({
                    landing: { headline: 'Hello' },
                    items: Object.assign({}, EMPTY, items || {}),
                }),
            });
        },
    });
    return dom.window;
}

const grid = (w, id) => w.document.getElementById(id);

(async () => {
    // --- nothing configured ---------------------------------------------------
    {
        const w = boot({});
        await wait(200);
        const modules = grid(w, 'modules-grid');
        const faq = w.document.getElementById('faq-list');
        check('an empty modules section keeps the built-in cards',
            modules.querySelectorAll('.tile').length > 0,
            modules.querySelectorAll('.tile').length);
        check('and an empty FAQ keeps its built-in questions',
            faq.querySelectorAll('.faq-item').length > 0,
            faq.querySelectorAll('.faq-item').length);
    }

    // --- entries replace what ships -------------------------------------------
    {
        const w = boot({
            module: [{ id: 1, title: 'Payroll', body: 'Pay people.', icon: '💷' },
                     { id: 2, title: 'Invoicing', body: 'Get paid.', icon: '📄' }],
        });
        await wait(200);
        const tiles = grid(w, 'modules-grid').querySelectorAll('.tile');
        check('configured modules replace the built-in ones',
            tiles.length === 2, tiles.length);
        check('showing the title', /Payroll/.test(tiles[0].textContent));
        check('the description', /Pay people/.test(tiles[0].textContent));
        check('and the icon', /💷/.test(tiles[0].textContent));
    }

    {
        const w = boot({
            industry: [{ id: 3, title: 'Retail', body: 'Shops.', icon: '🛍' }],
        });
        await wait(200);
        check('industries are replaced independently of modules',
            grid(w, 'industries-grid').querySelectorAll('.tile').length === 1);
        check('while modules keep their built-in cards',
            grid(w, 'modules-grid').querySelectorAll('.tile').length > 1);
    }

    // --- the FAQ still behaves like a FAQ ---------------------------------------
    {
        const w = boot({
            faq: [{ id: 4, title: 'Do you do payroll?', body: 'Yes we do.' },
                  { id: 5, title: 'How much?', body: 'It depends.' }],
        });
        await wait(200);
        const items = w.document.getElementById('faq-list').querySelectorAll('.faq-item');
        check('configured questions replace the built-in ones', items.length === 2, items.length);

        const btn = items[0].querySelector('.faq-q');
        const answer = items[0].querySelector('.faq-a');
        check('an answer starts hidden', answer.hidden);
        check('and is announced closed', btn.getAttribute('aria-expanded') === 'false');

        btn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
        await wait(20);
        check('a rebuilt question still opens when clicked',
            !answer.hidden && btn.getAttribute('aria-expanded') === 'true');

        const second = items[1].querySelector('.faq-q');
        second.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
        await wait(20);
        check('and opening another closes the first',
            answer.hidden === true);
        check('the answer is joined to its question for a screen reader',
            answer.getAttribute('aria-labelledby') === btn.id);
    }

    // --- copy is copy, not markup ------------------------------------------------
    {
        const w = boot({
            module: [{ id: 6, icon: '', body: 'safe',
                       title: '<img src=x onerror="window.__pwned=1">' }],
            faq: [{ id: 7, title: 'Q', body: '<script>window.__pwned=1<\/script>' }],
        });
        await wait(250);
        check('a script in operator copy does not run', !w.__pwned);
        check('it is shown as the characters that were typed',
            /<img src=x/.test(grid(w, 'modules-grid').textContent),
            grid(w, 'modules-grid').textContent.slice(0, 60));
        check('and no element was created from it',
            grid(w, 'modules-grid').querySelectorAll('img').length === 0);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
