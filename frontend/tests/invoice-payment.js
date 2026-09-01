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
    amount_due: 780, currency: 'GBP', total: 780,
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
                if (p.endsWith('/pay/stripe/confirm')) {
                    if (opts.confirmFails) {
                        return Promise.resolve({ ok: false, status: 400,
                            json: () => Promise.resolve({ detail: 'That payment could not be verified' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve({ paid: true }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve(INVOICE) });
            };
        },
    });
    return dom.window;
}

const rzp = { provider: 'razorpay', label: 'Razorpay (UPI, cards, netbanking)', mode: 'direct' };
const card = { provider: 'stripe', label: 'Stripe (cards)', mode: 'direct' };
const bank = { provider: 'gocardless', label: 'Bank payment (GoCardless)', mode: 'platform' };
const buttons = w => w.document.getElementById('payButtons');

(async () => {
    {
        const w = boot({ methods: [card] });
        await wait(200);
        check('an activated Stripe account gets a card button',
            !!w.document.getElementById('payCardBtn'));
        check('and no Razorpay button it cannot honour',
            !w.document.getElementById('payBtn'));
        check('the amount owed is on the button',
            /780/.test(buttons(w).textContent), buttons(w).textContent);
    }

    {
        const w = boot({ methods: [rzp] });
        await wait(200);
        check('Razorpay alone still gets its own button',
            !!w.document.getElementById('payBtn') && !w.document.getElementById('payCardBtn'));
    }

    {
        const w = boot({ methods: [rzp, card] });
        await wait(200);
        check('both set up means both offered',
            !!w.document.getElementById('payBtn') && !!w.document.getElementById('payCardBtn'));
    }

    {
        const w = boot({ methods: [] });
        await wait(200);
        check('nothing set up offers no way to pay',
            !w.document.getElementById('payBtn') && !w.document.getElementById('payCardBtn'));
        check('but the invoice can still be printed',
            /Print or save/.test(buttons(w).textContent));
    }

    {
        const w = boot({ methods: [card], isPaid: true });
        await wait(200);
        check('an invoice already paid is not asked for again',
            !w.document.getElementById('payCardBtn'));
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
        check('a bank debit gets its own button',
            !!w.document.getElementById('payBankBtn'));
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

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
