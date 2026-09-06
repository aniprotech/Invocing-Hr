/**
 * Sending an AI draft instead of copying it out.
 *
 * Both AI panels on the invoice screen wrote an email and then stopped. The
 * invoice one offered "Copy Email"; the overdue reminder offered nothing at
 * all but "Dismiss". So the draft was pasted into whatever mail client the
 * person happened to have open, which meant it did not leave from the address
 * the account is set up to send from, was never recorded as a delivery, and
 * could not be chased when it bounced - the whole point of the send screen,
 * bypassed by the feature next to it.
 *
 * They can send from the panel now. Two things follow from that, and most of
 * this file is about them rather than about the button:
 *
 *   - It goes through the send screen rather than posting by itself. That
 *     screen owns the recipient, the attachment, cc/bcc and the wallet
 *     charge, and it is the one path that reports a refused send properly.
 *     The catch is that opening it applies the saved template, which fills
 *     the same two fields - so a draft that is not applied afterwards is
 *     silently replaced by the template and the person sends the wrong text.
 *   - A generated draft signs off with [Your Name] and [Your Company] until
 *     somebody fills them in. That was harmless while this was a copy button
 *     and is not harmless now, so the panel says so before it is sent.
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

const TEMPLATE = {
    id: 1, kind: 'invoice', name: 'Basic', is_default: true,
    subject: 'THE SAVED TEMPLATE SUBJECT',
    body: 'THE SAVED TEMPLATE BODY',
};

const DRAFT = {
    subject: 'Invoice INV-0004',
    body: 'Dear James Butler,\n\nPlease find attached Invoice INV-0004.\n\n[Your Name]',
};

const CLEAN_DRAFT = {
    subject: 'Invoice INV-0004',
    body: 'Dear James Butler,\n\nPlease find attached Invoice INV-0004.\n\nSam',
};

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };

    const account = opts.account || {
        can_send: true, from_email: 'billing@anibuild.test', transport: 'gmail',
    };
    const draft = opts.draft || DRAFT;

    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const json = body => Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}') });
        if (p === '/api/auth/me') return json({ user: { email: 'me@x' }, client_id: 1 });
        if (p === '/api/client/me') return json({ id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/email-settings') return json(account);
        if (p === '/api/email-templates') return json({ templates: [TEMPLATE] });
        if (p === '/api/email-placeholders') return json({ placeholders: [] });
        if (p === '/api/ai/personalize-email') return json(draft);
        if (p === '/api/ai/generate-followup') return json(draft);
        if (p.endsWith('/email-preview')) {
            const asked = JSON.parse(init.body);
            return json({ to: 'james@acme.test', subject: asked.subject,
                          body: asked.body, missing: [], currency: 'GBP' });
        }
        return json(p.endsWith('s') ? [] : {});
    };

    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    w.document.getElementById('view-inv-number-val').textContent = 'INV-0004';
    w.generateInvoicePDF = () => ({ output: () => 'data:application/pdf;base64,QUJD' });
    return w;
}

const panel = (w, id) => w.document.getElementById(id).innerHTML;

(async () => {
    // --- the invoice draft ----------------------------------------------------
    {
        const w = boot();
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await wait(40);
        const html = panel(w, 'ai-email-preview');

        check('the invoice draft offers to send it', /sendAiEmail\(\)/.test(html),
            'only a copy button, which is what sent people to another mail client');
        check('and still offers to copy it', /useAiEmail\(\)/.test(html));
        check('and to write it again', /aiPersonalizeEmail\(/.test(html));
    }

    // --- the overdue reminder, which had no way out at all ----------------------
    {
        const w = boot();
        await w.aiGenerateFollowup('INV-0004', 'James Butler', 7630, 14);
        await wait(40);
        const html = panel(w, 'ai-followup-result');

        check('the reminder offers to send it', /sendAiFollowup\(\)/.test(html),
            'it offered nothing but Dismiss, so the draft could only be retyped');
        check('and to copy it', /useAiFollowup\(\)/.test(html));
        check('and can still be dismissed', /dismissAiFollowup\(\)/.test(html));

        w.dismissAiFollowup();
        check('and dismissing it clears the panel',
            w.document.getElementById('ai-followup-result').innerHTML === '');
    }

    // --- whose address it leaves through -----------------------------------------
    {
        const w = boot();
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await w.aiGenerateFollowup('INV-0004', 'James Butler', 7630, 14);
        await wait(40);

        for (const [what, id] of [['invoice draft', 'ai-email-preview'],
                                  ['reminder', 'ai-followup-result']]) {
            check(`the ${what} names the account it sends from`,
                /billing@anibuild\.test/.test(panel(w, id)),
                'a send button that does not say who it is from is a guess');
        }
    }

    {
        const w = boot({ account: { can_send: false,
            blocked_reason: 'no Google account is connected' } });
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await wait(40);
        const html = panel(w, 'ai-email-preview');

        check('with nothing connected it says so rather than offering silently',
            /No email account connected/.test(html), html.slice(0, 200));
        check('and repeats the reason the server gave',
            /no Google account is connected/.test(html));
        check('and points at where to fix it', /#\/settings/.test(html));
    }

    // --- the draft has to survive the template ------------------------------------
    {
        const w = boot();
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await wait(40);
        await w.sendAiEmail();
        await wait(80);

        const subject = w.document.getElementById('send-subject').value;
        const body = w.document.getElementById('send-body').value;

        check('sending opens the screen that owns the recipient and the charge',
            w.document.getElementById('send-email-modal').style.display === 'flex');
        check('and the draft is what is in the box',
            subject === DRAFT.subject && body === DRAFT.body,
            `subject=${JSON.stringify(subject)} body=${JSON.stringify(body).slice(0, 60)}`);
        check('not the saved template, which fills the same two fields',
            !/THE SAVED TEMPLATE/.test(subject + body),
            'the template was applied after the draft and replaced it');
    }

    // --- the placeholders a generated draft arrives with -------------------------------
    {
        const w = boot();
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await wait(40);
        check('a draft still carrying [Your Name] says so before it is sent',
            /placeholders\] to fill in/.test(panel(w, 'ai-email-preview')),
            'harmless while this was a copy button; not harmless now');
    }

    {
        const w = boot({ draft: CLEAN_DRAFT });
        await w.aiPersonalizeEmail('INV-0004', 'James Butler', 7630, '2026-09-04');
        await wait(40);
        check('and a finished one does not nag',
            !/placeholders\] to fill in/.test(panel(w, 'ai-email-preview')));
    }

    // --- pressing send with nothing generated -------------------------------------------
    {
        const w = boot();
        let threw = '';
        try { w.sendAiEmail(); w.sendAiFollowup(); } catch (e) { threw = e.message; }
        check('asking to send nothing is refused rather than thrown', threw === '', threw);
        check('and no send screen is opened for it',
            w.document.getElementById('send-email-modal').style.display !== 'flex');
    }

    console.log(failures === 0
        ? '\nAll AI draft send checks passed.'
        : `\n${failures} AI draft send check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
