/**
 * The strip behind the status bar.
 *
 * Reported from a phone: the top bar and the system icons drawn on top of one
 * another - the clock over the hamburger, the battery over the logo.
 *
 * Every page in the site asks iOS for a translucent status bar and declares
 * viewport-fit=cover. Both are deliberate and both mean the same thing: when
 * the app is installed to a home screen it draws its own content from the very
 * top of the screen rather than below the clock. Android 15 does the same to
 * an installed PWA. That is fine, and it is how an app is supposed to look -
 * but only if something reserves the strip the system icons occupy, and
 * nothing did. env(safe-area-inset-top) appeared nowhere in the site, while
 * the left, right and bottom insets were all handled.
 *
 * Two shapes of page need opposite treatment, which is what most of this file
 * is about. A page with nothing anchored to the top can start lower, and
 * mobile.css does that for all of them at once. A page whose own bar is fixed
 * or sticky cannot: the bar is still drawn at the top of the screen, so
 * reserving space above it would only show the page scrolling past in the gap.
 * Those pages have to grow the bar itself, and say so by marking the body, or
 * they get both treatments and neither works.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const pages = fs.readdirSync(ROOT).filter(f => f.endsWith('.html'));

const mobileCss = read('mobile.css');
const appCss = read('styles.css');

const declaresCover = src => /viewport-fit=cover/.test(src);
const drawsBehindTheStatusBar = src =>
    /status-bar-style"\s*content="black-translucent"/.test(src);
const loadsSharedCss = src => /href="\/?mobile\.css/.test(src);
const marksTheBody = src => /<body[^>]*class="[^"]*owns-the-safe-area/.test(src);

// A page that only bounces somewhere else renders nothing there is room to
// collide with. Recognised by what it does rather than by name, so a new one
// is covered and a real page can never be mistaken for one.
const onlyRedirects = src =>
    /location\.replace\(/.test(src) && /http-equiv="refresh"/.test(src);

/* Anything pinned to the very top of the window: a rule in the page's own
   stylesheet that is fixed or sticky at top 0, or the Tailwind pair that says
   the same thing in markup. `inset: 0` is deliberately not matched - a
   full-screen backdrop or a centred modal overlay has nothing at its top edge
   to collide with. */
const hasATopAnchoredBar = src => {
    const rules = (src.match(/\{[^{}]*\}/g) || []).some(rule => {
        const flat = rule.replace(/\s+/g, '');
        return /position:(fixed|sticky)/.test(flat) && /(^|[;{])top:0/.test(flat);
    });
    const tailwind = /class="[^"]*\b(sticky|fixed)\s+top-0\b/.test(src);
    // app.html's bar lives in the shared stylesheet rather than in the page.
    const shared = /class="enterprise-topbar"/.test(src);
    return rules || tailwind || shared;
};

// --- the shared rule, which covers most of the site ----------------------------------
{
    check('the shared stylesheet starts a page below the status bar',
        /body\s*\{[^}]*padding-top:\s*env\(safe-area-inset-top/.test(mobileCss));

    check('and counts it inside a full-height page rather than adding to it',
        /body\s*\{[^}]*box-sizing:\s*border-box/.test(mobileCss),
        'without border-box, 100dvh plus the inset overflows the screen');

    check('a page that handles the strip in its own bar can opt out',
        /body\.owns-the-safe-area\s*\{\s*padding-top:\s*0/.test(mobileCss));

    check('the bottom inset is still handled',
        /padding-bottom:\s*env\(safe-area-inset-bottom/.test(mobileCss));

    // The fallback is what makes all of this a no-op in an ordinary browser
    // tab, where the browser has already made room and the inset is 0.
    // Comments are stripped first, since the prose explaining all this names
    // the function without one.
    const rulesOnly = css => css.replace(/\/\*[\s\S]*?\*\//g, '');
    const bare = [...[mobileCss, appCss], ...pages.map(read)]
        .flatMap(src => rulesOnly(src).match(/env\(safe-area-inset-[a-z]+\)/g) || []);
    check('every inset names a fallback, so a browser that has none gets 0',
        bare.length === 0, bare.join(', '));
}

// --- every page that opts into drawing edge to edge gets that rule ---------------------
{
    const missing = pages.filter(f => declaresCover(read(f)) && !loadsSharedCss(read(f)));
    check('every page that draws edge to edge loads the shared stylesheet',
        missing.length === 0, missing.join(', '));

    // Without viewport-fit=cover the inset reports 0, so a page that draws
    // behind the status bar without it cannot be corrected in CSS at all.
    const uncorrectable = pages.filter(f => {
        const src = read(f);
        return drawsBehindTheStatusBar(src) && !declaresCover(src) && !onlyRedirects(src);
    });
    check('and none draws behind the status bar without a way to measure it',
        uncorrectable.length === 0, uncorrectable.join(', '));
}

// --- a page with its own bar has to grow it ---------------------------------------------
{
    const withBars = pages.filter(f => {
        const src = read(f);
        return declaresCover(src) && hasATopAnchoredBar(src);
    });
    check('some pages pin a bar to the top of the window', withBars.length > 0,
        withBars.join(', '));

    const unmarked = withBars.filter(f => !marksTheBody(read(f)));
    check('and every one of them says it handles the strip itself',
        unmarked.length === 0,
        `${unmarked.join(', ')} would be pushed down and still collide`);

    // The mark alone is a promise. This is the bar keeping it.
    const empty = withBars.filter(f => {
        const src = read(f);
        const own = /env\(safe-area-inset-top/.test(src);
        const shared = loadsSharedCss(src) && /class="enterprise-topbar"/.test(src)
            && /env\(safe-area-inset-top/.test(appCss);
        return !own && !shared;
    });
    check('and reserves it somewhere, rather than only opting out',
        empty.length === 0, empty.join(', '));

    // The inverse: opting out without a bar means the strip is reserved by
    // nobody, which is the original fault with an extra step.
    const claiming = pages.filter(f => marksTheBody(read(f)));
    const idle = claiming.filter(f => !hasATopAnchoredBar(read(f)));
    check('and nothing opts out without a bar to do the job',
        idle.length === 0, idle.join(', '));
}

// --- the app's own bar, and everything measured against it -------------------------------
{
    check('the app bar is taller by the strip, not merely padded',
        /--topbar-total:\s*calc\(var\(--topbar-height\)\s*\+\s*env\(safe-area-inset-top/
            .test(appCss),
        'padding inside a fixed height squashes the contents instead');

    check('and holds its contents below it',
        /\.enterprise-topbar\s*\{[^}]*padding-top:\s*env\(safe-area-inset-top/.test(appCss));

    // The drawer opens directly under the bar. Measured against the old height
    // it would open behind it, hiding its first menu item.
    const stale = appCss.split('\n')
        .map((line, i) => [i + 1, line])
        .filter(([, line]) => /var\(--topbar-height\)/.test(line))
        .filter(([, line]) => !/--topbar-height:|--topbar-total:/.test(line));
    check('and everything positioned against it follows the taller bar',
        stale.length === 0, stale.map(([n, l]) => `${n}: ${l.trim()}`).join(' | '));
}

// --- the staff app, whose two bars are stacked ----------------------------------------------
{
    const staff = read('employee-dashboard.html');

    check('the staff app bar reserves the strip',
        /\.app-bar\s*\{\s*padding-top:\s*env\(safe-area-inset-top/.test(staff));
    check('and the markup uses it', /class="app-bar /.test(staff));

    // The tabs bar sits under the nav. It was pinned at top-16 (64px) beneath a
    // bar that is h-14 (56px), so 8px of the page scrolled through the gap
    // between them - before any of this, and on every device.
    check('the second bar starts exactly where the first ends',
        /\.app-bar-second\s*\{\s*top:\s*calc\(3\.5rem\s*\+\s*env\(safe-area-inset-top/
            .test(staff),
        'h-14 is 3.5rem; anything else leaves a slot or an overlap');
    check('and the markup uses that too', /class="app-bar-second /.test(staff));
}

console.log(failures === 0
    ? '\nAll safe-area checks passed.'
    : `\n${failures} safe-area check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
