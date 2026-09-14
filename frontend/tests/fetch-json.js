/**
 * Reading a response that was not one.
 *
 * fetch() resolves on a 401 and a 500 exactly as it does on a 200, and the
 * body of those is {"detail": "..."}. Thirteen places did
 * `await (await fetch(x)).json()` and then .forEach or .toLocaleString on
 * the result, so a session that had expired produced a TypeError three
 * lines later - inside a catch, so it failed quietly - with the server's
 * actual reason lost. fetchJson throws the reason instead.
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

function boot(status, body) {
    const dom = new JSDOM('<div></div>', { runScripts: 'outside-only', url: 'https://localhost/app.html' });
    const w = dom.window;
    w.console.error = () => { };
    w.fetch = () => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return w;
}

(async () => {
    {
        const w = boot(200, { rows: [1, 2] });
        const got = await w.fetchJson('/api/x');
        check('a good response is returned as its body', got && got.rows.length === 2);
    }
    {
        const w = boot(401, { detail: 'Not logged in' });
        let err = null;
        try { await w.fetchJson('/api/x'); } catch (e) { err = e; }
        check('a 401 throws rather than returning {"detail"}', !!err);
        check('  with the reason the server gave', err && err.message === 'Not logged in', err && err.message);
    }
    {
        const w = boot(500, {});
        let err = null;
        try { await w.fetchJson('/api/x'); } catch (e) { err = e; }
        check('a bodyless failure still throws, naming the status', err && /500/.test(err.message), err && err.message);
    }
    {
        // The idiom this replaces must be gone from the pages that used it.
        const files = ['app.js', 'superadmin.html'];
        // Comments excluded: the helper's own explanation names the idiom.
        const code = f => fs.readFileSync(path.join(ROOT, f), 'utf8')
            .split(/\r?\n/).filter(l => !/^\s*\/\//.test(l)).join('\n');
        const left = files.filter(f => /await \(await fetch\(/.test(code(f)));
        check('the unguarded idiom is gone from the pages that had it', left.length === 0, left.join(', '));
    }

    console.log(failures === 0 ? '\nAll fetchJson checks passed.' : `\n${failures} fetchJson check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
