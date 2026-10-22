/**
 * The Payment options page shows, for each method switched on, the marks it
 * puts beside "View and pay online" on the invoice - the server's own badge
 * markup, so the page, the email and the PDF never disagree.
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

function boot(gateways, platform) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/payment-gateways') return give({ gateways, platform_methods: platform || [] });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return w;
}

(async () => {
    {
        const w = boot([
            { provider: 'stripe', label: 'Stripe <b>(cards)</b>', is_active: true, badges: ['visa'], badges_html: '<span class="b">VISA</span>' },
            { provider: 'paypal', label: 'PayPal', is_active: false, badges: ['paypal'], badges_html: '<span class="b">PayPal</span>' }],
            [{ provider: 'saltedge', label: 'Pay from your bank', currencies: ['GBP'], offered: true, badges_html: '<span class="b">Pay by bank</span>' }]);
        await w.loadPaymentOptions();
        const host = w.document.getElementById('payment-options-list');
        const t = host.textContent;
        check('each method switched on is listed with its marks', /Stripe <b>\(cards\)<\/b>/.test(t) && /VISA/.test(t) && /Pay from your bank \(GBP\)/.test(t) && /Pay by bank/.test(t));
        check('  a method switched off is not', !/PayPal/.test(t));
        check('  the method name stays text', !host.querySelector('b'));
        check('  and the page says the invoice carries them', /View and pay online/.test(t));
    }
    {
        const w = boot([{ provider: 'stripe', label: 'Stripe', is_active: false }]);
        await w.loadPaymentOptions();
        check('with nothing switched on it says so', /No online payment method is switched on yet/.test(w.document.getElementById('payment-options-list').textContent));
    }
    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
