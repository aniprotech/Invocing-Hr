/**
 * Policy pages, written in the operator screen and published from there.
 *
 * The front page had no policies at all and no way to add one without a
 * deploy. These now come from the same store as the other landing entries.
 *
 * Two things are worth holding to. A policy is copy typed into a form, so it
 * must render as text - a legal notice is the last page on which somebody
 * else's markup should run. And a policy that fails to load must say so
 * rather than showing an empty page under a legal heading, which reads as
 * though the policy itself is blank.
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

function boot(opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'policy.html'), 'utf8');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously', pretendToBeVisual: true,
        url: 'https://localhost/policy.html?id=' + (opts.id === undefined ? '1' : opts.id),
        beforeParse(w) {
            w.console.error = () => { };
            w.fetch = (u) => {
                const p = String(u);
                if (p.indexOf('/api/platform/policies/') > -1) {
                    if (opts.missing) {
                        return Promise.resolve({ ok: false, status: 404,
                            json: () => Promise.resolve({ detail: 'No such policy' }) });
                    }
                    return Promise.resolve({ ok: true, status: 200,
                        json: () => Promise.resolve(opts.policy || {
                            id: 1, title: 'Privacy Policy', updated: '2026-09-02 10:00:00',
                            body: 'First paragraph.\n\nSecond paragraph.',
                        }) });
                }
                return Promise.resolve({ ok: true, status: 200,
                    json: () => Promise.resolve({
                        landing: { footer_copy: '(c) 2026 Ani Protech' },
                        items: { policy: opts.others || [
                            { id: 1, title: 'Privacy Policy' },
                            { id: 2, title: 'Terms of Service' }] },
                    }) });
            };
        },
    });
    return dom.window;
}

(async () => {
    {
        const w = boot();
        await wait(150);
        const d = w.document;
        check('the policy is shown', !d.getElementById('sheet').hidden);
        check('under its own title',
            d.getElementById('policy-title').textContent === 'Privacy Policy',
            d.getElementById('policy-title').textContent);
        check('the tab says which policy it is',
            /Privacy Policy/.test(d.title), d.title);
        check('with the date it last changed',
            /2026-09-02/.test(d.getElementById('policy-updated').textContent),
            d.getElementById('policy-updated').textContent);

        const paras = d.querySelectorAll('#policy-body p');
        check('blank lines become paragraphs, not one wall of text',
            paras.length === 2, paras.length);
        check('and keep their wording',
            paras[1].textContent === 'Second paragraph.', paras[1].textContent);
    }

    // --- copy is copy ---------------------------------------------------------
    {
        const w = boot({ policy: { id: 1, title: 'Terms', updated: '',
            body: '<script>window.__pwned=1<\/script>\n\nSecond.' } });
        await wait(150);
        check('markup in a policy does not run', !w.__pwned);
        check('it is shown as the characters that were typed',
            /<script>/.test(w.document.getElementById('policy-body').textContent),
            w.document.getElementById('policy-body').textContent.slice(0, 40));
        check('and no element was created from it',
            w.document.querySelectorAll('#policy-body script').length === 0);
    }

    // --- when it is not there --------------------------------------------------
    {
        const w = boot({ missing: true });
        await wait(150);
        const d = w.document;
        check('a policy that is gone says so',
            /not available/i.test(d.getElementById('state').textContent),
            d.getElementById('state').textContent);
        check('rather than showing an empty page under a legal heading',
            d.getElementById('sheet').hidden);
    }

    {
        const w = boot({ id: '' });
        await wait(150);
        check('asking for no policy at all is explained, not left loading',
            /no policy/i.test(w.document.getElementById('state').textContent),
            w.document.getElementById('state').textContent);
    }

    // --- finding the others -----------------------------------------------------
    {
        const w = boot();
        await wait(150);
        const links = [...w.document.querySelectorAll('#others a')];
        check('the other policies are linked', links.length === 1, links.length);
        check('and the one being read is not linked to itself',
            links[0].textContent === 'Terms of Service', links[0].textContent);
        check('each link carries its id',
            /id=2/.test(links[0].getAttribute('href')), links[0].getAttribute('href'));
    }

    {
        const w = boot({ others: [{ id: 1, title: 'Privacy Policy' }] });
        await wait(150);
        check('with nothing else to link, the row stays hidden',
            w.document.getElementById('others').hidden);
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
