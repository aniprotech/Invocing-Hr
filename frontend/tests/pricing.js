/**
 * The pricing section, and why it has no tiers on it.
 *
 * The nav has said Pricing for as long as there has been a nav, and it landed
 * on a call-to-action card with no prices anywhere on it. There are also no
 * tiers to list: nothing here is a subscription. Every action draws from a
 * wallet, each has a price and a free monthly allowance.
 *
 * So the page reads the same rows that are actually charged rather than
 * restating them, and this checks that it does - a price list typed into a
 * page drifts from the one being billed, and the first person to notice is a
 * customer who has just paid something the site does not mention.
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

const PRICING = {
    currency: 'GBP', symbol: '£',
    actions: [
        { action_key: 'invoice_send', label: 'Send invoice by email',
          description: 'Charged when an invoice is emailed to a customer.',
          module: 'invoicing', unit_price: 0.05, free_allowance: 50 },
        { action_key: 'invoice_whatsapp', label: 'Send invoice on WhatsApp',
          description: 'Charged per WhatsApp message delivered.',
          module: 'invoicing', unit_price: 0.15, free_allowance: 0 },
        { action_key: 'payslip_send', label: 'Send payslip by email',
          description: '', module: 'hr', unit_price: 0.05, free_allowance: 50 },
        { action_key: 'ai_assistant', label: 'AI assistant question',
          description: '', module: 'platform', unit_price: 0.10, free_allowance: 30 },
    ],
    note: 'There is no monthly fee and no plan to choose. You add credit and each ' +
          'action draws from it, so a quiet month costs nothing.',
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/index.html',
        beforeParse(w) {
            w.fetch = (url) => {
                const p = String(url).split('?')[0];
                if (p === '/api/platform/pricing') {
                    return opts.fails
                        ? Promise.resolve({ ok: false, status: 500,
                            json: () => Promise.resolve({}) })
                        : Promise.resolve({ ok: true, status: 200,
                            json: () => Promise.resolve(opts.pricing || PRICING) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve({}), text: () => Promise.resolve('{}') });
            };
            w.console.error = () => { };
        },
    });
    return dom.window;
}

const groups = w => (w.document.getElementById('pricing-groups') || {}).textContent || '';

(async () => {
    // --- the nav item leads somewhere now -------------------------------------
    {
        const w = boot();
        await wait(80);
        check('the pricing anchor is a pricing section',
            !!w.document.getElementById('pricing'));
        const section = w.document.getElementById('pricing');
        check('with prices in it, not a call to action',
            /£0\.05/.test(section.textContent), groups(w).slice(0, 120));
    }

    // --- what is actually charged -----------------------------------------------
    {
        const w = boot();
        await wait(80);
        const out = groups(w);
        check('each action is named', /Send invoice by email/.test(out));
        check('with what it costs', /£0\.05/.test(out) && /£0\.15/.test(out));
        check('and what it is for', /emailed to a customer/.test(out));

        // The allowance decides whether this costs a small business anything
        // at all, so it is not a footnote.
        check('the free allowance is shown beside the price',
            /first 50 free each month/.test(out), out.slice(0, 200));
        check('and an action with none does not claim one',
            !/first 0 free/.test(out), out);
    }

    {
        const w = boot();
        await wait(80);
        const out = groups(w);
        // Grouped the way somebody thinks about them rather than in storage
        // order.
        check('actions are grouped by part of the product',
            /Invoicing/.test(out) && /People and payroll/.test(out), out.slice(0, 160));
        check('with invoicing before HR, as the nav has them',
            out.indexOf('Invoicing') < out.indexOf('People and payroll'));
    }

    // --- the thing people get wrong ------------------------------------------------
    {
        const w = boot();
        await wait(80);
        const section = w.document.getElementById('pricing').textContent;
        check('it says there is no monthly fee', /No monthly fee/i.test(section),
            section.slice(0, 120));
    }

    {
        // Asked with a note the page does not already contain. The shipped
        // wording says "a quiet month costs nothing" too, so matching that
        // would pass whether or not the server's copy was used at all - which
        // is the difference between operator-editable and merely looking it.
        const w = boot({ pricing: Object.assign({}, PRICING, {
            note: 'Billing is per action and settled from wallet credit only.' }) });
        await wait(80);
        const section = w.document.getElementById('pricing').textContent;
        check("and the wording is the server's, so it can be changed there",
            /settled from wallet credit only/.test(section), section.slice(0, 300));
    }

    // --- no invented tiers ------------------------------------------------------------
    {
        const page = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
        const section = page.slice(page.indexOf('<section id="pricing"'),
                                   page.indexOf('</section>', page.indexOf('<section id="pricing"')));
        // There are no plans in this product. A tier named in the markup would
        // be a price nobody is charged.
        check('no plan names are written into the page',
            !/\b(Starter|Basic|Pro|Premium|Enterprise|Business plan)\b/i.test(section),
            section.slice(0, 200));
        check('and no prices are hardcoded either',
            !/[£$€]\s?\d/.test(section), section.slice(0, 200));
    }

    // --- when it cannot be loaded -------------------------------------------------------
    {
        const w = boot({ fails: true });
        await wait(80);
        // A pricing heading with nothing under it reads as a page still being
        // written, which is worse than not offering one.
        check('a section that could not load its prices is removed',
            !w.document.getElementById('pricing'));
        check('and the nav does not point at a section that is gone',
            w.document.querySelectorAll('a[href="#pricing"]').length === 0);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
