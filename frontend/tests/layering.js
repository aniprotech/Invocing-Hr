/**
 * What sits on top of what.
 *
 * Every fixed thing in this app had a z-index picked in isolation, and the
 * result was predictable: the floating AI orb painted over open dialogs, the
 * "powered by" badge sat at dialog level in the same corner as the orb, and
 * the scrim behind the mobile drawer covered the drawer itself.
 *
 * jsdom does no layout, so this reads the stylesheet. That is enough: a
 * stacking bug is a comparison between two numbers, and the numbers are here.
 */
const fs = require('fs');
const path = require('path');

const css = fs.readFileSync(path.resolve(__dirname, '..', 'styles.css'), 'utf8');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

/** The declared value of one --layer-* variable. */
function layer(name) {
    const m = css.match(new RegExp('--layer-' + name + ': *([0-9]+)'));
    return m ? Number(m[1]) : null;
}

/** What a selector's own rule resolves to, following one level of variable. */
function zOf(selector) {
    const at = css.indexOf(selector + ' {');
    if (at < 0) return null;
    const rule = css.slice(at, css.indexOf('}', at));
    const z = rule.match(/z-index: *([^;]+)/);
    if (!z) return null;
    const raw = z[1].trim();
    const named = raw.match(/--layer-([a-z]+)/);
    if (!named) return Number(raw);
    const base = layer(named[1]);
    const plus = raw.match(/[+] *([0-9]+)/);
    return base === null ? null : base + (plus ? Number(plus[1]) : 0);
}

// --- the scale exists at all -------------------------------------------------

const names = ['sticky', 'scrim', 'topbar', 'drawer', 'menu', 'popover',
    'float', 'decor', 'modal', 'toast', 'skip'];
for (const n of names) {
    check(`the scale defines --layer-${n}`, layer(n) !== null);
}

check('the scale is in ascending order',
    names.every((n, i) => i === 0 || layer(n) > layer(names[i - 1])),
    names.map(n => `${n}=${layer(n)}`).join(' '));

// --- the comparisons that were actually wrong --------------------------------

check('the floating AI orb sits below dialogs',
    zOf('.ai-core') < zOf('.modal-overlay'),
    `orb ${zOf('.ai-core')} vs dialog ${zOf('.modal-overlay')} - the orb covered open dialogs`);

check('the AI window sits below dialogs',
    zOf('.ai-chat-window') < zOf('.modal-overlay'),
    `window ${zOf('.ai-chat-window')} vs dialog ${zOf('.modal-overlay')}`);

check('the AI window sits above its own orb',
    zOf('.ai-chat-window') > zOf('.ai-core'));

check('the drawer scrim sits below the header',
    zOf('.mobile-overlay') < zOf('.enterprise-topbar'),
    'the header makes a stacking context, so a scrim above it covers the open drawer');

check('the decorative scanline never covers a dialog',
    zOf('body::after') < zOf('.modal-overlay'),
    'a full-screen overlay at dialog level dims every dialog');

check('toasts are readable over a dialog',
    zOf('#toast-container') > zOf('.modal-overlay'),
    'a toast usually reports on what the dialog just did');

check('the keyboard skip link comes before everything',
    zOf('.skip-link') >= layer('skip'));

check('the credit line is nowhere near the dialog layer',
    zOf('.powered-by') !== null && zOf('.powered-by') < zOf('.modal-overlay'),
    `badge ${zOf('.powered-by')} - it used to be 9999, floating over dialogs`);

// --- the two things that shared a corner -------------------------------------

function corner(selector) {
    const at = css.indexOf(selector + ' {');
    if (at < 0) return {};
    const rule = css.slice(at, css.indexOf('}', at));
    const grab = k => {
        const m = rule.match(new RegExp(k + ': *([0-9]+)px'));
        return m ? Number(m[1]) : null;
    };
    return { bottom: grab('bottom'), right: grab('right'), left: grab('left') };
}

const orb = corner('.ai-core');
const badge = corner('.powered-by');
check('the orb and the credit line are not in the same corner',
    !(orb.right !== null && badge.right !== null),
    'both pinned bottom-right, so they overlapped');

// --- nothing is left underneath the orb --------------------------------------

check('scrolling content clears the floating orb',
    /[.]main-content *[{][^}]*padding-bottom: *[0-9]+px/.test(css),
    'the last row of every view sits under the orb without it');

// --- every dialog is actually styled ----------------------------------------
// Five dialogs carried class="modal-content", which no rule in the stylesheet
// mentions. They rendered with no background, no height cap and no scroll: the
// page showed through them and a tall form ran off the top of the screen with
// its first fields unreachable.
//
// Nothing caught it because a DOM test asks whether an element exists, and it
// did. What was missing was the styling.
{
    const { JSDOM } = require('jsdom');
    const styledClasses = new Set(
        (css.match(/\.([a-zA-Z][\w-]*)/g) || []).map(c => c.slice(1)));

    for (const page of ['app.html', 'hr.html', 'superadmin.html',
                        'employee-dashboard.html']) {
        let raw;
        try {
            raw = fs.readFileSync(path.resolve(__dirname, '..', page), 'utf8');
        } catch (e) { continue; }

        const doc = new JSDOM(raw).window.document;
        const overlays = [...doc.querySelectorAll('.modal-overlay')];
        if (!overlays.length) continue;

        const unstyled = overlays.filter(o => {
            const box = o.firstElementChild;
            if (!box) return true;
            // At least one of its classes has to appear in the stylesheet, or
            // the box is drawn with nothing at all.
            return ![...box.classList].some(c => styledClasses.has(c));
        }).map(o => o.id || '(no id)');

        check(`${page}: every dialog carries a class the stylesheet knows`,
            unstyled.length === 0, unstyled.join(', '));
    }

    // The rule those dialogs depend on, so a rename cannot quietly remove it.
    check('.modal caps its height and scrolls',
        /\.modal *\{[^}]*max-height:[^}]*overflow-y: *auto/.test(css),
        'a tall dialog would run off the screen with no way back to the top');
    check('.modal paints its own background',
        /\.modal *\{[^}]*background:/.test(css),
        'the page would show through it');
}

console.log(failures ? `\n${failures} layering problem(s)` : '\nthe stacking order holds together');
process.exit(failures ? 1 : 0);
