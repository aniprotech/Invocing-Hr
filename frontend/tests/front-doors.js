/**
 * One app, three front doors.
 *
 * invoice., hr. and employee. are the same deployment wearing one face each.
 * On hr.<domain> the app shows HR and nothing of invoicing, whatever the plan
 * holds; the brand says which product it is; the account menu offers the
 * other product when the plan has it; a hash for the other product goes to
 * the other host, hash and all; and a plan without this host's product is
 * sent to the door it does have. On the site or on localhost there is no
 * face and the plan alone decides, as before.
 *
 * The sign-in page on a product host says which product it is and sends
 * Google to that product. The front page's sign-in links go to the doors the
 * server names, and stay put until it names them.
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

function bootApp(url, me) {
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = (u) => {
        const p = String(u).split('?')[0];
        const give = b => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/client/me') return give(me || { modules: ['invoicing', 'hr'] });
        if (p === '/api/auth/me') return give({ user: { email: 'me@example.com' }, client_id: 1 });
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    const gone = [];
    w.goToProduct = (product, p) => { gone.push(product + ':' + (p || '/app.html')); return true; };
    return { w, doc: w.document, gone };
}
const shown = (doc, id) => doc.getElementById(id).style.display !== 'none';

(async () => {
    // --- the face is the host's first label ------------------------------------------
    {
        const { w } = bootApp('https://localhost/app.html');
        check('the first label of the host names the face',
            w.productForHost('hr.aniprotech.com') === 'hr' && w.productForHost('invoice.aniprotech.com:8000') === 'invoicing'
            && w.productForHost('employee.localhost') === 'employee' && w.productForHost('www.aniprotech.com') === ''
            && w.productForHost('localhost') === '');
        check('  the other door is this host with its first label swapped, once the host wears a face',
            w.productUrl('hr') === '' /* localhost wears none */);
    }
    // --- hr.<domain> shows HR alone ---------------------------------------------------
    {
        const { w, doc } = bootApp('https://hr.aniprotech.com/app.html');
        check('on hr. the menu starts as HR before the server has answered',
            w.hasModule('hr') && !w.hasModule('invoicing'));
        w.applyModuleAccess(['invoicing', 'hr']);
        check('  with a plan that has both, invoicing stays hidden and HR shows',
            !shown(doc, 'nav-invoices') && !shown(doc, 'nav-dashboard') && shown(doc, 'nav-people') && shown(doc, 'nav-leave') && shown(doc, 'nav-settings'));
        check('  the Sales and Money groups hide themselves',
            doc.querySelector('[data-nav-group="Sales"]').style.display === 'none' && doc.querySelector('[data-nav-group="People"]').style.display !== 'none');
        check('  the brand says HR and so does the title',
            doc.getElementById('brand-product').textContent === 'HR' && doc.title === 'aniprotech HR');
        const sw = doc.getElementById('user-menu-switch');
        check('  the account menu offers Invoicing, at invoice.aniprotech.com',
            sw.style.display !== 'none' && sw.textContent === 'Switch to Invoicing' && sw.href === 'https://invoice.aniprotech.com/app.html');
        check('  the employee portal link goes to employee.aniprotech.com',
            [...doc.querySelectorAll('a')].some(a => a.href === 'https://employee.aniprotech.com/employee-login.html'));
        check('  the default view is the HR dashboard', w.defaultView() === 'hr-dashboard-view');
        w.applyModuleAccess(['hr']);
        check('  a plan with HR alone has no switch', sw.style.display === 'none');
    }
    // --- invoice.<domain> shows invoicing alone ----------------------------------------
    {
        const { w, doc, gone } = bootApp('https://invoice.aniprotech.com/app.html');
        w.applyModuleAccess(['invoicing', 'hr']);
        check('on invoice. HR is hidden and invoicing shows',
            shown(doc, 'nav-invoices') && shown(doc, 'nav-dashboard') && !shown(doc, 'nav-people') && !shown(doc, 'nav-recruitment')
            && doc.querySelector('[data-nav-group="People"]').style.display === 'none' && doc.querySelector('[data-nav-group="Hiring"]').style.display === 'none');
        check('  the brand says Invoicing', doc.getElementById('brand-product').textContent === 'Invoicing');
        check('  #/leave goes to the HR host, hash and all',
            w.applyRoute('leave') === true && gone[gone.length - 1] === 'hr:/app.html#/leave');
        check('  #/people/12 too', w.applyRoute('people/12') === true && gone[gone.length - 1] === 'hr:/app.html#/people/12');
        check('  #/invoices stays here', w.applyRoute('invoices') === true && gone.length === 2);
        w.applyModuleAccess(['invoicing']);
        check('  with no HR in the plan, #/leave falls to the default view rather than leaving',
            w.applyRoute('leave') === false && gone.length === 2);
    }
    // --- the wrong door ---------------------------------------------------------------
    {
        const { w, gone } = bootApp('https://hr.aniprotech.com/app.html');
        w.applyModuleAccess(['invoicing']);
        check('an invoicing-only plan on hr. is sent to Invoicing', gone[0] === 'invoicing:/app.html');
    }
    // --- the server's word on where the doors are --------------------------------------
    {
        const { w, doc } = bootApp('https://hr.aniprotech.com/app.html', { modules: ['invoicing', 'hr'], product: 'hr',
            products: { invoicing: 'https://bills.example.com', hr: 'https://hr.aniprotech.com', employee: 'https://staff.example.com' } });
        await w.requireAuth();
        // the boot path that reads /api/client/me
        const res = await w.fetch('/api/client/me'); const me = await res.json();
        w._productUrls = me.products; w.applyModuleAccess(me.modules);
        check('the server\'s hosts win over the label convention',
            doc.getElementById('user-menu-switch').href === 'https://bills.example.com/app.html'
            && [...doc.querySelectorAll('a')].some(a => a.href === 'https://staff.example.com/employee-login.html'));
    }
    // --- no face: the site, localhost -----------------------------------------------------
    {
        const { w, doc } = bootApp('https://localhost/app.html');
        w.applyModuleAccess(['invoicing', 'hr']);
        check('with no face the plan alone decides and both products show',
            shown(doc, 'nav-invoices') && shown(doc, 'nav-people') && doc.getElementById('brand-product').textContent === ''
            && doc.getElementById('user-menu-switch').style.display === 'none' && doc.title === 'aniprotech');
    }
    // --- the sign-in page --------------------------------------------------------------------
    {
        const login = (url) => {
            const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'login.html'), 'utf8'), { runScripts: 'dangerously', pretendToBeVisual: true, url,
                beforeParse(w) { w.fetch = () => Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }); w.console.error = () => { }; } });
            return dom.window.document;
        };
        const hr = login('https://hr.aniprotech.com/login.html');
        check('on hr. the door says Sign in to HR and points Google at HR',
            hr.getElementById('door-title').textContent === 'Sign in to HR' && hr.getElementById('google-btn').getAttribute('href') === '/api/auth/login?portal=hr'
            && /Looking for invoicing/.test(hr.getElementById('door-intro').textContent)
            && hr.querySelector('#door-intro a').href === 'https://invoice.aniprotech.com/login.html');
        const inv = login('https://invoice.aniprotech.com/login.html');
        check('  on invoice. it says Invoicing and offers HR',
            inv.getElementById('door-title').textContent === 'Sign in to Invoicing' && inv.getElementById('google-btn').getAttribute('href') === '/api/auth/login?portal=invoicing'
            && inv.querySelector('#door-intro a').href === 'https://hr.aniprotech.com/login.html');
        const www = login('https://www.aniprotech.com/login.html');
        check('  on the site it is the one door it always was',
            www.getElementById('door-title').textContent === 'Welcome back' && !www.querySelector('#door-intro a'));
    }
    // --- the front page --------------------------------------------------------------------------
    {
        const landing = (products) => new Promise(resolve => {
            const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8'), { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://www.aniprotech.com/',
                beforeParse(w) {
                    w.fetch = (u) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(String(u).indexOf('/api/platform/landing') >= 0 ? { landing: {}, items: {}, products } : {}), text: () => Promise.resolve('{}') });
                    w.console.error = () => { };
                } });
            setTimeout(() => resolve(dom.window.document), 40);
        });
        const split = await landing({ invoicing: 'https://invoice.aniprotech.com', hr: 'https://hr.aniprotech.com', employee: 'https://employee.aniprotech.com' });
        const hrefs = [...split.querySelectorAll('a')].map(a => a.getAttribute('href'));
        check('once the doors are named, every business sign-in link goes to Invoicing and every staff one to the portal',
            !hrefs.includes('/login.html') && !hrefs.includes('/employee-login.html')
            && hrefs.filter(h => h === 'https://invoice.aniprotech.com/login.html').length >= 3
            && hrefs.filter(h => h === 'https://employee.aniprotech.com/employee-login.html').length >= 3, hrefs.filter(h => /login/.test(h)).join(' '));
        check('  and the HR button appears', split.getElementById('cta-hr').style.display !== 'none' && split.getElementById('cta-hr').getAttribute('href') === 'https://hr.aniprotech.com/login.html');
        const one = await landing({});
        check('  until then the links stay on this address and there is no HR button',
            one.querySelector('a[href="/login.html"]') && one.querySelector('a[href="/employee-login.html"]') && one.getElementById('cta-hr').style.display === 'none');
    }
    console.log(failures === 0 ? '\nAll front-door checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
