/**
 * Bank feeds: the three screens a business knows from Xero, the card with
 * the bank's three figures, and the way back from the bank.
 *
 * Find the bank; "Add accounts for TSB (UK)"; the consent screen that names
 * the provider, lists the four things shared, says ninety days, and offers
 * Back / Continue without bank feed / Continue and log in to bank. Back from
 * the bank with ?feed=<reference>, the connection is completed and the
 * reference taken off the address. The card shows statement balance,
 * balance in aniprotech and the difference, on the Bank screen and the
 * dashboard alike.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const FEED = { id: 7, provider: 'GoCardless Bank Account Data', institution_id: 'TSB_TSBSGB2A', institution_name: 'TSB (UK)', institution_logo: 'https://cdn.example/tsb.png',
    status: 'linked', consent_expires_on: '2026-12-20', days_left: 90, renew_soon: false, last_synced_at: '2026-09-21 07:00:00', last_error: '', syncs_left_today: 3,
    accounts: [{ id: 3, feed_id: 7, name: 'Business Current', sort_code: '77-68-29', account_number: '00028276', currency: 'GBP', enabled: true, account_id: 1, account: 'TSB (UK) Business Current',
        statement_balance: 4289.33, balance_on: '2026-09-21', in_app: 2507.33, difference: 1782.0, to_match: 2, lines_total: 3 }] };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: opts.url || 'https://localhost/app.html#/bank' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, full, method, body: init && init.body });
        const give = (b, ok) => Promise.resolve({ ok: ok !== false, status: ok === false ? 400 : 200, json: () => Promise.resolve(b) });
        if (p === '/api/bank/feeds' && method === 'GET') return give({ configured: opts.configured !== false, provider: 'GoCardless Bank Account Data', blurb: 'aniprotech partners with GoCardless to securely import your transactions. GoCardless is authorised and regulated by the Financial Conduct Authority.', consent_days: 90, feeds: opts.feeds || [] });
        if (p === '/api/bank/feeds' && method === 'POST') return give({ feed_id: 8, reference: 'abc123', link: 'https://ob.example/consent/abc123', consent_days: 90 });
        if (p === '/api/bank/feeds/institutions') return give({ institutions: /tsb/i.test(full) ? [{ id: 'TSB_TSBSGB2A', name: 'TSB (UK)', logo: 'https://cdn.example/tsb.png' }] : [] });
        if (p === '/api/bank/feeds/complete') return give(FEED);
        if (p === '/api/bank/feeds/7/sync') return give({ new_lines: 1, feed: FEED });
        if (p === '/api/bank/lines') return give({ lines: [], counts: {}, accounts: [], auto: 0, unmatched_total: 0 });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = (m) => { w._toasts = (w._toasts || []).concat([m]); };
    w.uiConfirm = () => Promise.resolve(true);
    w.getCurrencySymbol = () => '£';
    const gone = [];
    w.goToBank = (link) => gone.push(link);
    return { w, doc: w.document, sent, gone };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the Bank screen has Add bank account, a strip for the feeds, and the dashboard a place for the card',
            /id="bank-add-account"/.test(src) && /id="bank-feeds"/.test(src) && /id="dashboard-bank"/.test(src));
        check('  the modal has the three screens', /id="bank-feed-step-find"/.test(src) && /id="bank-feed-step-add"/.test(src) && /id="bank-feed-step-consent"/.test(src));
        check('  the consent screen says what Xero\'s says',
            /aniprotech needs your approval to access:/.test(src) && /Your account name, number, and sort code/.test(src) && /Your account balance/.test(src)
            && /Your card number/.test(src) && /Details of your transactions/.test(src) && /after which you will be asked to renew the connection/.test(src)
            && /Continue without bank feed/.test(src) && /Continue and log in to bank/.test(src));
        check('  the second screen says what Xero\'s says', /Enter your account details to get started\. Once added, you can set up an automatic bank feed or manually import bank statements\./.test(src));
    }
    // --- nothing connected: the invitation ------------------------------------------------------
    {
        const { w, doc } = boot();
        await w.loadBankFeeds();
        await wait(20);
        check('with nothing connected the Bank screen invites you to connect', /Connect your bank/.test(doc.getElementById('bank-feeds').textContent) && doc.getElementById('bank-add-account').style.display !== 'none');
        check('  and the dashboard shows no card', doc.getElementById('dashboard-bank').style.display === 'none');
    }
    {
        const { w, doc } = boot({ configured: false });
        await w.loadBankFeeds();
        await wait(20);
        check('with no provider keys the button and the invitation are absent - files only', doc.getElementById('bank-feeds').innerHTML === '' && doc.getElementById('bank-add-account').style.display === 'none');
    }
    // --- the three screens ------------------------------------------------------------------------
    {
        const { w, doc, sent, gone } = boot();
        await w.loadBankFeeds();
        w.addBankAccount();
        await wait(300);
        check('Add bank account opens on the search', doc.getElementById('bank-feed-modal').style.display === 'flex' && doc.getElementById('bank-feed-title').textContent === 'Add bank account');
        doc.getElementById('bank-feed-search').value = 'tsb';
        w.searchBankFeedInstitutions();
        await wait(320);
        const hit = doc.querySelector('.bank-feed-hit');
        check('  typing the name finds the bank, with its logo', hit && /TSB \(UK\)/.test(hit.textContent) && hit.querySelector('img'));
        hit.click();
        await wait(20);
        check('  screen two: Add accounts for TSB (UK)', doc.getElementById('bank-feed-add-title').textContent === 'Add accounts for TSB (UK)' && doc.getElementById('bank-feed-step-add').style.display !== 'none');
        w.bankFeedStep('consent');
        const consent = doc.getElementById('bank-feed-step-consent');
        check('  screen three: Connect to TSB (UK), naming the provider and ninety days',
            doc.getElementById('bank-feed-consent-title').textContent === 'Connect to TSB (UK)' && /GoCardless/.test(consent.textContent) && /regulated/.test(consent.textContent)
            && /90 days/.test(consent.textContent) && doc.getElementById('bank-feed-provider-mark').textContent === 'GoCardless');
        await w.startBankFeed();
        await wait(30);
        const started = sent.find(s => s.url === '/api/bank/feeds' && s.method === 'POST');
        check('  Continue and log in to bank starts the connection for that bank and goes to the link',
            started && bodyOf(started).institution_id === 'TSB_TSBSGB2A' && gone[0] === 'https://ob.example/consent/abc123');
    }
    // --- back from the bank ------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ url: 'https://localhost/app.html?feed=abc123#/bank', feeds: [FEED] });
        await w.loadBankView();
        await wait(60);
        const done = sent.find(s => s.url === '/api/bank/feeds/complete');
        check('back with ?feed= the connection is completed', done && bodyOf(done).reference === 'abc123');
        check('  the business is told what came in', (w._toasts || []).some(t => /TSB \(UK\) connected: 1 account, 3 lines/.test(t)), JSON.stringify(w._toasts));
        check('  and the reference comes off the address', !/feed=/.test(w.location.href) && /#\/bank$/.test(w.location.href), w.location.href);
    }
    // --- the card --------------------------------------------------------------------------------------
    {
        const { w, doc } = boot({ feeds: [FEED] });
        await w.loadBankFeeds();
        await wait(20);
        const strip = doc.getElementById('bank-feeds').textContent;
        check('the card carries the bank, the account and the three figures',
            /TSB \(UK\)/.test(strip) && /Feed connected/.test(strip) && /Business Current/.test(strip) && /77-68-29 00028276/.test(strip)
            && /Statement balance \(2026-09-21\)/.test(strip) && /£4289\.33/.test(strip) && /Balance in aniprotech/.test(strip) && /£2507\.33/.test(strip)
            && /Balance difference/.test(strip) && /£1782\.00/.test(strip) && /2 lines to match/.test(strip), strip);
        check('  with Refresh, Disconnect and a Feed on switch', doc.querySelector('#bank-feeds [data-feed-sync]') && doc.querySelector('#bank-feeds [data-feed-disconnect]') && doc.querySelector('#bank-feeds [data-feed-toggle]'));
        const tile = doc.getElementById('dashboard-bank');
        check('  the dashboard shows the same card, with Reconcile instead of Disconnect', tile.style.display !== 'none' && /£4289\.33/.test(tile.textContent) && /Reconcile/.test(tile.textContent) && !tile.querySelector('[data-feed-disconnect]'));
    }
    {
        const soon = Object.assign({}, FEED, { renew_soon: true, days_left: 6 });
        const { w, doc } = boot({ feeds: [soon] });
        await w.loadBankFeeds();
        await wait(20);
        check('near the end of the ninety days the card says Renew by, and offers Renew', /Renew by 2026-12-20/.test(doc.getElementById('bank-feeds').textContent) && doc.querySelector('#bank-feeds [data-feed-renew]'));
        const stopped = Object.assign({}, FEED, { status: 'expired' });
        const b2 = boot({ feeds: [stopped] });
        await b2.w.loadBankFeeds();
        await wait(20);
        check('  a stopped feed says so, offers Renew, and no Refresh', /Feed stopped/.test(b2.doc.getElementById('bank-feeds').textContent) && b2.doc.querySelector('#bank-feeds [data-feed-renew]') && !b2.doc.querySelector('#bank-feeds [data-feed-sync]'));
    }
    console.log(failures === 0 ? '\nAll bank-feed checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
