/**
 * Shared setup for the Purchases screens' tests: the app in jsdom with a fake
 * server. `route(path, init, full)` returns a body (200), or
 * { status, body } for anything else, or undefined to fall through to an empty
 * answer. Questions are answered by the test and what the page said is recorded.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

function makeChecker() {
    const state = { failures: 0 };
    state.check = (label, ok, detail) => {
        if (ok) console.log(`ok    ${label}`);
        else { state.failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
    };
    state.finish = (name) => {
        if (state.failures) { console.log(`\n${state.failures} ${name} check(s) failed.`); process.exit(1); }
        console.log(`\nAll ${name} checks passed.`);
    };
    return state;
}

const wait = ms => new Promise(r => setTimeout(r, ms));

function appDocument() {
    return new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '')).window.document;
}

function boot(route, opts) {
    opts = opts || {};
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    const sent = [];
    const reply = (status, body) => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
    w.fetch = (url, init) => {
        const full = String(url);
        const p = full.split('?')[0];
        const entry = { url: p, full, method: (init && init.method) || 'GET', body: init && init.body };
        sent.push(entry);
        if (p === '/api/auth/me') return reply(200, { user: { email: 'me@x' }, client_id: 1 });
        if (p === '/api/client/me') return reply(200, { id: 1, modules: ['invoicing', 'hr'] });
        const got = route(p, init || {}, full, entry);
        if (got === undefined) return reply(200, p.endsWith('s') ? [] : {});
        if (got && typeof got === 'object' && got.__status) return reply(got.__status, got.body);
        return reply(200, got);
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    const confirms = [];
    w.uiConfirm = (m) => { confirms.push(m); return Promise.resolve(opts.confirm !== false); };
    const toasts = [];
    w.showToast = (m, k) => toasts.push({ m, k });
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, sent, confirms, toasts };
}

const fail = (status, detail) => ({ __status: status, body: { detail } });

module.exports = { boot, wait, makeChecker, appDocument, fail, ROOT };
