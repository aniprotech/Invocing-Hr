/**
 * One brand across the pages.
 *
 * These had drifted in ways nobody notices one page at a time: the name was
 * spelled two ways in the titles and the ordering flipped between them, two
 * pages wore the system font while their siblings loaded a real face, one had
 * no icon at all, and nothing anywhere carried an Open Graph tag - so every
 * link shared or previewed showed a bare URL, including the invoice link that
 * now goes out to customers in every emailed invoice.
 *
 * A brand comes apart one page at a time, which is why this sweeps the pages
 * rather than checking a list somebody has to remember to update.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

// Every page a person can land on. Fragments and partials are not pages.
const PAGES = fs.readdirSync(ROOT)
    .filter(f => f.endsWith('.html') && !f.startsWith('__'))
    .sort();

const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const titleOf = s => (s.match(/<title>([^<]*)<\/title>/) || [])[1] || '';

// The pages a stranger can open, and so the only ones worth describing to a
// link preview. There is no point describing a page that answers 401.
const PUBLIC = ['index.html', 'login.html', 'employee-login.html',
                'invoice.html', 'policy.html', 'jobs.html'];

(async () => {
    check('there are pages to check', PAGES.length > 5, PAGES.length);

    // --- one name -------------------------------------------------------------
    {
        const titles = PAGES.map(f => ({ f, t: titleOf(read(f)) }));
        const empty = titles.filter(x => !x.t.trim());
        check('every page says what it is', empty.length === 0,
            empty.map(x => x.f).join(', '));

        // The logo writes it as one lowercase word. Two spellings in a row of
        // tabs reads as two products.
        const wrongName = titles.filter(x => /Ani\s+Protech/.test(x.t));
        check('the name is spelled one way', wrongName.length === 0,
            wrongName.map(x => x.f + ': ' + x.t).join(' | '));

        const branded = titles.filter(x => /aniprotech/i.test(x.t));
        check('and every title carries it',
            branded.length === titles.length,
            titles.filter(x => !/aniprotech/i.test(x.t)).map(x => x.f).join(', '));

        // Page first, brand last, so a row of tabs is readable.
        const backwards = titles.filter(
            x => /^aniprotech\s*-\s*\S/.test(x.t) && x.f !== 'index.html');
        check('the page comes before the brand', backwards.length === 0,
            backwards.map(x => x.f + ': ' + x.t).join(' | '));
    }

    // --- one icon ---------------------------------------------------------------
    {
        const missing = PAGES.filter(f => !/rel="icon"/.test(read(f)));
        check('every page carries the icon', missing.length === 0, missing.join(', '));

        const partial = PAGES.filter(f => {
            const s = read(f);
            return !/favicon-32/.test(s) || !/favicon-16/.test(s) ||
                   !/icon\.svg/.test(s) || !/apple-touch-icon/.test(s);
        });
        check('and the whole set, not half of it', partial.length === 0,
            partial.join(', '));
    }

    // --- one face ----------------------------------------------------------------
    {
        // A page that asks for no web font falls back to whatever the machine
        // has, so it looks like a different product on every machine.
        const bare = PAGES.filter(f => {
            const s = read(f);
            return !/fonts\.googleapis\.com/.test(s);
        });
        check('no page is left wearing the system font', bare.length === 0,
            bare.join(', '));
    }

    // --- something to show when a link is shared ------------------------------------
    {
        const undescribed = PUBLIC.filter(f => !/og:title/.test(read(f)));
        check('every public page describes itself to a link preview',
            undescribed.length === 0, undescribed.join(', '));

        // This is the one that matters most: it is emailed to customers.
        const invoice = read('invoice.html');
        check('the invoice page especially, since customers are sent it',
            /og:title/.test(invoice) && /og:description/.test(invoice));
        check('with a picture to show', /og:image/.test(invoice));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
