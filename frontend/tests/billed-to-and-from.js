/**
 * Billed to and billed from, on every screen: the contact form keeps a
 * company, billing address and tax id; picking a contact fills them on
 * an invoice or quote; the invoice view, the PDF, the public page and
 * the receive-payment form all show both parties. Words are text.
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
const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

const CONTACT = { id: 7, name: 'Ann <b>Lee</b>', email: 'a@x', phone_number: '0117', company: 'Ann & Co', address: '1 High St\nLeeds', tax_id: 'GB123' };
const INVOICE = { number: 'INV-1', to: 'Ann <b>Lee</b>', email: 'a@x', phone_number: '0117', to_company: 'Ann & Co', to_address: '1 High St\nLeeds', to_tax_id: 'GB123',
    bill_to: { name: 'Ann <b>Lee</b>', company: 'Ann & Co', address: '1 High St\nLeeds', email: 'a@x', phone: '0117', tax_id: 'GB123' },
    bill_from: { name: 'Me <i>Ltd</i>', address: '9 Dock Rd', email: 'me@x', phone_number: '', abn: 'GB999', tax_id: 'GB999' },
    company: { name: 'Me <i>Ltd</i>', address: '9 Dock Rd', email: 'me@x', phone_number: '', abn: 'GB999', tax_id: 'GB999' },
    date: '2026-09-01', issue_date: '2026-09-01', due_date: '2026-09-30', status: 'Awaiting Payment', paid: 0, due: 100, total: 100, subtotal: 100, tax_total: 0,
    currency: 'GBP', tax_type: 'exclusive', line_items: [{ name: 'x', description: 'x', qty: 1, price: 100, disc: 0, tax_rate: '0%', amount: 100, tax_amount: 0 }], payments: [], refunds: [], is_overdue: false, days_overdue: 0, tracking_id: 't' };

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://localhost/app.html' });
    const w = dom.window;
    const sent = [];
    w.console.error = () => { };
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, method, body: init && init.body });
        const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
        if (p === '/api/contacts/search') return give([CONTACT]);
        if (p === '/api/contacts' && method === 'GET') return give([CONTACT]);
        if (p === '/api/contacts' && method === 'POST') return give(CONTACT);
        if (p === '/api/contacts/7' && method === 'PUT') return give(CONTACT);
        if (p === '/api/invoices/INV-1' && method === 'GET') return give(INVOICE);
        if (p === '/api/invoices' && method === 'POST') return give({ number: 'INV-2' });
        if (p === '/api/client/logo') return give({});
        return give(p.endsWith('s') ? [] : {});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    w.showToast = () => { };
    w.allContacts = [CONTACT];
    return { w, doc: w.document, sent };
}

(async () => {
    {
        const src = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        check('the contact form, invoice form and quote form ask for company, billing address and tax id',
            /id="contact-company"/.test(src) && /id="contact-address"/.test(src) && /id="contact-taxid"/.test(src) &&
            /id="inv-to-company"/.test(src) && /id="inv-to-address"/.test(src) && /id="inv-to-taxid"/.test(src) &&
            /id="quote-to-company"/.test(src) && /id="quote-to-address"/.test(src) && /id="quote-to-taxid"/.test(src));
        check('the invoice view says Billed to and Billed from', /Billed to<\/label>/.test(src) && />Billed from</.test(src) && /id="view-inv-to-address"/.test(src) && /id="view-quote-to-address"/.test(src));
    }
    {
        const { w, doc, sent } = boot();
        await w.editContact(7);
        check('editing a contact fills its company, address and tax id',
            doc.getElementById('contact-company').value === 'Ann & Co' && doc.getElementById('contact-address').value === '1 High St\nLeeds' && doc.getElementById('contact-taxid').value === 'GB123');
        doc.getElementById('contact-taxid').value = 'GB777';
        await w.saveContact();
        await wait(30);
        const put = sent.find(s => s.url === '/api/contacts/7' && s.method === 'PUT');
        check('  and saving sends them', put && bodyOf(put).company === 'Ann & Co' && bodyOf(put).tax_id === 'GB777' && bodyOf(put).address === '1 High St\nLeeds', put && put.body);
    }
    {
        const { w, doc } = boot();
        w.setupContactAutocomplete('inv-contact', 'contact-autocomplete-dropdown', 'inv-email', 'inv-phone');
        const input = doc.getElementById('inv-contact');
        input.value = 'Ann';
        input.dispatchEvent(new w.Event('input'));
        await wait(320);
        const item = doc.querySelector('#contact-autocomplete-dropdown .contact-autocomplete-item');
        check('typing a name offers the contact', !!item);
        item.click();
        check('  and picking it fills email, phone, company, billing address and tax id on the invoice',
            doc.getElementById('inv-email').value === 'a@x' && doc.getElementById('inv-to-company').value === 'Ann & Co' && doc.getElementById('inv-to-address').value === '1 High St\nLeeds' && doc.getElementById('inv-to-taxid').value === 'GB123');
    }
    {
        const { w, doc, sent } = boot();
        await w.viewInvoice('INV-1');
        await wait(60);
        const to = doc.getElementById('view-inv-to-company').textContent + ' | ' + doc.getElementById('view-inv-to-address').textContent + ' | ' + doc.getElementById('view-inv-to-taxid').textContent;
        check('the invoice view shows the customer\'s company, address and tax id, as text',
            /Ann & Co \| 1 High St\nLeeds \| Tax ID: GB123/.test(to) && !doc.getElementById('view-inv-contact').querySelector('b'), to);
        check('  and the business as Billed from with its tax id', /Me <i>Ltd<\/i>/.test(doc.getElementById('view-inv-company-name').textContent) && /Tax ID: GB999/.test(doc.getElementById('view-inv-company-abn').textContent));
        w.recordPayment('INV-1');
        await wait(40);
        const parties = doc.getElementById('payment-parties');
        const text = parties.textContent.replace(/\s+/g, ' ');
        check('receiving a payment shows both parties like the bank details block, as text',
            parties.style.display === 'grid' && /Billed from/.test(text) && /Me <i>Ltd<\/i>/.test(text) && /Billed to/.test(text) && /Ann & Co/.test(text) && /1 High St/.test(text) && /Tax ID GB123/.test(text) && !parties.querySelector('i'), text);
    }
    {
        const { w, doc, sent } = boot();
        // The PDF reads the view; a stub jsPDF records what it is told to print.
        await w.viewInvoice('INV-1');
        await wait(60);
        const printed = [];
        function FakeDoc() { }
        FakeDoc.prototype = { internal: { pageSize: { getWidth: () => 595, getHeight: () => 842 } }, setFont() { }, setFontSize() { }, setTextColor() { }, setDrawColor() { }, setLineWidth() { }, setFillColor() { },
            rect() { }, line() { }, addImage() { }, addPage() { }, setPage() { }, getNumberOfPages() { return 1; }, roundedRect() { }, setLineDash() { },
            text(t) { (Array.isArray(t) ? t : [t]).forEach(x => printed.push(String(x))); }, splitTextToSize(t) { return [t]; }, getTextWidth() { return 10; }, output() { return ''; }, save() { }, setProperties() { } };
        w.jspdf = { jsPDF: FakeDoc };
        try { w.generateInvoicePDF(false); } catch (e) { printed.push('ERR ' + e.message); }
        const all = printed.join('\n');
        check('the PDF prints the customer\'s company, address lines and tax id under their name',
            /Ann & Co/.test(all) && /1 High St/.test(all) && /Leeds/.test(all) && /Tax ID: GB123/.test(all), all.slice(0, 300));
        check('  and the business\'s tax id', /Tax ID: GB999/.test(all));
    }
    {
        // The public page.
        const html = fs.readFileSync(path.join(ROOT, 'invoice.html'), 'utf8').replace(/<script[^>]*src=[^>]*><\/script>/g, '');
        const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://localhost/invoice.html?id=t',
            beforeParse(w) {
                w.console.error = () => { };
                w.fetch = (url) => { const p = String(url).split('?')[0];
                    const give = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });
                    if (p.endsWith('/pay/methods')) return give({ methods: [], is_paid: false, amount_due: 100, currency: 'GBP' });
                    return give({ number: 'INV-1', status: 'Awaiting Payment', payment: null, amount_due: 100, currency: 'GBP', total: 100, subtotal: 100, tax: 0, paid: 0, is_settled: false,
                        issue_date: '2026-09-01', due_date: '2026-09-30', line_items: [],
                        from: { company: 'Me <i>Ltd</i>', email: 'me@x', address: '9 Dock Rd', phone: '', tax_id: 'GB999' },
                        to: { name: 'Ann <b>Lee</b>', company: 'Ann & Co', address: '1 High St\nLeeds', tax_id: 'GB123' } }); };
            } });
        await wait(250);
        const sheet = dom.window.document.getElementById('sheet');
        const text = sheet.textContent.replace(/\s+/g, ' ');
        check('the public page shows the customer\'s company, address and tax id under Billed to, and the business\'s tax id, as text',
            /Billed to\s*Ann <b>Lee<\/b>\s*Ann & Co\s*1 High St\s*Leeds\s*Tax ID GB123/.test(text) && /Tax ID GB999/.test(text) && !sheet.querySelector('b, i'), text.slice(0, 300));
    }
    console.log(failures === 0 ? '\nAll billed-to-and-from checks passed.' : `\n${failures} check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
