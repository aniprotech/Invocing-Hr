/**
 * The dashboard's money chart.
 *
 * It was a smoothed line with the raw integers up the side, which drew a
 * hump between two months nothing happened in and labelled the axis
 * 45,000,000,000,000. Now: bars, one grey and one blue per month, a
 * compact-money axis on five ticks, a headline for the period with the
 * change on the period before, and a range the reader picks.
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

const MONTHS = ['Oct 2025', 'Nov 2025', 'Dec 2025', 'Jan 2026', 'Feb 2026', 'Mar 2026', 'Apr 2026', 'May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026', 'Sep 2026'];
function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [], charts = [];
    w.console.error = () => { };
    w.Chart = function (el, config) { charts.push({ id: el.id, config }); this.destroy = () => { }; };
    w.Chart.defaults = {};
    w.fetch = (url) => {
        const p = String(url).split('?')[0];
        const q = String(url).split('?')[1] || '';
        sent.push({ url: p, q });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/insights') {
            const n = Number((q.match(/months=(\d+)/) || [])[1] || 6);
            const months = MONTHS.slice(-n);
            const invoiced = months.map((_, i) => opts.empty ? 0 : 1000 * (i + 1));
            const collected = months.map((_, i) => opts.empty ? 0 : 800 * (i + 1));
            return give({ months, series: { invoiced, collected }, totals: { currency: 'GBP' } });
        }
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return { w, doc: w.document, sent, charts };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the card has a headline, a legend and a 3/6/12 range', /id="cf-headline"/.test(src) && /id="cf-legend"/.test(src) && /setCashflowRange\(12, this\)/.test(src));
    }
    {
        const { w, doc, sent, charts } = boot();
        await w.renderInvoiceChart();
        await wait(40);
        check('six months asks for twelve, to have the period before', sent.some(s => s.url === '/api/insights' && /months=12/.test(s.q)));
        const cfg = charts[0].config;
        check('it is bars, not a line', cfg.type === 'bar');
        check('  two series: invoiced in grey as context, collected in the accent', cfg.data.datasets.length === 2 && cfg.data.datasets[0].label === 'Invoiced' && cfg.data.datasets[1].label === 'Collected' && cfg.data.datasets[0].backgroundColor !== cfg.data.datasets[1].backgroundColor);
        check('  only the last six months are drawn', cfg.data.labels.length === 6 && cfg.data.labels[5] === "Sep ’26");
        check('  one y axis with compact money on at most five ticks', Object.keys(cfg.options.scales).filter(k => k.startsWith('y')).length === 1 && cfg.options.scales.y.ticks.maxTicksLimit === 5 && cfg.options.scales.y.ticks.callback(1200000) === '£1.2m');
        check('  the hover shows every series for the month and the collection rate', cfg.options.interaction.mode === 'index' && /collected/.test(cfg.options.plugins.tooltip.callbacks.footer([{ dataIndex: 0 }])));
        // twelve months of 800..9600 collected: the last six sum to 45,600, the six before to 16,800.
        check('the headline is the period total in compact money', doc.getElementById('cf-headline').textContent === '£45.6k', doc.getElementById('cf-headline').textContent);
        check('  the line under it says how much of the invoicing that is, and the change on the period before', /of £57k invoiced \(80% collected\)/.test(doc.getElementById('cf-sub').textContent) && /▲ 171% on the 6 months before/.test(doc.getElementById('cf-sub').textContent), doc.getElementById('cf-sub').textContent);
        check('  the legend names both series', /Invoiced/.test(doc.getElementById('cf-legend').textContent) && /Collected/.test(doc.getElementById('cf-legend').textContent));
        w.setCashflowRange(12, null);
        await wait(40);
        check('twelve months asks for twenty-four and draws twelve', sent.some(s => /months=24/.test(s.q)) && charts[1].config.data.labels.length === 12);
    }
    {
        const { w, doc, charts } = boot({ empty: true });
        await w.renderInvoiceChart();
        await wait(40);
        check('with nothing invoiced the chart says so instead of drawing empty bars', charts.length === 0 && /No invoices in the last 6 months/.test(doc.querySelector('#cashflow-card .chart-empty').textContent));
    }
    console.log(failures === 0 ? '\nAll cash-in chart checks passed.' : `\n${failures} cash-in chart check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
