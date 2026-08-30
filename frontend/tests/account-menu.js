/**
 * Your own account, from the app and from the sign-in page.
 *
 * The avatar in the header was an initial in a circle next to a bare logout
 * icon - so the only thing you could do with your own account was leave it,
 * and the icon did it without asking. And sign-in was Google only: the
 * password endpoints had existed and been tested since the beginning, but no
 * page offered them, so an account that lost its Google access had no way in.
 *
 * These cover the two things that are easy to get wrong and quiet when wrong:
 * a menu that cannot be dismissed, and a password form that sends the current
 * password when there is not one (or omits it when there is).
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

// --- the app's header menu ---------------------------------------------------
function bootApp(opts) {
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
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({
                    user: { email: 'ada@acme.test', name: 'Ada Reid' }, client_id: 1,
                }),
            });
        }
        if (p === '/api/client/password-status') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({
                    has_password: opts.hasPassword !== false,
                    email: 'ada@acme.test',
                    is_owner: opts.isOwner !== false,
                }),
            });
        }
        if (p === '/api/client/set-password') {
            const failWith = opts.setPasswordError;
            if (failWith) {
                return Promise.resolve({
                    ok: false, status: 400,
                    json: () => Promise.resolve({ detail: failWith }),
                });
            }
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ message: 'Password changed', has_password: true }),
            });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }),
            });
        }
        const body = p.endsWith('s') ? [] : {};
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    // The pages load dialogs.js from a <script src>, which this harness strips.
    // Without it every alert/confirm/prompt call site throws.
    if (!w.requestAnimationFrame) w.requestAnimationFrame = function (cb) { return setTimeout(cb, 0); };
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));

    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent };
}

const isOpen = w => w.document.getElementById('user-info').classList.contains('open');

(async () => {
    // --- the menu opens, closes, and says who you are -----------------------
    {
        const { w } = bootApp();
        await wait(120);
        const btn = w.document.getElementById('user-menu-btn');

        check('the avatar is a real button, so it can be tabbed to',
            btn.tagName === 'BUTTON', btn.tagName);
        check('it announces itself as a menu',
            btn.getAttribute('aria-haspopup') === 'menu');
        check('the menu starts closed', !isOpen(w));
        check('and says so for a screen reader',
            btn.getAttribute('aria-expanded') === 'false');

        w.toggleUserMenu();
        check('clicking opens it', isOpen(w));
        check('and updates aria-expanded',
            btn.getAttribute('aria-expanded') === 'true');

        check('the menu names who is signed in',
            w.document.getElementById('user-menu-name').textContent === 'Ada Reid',
            w.document.getElementById('user-menu-name').textContent);
        check('and their email',
            w.document.getElementById('user-menu-email').textContent === 'ada@acme.test',
            w.document.getElementById('user-menu-email').textContent);

        check('log out is in the menu, not a bare icon',
            /Log out/.test(w.document.getElementById('user-menu').textContent));
    }

    // --- a menu you cannot dismiss is a menu people leave open --------------
    {
        const { w } = bootApp();
        await wait(120);
        w.toggleUserMenu();
        check('a click elsewhere closes it', (() => {
            w.document.body.dispatchEvent(new w.Event('click', { bubbles: true }));
            return !isOpen(w);
        })());

        w.toggleUserMenu();
        check('Escape closes it too', (() => {
            const e = new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
            w.document.dispatchEvent(e);
            return !isOpen(w);
        })());

        w.toggleUserMenu();
        check('clicking inside the menu does not close it', (() => {
            const item = w.document.querySelector('#user-menu .user-menu-item');
            item.dispatchEvent(new w.Event('click', { bubbles: true }));
            return isOpen(w);
        })());
    }

    // --- the wording follows how this account actually signs in -------------
    {
        const { w } = bootApp({ hasPassword: false });
        await wait(120);
        check('an account with no password is offered one',
            w.document.getElementById('user-menu-password-label').textContent
                === 'Create a password',
            w.document.getElementById('user-menu-password-label').textContent);

        w.openPasswordModal();
        check('and the form does not ask for a current password it cannot have',
            w.document.getElementById('password-current-group').style.display === 'none');
        check('the title says what it is doing',
            w.document.getElementById('password-modal-title').textContent
                === 'Create a password');
    }

    {
        const { w } = bootApp({ hasPassword: true });
        await wait(120);
        check('an account that has one is offered a change',
            w.document.getElementById('user-menu-password-label').textContent
                === 'Change password',
            w.document.getElementById('user-menu-password-label').textContent);

        w.openPasswordModal();
        check('and the form asks for the current password',
            w.document.getElementById('password-current-group').style.display !== 'none');
    }

    {
        const { w } = bootApp({ isOwner: false });
        await wait(120);
        check('a colleague is told they are one',
            w.document.getElementById('user-menu-role').style.display !== 'none' &&
            /Team member/.test(w.document.getElementById('user-menu-role').textContent));
    }

    // --- what the form actually sends ---------------------------------------
    {
        const { w, sent } = bootApp({ hasPassword: true });
        await wait(120);
        w.openPasswordModal();
        w.document.getElementById('pw-current').value = 'OldPass1';
        w.document.getElementById('pw-new').value = 'NewPass1';
        w.document.getElementById('pw-confirm').value = 'NewPass1';
        sent.length = 0;
        await w.savePassword();

        const post = sent.find(s => s.url === '/api/client/set-password');
        check('changing sends both passwords', !!post && (() => {
            const b = JSON.parse(post.body);
            return b.current_password === 'OldPass1' && b.new_password === 'NewPass1';
        })(), post && post.body);
        check('and the modal closes on success',
            w.document.getElementById('password-modal').style.display === 'none');
    }

    {
        const { w, sent } = bootApp({ hasPassword: false });
        await wait(120);
        w.openPasswordModal();
        w.document.getElementById('pw-new').value = 'FirstPass1';
        w.document.getElementById('pw-confirm').value = 'FirstPass1';
        sent.length = 0;
        await w.savePassword();

        const post = sent.find(s => s.url === '/api/client/set-password');
        check('creating a first password sends no current password',
            !!post && JSON.parse(post.body).current_password === undefined,
            post && post.body);
    }

    // --- mistakes are caught where they can be explained --------------------
    {
        const { w, sent } = bootApp({ hasPassword: true });
        await wait(120);
        w.openPasswordModal();
        w.document.getElementById('pw-current').value = 'OldPass1';
        w.document.getElementById('pw-new').value = 'NewPass1';
        w.document.getElementById('pw-confirm').value = 'Different1';
        sent.length = 0;
        await w.savePassword();

        check('two new passwords that differ never reach the server',
            !sent.some(s => s.url === '/api/client/set-password'));
        check('and the reason is on screen',
            /do not match/i.test(w.document.getElementById('password-modal-error').textContent),
            w.document.getElementById('password-modal-error').textContent);
        check('the form stays open so it can be corrected',
            w.document.getElementById('password-modal').style.display !== 'none');
    }

    {
        const { w } = bootApp({ hasPassword: true, setPasswordError: 'That is not your current password' });
        await wait(120);
        w.openPasswordModal();
        w.document.getElementById('pw-current').value = 'WrongPass1';
        w.document.getElementById('pw-new').value = 'NewPass1';
        w.document.getElementById('pw-confirm').value = 'NewPass1';
        await w.savePassword();

        check("the server's reason is shown, not a generic failure",
            /not your current password/i.test(
                w.document.getElementById('password-modal-error').textContent),
            w.document.getElementById('password-modal-error').textContent);
    }

    // --- the sign-in page ----------------------------------------------------
    {
        const raw = fs.readFileSync(path.join(ROOT, 'login.html'), 'utf8');
        const doc = new JSDOM(raw).window.document;
        check('the sign-in page offers an email and password',
            !!doc.getElementById('pw-email') && !!doc.getElementById('pw-password'));
        check('and a way to create an account', !!doc.getElementById('pw-mode-toggle'));
        check('Google is still offered', !!doc.getElementById('google-btn'));

        // reset-password.html needs a ?token= and shows a dead link without
        // one, so Forgot password must not simply link there.
        const forgot = doc.getElementById('pw-forgot');
        check('forgot password does not link to the page that needs a token',
            forgot.tagName === 'BUTTON' || !/reset-password\.html/.test(forgot.getAttribute('href') || ''),
            forgot.outerHTML.slice(0, 90));
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
