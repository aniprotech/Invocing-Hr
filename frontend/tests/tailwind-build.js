/**
 * The Tailwind CSS these pages load has to match the classes they use.
 *
 * Four pages - the employee portal, its login, the meeting room and the
 * password reset - used to pull https://cdn.tailwindcss.com and compile their
 * CSS in the browser on every load. Tailwind's own docs say that script is not
 * for production. It meant a flash of unstyled content on every visit, on the
 * employee phones that are the slowest devices we serve, and no styling at all
 * behind a network that blocks CDNs - which is the network most employees are
 * on. The service worker could not cache it either, being another origin.
 *
 * The generated CSS is committed instead, because the Dockerfile copies
 * frontend/ as-is and has no Node in it to build with. That trade has one
 * failure mode: someone adds a class, does not rebuild, and the style is
 * silently missing in production while looking right in their editor.
 *
 * So this rebuilds and compares. If it fails, run: npm run build:css
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const REPO = path.resolve(ROOT, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

const PAGES = ['employee-dashboard', 'employee-login', 'meeting', 'reset-password', 'login'];

// --- No page may go back to compiling in the browser ----------------------
for (const page of PAGES) {
    const raw = fs.readFileSync(path.join(ROOT, page + '.html'), 'utf8');
    check(`${page}.html does not pull Tailwind from a CDN`,
        !raw.includes('cdn.tailwindcss.com'));
    check(`${page}.html loads the built stylesheet`,
        /<link[^>]+href="tailwind\.css/.test(raw));
    // The inline config is only read by the CDN build. Left behind it is dead
    // code that looks like it still controls the theme - the next person to
    // change a brand colour there would watch it do nothing.
    check(`${page}.html has no stale inline tailwind.config`,
        !/tailwind\.config\s*=/.test(raw));
}

// --- The committed CSS must be what the config produces -------------------
const committed = path.join(ROOT, 'tailwind.css');
check('the built stylesheet is committed', fs.existsSync(committed));

if (fs.existsSync(committed)) {
    const tmp = path.join(os.tmpdir(), `tw-check-${process.pid}.css`);
    // The CLI's JS entry, run with node. The .bin shim is a .cmd on Windows
    // and execFileSync cannot spawn one without a shell.
    const cli = require.resolve('tailwindcss/lib/cli.js');

    let built = null;
    try {
        execFileSync(process.execPath, [cli,
            '-c', 'frontend/tailwind.config.js',
            '-i', 'frontend/tailwind.src.css',
            '-o', tmp, '--minify',
        ], { cwd: REPO, stdio: 'pipe' });
        built = fs.readFileSync(tmp, 'utf8');
        fs.unlinkSync(tmp);
    } catch (e) {
        check('tailwind rebuilds', false,
            'could not run the CLI - is tailwindcss installed? ' + (e.message || e));
    }

    if (built !== null) {
        check('the committed CSS is up to date with the classes in use',
            built.trim() === fs.readFileSync(committed, 'utf8').trim(),
            'the pages use classes the committed CSS does not have (or vice ' +
            'versa). Run: npm run build:css');
    }
}

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
