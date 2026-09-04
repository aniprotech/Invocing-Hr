/**
 * What Android needs, which is not what iOS needs.
 *
 * Safari installs from the page: it ignores the manifest and reads the apple
 * meta tags. Chrome does the opposite - it reads the manifest and, for a real
 * install rather than a bookmark, wants a service worker with a fetch handler
 * controlling the page. Only one page in the whole site ever registered one,
 * so the same app installed properly from the employee dashboard and as a
 * shortcut from everywhere else, which is not a difference anybody would
 * think to test for.
 *
 * The other half is the icon. Android masks a home-screen icon to whatever
 * shape the launcher uses. An icon that does not declare itself maskable is
 * assumed not to be, so the launcher shrinks the whole thing into a white
 * circle - which is the worst possible treatment for a full-bleed rounded
 * square, and it looks like a mistake because it is one.
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
const offersAnApp = f => /rel="manifest"/.test(read(f));

// PNG colour type lives at byte 25 of the header. 2 is RGB, 6 is RGBA - so
// this says whether a file can have transparency at all, without decoding it.
const colourType = f => fs.readFileSync(path.join(ROOT, f))[25];

// --- a worker behind every app -------------------------------------------------
{
    const offering = pages.filter(offersAnApp);
    check('some pages offer to be installed', offering.length > 0, offering.length);

    const bare = offering.filter(f => !/src="\/pwa\.js/.test(read(f)));
    check('every page that offers an app registers the worker behind it',
        bare.length === 0, bare.join(', '));

    const worker = read('pwa.js');
    check('and the shared script registers the worker',
        /serviceWorker/.test(worker) && /register\('\/sw\.js'\)/.test(worker));
    check('after load, so it does not compete with first paint',
        /addEventListener\('load'/.test(worker));
    check('and a failure is swallowed, since the page works without it',
        /catch\(/.test(worker));

    // Chrome will not treat a page as installable without one of these.
    check('the worker answers fetches, which is what Chrome asks for',
        /addEventListener\('fetch'/.test(read('sw.js')));

    // One place, or the two drift and only one gets fixed.
    const duplicates = pages.filter(f =>
        /navigator\.serviceWorker\.register/.test(read(f)));
    check('no page registers it a second time of its own', duplicates.length === 0,
        duplicates.join(', '));
}

// --- an icon Android can mask -----------------------------------------------------
['manifest.webmanifest', 'employee.webmanifest'].forEach(file => {
    const m = JSON.parse(read(file));
    const maskable = (m.icons || []).filter(i => /maskable/.test(i.purpose || ''));
    check(`${file} offers a maskable icon`, maskable.length > 0);
    check(`${file} offers one at each size Android asks for`,
        ['192x192', '512x512'].every(s => maskable.some(i => i.sizes === s)),
        maskable.map(i => i.sizes).join(', '));

    // Still needs the plain ones: maskable art is cropped, so it is the wrong
    // thing to show anywhere the full square is visible.
    check(`${file} still offers the unmasked icon too`,
        (m.icons || []).some(i => (i.purpose || 'any') === 'any'));

    maskable.forEach(icon => {
        const f = icon.src.replace(/^\//, '');
        check(`${icon.src} exists`, fs.existsSync(path.join(ROOT, f)));
        // A maskable icon is cropped to the launcher's shape, so a transparent
        // corner becomes a bite taken out of the icon.
        check(`${icon.src} reaches every edge`, colourType(f) === 2,
            'PNG colour type ' + colourType(f));
    });
});

// --- and the two apps are still two apps ------------------------------------------
{
    const differs = (a, b) => !fs.readFileSync(path.join(ROOT, a))
        .equals(fs.readFileSync(path.join(ROOT, b)));
    check('the masked staff icon is not the masked business one',
        differs('icons/icon-192-maskable.png', 'icons/icon-staff-192-maskable.png'));
}

// --- the bar at the top of the app -------------------------------------------------
{
    // Chrome paints the status bar with theme-color when an app is open. The
    // staff app saying one colour and its pages another shows as a seam.
    const staff = JSON.parse(read('employee.webmanifest'));
    ['employee-login.html', 'employee-dashboard.html'].forEach(page => {
        const colour = (read(page).match(/name="theme-color" content="([^"]*)"/) || [])[1];
        check(`${page} is painted the colour its own manifest names`,
            colour === staff.theme_color, `${colour} vs ${staff.theme_color}`);
    });

    const business = JSON.parse(read('manifest.webmanifest'));
    const appColour = (read('app.html').match(/name="theme-color" content="([^"]*)"/) || [])[1];
    check('and the business app the colour of its own',
        appColour === business.theme_color, `${appColour} vs ${business.theme_color}`);
}

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
