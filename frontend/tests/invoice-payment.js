/**
 * What a customer is offered on the public invoice page.
 *
 * The page drew one button, Razorpay's, whatever the business had actually set
 * up. A business that saved and activated Stripe keys saw them listed as
 * active in settings and no customer could ever use them.
 *
 * The check worth having is the return from Stripe: the id in the URL is only
 * a claim that something happened, and the page must hand it to the server to
 * be checked rather than treating the invoice as settled itself.
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

const INVOICE = {
    number: 'INV-0010', status: 'Awaiting Payment', payment: true,
    amount_due: 780, currency: 'GBP', currency_symbol: '£', total: 780,
    issue_date: '2026-01-01', due_date: '2026-01-31',
    from: { company: 'Acme Ltd', email: 'billing@acme.test' },
    to: { name: 'Ada Reid' }, line_items: [],
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    let search = '?id=track-1';
    if (opts.paid) search += `&paid=${opts.paid}`;
    if (opts.bank) search += `&bank=${opts.bank}`;
    if (opts.paypal) search += `&paypal=return&token=${opts.paypal}`;
    if (opts.pay) search += '&pay=1';
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/invoice.html' + search,
        beforeParse(w) {
            w.Razorpay = function () { this.open = () => { }; };
            w.console.error = () => { };
            const sent = [];
            w.__sent = sent;
            w.fetch = (url, init) => {
                const p = String(url).split('?')[0];
                sent.push({ url: p, method: (init && init.method) || 'GET',
                            body: init && init.body });
                if (p.endsWith('/pay/methods')) {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({
                            invoice_number: 'INV-0010', currency: 'GBP',
                            amount_due: 780, is_paid: !!opts.isPaid,
                            methods: opts.methods || [],
                        }) });
                }
                if (p.endsWith('/pay/gocardless/start')) {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({
                            authorisation_url: 'https://pay.gocardless.test/flow/1',
                            settles_immediately: false,
                        }) });
                }
                if (p.endsWith('/pay/stripe/session')) {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({
                            session_id: 'cs_1',
                            checkout_url: 'https://checkout.stripe.test/cs_1',
                        }) });
                }
                if (p.endsWith('/pay/paypal/order')) {
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({
                            order_id: 'ORD1', approve_url: 'https://www.sandbox.paypal.test/checkoutnow?token=ORD1',
                            amount: '780.00', currency: 'GBP', live: false,
                        }) });
                }
                if (p.endsWith('/pay/paypal/capture')) {
                    if (opts.confirmFails) {
                        return Promise.resolve({ ok: false, status: 400,
                            json: () => Promise.resolve({ detail: 'That payment could not be verified' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ paid: true, already_recorded: false }) });
                }
                if (p.endsWith('/pay/stripe/confirm')) {
                    if (opts.confirmFails) {
                        return Promise.resolve({ ok: false, status: 400,
                            json: () => Promise.resolve({ detail: 'That payment could not be verified' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ paid: true }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(Object.assign({}, INVOICE, opts.invoice || {})) });
            };
        },
    });
    return dom.window;
}

const rzp = { provider: 'razorpay', label: 'Razorpay (UPI, cards, netbanking)', mode: 'direct' };
const card = { provider: 'stripe', label: 'Stripe (cards)', mode: 'direct' };
const bank = { provider: 'gocardless', label: 'Bank payment (GoCardless)', mode: 'platform' };
const paypal = { provider: 'paypal', label: 'PayPal', mode: 'direct' };
const buttons = w => w.document.getElementById('payButtons');
const payBox = w => w.document.getElementById('payBox');
// The ways to pay the step offers, by key - opening it first if need be.
const offered = w => {
    if (!w.document.querySelector('input[name="paymethod"]') && w.openPayStep && w.document.getElementById('payOpen')) w.openPayStep();
    return [...w.document.querySelectorAll('input[name="paymethod"]')].map(r => r.value);
};

(async () => {
    {
        const w = boot({ methods: [card] });
        await wait(200);
        check('the invoice opens with a Pay button carrying the amount owed',
            !!w.document.getElementById('payOpen') && /Pay £780\.00/.test(w.document.getElementById('payOpen').textContent), payBox(w).textContent);
        check('an activated Stripe account is offered as Card',
            offered(w).includes('stripe'));
        check('and no Razorpay it cannot honour',
            !offered(w).includes('razorpay'));
    }

    {
        const w = boot({ methods: [rzp] });
        await wait(200);
        check('Razorpay alone is offered alone',
            offered(w).join() === 'razorpay', offered(w).join());
    }

    {
        const w = boot({ methods: [rzp, card] });
        await wait(200);
        check('both set up means both offered',
            offered(w).includes('razorpay') && offered(w).includes('stripe'));
    }

    {
        const w = boot({ methods: [] });
        await wait(200);
        check('nothing set up offers no way to pay',
            offered(w).length === 0 && !w.document.getElementById('payOpen'));
        check('  but is never a dead end: it says who to contact',
            /has not set up a way to pay online/.test(payBox(w).textContent) && /billing@acme\.test/.test(payBox(w).textContent), payBox(w).textContent);
        check('but the invoice can still be printed, and the document itself taken as a PDF',
            /Print/.test(buttons(w).textContent)
            && [...w.document.querySelectorAll('#payButtons a')].some(a => a.textContent === 'Download PDF' && /\/api\/public\/invoices\/.+\/pdf$/.test(a.getAttribute('href')) && a.getAttribute('download')));
    }

    {
        const w = boot({ methods: [card], isPaid: true });
        await wait(200);
        check('an invoice already paid is not asked for again',
            offered(w).length === 0 && !w.document.getElementById('payOpen'));
    }

    // --- going to Stripe -------------------------------------------------------
    {
        const w = boot({ methods: [card] });
        await wait(200);
        // jsdom will not navigate, so what is checked is that the page asks
        // the server for the destination instead of assembling a Stripe URL
        // itself - a URL built here could not carry a verified amount.
        w.__sent.length = 0;
        await w.payByCard();
        await wait(60);
        const started = w.__sent.find(s => s.url.endsWith('/pay/stripe/session'));
        check('paying by card asks the server to open the session', !!started);
        check('by POST, not by guessing a link',
            started && started.method === 'POST', started && started.method);
    }

    // --- bank debit ------------------------------------------------------------
    {
        const w = boot({ methods: [bank] });
        await wait(200);
        check('a bank debit is offered as Direct Debit',
            offered(w).includes('gocardless') && /Direct Debit/.test(payBox(w).textContent));
        w.__sent.length = 0;
        await w.payByBank();
        await wait(60);
        const started = w.__sent.find(s => s.url.endsWith('/pay/gocardless/start'));
        check('which asks the server to open the authorisation', !!started);
    }

    {
        // A direct debit clears days later. Saying paid here would stop
        // anyone chasing a payment that can still fail.
        const w = boot({ methods: [bank], bank: 'authorised' });
        await wait(250);
        const note = w.document.getElementById('payNote').textContent;
        check('returning from the bank does not claim the invoice is paid',
            !/is paid|has been paid|payment received/i.test(note), note);
        check('it says it is set up and still to clear',
            /clear/i.test(note) && /few working days/i.test(note), note);
        check('and nothing is posted to settle it from the browser',
            !w.__sent.some(s => /gocardless\/confirm|\/settle/.test(s.url)));
    }

    {
        const w = boot({ methods: [bank], bank: 'cancelled' });
        await wait(250);
        check('a cancelled bank payment says nothing was taken',
            /nothing was taken/i.test(w.document.getElementById('payNote').textContent));
    }

    // --- coming back from Stripe -----------------------------------------------
    {
        const w = boot({ methods: [card], paid: 'cs_test_99' });
        await wait(250);
        const post = w.__sent.find(s => s.url.endsWith('/pay/stripe/confirm'));
        check('returning from Stripe asks the server to confirm', !!post);
        check('handing over the session id it was given',
            post && JSON.parse(post.body).session_id === 'cs_test_99',
            post && post.body);
    }

    {
        const w = boot({ methods: [card], paid: 'cs_test_99', confirmFails: true });
        await wait(250);
        const note = w.document.getElementById('payNote');
        check('a payment the server will not verify is not shown as settled',
            !/thank|paid|settled/i.test(note.textContent), note.textContent);
        check('and the customer is told who to contact',
            /billing@acme.test/.test(note.textContent), note.textContent);
    }

    // --- PayPal -----------------------------------------------------------------
    {
        const w = boot({ methods: [paypal] });
        await wait(200);
        check('PayPal keys offer PayPal',
            offered(w).includes('paypal'));
        w.__sent.length = 0;
        await w.payWithPayPal();
        await wait(60);
        const started = w.__sent.find(s => s.url.endsWith('/pay/paypal/order'));
        check('paying with PayPal asks the server to open the order, by POST',
            started && started.method === 'POST');
        let kept = '';
        try { kept = w.sessionStorage.getItem('paypal-order-track-1'); } catch (e) { }
        check('and remembers the order for the way back', kept === 'ORD1', kept);
    }

    {
        const w = boot({ methods: [paypal], paypal: 'ORD1' });
        await wait(250);
        const post = w.__sent.find(s => s.url.endsWith('/pay/paypal/capture'));
        check('returning from PayPal asks the server to capture the order it names',
            post && JSON.parse(post.body).order_id === 'ORD1', post && post.body);
    }

    {
        const w = boot({ methods: [paypal], paypal: 'ORD1', confirmFails: true });
        await wait(250);
        const note = w.document.getElementById('payNote');
        check('a capture the server will not verify is not shown as settled, and says who to contact',
            !/thank|settled|is paid/i.test(note.textContent) && /billing@acme.test/.test(note.textContent), note.textContent);
    }

    {
        const w = boot({ methods: [rzp, card, paypal] });
        await wait(200);
        check('all three set up means all three offered',
            ['razorpay', 'stripe', 'paypal'].every(k => offered(w).includes(k)), offered(w).join());
    }

    // --- Review and pay: the step itself -------------------------------------------
    {
        const w = boot({ methods: [bank, card], pay: true });
        await wait(250);
        const box = payBox(w).textContent;
        check('Review and pay (?pay=1) lands straight on "How would you like to pay?"',
            /How would you like to pay\?/.test(box), box.slice(0, 200));
        check('  the first way is chosen, and it says where it will go next',
            w.document.querySelector('input[name="paymethod"]:checked').value === 'gocardless'
            && /You will be redirected to GoCardless to complete payment\./.test(w.document.getElementById('payVia').textContent),
            w.document.getElementById('payVia').textContent);
        check('  with a Continue button and "Secure checkout"',
            !!w.document.getElementById('payContinue') && /Secure checkout/.test(box));
        const cardRadio = w.document.querySelector('input[name="paymethod"][value="stripe"]');
        cardRadio.checked = true;
        cardRadio.dispatchEvent(new w.Event('change'));
        check('  choosing Card says Stripe instead, and highlights it',
            /redirected to Stripe/.test(w.document.getElementById('payVia').textContent)
            && w.document.querySelector('.method[data-method="stripe"]').classList.contains('on')
            && !w.document.querySelector('.method[data-method="gocardless"]').classList.contains('on'));
        w.__sent.length = 0;
        w.document.getElementById('payContinue').click();
        await wait(60);
        check('  Continue starts the chosen one on the server, by POST',
            w.__sent.some(x => x.url.endsWith('/pay/stripe/session') && x.method === 'POST')
            && !w.__sent.some(x => x.url.endsWith('/pay/gocardless/start')));
        w.document.querySelector('.linkish').click();
        check('  and Back to the invoice folds it away again', !!w.document.getElementById('payOpen') && !w.document.getElementById('payContinue'));
    }

    {
        const w = boot({ methods: [card] });
        await wait(250);
        check('opened without ?pay=1 the invoice shows first, with the Pay button, not the step',
            !!w.document.getElementById('payOpen') && !w.document.querySelector('input[name="paymethod"]'));
        w.document.getElementById('payOpen').click();
        check('  and the Pay button opens the step', /How would you like to pay\?/.test(payBox(w).textContent));
    }

    // --- bank transfer ---------------------------------------------------------------
    {
        const w = boot({ methods: [], pay: true, invoice: { bank_details: 'Acme Ltd\nSort code 20-00-00\nAccount 12345678' } });
        await wait(250);
        check('with only bank details, bank transfer is still a way to pay',
            offered(w).join() === 'bank', offered(w).join());
        const info = w.document.getElementById('bankInfo');
        check('  its details show, with the amount and the invoice number as the reference',
            !info.hidden && /Sort code 20-00-00/.test(info.textContent) && /£780\.00/.test(info.textContent) && /Reference: INV-0010/.test(info.textContent), info.textContent);
        check('  and there is no checkout to continue to',
            w.document.getElementById('payContinue').hidden && w.document.getElementById('payVia').textContent === '');
    }

    {
        const w = boot({ methods: [card], pay: true, invoice: { bank_details: '<img src=x onerror=alert(1)>' } });
        await wait(250);
        check('bank details are shown as text, never as markup',
            !payBox(w).querySelector('img'));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
