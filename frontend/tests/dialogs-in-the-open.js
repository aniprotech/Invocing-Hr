/**
 * A dialog must not live inside a box that blurs or moves.
 *
 * The workflow dialog opened with its top third above the screen and no way
 * to scroll up to it. So did the survey, asset and password dialogs. Their
 * markup sat inside the <header>, and the header blurs what is behind it
 * (backdrop-filter). That property - like transform, filter, perspective and
 * contain - makes the element the containing block for any position:fixed
 * descendant, so an overlay declared as inset:0 filled a 63px strip of header
 * instead of the screen, and a 520px dialog centred inside 63px hung off the
 * top. "Assets UI is breaking" was this.
 *
 * jsdom does no layout, so this reads the stylesheet for every selector that
 * sets one of those properties and checks that no dialog on any page has an
 * ancestor matching one. Pseudo-classes are stripped: .widget:hover moves the
 * widget while the mouse is on it, and the mouse is on it when the button
 * inside it is pressed.
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

const TRAPPING = /(?:^|[;\s{])(?:-webkit-)?(?:backdrop-filter|filter|transform|perspective|contain)\s*:\s*(?!none)/;

/** Every selector in styles.css whose rule turns the element into a containing block. */
function trappingSelectors() {
    const css = fs.readFileSync(path.join(ROOT, 'styles.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
    const out = new Set();
    const re = /([^{}]+)\{([^{}]*)\}/g;
    let m;
    while ((m = re.exec(css))) {
        const body = m[2];
        if (!TRAPPING.test(body)) continue;
        // `transform: none` on a hover reset, or `backdrop-filter: none` in
        // print, is not a trap - only a value that is something.
        for (let sel of m[1].split(',')) {
            sel = sel.trim().split(/\s+/).pop();     // the element the rule lands on
            if (!sel || /^[@%]|^(from|to|\d)/.test(sel)) continue;
            sel = sel.replace(/::?[a-z-]+(\([^)]*\))?/g, '');    // :hover, ::after
            if (sel && /^[.#a-zA-Z]/.test(sel)) out.add(sel);
        }
    }
    return [...out];
}

const traps = trappingSelectors();
check('the stylesheet was read and has blurred or moving boxes in it', traps.length >= 5, String(traps.length));
check('  and the header is one of them, so this test can see what broke',
    traps.includes('.enterprise-topbar'), traps.join(' '));

const pages = fs.readdirSync(ROOT).filter(f => f.endsWith('.html'));
let dialogs = 0;
for (const page of pages) {
    const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const doc = new JSDOM(html).window.document;
    const overlays = [...doc.querySelectorAll('.modal-overlay, [style*="position:fixed"], [style*="position: fixed"]')];
    if (!overlays.length) continue;
    dialogs += overlays.length;
    const trapped = [];
    for (const el of overlays) {
        for (const sel of traps) {
            let hit = null;
            try { hit = el.parentElement && el.parentElement.closest(sel); } catch (e) { /* not a jsdom selector */ }
            if (hit) trapped.push((el.id || el.className || el.tagName) + ' inside ' + sel);
        }
    }
    check(page + ': ' + overlays.length + ' fixed thing(s), none inside a box that would trap them',
        trapped.length === 0, trapped.join('; '));
}
check('dialogs were actually found across the pages', dialogs >= 31, String(dialogs));

console.log(failures === 0
    ? '\nAll dialog-placement checks passed.'
    : `\n${failures} dialog-placement check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
