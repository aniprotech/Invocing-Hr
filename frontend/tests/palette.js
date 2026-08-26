/**
 * One palette, and it is the logo's.
 *
 * The app had grown four unrelated colour families in it: the mark's sky blue,
 * an indigo the employee portal and the default invoice were branded in, a
 * cyan-to-blue on the hiring pages, and a set of neon accents (#39ff14,
 * #ff003c) left over from an earlier look. That is why the product did not
 * read as one product however many individual screens got tidied - the fix was
 * never on any single screen.
 *
 * So this checks the palette as a whole rather than any one colour: every hex
 * in the frontend has to be a member of the family, and anything new has to be
 * added here deliberately. A stray indigo is not a small thing; it is the
 * start of the fifth family.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log('ok    ' + label);
    else { failures++; console.log('FAIL  ' + label + (detail ? ': ' + detail : '')); }
};

// --- the family ------------------------------------------------------------
// Sky, from the mark's own gradient. Anything that is active, selected,
// linked or ours is one of these.
const SKY = ['#f0f9ff', '#e0f2fe', '#bae6fd', '#7dd3fc', '#38bdf8',
             '#0ea5e9', '#0284c7', '#0369a1', '#075985', '#0c4a6e', '#082f49'];

// Slate, for everything structural. Backgrounds, panels, borders, type.
const SLATE = ['#ffffff', '#fff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#cbd5e1',
               '#94a3b8', '#64748b', '#475569', '#334155', '#1e293b', '#0f172a',
               '#161f2d', '#1b2436', '#141b2d', '#131a2b', '#0b0f19', '#020617',
               '#1a1a1a', '#000000', '#000'];

// The three status colours, each from the same ramp as the sky so they sit
// beside it rather than shouting over it.
const STATUS = ['#34d399', '#10b981', '#6ee7b7', '#a7f3d0', '#d1fae5', '#ecfdf5',  // emerald
                '#fb7185', '#f43f5e', '#e11d48', '#fda4af', '#ffe4e6',  // rose
                '#fbbf24', '#fb923c', '#b45309', '#fef3c7', '#fde68a',
                '#fff7ed'];                                             // amber

// Series colours a chart needs to tell apart, and two greens that only appear
// on the printed invoice, which is ink on white paper and not app chrome.
const EXTRA = ['#a3e635', '#0f6b4f', '#a63321', '#14161d', '#5b6070',
               '#e4e6ec', '#f4f5f8', '#4a2c2a'];

// Other companies' marks. Restyling these would be misrepresenting them.
const FOREIGN = ['#4285f4', '#ea4335', '#fbbc05', '#34a853',  // Google
                 '#25d366',                                     // WhatsApp
                 '#1a73e8', '#5f6368', '#202124', '#1557b0',    // Google UI
                 '#f1f3f4', '#e6e6e6', '#e5e7eb', '#e8eaed', '#9ca3af',
                 '#fbfdff', '#f6f7fa', '#2d3748', '#1a202c', '#0d1117'];

const ALLOWED = new Set([...SKY, ...SLATE, ...STATUS, ...EXTRA, ...FOREIGN]
    .map(c => c.toLowerCase()));

// The families that were removed. Named individually so the failure says what
// came back rather than only that something did.
const BANISHED = {
    '#39ff14': 'the neon green',
    '#ff003c': 'the neon red',
    '#ff3b5c': 'the neon red',
    '#6366f1': 'the indigo brand',
    '#4f46e5': 'the indigo brand',
    '#4338ca': 'the indigo brand',
    '#818cf8': 'the indigo brand',
    '#8b5cf6': 'the violet accent',
    '#7877c6': 'the violet accent',
    '#3b82f6': 'the generic blue',
    '#2563eb': 'the generic blue',
    '#22d3ee': 'the cyan',
    '#0e7490': 'the cyan',
    '#ef4444': 'the old red',
    '#f59e0b': 'the old amber',
    '#fcd34d': 'the old amber',
};

// tailwind.css is generated from tailwind.config.js - checking it would report
// the same mistake twice and point at a file nobody edits.
const files = fs.readdirSync(ROOT)
    .filter(f => /\.(html|js|css)$/.test(f) && f !== 'tailwind.css')
    .map(f => path.join(ROOT, f));

// A numeric HTML entity looks exactly like a hex colour to a careless regex -
// &#128100; contains "#128100" - so the lookbehind is doing real work.
const HEX = /(?<![&\w])#([0-9a-fA-F]{6})\b/g;

const strays = new Map();
const returned = new Map();

for (const file of files) {
    const src = fs.readFileSync(file, 'utf8');
    for (const m of src.matchAll(HEX)) {
        const c = ('#' + m[1]).toLowerCase();
        const where = path.basename(file);
        if (BANISHED[c]) {
            if (!returned.has(c)) returned.set(c, new Set());
            returned.get(c).add(where);
        } else if (!ALLOWED.has(c)) {
            if (!strays.has(c)) strays.set(c, new Set());
            strays.get(c).add(where);
        }
    }
}

// The same sweep over rgb()/rgba(), which is where two blues survived the
// first pass: a colour written as a triple is the same colour, and checking
// only hex left exactly half the door open.
const RGB = /\brgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*[,)]/g;
const hex3 = (r, g, b) => '#' + [r, g, b].map(v =>
    Number(v).toString(16).padStart(2, '0')).join('');

for (const file of files) {
    const src = fs.readFileSync(file, 'utf8');
    for (const m of src.matchAll(RGB)) {
        const c = hex3(m[1], m[2], m[3]);
        // Neutrals written as a triple - white and black at every opacity -
        // are how translucent overlays are built and are not a colour choice.
        if (m[1] === m[2] && m[2] === m[3]) continue;
        const where = path.basename(file);
        if (BANISHED[c]) {
            if (!returned.has(c)) returned.set(c, new Set());
            returned.get(c).add(where + ' (as rgb)');
        } else if (!ALLOWED.has(c)) {
            if (!strays.has(c)) strays.set(c, new Set());
            strays.get(c).add(where + ' (as rgb)');
        }
    }
}

check('no banished colour has come back',
    returned.size === 0,
    [...returned].map(([c, w]) => `${c} (${BANISHED[c]}) in ${[...w].join(', ')}`).join('; '));

check('every colour in the frontend is in the palette',
    strays.size === 0,
    [...strays].map(([c, w]) => `${c} in ${[...w].join(', ')}`).join('; '));

// --- the tokens the whole app resolves through -----------------------------
const css = fs.readFileSync(path.join(ROOT, 'styles.css'), 'utf8');
const root = css.slice(css.indexOf(':root'), css.indexOf('}', css.indexOf(':root')));
const token = name => (root.match(new RegExp('--' + name + ':\\s*([^;]+);')) || [])[1];

[
    ['primary-color', '#38bdf8'],
    ['primary-light', '#7dd3fc'],
    ['success-color', '#34d399'],
    ['danger-color', '#f43f5e'],
    ['warning-color', '#fbbf24'],
].forEach(([name, want]) => {
    check(`--${name} is ${want}`,
        (token(name) || '').trim().toLowerCase() === want, token(name));
});

// --- and they have to be readable on the page ------------------------------
const lum = hex => {
    const c = [1, 3, 5].map(i => parseInt(hex.substr(i, 2), 16) / 255)
        .map(x => x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
};

const BG = (token('background-color') || '#0b0f19').trim();
[
    ['primary-color', 4.5],
    ['primary-light', 4.5],
    ['success-color', 4.5],
    ['danger-color', 4.5],
    ['warning-color', 4.5],
    ['text-secondary', 4.5],
].forEach(([name, need]) => {
    const c = (token(name) || '').trim();
    const r = ratio(c, BG);
    check(`--${name} is readable on the page`, r >= need,
        `${c} on ${BG} is ${r.toFixed(2)}:1, needs ${need}:1`);
});

// --- the Tailwind brand scale is the same sky ------------------------------
const cfg = fs.readFileSync(path.join(ROOT, 'tailwind.config.js'), 'utf8');
const brand = cfg.slice(cfg.indexOf('brand: {'), cfg.indexOf('}', cfg.indexOf('brand: {')));
check('the Tailwind brand scale is the mark\'s own, not an indigo',
    /#38bdf8/.test(brand) && !/#6366f1/i.test(brand),
    (brand.match(/#[0-9a-f]{6}/gi) || []).slice(0, 3).join(' '));

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
