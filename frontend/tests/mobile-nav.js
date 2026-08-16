/**
 * The mobile header, which has now broken three times.
 *
 * Two failures keep recurring. The drawer opens but tapping an item leaves it
 * open over the view it just navigated to, so the nav looks dead. And the
 * horizontal scroll fade, which is a hint on a wide desktop, sits over a real
 * menu item once the bar overflows and makes it look disabled.
 *
 * jsdom does no layout, so the fade is checked by reading the stylesheet
 * itself: every breakpoint that turns the nav into a drawer must also switch
 * the mask off.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(ROOT, 'styles.css'), 'utf8');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

// --- the stylesheet ---------------------------------------------------------

/** Pull out each `@media (...) { ... }` block, brace-matched. */
function mediaBlocks(source) {
    const blocks = [];
    const re = /@media([^{]+)\{/g;
    let m;
    while ((m = re.exec(source))) {
        let depth = 1, i = re.lastIndex;
        while (i < source.length && depth > 0) {
            if (source[i] === '{') depth++;
            else if (source[i] === '}') depth--;
            i++;
        }
        blocks.push({ query: m[1].trim(), body: source.slice(re.lastIndex, i - 1) });
    }
    return blocks;
}

const blocks = mediaBlocks(css);
const drawerBlocks = blocks.filter(b => b.body.includes('.top-nav-menu.mobile-open'));

check('some breakpoint turns the nav into a drawer', drawerBlocks.length > 0);

for (const b of drawerBlocks) {
    const q = b.query;
    check(`the drawer at ${q} switches the scroll fade off`,
        /mask-image:\s*none/.test(b.body),
        'a horizontal fade over a vertical drawer washes out every item');
}

// The drawer has to appear before the bar runs out of room. Eleven items at
// roughly 90px each need about a thousand pixels.
const widths = drawerBlocks
    .map(b => (b.query.match(/max-width:\s*(\d+)px/) || [])[1])
    .filter(Boolean)
    .map(Number);
check('the drawer starts at 1024px or wider', Math.max(...widths, 0) >= 1024,
    `widest drawer breakpoint is ${Math.max(...widths, 0)}px, but the bar overflows well above that`);

const baseRule = (css.match(/^\.top-nav-menu \{[^}]*\}/m) || [''])[0];

// The group menus are absolutely positioned against the nav. An overflow
// container clips anything positioned inside it, so scrolling the bar
// sideways makes every menu open where nobody can see it.
check('the header does not clip its dropdowns',
    !/overflow(-x)?:\s*(auto|scroll|hidden)/.test(baseRule),
    'an overflow container hides the group menus completely');

// If a fade is ever reinstated it must not be wide enough to cover an item.
const fade = baseRule.match(/mask-image:[^;]*/);
check('no fade covers a whole menu item',
    !fade || /calc\(100% - \d+px\)/.test(fade[0]),
    'a percentage-based fade washes out the last item');

// A group in the drawer must be collapsed until tapped. Rendering them all
// expanded lists every item flat under a label, which is the ungrouped header
// again wearing a hat.
const drawerGroupBlocks = blocks.filter(b => b.body.includes('.nav-group-menu'));
check('some breakpoint styles groups inside the drawer', drawerGroupBlocks.length > 0);
for (const b of drawerGroupBlocks) {
    const menu = b.body.match(/\.nav-group-menu\s*\{[^}]*\}/);
    check(`the drawer at ${b.query} keeps groups closed until opened`,
        !!menu && /display:\s*none/.test(menu[0]) &&
        /\.nav-group\.open\s*>\s*\.nav-group-menu/.test(b.body),
        'every group renders expanded, so the drawer is a flat list again');
}

// The overlay must sit below the header. The header sets backdrop-filter,
// which makes it a stacking context, so the drawer inside it cannot climb above
// the header's own z-index no matter what its own is. An overlay above that
// number covers the open menu: every item dimmed, every tap swallowed.
function zOf(selector) {
    const at = css.indexOf(selector + ' {');
    if (at < 0) return null;
    const rule = css.slice(at, css.indexOf('}', at));
    const z = rule.match(/z-index:\s*(\d+)/);
    return z ? Number(z[1]) : null;
}
const topbarZ = zOf('.enterprise-topbar');
const overlayZ = zOf('.mobile-overlay');
check('the header and the overlay both declare a stacking order',
    topbarZ !== null && overlayZ !== null, `topbar ${topbarZ}, overlay ${overlayZ}`);
check('the overlay sits below the header, not over it',
    overlayZ < topbarZ,
    `overlay ${overlayZ} covers the header at ${topbarZ}, so the open drawer is dimmed and untappable`);

// --- the behaviour ----------------------------------------------------------

(async () => {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const body = p === '/api/client/me' ? { id: 1, email: 'me@example.com' }
            : p === '/api/auth/me' ? { user: { email: 'me@example.com' } }
                : (p.endsWith('s') ? [] : {});
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(body), text: () => Promise.resolve('{}'),
        });
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    await new Promise(r => setTimeout(r, 400));

    const nav = w.document.getElementById('main-nav');
    const overlay = w.document.getElementById('mobile-overlay');
    check('the header has a nav and an overlay', !!nav && !!overlay);

    w.eval('toggleMobileMenu()');
    check('the hamburger opens the drawer', nav.classList.contains('mobile-open'));
    check('opening dims the page behind it', overlay.classList.contains('active'));
    check('opening stops the page scrolling', w.document.body.classList.contains('no-scroll'));

    // The bug: tapping a menu item navigated but left the drawer covering it.
    w.eval("showView('invoices-view')");
    check('choosing a view closes the drawer', !nav.classList.contains('mobile-open'),
        'the drawer stayed open over the view it had just opened');
    check('choosing a view clears the overlay', !overlay.classList.contains('active'));
    check('choosing a view lets the page scroll again', !w.document.body.classList.contains('no-scroll'));

    // Closing twice must not leave the page unscrollable.
    w.eval('closeMobileMenu(); closeMobileMenu();');
    check('closing an already closed drawer is harmless', !w.document.body.classList.contains('no-scroll'));

    dom.window.close();
    console.log(failures ? `\n${failures} check(s) failed` : '\nthe mobile header opens, navigates and gets out of the way');
    process.exit(failures ? 1 : 0);
})();
