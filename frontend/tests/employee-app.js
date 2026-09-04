/**
 * The staff portal as an app of its own.
 *
 * The portal linked the business manifest, whose start_url is "/". So an
 * employee who installed from their own portal got an icon called
 * "aniprotech" that opened the marketing page - the one page they have no
 * reason to be on. And the sign-in page, which is where somebody installs
 * from before they have an account set up, carried no manifest at all, so on
 * Android there was nothing to install.
 *
 * Two things have to hold. The manifest has to describe a different app, or
 * the browser installs the one that already exists. And the apple tags have
 * to name it too, because Safari ignores the manifest entirely on Add to
 * Home Screen - the meta tags are the only thing that decides what the icon
 * on an iPhone is called.
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
const json = f => JSON.parse(read(f));
const exists = f => fs.existsSync(path.join(ROOT, f));

const PORTAL_PAGES = ['employee-login.html', 'employee-dashboard.html'];

const business = json('manifest.webmanifest');
const staff = json('employee.webmanifest');

// --- a different app, not the same one under another name ----------------------
{
    check('the staff portal has a manifest of its own',
        exists('employee.webmanifest'));

    // id is what the browser keys an installed app on. Same id, same app.
    check('with an identity of its own', staff.id && staff.id !== business.id,
        `${staff.id} vs ${business.id}`);
    check('and a name somebody can tell apart on a home screen',
        staff.name && staff.name !== business.name, staff.name);
    check('including the short one, which is what the icon is labelled with',
        staff.short_name && staff.short_name !== business.short_name,
        staff.short_name);

    check('it opens the portal, not the front page',
        /employee/.test(staff.start_url || ''), staff.start_url);
    check('rather than wherever the business app opens',
        staff.start_url !== business.start_url, staff.start_url);

    check('and it opens as an app rather than in a browser tab',
        staff.display === 'standalone', staff.display);
}

// --- and it looks different ------------------------------------------------------
{
    const icons = (staff.icons || []).map(i => i.src);
    check('it names icons', icons.length > 0);
    check('every icon it names exists',
        icons.every(src => exists(src.replace(/^\//, ''))),
        icons.filter(src => !exists(src.replace(/^\//, ''))).join(', '));

    // Same again for the business one, since a broken icon there is invisible
    // until somebody installs.
    const theirs = (business.icons || []).map(i => i.src);
    check('and so does every icon the business app names',
        theirs.every(src => exists(src.replace(/^\//, ''))),
        theirs.filter(src => !exists(src.replace(/^\//, ''))).join(', '));

    // Two apps with one icon is one app as far as anybody looking at their
    // phone is concerned.
    const differs = (a, b) => !fs.readFileSync(path.join(ROOT, a))
        .equals(fs.readFileSync(path.join(ROOT, b)));
    check('the staff icon is not the business icon over again',
        differs('icons/icon-staff-192.png', 'icons/icon-192.png'));
    check('nor is the one iOS uses',
        differs('icons/apple-touch-icon-staff.png', 'icons/apple-touch-icon.png'));
}

// --- the pages point at it ---------------------------------------------------------
PORTAL_PAGES.forEach(page => {
    const src = read(page);
    check(`${page} offers the staff app`,
        /rel="manifest"\s+href="\/employee\.webmanifest"/.test(src));
    check(`${page} does not also offer the business one`,
        !/href="\/manifest\.webmanifest"/.test(src));

    // Safari never reads the manifest for Add to Home Screen. On an iPhone
    // this tag is the whole of what the icon gets called.
    const title = (src.match(/apple-mobile-web-app-title" content="([^"]*)"/) || [])[1];
    check(`${page} names the staff app for iOS too`,
        title === staff.short_name || /staff/i.test(title || ''), title);

    check(`${page} carries the staff touch icon`,
        /apple-touch-icon" href="\/icons\/apple-touch-icon-staff\.png/.test(src));
    check(`${page} still tells Safari it can run standalone`,
        /apple-mobile-web-app-capable" content="yes"/.test(src));
});

// --- and nothing else does ----------------------------------------------------------
{
    const wrong = fs.readdirSync(ROOT)
        .filter(f => f.endsWith('.html') && !PORTAL_PAGES.includes(f))
        .filter(f => /employee\.webmanifest/.test(read(f)));
    check('no other page installs itself as the staff app', wrong.length === 0,
        wrong.join(', '));

    check('the business app still has its own manifest',
        /href="\/manifest\.webmanifest"/.test(read('app.html')));
}

// --- offline, like the other one ------------------------------------------------------
{
    const sw = read('sw.js');
    ['icon-staff-192.png', 'icon-staff-512.png', 'apple-touch-icon-staff.png']
        .forEach(icon => {
            check(`the worker precaches ${icon}`, sw.includes(icon));
        });
}

// --- somebody has to be told it exists -------------------------------------------------
{
    const landing = read('index.html');
    check('the install section says staff install a different app',
        /staff install a different app/i.test(landing));
    check('and links them to the portal to do it',
        /href="\/employee-login\.html"/.test(landing));
}

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
