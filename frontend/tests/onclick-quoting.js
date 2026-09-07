/**
 * Buttons that broke on ordinary names.
 *
 * Nine action buttons are built by concatenating a value into a JavaScript
 * string literal that sits inside an onclick attribute. esc() was used on the
 * value, which looks right and is not: a browser decodes the entities in an
 * attribute value BEFORE the JavaScript inside it is parsed, so esc()'s &#39;
 * turns back into an apostrophe and ends the string early.
 *
 * The escaping meant to protect them was what broke them.
 *
 *   - An employee called O'Brien could not have their leave approved or
 *     rejected. Both buttons raised a SyntaxError, so they did nothing at all
 *     - no error, no toast, nothing. A manager clicks Approve and the row just
 *     sits there, forever, for that one person.
 *   - An asset tagged 24" Monitor could not be issued or taken back.
 *   - A customer called O'Brien broke Regenerate on the AI email panel.
 *
 * jsq() escapes for the JavaScript string position and esc() then escapes for
 * the attribute, in that order: jsq puts the backslash in, esc makes the
 * attribute well formed, the browser decodes the entity back to a quote, and
 * the parser finally sees the backslash that was always meant to be there.
 *
 * The mechanism is tested here through a real DOM and a real click rather than
 * by matching strings, because the whole bug lived in the step where the
 * browser decodes the attribute - which string matching cannot see.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

// The "esc() alone is broken" check deliberately triggers a SyntaxError inside
// an onclick. jsdom reports that as an uncaught page error, which is the point
// of the check and not something to print a stack trace for.
const quiet = () => new VirtualConsole();

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

const APP = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');

// Pull the two helpers out of app.js and run the real ones.
function helpers() {
    const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only' });
    const w = dom.window;
    const grab = name => {
        const at = APP.indexOf(`function ${name}(`);
        if (at < 0) throw new Error(`${name}() is not defined in app.js`);
        // to the closing brace of the function, which is the first line that is
        // exactly "}" after the declaration
        const end = APP.indexOf('\n}', at);
        return APP.slice(at, end + 2);
    };
    w.eval(grab('esc'));
    w.eval(grab('jsq'));
    return w;
}

const NASTY = [
    ["O'Brien", 'an apostrophe, which is what was reported'],
    ['24" Monitor', 'a double quote, common in an asset tag'],
    ["D'Angelo O\"Hara", 'both at once'],
    ['back\\slash', 'a backslash, which must not double up'],
    ['line\nbreak', 'a newline, which ends a string literal too'],
    ["'); alert(1); //", 'a deliberate break-out attempt'],
    ['plain name', 'nothing special, must survive untouched'],
    ['', 'empty'],
];

(async () => {
    const w = helpers();

    // --- the mechanism, through a real attribute and a real click -------------
    {
        for (const [value, why] of NASTY) {
            const dom = new JSDOM('<!doctype html><body><div id="host"></div></body>',
                { runScripts: 'dangerously', virtualConsole: quiet() });
            const win = dom.window;
            const got = [];
            win.received = v => got.push(v);

            // Exactly how the list renderers build these.
            win.document.getElementById('host').innerHTML =
                '<button onclick="received(\'' + w.esc(w.jsq(value)) + '\')">go</button>';
            const btn = win.document.querySelector('button');

            let threw = '';
            try { btn.click(); } catch (e) { threw = e.message; }

            check(`survives ${why}`,
                threw === '' && got.length === 1 && got[0] === value,
                threw ? `threw ${threw}` : `got ${JSON.stringify(got)}`);
        }
    }

    // --- and the old way genuinely failed, so this is not a no-op -------------
    {
        const dom = new JSDOM('<!doctype html><body><div id="host"></div></body>',
            { runScripts: 'dangerously', virtualConsole: quiet() });
        const win = dom.window;
        const got = [];
        win.received = v => got.push(v);
        win.document.getElementById('host').innerHTML =
            '<button onclick="received(\'' + w.esc("O'Brien") + '\')">go</button>';
        let threw = '';
        try { win.document.querySelector('button').click(); } catch (e) { threw = e.message; }
        check('esc() alone really does break on an apostrophe',
            got.length === 0,
            'if this passes with a value, the bug never existed and jsq is pointless');
    }

    // --- no site may go back to esc() on its own ---------------------------------
    {
        // An onclick whose JS argument is a quoted string built from a value.
        const risky = /onclick="([A-Za-z_$][\w$]*)\((?:(?!onclick=)[\s\S]){0,400}?esc\((?:(?!onclick=)[\s\S]){0,400}?\)">/g;
        const bare = [];
        let m;
        while ((m = risky.exec(APP)) !== null) {
            if (!/esc\(jsq\(/.test(m[0])) {
                bare.push(`${m[1]} at line ${APP.slice(0, m.index).split('\n').length}`);
            }
        }
        check('every onclick string argument goes through jsq()',
            bare.length === 0, bare.join(', '));
    }

    {
        const count = (APP.match(/esc\(jsq\(/g) || []).length;
        check('and all nine sites were converted', count >= 9, `found ${count}`);
    }

    // --- jsq is only ever used inside esc() -------------------------------------
    {
        // jsq() alone in an attribute would leave a raw quote and break the HTML.
        // Comments are stripped first: the note above jsq() names it several
        // times, and prose is not a call site.
        const code = APP.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
        const alone = (code.match(/(?<!esc\()jsq\(/g) || []).length;
        const inside = (code.match(/esc\(jsq\(/g) || []).length;
        const declaration = 1;   // function jsq(s)
        check('jsq is never used without esc around it',
            alone <= declaration, `${alone - declaration} bare use(s) besides the declaration`);
        check('and the pair is used the right way round',
            inside > 0 && !/jsq\(esc\(/.test(APP),
            'jsq(esc(x)) would escape the entity’s own backslash');
    }

    console.log(failures === 0
        ? '\nAll onclick quoting checks passed.'
        : `\n${failures} onclick quoting check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
