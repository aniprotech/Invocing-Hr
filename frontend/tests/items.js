/**
 * The item box on an invoice line.
 *
 * Every line was typed from scratch, so the same product got a slightly
 * different name, price and account each time it was billed. The box looks up
 * the saved catalogue now, fills the line from what it finds, and offers to
 * save what is not in it yet - from the line that needed it, rather than by
 * leaving a half-written invoice to go and set one up.
 *
 * The two things worth pinning: picking an item must not overwrite work
 * somebody has already done on that line, and creating one must land back on
 * the line it was created from.
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

const CATALOGUE = [
    { id: 7, code: 'BMW', name: 'BMW hire', description: 'Daily hire',
      sale_price: 250, sale_account: '200 - Sales', sale_tax_rate: 'No VAT',
      is_sold: true, is_purchased: false, is_active: true },
];

function boot(opts) {
    opts = opts || {};
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
    w.console.error = () => { };

    const sent = [];
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
        if (p === '/api/auth/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'me@x' }, client_id: 1 }) });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }) });
        }
        if (p === '/api/ai/describe-item') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve(opts.describeUnavailable
                    ? { available: false, description: '' }
                    : { available: true, description: opts.describe || 'A description.' }) });
        }
        if (p === '/api/items') {
            if ((init && init.method) === 'POST') {
                if (opts.saveError) {
                    return Promise.resolve({ ok: false, status: 400,
                        json: () => Promise.resolve({ detail: opts.saveError }) });
                }
                const body = JSON.parse(init.body);
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(Object.assign({ id: 99 }, body)) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ items: opts.catalogue || CATALOGUE }) });
        }
        const body = p.endsWith('s') ? [] : {};
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}') });
    };

    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

// The first line of the invoice form, as the app builds it.
function firstRow(w) {
    const body = w.document.getElementById('line-items-body');
    if (!body.querySelector('.line-item-row')) w.addLineItemRow('invoice');
    return body.querySelector('.line-item-row');
}

const val = (row, sel) => {
    const el = row.querySelector(sel);
    return el ? el.value : null;
};

(async () => {
    // --- the markup ----------------------------------------------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const doc = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
        check('the app ships the new-item modal', !!doc.getElementById('item-modal'));
        check('with a code, which is the handle people type',
            !!doc.getElementById('item-code'));
        check('and the sell/purchase choice from the brief',
            !!doc.getElementById('item-sell') && !!doc.getElementById('item-purchase'));
    }

    // --- the lookup ----------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        const row = firstRow(w);
        const input = row.querySelector('.item-name');

        input.value = 'bm';
        w.onItemBoxInput(input);
        await wait(250);

        check('typing asks the catalogue',
            sent.some(s => s.url === '/api/items' && s.method === 'GET'));

        const dropdown = row.querySelector('.item-lookup');
        check('the match is offered', /BMW/.test(dropdown.textContent), dropdown.textContent);
        check('and so is creating a new one',
            /Create new item/.test(dropdown.textContent));
        check('the dropdown is actually shown',
            dropdown.classList.contains('show'));
    }

    // --- picking one fills the line -------------------------------------------
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        w.applyItemToRow(row, CATALOGUE[0]);

        check('the name goes in the name box, not the code',
            val(row, '.item-name') === 'BMW hire', val(row, '.item-name'));
        check('and the description box gets the item own description',
            val(row, '.item-desc') === 'Daily hire', val(row, '.item-desc'));
        // The code identifies the item but is not what the customer is
        // reading, so it stays on the row rather than taking a column.
        check('the code is kept on the row rather than shown as the name',
            row.dataset.itemCode === 'BMW', row.dataset.itemCode);
        check('the price comes from the item', Number(val(row, '.item-price')) === 250,
            val(row, '.item-price'));
        check('a quantity of one is assumed rather than zero',
            Number(val(row, '.item-qty')) === 1, val(row, '.item-qty'));
        check('the account comes from the item',
            val(row, '.item-account') === '200 - Sales', val(row, '.item-account'));
    }

    // --- and does not throw away work already done on that line ---------------
    {
        const { w } = boot();
        await wait(80);
        const row = firstRow(w);
        row.querySelector('.item-desc').value = 'Hire for the Glasgow job';
        row.querySelector('.item-qty').value = '3';
        w.applyItemToRow(row, CATALOGUE[0]);

        check('a description already written is kept',
            val(row, '.item-desc') === 'Hire for the Glasgow job',
            val(row, '.item-desc'));
        check('and a quantity already entered is kept',
            Number(val(row, '.item-qty')) === 3, val(row, '.item-qty'));
    }

    // --- creating one from the line -------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        const row = firstRow(w);

        w.openItemModal(row, 'AUDI');
        check('the modal opens',
            w.document.getElementById('item-modal').style.display === 'flex');
        check('the code is carried over from what was typed',
            w.document.getElementById('item-code').value === 'AUDI',
            w.document.getElementById('item-code').value);
        check('the account list is the one the line itself offers',
            w.document.getElementById('item-sale-account').innerHTML ===
            row.querySelector('.item-account').innerHTML);

        w.document.getElementById('item-name').value = 'Audi hire';
        w.document.getElementById('item-sale-price').value = '180';
        sent.length = 0;
        await w.saveItem();

        const post = sent.find(s => s.url === '/api/items' && s.method === 'POST');
        check('saving posts the item', !!post);
        check('with what was filled in', !!post && (() => {
            const b = JSON.parse(post.body);
            return b.code === 'AUDI' && b.name === 'Audi hire' && b.sale_price === 180;
        })(), post && post.body);

        check('the modal closes',
            w.document.getElementById('item-modal').style.display === 'none');
        check('and the new item lands on the line it was created from',
            val(row, '.item-name') === 'Audi hire' && Number(val(row, '.item-price')) === 180,
            val(row, '.item-name') + ' / ' + val(row, '.item-price'));
    }

    // --- an item needs a code -------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(80);
        w.openItemModal(firstRow(w), '');
        w.document.getElementById('item-name').value = 'No code';
        sent.length = 0;
        await w.saveItem();

        check('saving without a code never reaches the server',
            !sent.some(s => s.method === 'POST'));
        check('and says why',
            /code/i.test(w.document.getElementById('item-modal-error').textContent),
            w.document.getElementById('item-modal-error').textContent);
    }

    // --- a refusal is explained, not swallowed --------------------------------
    {
        const { w } = boot({ saveError: "'BMW' is already in your items" });
        await wait(80);
        w.openItemModal(firstRow(w), 'BMW');
        w.document.getElementById('item-name').value = 'Duplicate';
        await w.saveItem();

        check("the server's reason is shown",
            /already in your items/.test(
                w.document.getElementById('item-modal-error').textContent),
            w.document.getElementById('item-modal-error').textContent);
        check('and the modal stays open so it can be fixed',
            w.document.getElementById('item-modal').style.display === 'flex');
    }

    // --- the AI description ---------------------------------------------------
    // Optional and metered, so it is a button. The AI being off or out of
    // credit must not stop somebody saving an item with a typed description.
    {
        const { w, sent } = boot({ describe: 'Daily hire of a BMW, collected from depot.' });
        await wait(80);
        w.openItemModal(firstRow(w), 'BMW-DAY');
        w.document.getElementById('item-name').value = 'BMW daily hire';
        sent.length = 0;
        await w.describeItemWithAi();

        const post = sent.find(s => s.url === '/api/ai/describe-item');
        check('it asks the AI endpoint', !!post);
        check('and gives it the name and code to work from', !!post && (() => {
            const b = JSON.parse(post.body);
            return b.text.includes('BMW daily hire') && b.text.includes('BMW-DAY');
        })(), post && post.body);
        check('the answer lands in the description box',
            w.document.getElementById('item-description').value
                === 'Daily hire of a BMW, collected from depot.',
            w.document.getElementById('item-description').value);
        check('and it says the words came from the AI, so they get checked',
            /ai/i.test(w.document.getElementById('item-ai-note').textContent),
            w.document.getElementById('item-ai-note').textContent);
    }

    {
        const { w, sent } = boot();
        await wait(80);
        w.openItemModal(firstRow(w), '');
        sent.length = 0;
        await w.describeItemWithAi();
        check('with nothing to describe it never asks, and never charges',
            !sent.some(s => s.url === '/api/ai/describe-item'));
        check('and says what is missing',
            /code or a name/i.test(w.document.getElementById('item-ai-note').textContent),
            w.document.getElementById('item-ai-note').textContent);
    }

    {
        // AI off, or out of credit. The description is optional, so this is a
        // note rather than a failure - the item still saves without one.
        const { w } = boot({ describeUnavailable: true });
        await wait(80);
        w.openItemModal(firstRow(w), 'BMW');
        await w.describeItemWithAi();
        check('the AI being unavailable is explained, not thrown',
            /not available/i.test(w.document.getElementById('item-ai-note').textContent),
            w.document.getElementById('item-ai-note').textContent);
        check('and the description box is left alone to be typed',
            w.document.getElementById('item-description').value === '');
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
