/**
 * Business expenses.
 *
 * The totals are the server's. What the page decides: that the form offers
 * the business's own open accounts, that it sends exactly what was typed and
 * nothing when cancelled or incomplete, that the list asks for what the
 * filters say and the CSV link carries the same filters, that delete asks
 * first, that a refusal is shown, and that no name becomes markup.
 */
const { boot, wait, makeChecker, appDocument, fail } = require('./purchases-harness');
const t = makeChecker();
const check = t.check;

const ROWS = [
    { id: 1, spent_on: '2026-11-05', payee: 'Stationers', description: 'Pens', category: 'office', amount: 10, tax_amount: 2, total: 12, method: 'card', account_id: 3, account: 'Company card', reference: 'R-1' },
    { id: 2, spent_on: '2026-11-04', payee: '<b>Evil</b> Cafe', description: '', category: 'travel', amount: 5, tax_amount: 0, total: 5, method: 'cash', account_id: null, account: '', reference: '' },
];

function server(opts) {
    opts = opts || {};
    return (p, init, full) => {
        const method = init.method || 'GET';
        if (p === '/api/accounts') return { accounts: [{ id: 3, name: 'Company card', active: true }, { id: 4, name: 'Old', active: false }] };
        if (p === '/api/business-expenses' && method === 'GET') {
            if (opts.listFails) return fail(500, 'Server is down');
            return { expenses: ROWS, count: 2, total: 17, by_category: { office: 12, travel: 5 } };
        }
        if (p === '/api/business-expenses' && method === 'POST') return opts.saveFails ? fail(400, opts.saveFails) : ROWS[0];
        if (/^\/api\/business-expenses\/\d+$/.test(p)) return method === 'DELETE' ? { message: 'Expense deleted' } : ROWS[0];
        return undefined;
    };
}
const asking = (w, answers) => { const asked = []; w.uiForm = (f, o) => { asked.push({ fields: f, opts: o || {} }); return Promise.resolve(answers.length ? answers.shift() : null); }; return asked; };

(async () => {
    {
        const doc = appDocument();
        check('Business expenses is in the Purchases menu, named differently from People > Expenses',
            !!doc.querySelector('[data-nav-group="Purchases"] #nav-business-expenses')
            && doc.getElementById('nav-business-expenses').textContent.trim() !== doc.getElementById('nav-expenses').textContent.trim());
        check('the screen has filters, a CSV link and a table', ['business-expenses-view', 'be-search', 'be-from', 'be-to', 'be-category', 'be-csv', 'be-body', 'be-categories', 'be-summary'].every(id => !!doc.getElementById(id)));
    }
    {
        const { w, sent, confirms } = boot(server());
        await wait(60);
        check('the address and highlight are known', w.ROUTE_SLUGS['business-expenses-view'] === 'business-expenses' && w.NAV_FOR_VIEW['business-expenses-view'] === 'nav-business-expenses');
        w.showView('business-expenses-view');
        await wait(300);
        const doc = w.document, body = doc.getElementById('be-body');
        check('it lists the expenses with a summary and totals by category',
            body.querySelectorAll('tr').length === 2 && /2 expenses/.test(doc.getElementById('be-summary').textContent) && /17\.00/.test(doc.getElementById('be-summary').textContent)
            && /Office Supplies £12\.00/.test(doc.getElementById('be-categories').textContent) && /Travel £5\.00/.test(doc.getElementById('be-categories').textContent));
        check('each row shows who, category, how and from which account', /Stationers/.test(body.textContent) && /Card/.test(body.textContent) && /Company card/.test(body.textContent));
        check('a name can never become markup', body.querySelector('b') === null && /<b>Evil<\/b> Cafe/.test(body.textContent));
        doc.getElementById('be-search').value = 'pens'; doc.getElementById('be-from').value = '2026-11-01'; doc.getElementById('be-category').value = 'office';
        w.loadBusinessExpenses();
        await wait(300);
        const last = sent.filter(s => s.url === '/api/business-expenses' && s.method === 'GET').pop();
        check('the filters are sent', /q=pens/.test(last.full) && /start=2026-11-01/.test(last.full) && /category=office/.test(last.full), last.full);
        check('and the CSV link carries the same filters', /business-expenses\.csv\?/.test(doc.getElementById('be-csv').getAttribute('href')) && /q=pens/.test(doc.getElementById('be-csv').getAttribute('href')));
        body.querySelector('[data-be-delete]').click();
        await wait(60);
        check('Delete asks first, naming the amount and who, then deletes',
            confirms.length === 1 && /£12\.00/.test(confirms[0]) && /Stationers/.test(confirms[0]) && sent.some(s => s.method === 'DELETE' && s.url === '/api/business-expenses/1'));
    }
    {
        const { w, sent, toasts } = boot(server());
        await wait(60);
        const asked = asking(w, [null, { spent_on: '2026-11-06', payee: ' Landlord ', description: 'Deposit', category: 'rent', amount: '100', tax_amount: '', method: 'bank_transfer', account_id: '3', reference: ' DEP-1 ' },
            { spent_on: '', payee: '', description: '', category: 'general', amount: '5', tax_amount: '0', method: 'card', account_id: '' },
            { spent_on: '', payee: 'X', description: '', category: 'general', amount: '0', tax_amount: '0', method: 'card', account_id: '' }]);
        const posts = () => sent.filter(s => s.method === 'POST' && s.url === '/api/business-expenses');
        await w.newBusinessExpense();
        check('cancelling the form sends nothing', posts().length === 0);
        const f = n => asked[0].fields.find(x => x.name === n);
        check('the form offers the open accounts only, and starts today',
            f('account_id').options.map(o => o.value).join() === ',3' && /^\d{4}-\d\d-\d\d$/.test(f('spent_on').value));
        check('and the categories and methods by name', f('category').options.some(o => o.label === 'Software/SaaS') && f('method').options.some(o => o.label === 'Bank transfer'));
        await w.newBusinessExpense();
        const body = posts().length && JSON.parse(posts()[0].body);
        check('Save posts exactly what was typed',
            body && body.payee === 'Landlord' && body.description === 'Deposit' && body.category === 'rent' && body.amount === 100 && body.tax_amount === 0
            && body.method === 'bank_transfer' && body.account_id === 3 && body.reference === 'DEP-1' && body.spent_on === '2026-11-06', posts()[0] && posts()[0].body);
        const n = posts().length;
        await w.newBusinessExpense();
        check('with neither who nor what, nothing is sent', toasts.some(x => /who it was paid to/.test(x.m)) && posts().length === n);
        await w.newBusinessExpense();
        check('an amount is required too', toasts.some(x => /more than nothing/.test(x.m)) && posts().length === n);
        asking(w, [{ spent_on: '2026-11-05', payee: 'Stationers', description: 'Pens', category: 'office', amount: '10', tax_amount: '2', method: 'card', account_id: '3', reference: '' }]);
        await w.editBusinessExpense(ROWS[0]);
        check('editing puts to that expense', sent.some(s => s.method === 'PUT' && s.url === '/api/business-expenses/1'));
    }
    {
        const { w, toasts } = boot(server({ saveFails: 'Pick a category from the list' }));
        await wait(60);
        asking(w, [{ spent_on: '', payee: 'X', description: '', category: 'general', amount: '5', tax_amount: '0', method: 'card', account_id: '' }]);
        await w.newBusinessExpense();
        check('a refusal from the server is shown', toasts.some(x => /Pick a category/.test(x.m)));
    }
    {
        const { w } = boot(server({ listFails: true }));
        await wait(60);
        w.showView('business-expenses-view');
        await wait(300);
        check('a failed load says so', /Server is down/.test(w.document.getElementById('be-body').textContent));
    }
    t.finish('business expenses');
})();
