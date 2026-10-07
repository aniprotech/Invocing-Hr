/**
 * Paying an invoice from the payer's own bank, and setting up automatic payment.
 *
 * The page does two things here and decides nothing. It sends the payer to
 * their bank, and when they come back it asks the server what happened - the
 * server having asked Salt Edge. So what is worth checking is what the page
 * will not do: say an invoice is paid because somebody came back, send
 * anything to start a recurring agreement before the payer has chosen their
 * own limits, or put a bank's name into the page as markup.
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
    amount_due: 120, currency: 'GBP', currency_symbol: '£', total: 120,
    issue_date: '2026-01-01', due_date: '2026-01-31',
    from: { company: 'Acme Ltd', email: 'billing@acme.test' },
    to: { name: 'Ada Reid' }, line_items: [],
};
const BANKS = [
    { code: 'fake_vrp_bank_gb', name: 'Fake VRP Bank' },
    { code: 'evil_gb', name: '<img src=x onerror=alert(1)>Evil Bank' },
];
const reply = (status, body) => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) });

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    let search = '?id=track-1';
    if (opts.saltedge) search += '&saltedge=return';
    if (opts.autodebit) search += '&autodebit=return';
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
                sent.push({ url: p, method: (init && init.method) || 'GET', body: init && init.body });
                if (p.endsWith('/pay/methods')) {
                    return reply(200, {
                        invoice_number: 'INV-0010', currency: 'GBP', amount_due: 120,
                        is_paid: !!opts.isPaid,
                        methods: opts.methods || [],
                        autodebit: opts.offer === undefined ? null : opts.offer,
                    });
                }
                if (p.endsWith('/pay/saltedge/start')) {
                    if (opts.startFails) return reply(502, { detail: 'This bank payment could not be started. Please try another way to pay.' });
                    return reply(200, { payment_url: 'https://www.saltedge.test/payments/connect?token=t1', payment_id: 'SEP1', settles_immediately: false });
                }
                if (p.endsWith('/pay/saltedge/check')) {
                    if (opts.checkFails) return reply(500, { detail: 'boom' });
                    return reply(200, opts.check || { paid: false, outcome: 'pending', status: 'authorizing', reason: '' });
                }
                if (p.endsWith('/autopay/saltedge/banks')) {
                    if (opts.bankFails) return reply(502, { detail: 'We could not load the list of banks' });
                    return reply(200, { banks: opts.banks === undefined ? BANKS : opts.banks, currency: 'GBP',
                        amount_due: 120, suggested_per_payment: 150, suggested_per_month: 450 });
                }
                if (p.endsWith('/autopay/saltedge/start')) {
                    if (opts.agreementFails) return reply(409, { detail: 'That bank does not offer automatic payments. Please choose another.' });
                    return reply(200, { consent_url: 'https://www.saltedge.test/vrp/checkout?token=c1', mandate_id: 7 });
                }
                if (p.endsWith('/autopay/saltedge/check')) {
                    return reply(200, opts.agreement || { status: 'pending', active: false });
                }
                return reply(200, Object.assign({}, INVOICE, opts.invoice || {}));
            };
        },
    });
    return dom.window;
}

const saltedge = { provider: 'saltedge', label: 'Pay from your bank (Salt Edge)', mode: 'platform' };
const offer = { provider: 'saltedge', currency: 'GBP', label: 'Pay future invoices from your bank automatically' };
const payBox = w => w.document.getElementById('payBox');
const note = w => w.document.getElementById('payNote').textContent;
const offered = w => {
    if (!w.document.querySelector('input[name="paymethod"]') && w.openPayStep && w.document.getElementById('payOpen')) w.openPayStep();
    return [...w.document.querySelectorAll('input[name="paymethod"]')].map(r => r.value);
};
const posts = w => w.__sent.filter(s => s.method === 'POST');

(async () => {
    // --- paying --------------------------------------------------------------------
    {
        const w = boot({ methods: [saltedge] });
        await wait(200);
        check('a bank payment is offered when the server offers it', offered(w).includes('saltedge'), offered(w).join());
        check('  as "Pay from your bank", saying what happens and where it goes next',
            /Pay from your bank/.test(payBox(w).textContent)
            && /Approve a bank transfer in your own banking app/.test(payBox(w).textContent)
            && /redirected to Salt Edge/.test(w.document.getElementById('payVia').textContent),
            w.document.getElementById('payVia').textContent);
        w.__sent.length = 0;
        w.document.getElementById('payContinue').click();
        await wait(80);
        const started = w.__sent.find(s => s.url.endsWith('/pay/saltedge/start'));
        check('  Continue asks the server to open it, by POST, and nothing else',
            started && started.method === 'POST' && posts(w).length === 1, JSON.stringify(w.__sent));
    }

    {
        const w = boot({ methods: [] });
        await wait(200);
        check('it is not offered when the server does not offer it', !offered(w).includes('saltedge'));
    }

    {
        const w = boot({ methods: [saltedge], startFails: true });
        await wait(200);
        offered(w);
        w.document.getElementById('payContinue').click();
        await wait(80);
        check('a payment the server cannot start says so, kindly, and can be tried again',
            /could not be started/.test(note(w)) && !w.document.getElementById('payContinue').disabled, note(w));
    }

    // --- coming back -----------------------------------------------------------------
    {
        const w = boot({ methods: [saltedge], saltedge: true, check: { paid: false, outcome: 'pending', status: 'authorizing', reason: '' } });
        await wait(250);
        const asked = w.__sent.find(s => s.url.endsWith('/pay/saltedge/check'));
        check('coming back asks the server whether it is paid, by POST',
            asked && asked.method === 'POST', JSON.stringify(w.__sent.map(s => s.url)));
        check('  and sends nothing from the address bar for the server to believe', asked && !asked.body, asked && asked.body);
        check('  while it is not confirmed the page does not say it is paid',
            !/is paid|has been paid|payment received|thank you/i.test(note(w)) && /Confirming|waiting/i.test(note(w)), note(w));
    }

    {
        const w = boot({ methods: [saltedge], saltedge: true, check: { paid: false, outcome: 'failed', status: 'failed', reason: 'internal: PaymentTemplateNotSupported' } });
        await wait(250);
        check('a payment the bank did not take says nothing was taken, and offers another go',
            /did not complete/.test(note(w)) && /nothing was taken/.test(note(w)) && /try again/.test(note(w)), note(w));
        check('  without showing the payer anything internal', !/PaymentTemplate|internal/.test(note(w)), note(w));
    }

    {
        const w = boot({ methods: [saltedge], saltedge: true, check: { paid: false, outcome: 'none', status: '', reason: '' } });
        await wait(250);
        check('coming back with nothing to confirm says so', /could not find a bank payment/.test(note(w)) && /Nothing was taken/.test(note(w)), note(w));
    }

    {
        const w = boot({ methods: [saltedge], saltedge: true, check: { paid: true, outcome: 'paid', status: 'executed', reason: '' } });
        await wait(250);
        check('once the server says paid, the return is dropped from the address so a refresh does not repeat it',
            !/saltedge=return/.test(w.location.search) && /id=track-1/.test(w.location.search), w.location.search);
    }

    {
        const w = boot({ methods: [saltedge], saltedge: true, checkFails: true });
        await wait(250);
        check('if the check itself fails it is not shown as paid, and says it will show once confirmed',
            !/is paid|thank/i.test(note(w)) && /show as paid once it is confirmed/.test(note(w)), note(w));
    }

    {
        const w = boot({ methods: [saltedge] });
        await wait(250);
        check('without a return there is no check, and nothing posted on load', !w.__sent.some(s => /saltedge\/check/.test(s.url)) && posts(w).length === 0);
    }

    // --- automatic payment --------------------------------------------------------------
    {
        const w = boot({ methods: [saltedge], offer });
        await wait(200);
        const link = w.document.getElementById('autodebitOpen');
        check('automatic payment is offered under the Pay button when the server offers it',
            !!link && /Pay future invoices from your bank automatically/.test(link.textContent));
    }

    {
        const w = boot({ methods: [saltedge], offer: null });
        await wait(200);
        check('and not when it does not', !w.document.getElementById('autodebitOpen'));
    }

    {
        const w = boot({ methods: [saltedge], offer, isPaid: true });
        await wait(200);
        check('nor on an invoice already paid', !w.document.getElementById('autodebitOpen'));
    }

    {
        const w = boot({ methods: [saltedge], offer });
        await wait(200);
        w.__sent.length = 0;
        w.document.getElementById('autodebitOpen').click();
        await wait(100);
        const box = payBox(w);
        check('opening it loads the banks, by GET, and sets nothing up yet',
            w.__sent.some(s => /autopay\/saltedge\/banks$/.test(s.url) && s.method === 'GET') && posts(w).length === 0, JSON.stringify(w.__sent));
        const options = [...box.querySelectorAll('#adBank option')];
        check('  the payer chooses their own bank from the list', options.length === 2 && options[0].value === 'fake_vrp_bank_gb');
        check('  a bank\'s name is text, never markup', !box.querySelector('img') && /Evil Bank/.test(box.textContent));
        check('  the limits are suggested, and are the payer\'s to change',
            box.querySelector('#adMax').value === '150' && box.querySelector('#adMonth').value === '450');
        check('  it says it is approved at their own bank, is capped, and can be stopped',
            /approve this once, at your own bank/.test(box.textContent) && /never more than the limits/.test(box.textContent)
            && /stop it any time/.test(box.textContent));
        check('  and that nothing is taken until they do', /Nothing is taken until you do/.test(box.textContent));
    }

    {
        const w = boot({ methods: [saltedge], offer });
        await wait(200);
        w.document.getElementById('autodebitOpen').click();
        await wait(100);
        w.document.getElementById('adMax').value = '60';
        w.document.getElementById('adMonth').value = '200';
        w.document.getElementById('adBank').value = 'fake_vrp_bank_gb';
        w.__sent.length = 0;
        w.document.getElementById('adGo').click();
        await wait(100);
        const started = w.__sent.find(s => /autopay\/saltedge\/start$/.test(s.url));
        const body = started && JSON.parse(started.body);
        check('setting it up sends exactly what the payer chose',
            started && started.method === 'POST' && body.provider_code === 'fake_vrp_bank_gb'
            && body.max_amount === 60 && body.period_max_amount === 200 && body.period_type === 'month', started && started.body);
    }

    {
        const w = boot({ methods: [saltedge], offer, agreementFails: true });
        await wait(200);
        w.document.getElementById('autodebitOpen').click();
        await wait(100);
        w.document.getElementById('adGo').click();
        await wait(100);
        check('a bank that cannot do it says so and the button works again',
            /does not offer automatic payments/.test(note(w)) && !w.document.getElementById('adGo').disabled, note(w));
    }

    {
        const w = boot({ methods: [saltedge], offer, banks: [] });
        await wait(200);
        w.document.getElementById('autodebitOpen').click();
        await wait(100);
        check('with no bank able to do it, it says so rather than showing an empty form',
            /None of the banks we can reach offer this yet/.test(payBox(w).textContent) && !w.document.getElementById('adGo'));
    }

    {
        const w = boot({ methods: [saltedge], offer, bankFails: true });
        await wait(200);
        w.document.getElementById('autodebitOpen').click();
        await wait(100);
        check('a list of banks that will not load is said so, with a way back',
            /could not load the list of banks/.test(payBox(w).textContent) && /Back to the invoice/.test(payBox(w).textContent));
        [...payBox(w).querySelectorAll('.linkish')].pop().click();
        check('  and Back to the invoice returns to the Pay button', !!w.document.getElementById('payOpen'));
    }

    // --- back from setting it up ----------------------------------------------------------
    {
        const w = boot({ methods: [saltedge], autodebit: true, agreement: { status: 'active', active: true, bank: 'Fake VRP Bank', max_amount: 150 } });
        await wait(250);
        check('once approved, it says who may take what, from which bank, and how to stop it',
            /Acme Ltd can now take future invoices from Fake VRP Bank, up to £150\.00 at a time/.test(note(w))
            && /stop it any time/.test(note(w)), note(w));
        check('  and the return is dropped from the address', !/autodebit=return/.test(w.location.search), w.location.search);
    }

    {
        const w = boot({ methods: [saltedge], autodebit: true, agreement: { status: 'pending', active: false } });
        await wait(250);
        check('while it is still to be approved nothing is claimed', !/Done|can now take/.test(note(w)) && /Checking/.test(note(w)), note(w));
    }

    {
        const w = boot({ methods: [saltedge], autodebit: true, agreement: { status: 'cancelled', active: false } });
        await wait(250);
        check('an agreement the bank did not set up says nothing will be taken',
            /did not set this up/.test(note(w)) && /nothing will be taken/.test(note(w)), note(w));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
