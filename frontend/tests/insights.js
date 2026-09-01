/**
 * Insights, and the chart that used to make its own data up.
 *
 * The dashboard drew one line chart whose five points were today's revenue
 * times 0.2, 0.4, 0.5, 0.8 and 1, labelled Week 1 to Current. It looked like a
 * history and was arithmetic on a single number, so any trend read off it was
 * invented.
 *
 * What is checked here is that every chart is drawn from the series the server
 * sent, that switching between them actually changes the chart, and that
 * having no data is said in words - an empty axis reads as a business that did
 * nothing rather than one that has not started.
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
const wait = ms => new Promise(r => setTimeout(r, ms));

const FULL = {
    months: ['Apr 2026', 'May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026', 'Sep 2026'],
    series: {
        invoiced: [100, 200, 0, 400, 500, 600],
        collected: [80, 150, 0, 300, 450, 500],
        invoice_count: [1, 2, 0, 4, 5, 6],
        days_to_pay: [10, 12, null, 8, 9, 7],
    },
    status_breakdown: [{ label: 'Paid', value: 12 }, { label: 'Awaiting Payment', value: 3 }],
    top_customers: [{ label: 'Acme Ltd', value: 900 }, { label: 'Beta Ltd', value: 400 }],
    top_debtors: [{ label: 'Late Ltd', value: 550 }],
    ageing: [
        { label: 'Not yet due', value: 300 }, { label: '1-30 days', value: 100 },
        { label: '31-60 days', value: 0 }, { label: '61-90 days', value: 0 },
        { label: 'Over 90 days', value: 50 },
    ],
    totals: {
        invoiced: 1800, collected: 1480, outstanding: 320,
        average_days_to_pay: 9.2, invoices: 18, currency: 'GBP',
    },
};

const EMPTY = {
    months: FULL.months,
    series: {
        invoiced: [0, 0, 0, 0, 0, 0], collected: [0, 0, 0, 0, 0, 0],
        invoice_count: [0, 0, 0, 0, 0, 0],
        days_to_pay: [null, null, null, null, null, null],
    },
    status_breakdown: [], top_customers: [], top_debtors: [],
    ageing: FULL.ageing.map(a => ({ label: a.label, value: 0 })),
    totals: {
        invoiced: 0, collected: 0, outstanding: 0,
        average_days_to_pay: null, invoices: 0, currency: 'GBP',
    },
};

function boot(payload) {
    const html = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/app.html',
    });
    const w = dom.window;
    const drawn = [];
    w.jspdf = { jsPDF: function () { } };
    // Records what each chart was asked to draw, which is the thing under test.
    w.Chart = function (canvas, config) {
        drawn.push({ type: config.type, config: config });
        this.destroy = () => { };
        this.update = () => { };
    };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:';
    w.URL.revokeObjectURL = () => { };
    w.console.error = () => { };
    w.fetch = (u) => {
        const p = String(u).split('?')[0];
        if (p === '/api/auth/me') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ user: { email: 'a@b' }, client_id: 1 }),
            });
        }
        if (p === '/api/client/me') {
            return Promise.resolve({
                ok: true, status: 200,
                json: () => Promise.resolve({ id: 1, modules: ['invoicing', 'hr'] }),
            });
        }
        if (p === '/api/insights') {
            return Promise.resolve({
                ok: true, status: 200, json: () => Promise.resolve(payload),
            });
        }
        return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve(p.endsWith('s') ? [] : {}),
            text: () => Promise.resolve('{}'),
        });
    };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = cb => setTimeout(cb, 0);
    w.eval(fs.readFileSync(path.join(ROOT, 'dialogs.js'), 'utf8'));
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return { w, drawn };
}

const last = drawn => drawn[drawn.length - 1];

(async () => {
    // --- the fabricated chart is gone -----------------------------------------
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
        const code = src.split('\n')
            .filter(line => !line.trim().startsWith('//'))
            .join('\n');
        check('no chart multiplies one number into a fake history',
            !/revenue\s*\*\s*0\.\d/.test(code));
        check('and no chart labels invented weeks', !/'Week 1'/.test(code));
    }

    // --- the picker ------------------------------------------------------------
    {
        const { w, drawn } = boot(FULL);
        await wait(80);
        await w.loadInsights();
        await wait(60);

        const pick = w.document.getElementById('insight-pick');
        check('more than four ways of looking at it are offered',
            pick.options.length >= 5, pick.options.length);
        check('and something is drawn straight away', drawn.length > 0);
        check('opening on the invoiced-and-collected line',
            last(drawn).type === 'line', last(drawn).type);
        check('drawn over the months the server sent',
            JSON.stringify(last(drawn).config.data.labels) === JSON.stringify(FULL.months));
        check('and from its figures, not from a total',
            JSON.stringify(last(drawn).config.data.datasets[0].data)
            === JSON.stringify(FULL.series.invoiced));
    }

    // --- each view draws its own shape ------------------------------------------
    {
        const { w, drawn } = boot(FULL);
        await wait(80);
        await w.loadInsights();
        const pick = w.document.getElementById('insight-pick');

        const shapes = {};
        ['status', 'ageing', 'customers', 'speed', 'volume'].forEach(id => {
            pick.value = id;
            w.drawInsight();
            shapes[id] = last(drawn);
        });

        check('invoice states are drawn as a doughnut',
            shapes.status.type === 'doughnut', shapes.status.type);
        check('with one slice per state',
            shapes.status.config.data.labels.length === 2);
        check('the ageing of unpaid money is drawn as bars',
            shapes.ageing.type === 'bar', shapes.ageing.type);
        check('keeping every bucket, including the empty ones',
            shapes.ageing.config.data.labels.length === 5);
        check('customers are drawn as a bar chart on its side',
            shapes.customers.type === 'bar' &&
            shapes.customers.config.options.indexAxis === 'y');
        check('ranked on what they actually paid',
            JSON.stringify(shapes.customers.config.data.datasets[0].data) === '[900,400]');
        check('time to pay is drawn as a line', shapes.speed.type === 'line');
        check('and months nobody paid in stay gaps, not joined across',
            shapes.speed.config.data.datasets[0].spanGaps === false);
        check('how many invoices were raised is drawn as bars',
            shapes.volume.type === 'bar');

        const kinds = new Set(Object.values(shapes).map(s => s.type));
        check('that is more than one kind of chart', kinds.size >= 3, [...kinds].join('/'));
    }

    // --- the totals row ----------------------------------------------------------
    {
        const { w } = boot(FULL);
        await wait(80);
        await w.loadInsights();
        const totals = w.document.getElementById('insight-totals').textContent;
        check('the headline figures are shown', /1800\.00/.test(totals), totals.slice(0, 80));
        check('with the currency', /GBP/.test(totals));
        check('and the average time to pay', /9\.2 days/.test(totals), totals.slice(0, 120));
    }

    {
        const { w } = boot(EMPTY);
        await wait(80);
        await w.loadInsights();
        const totals = w.document.getElementById('insight-totals').textContent;
        check('nobody having paid yet is said, not shown as nought days',
            /Not enough data yet/.test(totals), totals.slice(0, 140));
    }

    // --- nothing to draw ----------------------------------------------------------
    {
        const { w, drawn } = boot(EMPTY);
        await wait(80);
        const before = drawn.length;
        await w.loadInsights();
        await wait(20);
        const empty = w.document.getElementById('insight-empty');
        check('an empty business is told so in words',
            empty.style.display === 'block' && /Nothing to show/.test(empty.textContent),
            empty.textContent);
        check('rather than being drawn an axis with no bars',
            drawn.length === before, drawn.length - before);
        check('and the canvas is put away',
            w.document.getElementById('insightChart').style.display === 'none');
    }

    console.log(failures ? `\n${failures} failed` : '\nall good');
    process.exit(failures ? 1 : 0);
})();
