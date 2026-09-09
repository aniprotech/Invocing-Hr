/**
 * A button that says one thing and does another.
 *
 * The invoice, quote and payslip screens each carried a button labelled
 * "Print PDF". All three called a function that ends in doc.save(), which
 * downloads the file - none of them printed anything.
 *
 * So the one thing somebody went looking for was already there and looked
 * absent, and the thing the label promised was somewhere else entirely: in the
 * browser's own PDF viewer, reached through Preview. It was reported as a
 * missing feature, which is exactly how a mislabelled control presents.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
const APP = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

// The body of a top-level function, so a name is matched to what it does.
function bodyOf(name) {
    const at = APP.indexOf(`function ${name}(`);
    if (at < 0) return '';
    const end = APP.indexOf('\n}', at);
    return APP.slice(at, end + 2);
}

// Every button, with the handler it calls and the words on it.
const buttons = [...HTML.matchAll(/<button[^>]*onclick="([A-Za-z_$][\w$]*)\(\)"[^>]*>([^<]+)</g)]
    .map(m => ({ fn: m[1], label: m[2].trim() }));

check('the screens have buttons wired to named handlers', buttons.length > 5, buttons.length);

// --- saving a file is downloading, whatever the button says -------------------
{
    const saves = buttons.filter(b => /doc\.save\(/.test(bodyOf(b.fn)));
    check('some buttons save a PDF to disk', saves.length >= 3,
        saves.map(b => b.fn).join(', '));

    const lying = saves.filter(b => !/download/i.test(b.label));
    check('and every one of them says so',
        lying.length === 0,
        lying.map(b => `${b.fn} is labelled "${b.label}"`).join('; '));
}

// --- and nothing claims to print when it does not -----------------------------
{
    const claimsPrint = buttons.filter(b => /\bprint\b/i.test(b.label));
    const cannot = claimsPrint.filter(b => {
        const body = bodyOf(b.fn);
        return body && !/autoPrint|\.print\(/.test(body);
    });
    check('nothing offers to print without printing',
        cannot.length === 0,
        cannot.map(b => `${b.fn} is labelled "${b.label}"`).join('; '));
}

console.log(failures === 0
    ? '\nAll button-label checks passed.'
    : `\n${failures} button-label check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
