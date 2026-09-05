/**
 * Telling a business it cannot send anything, before it tries.
 *
 * Nothing said so. A business whose sending was not set up found out when an
 * invoice was already written, the customer was chosen and the send came back
 * refused - which is the worst moment available, because it is the moment
 * they were trying to get paid.
 *
 * The answer is knowable the second they sign in, so it is said then. Once per
 * session: a business that has deliberately left this alone must not be nagged
 * on every screen, and one that genuinely cannot send must not have to discover
 * it at the point of sale.
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

const CAN_SEND = {
    verified: true, email: 'a@b.com', can_send: true, blocked_reason: '',
    mine: { can_send: true, blocked_reason: '' },
};
const CANNOT = {
    verified: true, email: 'a@b.com', can_send: true, blocked_reason: '',
    mine: { can_send: false,
            blocked_reason: 'no Google account is connected for this business' },
};

function boot(status) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const sent = [];
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        sent.push({ url: p, method: (init && init.method) || 'GET' });
        const give = b => Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve(b) });
        if (p === '/api/auth/me') return give({ user: { email: 'a@b' }, client_id: 1 });
        if (p === '/api/client/me') return give({ id: 1, modules: ['invoicing', 'hr'] });
        if (p === '/api/client/verification-status') return give(status || CAN_SEND);
        return give(p.endsWith('s') ? [] : {});
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

const modal = w => w.document.getElementById('email-setup-modal');
const shown = w => modal(w) && modal(w).style.display === 'flex';

(async () => {
    // --- somebody who cannot send is told -------------------------------------
    {
        const { w } = boot(CANNOT);
        await wait(40);
        await w.checkEmailSending();
        check('a business that cannot send is told at sign-in', shown(w));
        check('and told what is stopping it, not just that something is',
            /no Google account is connected/.test(modal(w).textContent),
            modal(w).textContent.slice(0, 160));
        check('with what it costs them said plainly',
            /cannot be sent/.test(modal(w).textContent));
        check('and both ways out named, since either will do',
            /Gmail/.test(modal(w).textContent) &&
            /mail server/.test(modal(w).textContent));
    }

    // --- somebody who can is not -------------------------------------------------
    {
        const { w } = boot(CAN_SEND);
        await wait(40);
        await w.checkEmailSending();
        check('a business that can send is not interrupted', !shown(w));
    }

    {
        // The platform being broken is the operator's problem, not something a
        // tenant can fix from their own settings screen.
        const { w } = boot({ verified: true, email: 'a@b.com', can_send: false,
            blocked_reason: 'SMTP is selected but SMTP_HOST is not set',
            mine: { can_send: true, blocked_reason: '' } });
        await wait(40);
        await w.checkEmailSending();
        check('and is not asked to fix something that is not theirs', !shown(w));
    }

    // --- asked once, not on every screen ---------------------------------------------
    {
        const { w } = boot(CANNOT);
        await wait(40);
        await w.checkEmailSending();
        check('it can be put off', shown(w));
        w.closeEmailSetup();
        check('closing it closes it', !shown(w));

        await w.checkEmailSending();
        check('and it does not come straight back', !shown(w));
    }

    {
        // Session storage, not local: still true next sign-in, so it asks again
        // then rather than never again.
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const block = src.slice(src.indexOf('function closeEmailSetup'),
                                src.indexOf('window.closeEmailSetup'));
        check('the dismissal lasts the session, not forever',
            /sessionStorage/.test(block) && !/localStorage/.test(block), block);
    }

    // --- and it leads somewhere ----------------------------------------------------------
    {
        const { w } = boot(CANNOT);
        await wait(40);
        await w.checkEmailSending();

        // Two halves, because they can fail independently. The markup half
        // asks whether anything on screen reaches the function at all - a
        // prompt whose only button dismisses it is a dead end, and calling
        // the function directly would never notice. The behaviour half then
        // asks what the function does. They are separate because jsdom does
        // not run inline onclick attributes in outside-only mode, so a click
        // here would prove nothing either way.
        const buttons = [...modal(w).querySelectorAll('button')];
        const go = buttons.find(b => /set it up/i.test(b.textContent));
        check('the prompt has a button that leads somewhere', !!go,
            buttons.map(b => b.textContent).join(' | '));
        check('and it is wired to the thing that takes them there',
            !!go && /goToEmailSetup/.test(go.getAttribute('onclick') || ''),
            go && go.getAttribute('onclick'));

        w.goToEmailSetup();
        await wait(40);
        check('which goes to the settings screen',
            /settings/.test(w.location.hash), w.location.hash);
        check('closing the prompt behind it', !shown(w));
    }

    // --- a prompt is a nudge, not a gate --------------------------------------------------
    {
        // Started from a state where nothing is shown, so the modal appearing
        // could only come from the error path. Booting with CANNOT would have
        // opened it during boot and proved nothing.
        const { w } = boot(CAN_SEND);
        await wait(40);
        check('nothing is showing to begin with', !shown(w));

        w.fetch = () => Promise.reject(new Error('offline'));
        let threw = false;
        try {
            await w.checkEmailSending();
        } catch (e) {
            threw = true;
        }
        check('a failed check does not throw', !threw);
        check('and does not prompt on an answer it never got', !shown(w));
    }

    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        check('it runs on the same boot as the rest',
            /checkEmailSending\(\);/.test(src));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
