/**
 * Seeing an invoice email before it goes out.
 *
 * Sending fired the moment the button was pressed, with a subject and body
 * written into the code. Nobody could read what was about to reach a customer,
 * change a word of it, or send it to a different person at the same company.
 *
 * The check that matters most is the warning: a placeholder with no value
 * sends a blank "Hi ," and the send still succeeds, so nothing tells anyone it
 * went wrong. The rest is making sure the ticks actually do what they say.
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

const TEMPLATES = [
    { id: 1, kind: 'invoice', name: 'Basic', is_default: true,
      subject: 'Invoice #[Invoice Number] from [Trading Name] is due',
      body: 'Hi [Contact First Name],\n\nHere is [Invoice Number].' },
    { id: 2, kind: 'invoice', name: 'Terse', is_default: false,
      subject: '[Invoice Number]', body: 'Due [Due Date].' },
];

const PLACEHOLDERS = [
    { name: 'Contact First Name', group: 'Contact', help: "The customer's first name" },
    { name: 'Invoice Number', group: 'Invoice', help: 'e.g. INV-0010' },
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
        if (p === '/api/email-templates') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ templates: TEMPLATES }) });
        }
        if (p === '/api/email-placeholders') {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ placeholders: PLACEHOLDERS }) });
        }
        if (p.endsWith('/email-preview')) {
            const asked = JSON.parse(init.body);
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({
                    to: 'ada@acme.test',
                    subject: (asked.subject || '').replace(/\[[^\]]+\]/g, 'X'),
                    body: (asked.body || '').replace(/\[[^\]]+\]/g, 'X'),
                    missing: opts.missing || [],
                    currency: 'GBP',
                }) });
        }
        if (p.endsWith('/send')) {
            if (opts.sendError) {
                return Promise.resolve({ ok: false, status: 400,
                    json: () => Promise.resolve({ detail: opts.sendError }) });
            }
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve({ message: 'sent' }) });
        }
        const body = p.endsWith('s') ? [] : {};
        return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}') });
    };

    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

    // The screen reads the invoice number off the view, as it does in the app.
    w.document.getElementById('view-inv-number-val').textContent = 'INV-0010';
    // A PDF is only built when it is going to be attached; stubbed so the
    // test is about the send, not about jsPDF.
    w.generateInvoicePDF = () => ({ output: () => 'data:application/pdf;base64,QUJD' });
    return { w, sent };
}

const el = (w, id) => w.document.getElementById(id);

(async () => {
    // --- the markup ----------------------------------------------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const doc = new JSDOM(raw.replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
        check('the app ships a send screen', !!doc.getElementById('send-email-modal'));
        check('with the two ticks from the brief',
            !!doc.getElementById('send-attach-pdf') && !!doc.getElementById('send-copy-me'));
        check('and somewhere to warn about empty placeholders',
            !!doc.getElementById('send-missing'));
    }

    // --- opening it ----------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);

        check('sending opens the screen rather than firing straight away',
            el(w, 'send-email-modal').style.display === 'flex');
        check('and nothing has been sent yet',
            !sent.some(s => s.url.endsWith('/send')));

        check('the templates are offered',
            el(w, 'send-template').options.length === 2,
            el(w, 'send-template').options.length);
        check('the default is the one selected',
            el(w, 'send-template').value === '1', el(w, 'send-template').value);
        check('the subject is filled from it',
            el(w, 'send-subject').value === TEMPLATES[0].subject,
            el(w, 'send-subject').value);
        check('the To box is filled from the invoice',
            el(w, 'send-to').value === 'ada@acme.test', el(w, 'send-to').value);
        check('the placeholder picker is offered',
            el(w, 'send-placeholder-picker').querySelectorAll('option[value]:not([value=""])').length === 2);
    }

    // --- the preview ---------------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);

        check('the preview shows the filled-in subject',
            !/\[/.test(el(w, 'preview-subject').textContent),
            el(w, 'preview-subject').textContent);
        check('and says who it is going to',
            /ada@acme.test/.test(el(w, 'preview-to').textContent),
            el(w, 'preview-to').textContent);
    }

    // --- the warning this screen exists for -----------------------------------
    {
        const { w } = boot({ missing: ['Contact First Name'] });
        await wait(60);
        await w.sendEmail();
        await wait(200);

        const warn = el(w, 'send-missing');
        check('an empty placeholder is warned about',
            warn.style.display !== 'none');
        check('and named, so nobody has to hunt for which',
            /Contact First Name/.test(warn.textContent), warn.textContent);
    }

    {
        const { w } = boot({ missing: [] });
        await wait(60);
        await w.sendEmail();
        await wait(200);
        check('nothing missing means no warning',
            el(w, 'send-missing').style.display === 'none');
    }

    // --- switching template ---------------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);

        el(w, 'send-template').value = '2';
        w.applyEmailTemplate();
        await wait(200);
        check('choosing another template rewrites the subject',
            el(w, 'send-subject').value === '[Invoice Number]',
            el(w, 'send-subject').value);
    }

    // --- inserting a placeholder ----------------------------------------------
    {
        const { w } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);

        const box = el(w, 'send-body');
        box.value = 'Hello , thanks.';
        box.selectionStart = box.selectionEnd = 6;   // just after "Hello "
        w.insertPlaceholder('Contact First Name');

        check('a placeholder lands where the cursor was, not at the end',
            box.value === 'Hello [Contact First Name], thanks.', box.value);
    }

    // --- what actually gets sent ----------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);

        el(w, 'send-to').value = 'someone.else@acme.test';
        el(w, 'send-copy-me').checked = true;
        sent.length = 0;
        await w.confirmSendEmail();
        await wait(80);

        const post = sent.find(s => s.url.endsWith('/send'));
        check('sending posts once', !!post);
        const body = post && JSON.parse(post.body);
        check('to the address typed, not the one on the invoice',
            body && body.to === 'someone.else@acme.test', body && body.to);
        check('carrying the subject that was on screen',
            body && body.subject === TEMPLATES[0].subject, body && body.subject);
        check('and the copy-to-me choice', body && body.send_copy === true);
        check('with the PDF attached when the tick is on',
            body && body.attach_pdf === true && !!body.pdf_data);
        check('the screen closes on success',
            el(w, 'send-email-modal').style.display === 'none');
    }

    {
        // Unticking has to actually drop the attachment - the customer
        // notices which of "hidden" and "not sent" happened.
        const { w, sent } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);
        el(w, 'send-attach-pdf').checked = false;
        sent.length = 0;
        await w.confirmSendEmail();
        await wait(80);

        const body = JSON.parse(sent.find(s => s.url.endsWith('/send')).body);
        check('unticking the PDF sends no PDF',
            body.attach_pdf === false && !body.pdf_data, JSON.stringify(body.attach_pdf));
    }

    // --- refusals -------------------------------------------------------------
    {
        const { w, sent } = boot();
        await wait(60);
        await w.sendEmail();
        await wait(200);
        el(w, 'send-to').value = '   ';
        sent.length = 0;
        await w.confirmSendEmail();

        check('an empty address never reaches the server',
            !sent.some(s => s.url.endsWith('/send')));
        check('and says so', /email address/i.test(el(w, 'send-email-error').textContent),
            el(w, 'send-email-error').textContent);
        check('the screen stays open to be fixed',
            el(w, 'send-email-modal').style.display === 'flex');
    }

    {
        const { w } = boot({ sendError: 'No sender email configured.' });
        await wait(60);
        await w.sendEmail();
        await wait(200);
        await w.confirmSendEmail();
        await wait(80);
        check('a refused send leaves the screen open with the words still in it',
            el(w, 'send-email-modal').style.display === 'flex' &&
            el(w, 'send-subject').value === TEMPLATES[0].subject);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
