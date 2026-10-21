/**
 * Purchase reports.
 *
 * The figures are the server's. What the page decides: which tab asks which
 * report, that the dates are sent as typed, that the CSV link follows the tab
 * and the dates, that a late bill is coloured and a bill not yet due is not,
 * that names never become markup, and that an empty answer and a failure are
 * each said.
 */
const { boot, wait, makeChecker, appDocument, fail } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const AGEING = { as_of: '2026-11-10', total_outstanding: 180, buckets: { current: 30, '1_30': 50, '31_60': 0, '61_90': 100, over_90: 0 },
    suppliers: [
        { name: 'Paper Co', bills: 2, current: 0, '1_30': 50, '31_60': 0, '61_90': 100, over_90: 0, total: 150, oldest_days: 70 },
        { name: '<b>Evil</b> Ltd', bills: 1, current: 30, '1_30': 0, '31_60': 0, '61_90': 0, over_90: 0, total: 30, oldest_days: 0 },
    ],
    bills: [
        { id: 1, number: 'B-1', supplier: 'Paper Co', due_date: '2026-09-01', days_overdue: 70, bucket: '61_90', outstanding: 100 },
        { id: 3, number: 'B-3', supplier: '<b>Evil</b> Ltd', due_date: '2026-12-01', days_overdue: 0, bucket: 'current', outstanding: 30 },
    ] };
const row = (name, b, e, c) => ({ name, bills: b, expenses: e, credits: c, net: b + e - c, count: 1 });
const SPEND = { start: '2026-01-01', end: '2026-11-10', summary: { bills: 550, expenses: 50, credits: 25, net: 575 },
    by_supplier: [row('Landlord', 400, 0, 0), row('<i>Evil</i> Co', 150, 20, 25)],
    by_category: [{ name: 'rent', bills: 400, expenses: 0, net: 400 }, { name: 'software', bills: 150, expenses: 20, net: 170 }],
    by_month: [row('2026-10', 300, 20, 0), row('2026-11', 250, 30, 25)] };

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        if (p === '/api/purchases/reports/ageing') return opts.fails ? fail(500, 'Server is down') : (opts.empty ? { as_of: 'x', total_outstanding: 0, buckets: {}, suppliers: [], bills: [] } : AGEING);
        if (p === '/api/purchases/reports/spend') return opts.fails ? fail(500, 'Server is down') : (opts.empty ? { start: 'a', end: 'b', summary: { bills: 0, expenses: 0, credits: 0, net: 0 }, by_supplier: [], by_category: [], by_month: [] } : SPEND);
        return undefined;
    };
}

(async () => {
    {
        const doc = appDocument();
        check('Purchase reports is in the Purchases menu, named differently from Sales reports and Money > Reports',
            !!doc.querySelector('[data-nav-group="Purchases"] #nav-purchase-reports')
            && new Set(['nav-purchase-reports', 'nav-sales-reports', 'nav-reports'].map(id => doc.getElementById(id).textContent.trim())).size === 3);
        check('the screen has four tabs, two date controls, a CSV link and a content area',
            ['pr-tabs', 'pr-asof', 'pr-from', 'pr-to', 'pr-csv', 'pr-content'].every(id => !!doc.getElementById(id)) && doc.querySelectorAll('#pr-tabs .tab').length === 4);
    }
    {
        const { w, sent } = boot(server());
        await wait(60);
        check('the address and highlight are known', w.ROUTE_SLUGS['purchase-reports-view'] === 'purchase-reports' && w.NAV_FOR_VIEW['purchase-reports-view'] === 'nav-purchase-reports');
        w.showView('purchase-reports-view');
        await wait(300);
        const doc = w.document, host = doc.getElementById('pr-content');
        check('it opens on aged payables and asks that report', sent.some(s => s.url === '/api/purchases/reports/ageing'));
        check('the buckets and the total owed are shown', /Not yet due/.test(host.textContent) && /61-90 days/.test(host.textContent) && /1\.00|100\.00/.test(host.textContent) && /Total owed/.test(host.textContent) && /180\.00/.test(host.textContent));
        check('a supplier and a bill are listed, with how late', /Paper Co/.test(host.textContent) && /B-1/.test(host.textContent) && /70 days/.test(host.textContent) && /Not yet due/.test(host.textContent));
        check('names can never become markup', host.querySelector('b') === null && /<b>Evil<\/b> Ltd/.test(host.textContent));
        check('how late is coloured; not yet due is not',
            [...host.querySelectorAll('span')].some(s => /70 days/.test(s.textContent) && /danger/.test(s.getAttribute('style') || ''))
            && ![...host.querySelectorAll('td')].some(td => /^Not yet due$/.test(td.textContent) && /danger/.test(td.innerHTML)));
        check('the CSV link is the ageing one', /\/api\/purchases\/reports\/ageing\.csv/.test(doc.getElementById('pr-csv').getAttribute('href')));
        doc.getElementById('pr-asof').value = '2026-10-01';
        w.loadPurchaseReport();
        await wait(300);
        const last = sent.filter(s => s.url === '/api/purchases/reports/ageing').pop();
        check('the as-of date is sent, and carried into the CSV link', /as_of=2026-10-01/.test(last.full) && /as_of=2026-10-01/.test(doc.getElementById('pr-csv').getAttribute('href')), last.full);

        // spend tabs
        w.showPurchaseReport('supplier');
        await wait(300);
        check('the tab is lit, the range controls show and the as-of control hides',
            doc.querySelector('[data-pr-tab="supplier"]').classList.contains('active') && !doc.querySelector('[data-pr-tab="ageing"]').classList.contains('active')
            && doc.getElementById('pr-range-box').style.display === 'flex' && doc.getElementById('pr-asof-box').style.display === 'none');
        check('spend by supplier shows the four totals, the range and the note about drafts',
            /575\.00/.test(host.textContent) && /Net spend/.test(host.textContent) && /Credit notes/.test(host.textContent) && /2026-01-01 to 2026-11-10/.test(host.textContent) && /Drafts are not counted/.test(host.textContent));
        check('and a row per supplier with credits, names never markup',
            /Landlord/.test(host.textContent) && /Credits/.test(host.textContent) && host.querySelector('i') === null && /<i>Evil<\/i> Co/.test(host.textContent));
        doc.getElementById('pr-from').value = '2026-06-01'; doc.getElementById('pr-to').value = '2026-06-30';
        w.loadPurchaseReport();
        await wait(300);
        const spend = sent.filter(s => s.url === '/api/purchases/reports/spend').pop();
        check('the range is sent and carried into the CSV with the view',
            /start=2026-06-01/.test(spend.full) && /end=2026-06-30/.test(spend.full) && /view=supplier/.test(doc.getElementById('pr-csv').getAttribute('href'))
            && /start=2026-06-01/.test(doc.getElementById('pr-csv').getAttribute('href')), doc.getElementById('pr-csv').getAttribute('href'));
        w.showPurchaseReport('category');
        await wait(300);
        check('spend by category names categories properly and has no credits column',
            /Rent/.test(host.textContent) && /Software\/SaaS/.test(host.textContent) && !/Credits/.test(host.textContent) && /view=category/.test(doc.getElementById('pr-csv').getAttribute('href')));
        w.showPurchaseReport('month');
        await wait(300);
        check('spend by month lists the months', /2026-10/.test(host.textContent) && /2026-11/.test(host.textContent) && /view=month/.test(doc.getElementById('pr-csv').getAttribute('href')));
    }
    {
        const { w } = boot(server({ empty: true }));
        await wait(60);
        w.showView('purchase-reports-view');
        await wait(300);
        const host = w.document.getElementById('pr-content');
        check('an empty payables report says you owe nothing', /do not owe any supplier anything/.test(host.textContent));
        w.showPurchaseReport('supplier');
        await wait(300);
        check('and an empty spend report says nothing was spent', /Nothing was spent/.test(host.textContent));
    }
    {
        const { w } = boot(server({ fails: true }));
        await wait(60);
        w.showView('purchase-reports-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('pr-content').textContent));
    }
    t.finish('purchase reports');
})();
