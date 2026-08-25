/**
 * One logo, everywhere.
 *
 * A logo can live in two places: the account-wide one, which predates branding
 * themes, and the theme's own. The PDF prefers the theme. For a while the
 * invoice page preferred the account, so the screen showed one logo and the
 * customer received another - which is exactly how it was noticed.
 *
 * These check that whatever the PDF would print is also what the invoice page
 * displays, under each combination of the two being set.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');
const THEME_LOGO = 'data:image/gif;base64,R0lGODlhAQABAIAAAP8AAAAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';
const ACCOUNT_LOGO = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAA/wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';

function boot({ themeLogo, accountLogo }) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');

    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    // Shaped like the real Chart.js: the app sets Chart.defaults before drawing,
    // and a stub without it turns every run into a page of noise that a real
    // error could hide in.
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };

    const routes = {
        '/api/client/me': { id: 1, email: 'me@example.com', company_name: 'aniprotech', currency: 'GBP' },
        '/api/auth/me': { user: { email: 'me@example.com' }, client_id: 1 },
        '/api/settings': { currency: 'GBP' },
        '/api/next-invoice-number': { next_number: 'INV-0029', payment_terms_days: 14 },
        '/api/client/logo': { logo_url: accountLogo || '' },
        '/api/branding-themes/default': {
            id: 7, name: 'Standard', brand_color: '#4f46e5', font: 'helvetica',
            logo_data: themeLogo || '', logo_position: 'right',
        },
    };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = routes[p] !== undefined ? routes[p] : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body),
            text: () => Promise.resolve(JSON.stringify(body)),
        });
    };

    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return dom;
}

/** What the PDF would actually draw, taken from the generator itself. */
function logoInPdf(w) {
    let captured = null;
    const real = w.jspdf.jsPDF;
    function Recording() {
        const doc = new real(...arguments);
        const realImage = doc.addImage.bind(doc);
        doc.addImage = function (data) {
            if (captured === null) captured = data;
            try { return realImage.apply(null, arguments); } catch (e) { return doc; }
        };
        return doc;
    }
    w.jspdf = { jsPDF: Recording };
    try { w.eval('generateInvoicePDF(true, "invoice")'); } catch (e) { /* reported by the caller */ }
    w.jspdf = { jsPDF: real };
    return captured;
}

const wait = ms => new Promise(r => setTimeout(r, ms));
const name = v => v === THEME_LOGO ? 'theme' : (v === ACCOUNT_LOGO ? 'account' : (v ? 'other' : 'none'));

(async () => {
    let failures = 0;

    for (const [label, setup, expected] of [
        ['theme logo set, account logo set', { themeLogo: THEME_LOGO, accountLogo: ACCOUNT_LOGO }, THEME_LOGO],
        ['only the theme logo set', { themeLogo: THEME_LOGO, accountLogo: '' }, THEME_LOGO],
        ['only the account logo set', { themeLogo: '', accountLogo: ACCOUNT_LOGO }, ACCOUNT_LOGO],
    ]) {
        const dom = boot(setup);
        const w = dom.window;
        await wait(400);

        const onScreen = (w.document.getElementById('logo-img-create') || {}).src || '';
        const inPdf = logoInPdf(w);

        const problems = [];
        if (inPdf !== expected) problems.push(`PDF drew ${name(inPdf)}, expected ${name(expected)}`);
        if (onScreen !== expected) problems.push(`screen shows ${name(onScreen)}, expected ${name(expected)}`);
        if (inPdf !== onScreen) problems.push('the screen and the PDF disagree');

        if (problems.length) { failures++; console.log(`FAIL  ${label}: ${problems.join('; ')}`); }
        else console.log(`ok    ${label.padEnd(34)} -> both show the ${name(expected)} logo`);

        dom.window.close();
    }

    console.log(failures
        ? `\n${failures} case(s) where the screen and the invoice disagree`
        : '\nthe invoice page always shows the logo the customer will receive');
    process.exit(failures ? 1 : 0);
})();
