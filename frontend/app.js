// ============================================================
// aniprotech - app.js (Production)
// ============================================================

var _appCurrency = 'GBP';
var _viewCurrency = '';

var CURRENCIES = [
    {code:'AED', name:'UAE Dirham', symbol:'د.إ', country:'United Arab Emirates'},
    {code:'AFN', name:'Afghan Afghani', symbol:'؋', country:'Afghanistan'},
    {code:'ALL', name:'Albanian Lek', symbol:'L', country:'Albania'},
    {code:'AMD', name:'Armenian Dram', symbol:'֏', country:'Armenia'},
    {code:'ANG', name:'Netherlands Antillean Guilder', symbol:'ƒ', country:'Curaçao'},
    {code:'AOA', name:'Angolan Kwanza', symbol:'Kz', country:'Angola'},
    {code:'ARS', name:'Argentine Peso', symbol:'$', country:'Argentina'},
    {code:'AUD', name:'Australian Dollar', symbol:'A$', country:'Australia'},
    {code:'AWG', name:'Aruban Florin', symbol:'ƒ', country:'Aruba'},
    {code:'AZN', name:'Azerbaijani Manat', symbol:'₼', country:'Azerbaijan'},
    {code:'BAM', name:'Bosnia-Herzegovina Convertible Mark', symbol:'KM', country:'Bosnia and Herzegovina'},
    {code:'BBD', name:'Barbadian Dollar', symbol:'$', country:'Barbados'},
    {code:'BDT', name:'Bangladeshi Taka', symbol:'৳', country:'Bangladesh'},
    {code:'BGN', name:'Bulgarian Lev', symbol:'лв', country:'Bulgaria'},
    {code:'BHD', name:'Bahraini Dinar', symbol:'ب.د', country:'Bahrain'},
    {code:'BIF', name:'Burundian Franc', symbol:'FBu', country:'Burundi'},
    {code:'BMD', name:'Bermudan Dollar', symbol:'$', country:'Bermuda'},
    {code:'BND', name:'Brunei Dollar', symbol:'$', country:'Brunei'},
    {code:'BOB', name:'Bolivian Boliviano', symbol:'Bs', country:'Bolivia'},
    {code:'BRL', name:'Brazilian Real', symbol:'R$', country:'Brazil'},
    {code:'BSD', name:'Bahamian Dollar', symbol:'$', country:'Bahamas'},
    {code:'BTN', name:'Bhutanese Ngultrum', symbol:'Nu.', country:'Bhutan'},
    {code:'BWP', name:'Botswana Pula', symbol:'P', country:'Botswana'},
    {code:'BYN', name:'Belarusian Ruble', symbol:'Br', country:'Belarus'},
    {code:'BZD', name:'Belize Dollar', symbol:'$', country:'Belize'},
    {code:'CAD', name:'Canadian Dollar', symbol:'C$', country:'Canada'},
    {code:'CDF', name:'Congolese Franc', symbol:'FC', country:'DR Congo'},
    {code:'CHF', name:'Swiss Franc', symbol:'CHF', country:'Switzerland'},
    {code:'CLP', name:'Chilean Peso', symbol:'$', country:'Chile'},
    {code:'CNY', name:'Chinese Yuan', symbol:'¥', country:'China'},
    {code:'COP', name:'Colombian Peso', symbol:'$', country:'Colombia'},
    {code:'CRC', name:'Costa Rican Colón', symbol:'₡', country:'Costa Rica'},
    {code:'CUP', name:'Cuban Peso', symbol:'$', country:'Cuba'},
    {code:'CVE', name:'Cape Verdean Escudo', symbol:'Esc', country:'Cape Verde'},
    {code:'CZK', name:'Czech Koruna', symbol:'Kč', country:'Czech Republic'},
    {code:'DJF', name:'Djiboutian Franc', symbol:'Fdj', country:'Djibouti'},
    {code:'DKK', name:'Danish Krone', symbol:'kr', country:'Denmark'},
    {code:'DOP', name:'Dominican Peso', symbol:'RD$', country:'Dominican Republic'},
    {code:'DZD', name:'Algerian Dinar', symbol:'دج', country:'Algeria'},
    {code:'EGP', name:'Egyptian Pound', symbol:'£', country:'Egypt'},
    {code:'ERN', name:'Eritrean Nakfa', symbol:'Nfk', country:'Eritrea'},
    {code:'ETB', name:'Ethiopian Birr', symbol:'Br', country:'Ethiopia'},
    {code:'EUR', name:'Euro', symbol:'€', country:'European Union'},
    {code:'FJD', name:'Fijian Dollar', symbol:'FJ$', country:'Fiji'},
    {code:'FKP', name:'Falkland Islands Pound', symbol:'£', country:'Falkland Islands'},
    {code:'GBP', name:'British Pound', symbol:'£', country:'United Kingdom'},
    {code:'GEL', name:'Georgian Lari', symbol:'₾', country:'Georgia'},
    {code:'GHS', name:'Ghanaian Cedi', symbol:'₵', country:'Ghana'},
    {code:'GIP', name:'Gibraltar Pound', symbol:'£', country:'Gibraltar'},
    {code:'GMD', name:'Gambian Dalasi', symbol:'D', country:'Gambia'},
    {code:'GNF', name:'Guinean Franc', symbol:'FG', country:'Guinea'},
    {code:'GTQ', name:'Guatemalan Quetzal', symbol:'Q', country:'Guatemala'},
    {code:'GYD', name:'Guyanaese Dollar', symbol:'$', country:'Guyana'},
    {code:'HKD', name:'Hong Kong Dollar', symbol:'HK$', country:'Hong Kong'},
    {code:'HNL', name:'Honduran Lempira', symbol:'L', country:'Honduras'},
    {code:'HRK', name:'Croatian Kuna', symbol:'kn', country:'Croatia'},
    {code:'HTG', name:'Haitian Gourde', symbol:'G', country:'Haiti'},
    {code:'HUF', name:'Hungarian Forint', symbol:'Ft', country:'Hungary'},
    {code:'IDR', name:'Indonesian Rupiah', symbol:'Rp', country:'Indonesia'},
    {code:'ILS', name:'Israeli New Shekel', symbol:'₪', country:'Israel'},
    {code:'INR', name:'Indian Rupee', symbol:'₹', country:'India'},
    {code:'IQD', name:'Iraqi Dinar', symbol:'ع.د', country:'Iraq'},
    {code:'IRR', name:'Iranian Rial', symbol:'﷼', country:'Iran'},
    {code:'ISK', name:'Icelandic Króna', symbol:'kr', country:'Iceland'},
    {code:'JMD', name:'Jamaican Dollar', symbol:'J$', country:'Jamaica'},
    {code:'JOD', name:'Jordanian Dinar', symbol:'د.ا', country:'Jordan'},
    {code:'JPY', name:'Japanese Yen', symbol:'¥', country:'Japan'},
    {code:'KES', name:'Kenyan Shilling', symbol:'KSh', country:'Kenya'},
    {code:'KGS', name:'Kyrgystani Som', symbol:'с', country:'Kyrgyzstan'},
    {code:'KHR', name:'Cambodian Riel', symbol:'៛', country:'Cambodia'},
    {code:'KMF', name:'Comorian Franc', symbol:'CF', country:'Comoros'},
    {code:'KPW', name:'North Korean Won', symbol:'₩', country:'North Korea'},
    {code:'KRW', name:'South Korean Won', symbol:'₩', country:'South Korea'},
    {code:'KWD', name:'Kuwaiti Dinar', symbol:'د.ك', country:'Kuwait'},
    {code:'KYD', name:'Cayman Islands Dollar', symbol:'CI$', country:'Cayman Islands'},
    {code:'KZT', name:'Kazakhstani Tenge', symbol:'₸', country:'Kazakhstan'},
    {code:'LAK', name:'Laotian Kip', symbol:'₭', country:'Laos'},
    {code:'LBP', name:'Lebanese Pound', symbol:'ل.ل', country:'Lebanon'},
    {code:'LKR', name:'Sri Lankan Rupee', symbol:'₨', country:'Sri Lanka'},
    {code:'LRD', name:'Liberian Dollar', symbol:'$', country:'Liberia'},
    {code:'LSL', name:'Lesotho Loti', symbol:'L', country:'Lesotho'},
    {code:'LYD', name:'Libyan Dinar', symbol:'ل.د', country:'Libya'},
    {code:'MAD', name:'Moroccan Dirham', symbol:'د.م.', country:'Morocco'},
    {code:'MDL', name:'Moldovan Leu', symbol:'L', country:'Moldova'},
    {code:'MGA', name:'Malagasy Ariary', symbol:'Ar', country:'Madagascar'},
    {code:'MKD', name:'Macedonian Denar', symbol:'ден', country:'North Macedonia'},
    {code:'MMK', name:'Myanmar Kyat', symbol:'K', country:'Myanmar'},
    {code:'MNT', name:'Mongolian Tugrik', symbol:'₮', country:'Mongolia'},
    {code:'MOP', name:'Macanese Pataca', symbol:'MOP$', country:'Macau'},
    {code:'MRU', name:'Mauritanian Ouguiya', symbol:'UM', country:'Mauritania'},
    {code:'MUR', name:'Mauritian Rupee', symbol:'₨', country:'Mauritius'},
    {code:'MVR', name:'Maldivian Rufiyaa', symbol:'Rf', country:'Maldives'},
    {code:'MWK', name:'Malawian Kwacha', symbol:'MK', country:'Malawi'},
    {code:'MXN', name:'Mexican Peso', symbol:'$', country:'Mexico'},
    {code:'MYR', name:'Malaysian Ringgit', symbol:'RM', country:'Malaysia'},
    {code:'MZN', name:'Mozambican Metical', symbol:'MT', country:'Mozambique'},
    {code:'NAD', name:'Namibian Dollar', symbol:'$', country:'Namibia'},
    {code:'NGN', name:'Nigerian Naira', symbol:'₦', country:'Nigeria'},
    {code:'NIO', name:'Nicaraguan Córdoba', symbol:'C$', country:'Nicaragua'},
    {code:'NOK', name:'Norwegian Krone', symbol:'kr', country:'Norway'},
    {code:'NPR', name:'Nepalese Rupee', symbol:'₨', country:'Nepal'},
    {code:'NZD', name:'New Zealand Dollar', symbol:'NZ$', country:'New Zealand'},
    {code:'OMR', name:'Omani Rial', symbol:'ر.ع.', country:'Oman'},
    {code:'PAB', name:'Panamanian Balboa', symbol:'B/.', country:'Panama'},
    {code:'PEN', name:'Peruvian Sol', symbol:'S/', country:'Peru'},
    {code:'PGK', name:'Papua New Guinean Kina', symbol:'K', country:'Papua New Guinea'},
    {code:'PHP', name:'Philippine Peso', symbol:'₱', country:'Philippines'},
    {code:'PKR', name:'Pakistani Rupee', symbol:'₨', country:'Pakistan'},
    {code:'PLN', name:'Polish Złoty', symbol:'zł', country:'Poland'},
    {code:'PYG', name:'Paraguayan Guarani', symbol:'₲', country:'Paraguay'},
    {code:'QAR', name:'Qatari Rial', symbol:'ر.ق', country:'Qatar'},
    {code:'RON', name:'Romanian Leu', symbol:'lei', country:'Romania'},
    {code:'RSD', name:'Serbian Dinar', symbol:'дин', country:'Serbia'},
    {code:'RUB', name:'Russian Ruble', symbol:'₽', country:'Russia'},
    {code:'RWF', name:'Rwandan Franc', symbol:'FRw', country:'Rwanda'},
    {code:'SAR', name:'Saudi Riyal', symbol:'﷼', country:'Saudi Arabia'},
    {code:'SBD', name:'Solomon Islands Dollar', symbol:'SI$', country:'Solomon Islands'},
    {code:'SCR', name:'Seychellois Rupee', symbol:'₨', country:'Seychelles'},
    {code:'SDG', name:'Sudanese Pound', symbol:'ج.س', country:'Sudan'},
    {code:'SEK', name:'Swedish Krona', symbol:'kr', country:'Sweden'},
    {code:'SGD', name:'Singapore Dollar', symbol:'S$', country:'Singapore'},
    {code:'SHP', name:'Saint Helena Pound', symbol:'£', country:'Saint Helena'},
    {code:'SLL', name:'Sierra Leonean Leone', symbol:'Le', country:'Sierra Leone'},
    {code:'SOS', name:'Somali Shilling', symbol:'Sh', country:'Somalia'},
    {code:'SRD', name:'Surinamese Dollar', symbol:'$', country:'Suriname'},
    {code:'SSP', name:'South Sudanese Pound', symbol:'£', country:'South Sudan'},
    {code:'STN', name:'São Tomé and Príncipe Dobra', symbol:'Db', country:'São Tomé and Príncipe'},
    {code:'SVC', name:'Salvadoran Colón', symbol:'$', country:'El Salvador'},
    {code:'SYP', name:'Syrian Pound', symbol:'£', country:'Syria'},
    {code:'SZL', name:'Swazi Lilangeni', symbol:'L', country:'Eswatini'},
    {code:'THB', name:'Thai Baht', symbol:'฿', country:'Thailand'},
    {code:'TJS', name:'Tajikistani Somoni', symbol:'SM', country:'Tajikistan'},
    {code:'TMT', name:'Turkmenistani Manat', symbol:'m', country:'Turkmenistan'},
    {code:'TND', name:'Tunisian Dinar', symbol:'د.ت', country:'Tunisia'},
    {code:'TOP', name:'Tongan Paʻanga', symbol:'T$', country:'Tonga'},
    {code:'TRY', name:'Turkish Lira', symbol:'₺', country:'Turkey'},
    {code:'TTD', name:'Trinidad and Tobago Dollar', symbol:'TT$', country:'Trinidad and Tobago'},
    {code:'TWD', name:'New Taiwan Dollar', symbol:'NT$', country:'Taiwan'},
    {code:'TZS', name:'Tanzanian Shilling', symbol:'Sh', country:'Tanzania'},
    {code:'UAH', name:'Ukrainian Hryvnia', symbol:'₴', country:'Ukraine'},
    {code:'UGX', name:'Ugandan Shilling', symbol:'USh', country:'Uganda'},
    {code:'USD', name:'US Dollar', symbol:'$', country:'United States'},
    {code:'UYU', name:'Uruguayan Peso', symbol:'$U', country:'Uruguay'},
    {code:'UZS', name:'Uzbekistani Som', symbol:"so'm", country:'Uzbekistan'},
    {code:'VES', name:'Venezuelan Bolívar', symbol:'Bs', country:'Venezuela'},
    {code:'VND', name:'Vietnamese Đồng', symbol:'₫', country:'Vietnam'},
    {code:'VUV', name:'Vanuatu Vatu', symbol:'VT', country:'Vanuatu'},
    {code:'WST', name:'Samoan Tala', symbol:'T', country:'Samoa'},
    {code:'XAF', name:'Central African CFA Franc', symbol:'FCFA', country:'Central Africa'},
    {code:'XCD', name:'East Caribbean Dollar', symbol:'EC$', country:'Eastern Caribbean'},
    {code:'XOF', name:'West African CFA Franc', symbol:'CFA', country:'West Africa'},
    {code:'XPF', name:'CFP Franc', symbol:'₣', country:'French Pacific'},
    {code:'YER', name:'Yemeni Rial', symbol:'﷼', country:'Yemen'},
    {code:'ZAR', name:'South African Rand', symbol:'R', country:'South Africa'},
    {code:'ZMW', name:'Zambian Kwacha', symbol:'ZK', country:'Zambia'},
    {code:'ZWL', name:'Zimbabwean Dollar', symbol:'Z$', country:'Zimbabwe'}
];

function getCurrencyInfo(code) {
    code = (code || '').toUpperCase();
    for (var i = 0; i < CURRENCIES.length; i++) {
        if (CURRENCIES[i].code === code) return CURRENCIES[i];
    }
    return { code: code, name: code, symbol: code, country: '' };
}
function getCurrencySymbol(code) {
    code = code || _viewCurrency || _appCurrency || 'GBP';
    return getCurrencyInfo(code).symbol;
}
function formatMoney(val) { return getCurrencySymbol() + parseFloat(val || 0).toFixed(2); }

// --- Searchable Currency Picker ---
var _curPickers = {};

function setupCurrencyPicker(name, displayId, hiddenId, listId, searchId, itemsId, onChange) {
    _curPickers[name] = { displayId: displayId, hiddenId: hiddenId, listId: listId, itemsId: itemsId, onChange: onChange || null };
    var searchEl = document.getElementById(searchId);
    if (searchEl) searchEl.addEventListener('input', function() { renderCurrencyItems(name, this.value); });
    renderCurrencyItems(name, '');
    var hidden = document.getElementById(hiddenId);
    if (hidden && hidden.value) setCurrencyPickerDisplay(name, hidden.value);
}

function renderCurrencyItems(name, q) {
    var st = _curPickers[name];
    if (!st) return;
    q = (q || '').toLowerCase();
    var html = '';
    CURRENCIES.forEach(function(c) {
        if (q && c.code.toLowerCase().indexOf(q) === -1 &&
            c.name.toLowerCase().indexOf(q) === -1 &&
            (c.country || '').toLowerCase().indexOf(q) === -1) return;
        html += '<div class="currency-option" data-code="' + c.code + '" onclick="currencyPick(\'' + name + '\',\'' + c.code + '\')">' +
                '<span class="cur-code">' + c.code + '</span>' +
                '<span class="cur-symbol">' + c.symbol + '</span>' +
                '<span class="cur-name">' + c.name + '</span>' +
                (c.country ? '<span class="cur-country">' + c.country + '</span>' : '') +
                '</div>';
    });
    var items = document.getElementById(st.itemsId);
    if (items) items.innerHTML = html || '<div class="currency-option no-result">No currency found</div>';
}

function currencyPick(name, code) {
    var st = _curPickers[name];
    if (!st) return;
    setCurrencyPickerDisplay(name, code);
    var list = document.getElementById(st.listId);
    if (list) list.style.display = 'none';
    if (st.onChange) st.onChange(code);
}

function setCurrencyPickerDisplay(name, code) {
    var st = _curPickers[name];
    if (!st) return;
    var info = getCurrencyInfo(code);
    var disp = document.getElementById(st.displayId);
    if (disp) disp.value = code + ' (' + info.symbol + ') - ' + info.name;
    var hidden = document.getElementById(st.hiddenId);
    if (hidden) hidden.value = info.code;
}

function toggleCurrencyPicker(name, ev) {
    if (ev) ev.stopPropagation();
    var st = _curPickers[name];
    if (!st) return;
    var list = document.getElementById(st.listId);
    if (!list) return;
    var wasOpen = list.style.display === 'block';
    closeAllCurrencyPickers();
    if (!wasOpen) {
        list.style.display = 'block';
        var search = list.querySelector('.currency-search');
        if (search) { search.value = ''; renderCurrencyItems(name, ''); }
    }
}

function closeAllCurrencyPickers() {
    Object.keys(_curPickers).forEach(function(name) {
        var el = document.getElementById(_curPickers[name].listId);
        if (el) el.style.display = 'none';
    });
}

document.addEventListener('click', function(ev) {
    if (ev.target && ev.target.closest && !ev.target.closest('.currency-picker')) closeAllCurrencyPickers();
});

// --- Toast Notifications ---
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    const icons = { success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>', error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>', warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>', info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>' };
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || icons.info) + '</span><span class="toast-message">' + esc(message) + '</span><button class="toast-close" onclick="this.parentElement.remove()">&times;</button>';
    container.appendChild(toast);
    requestAnimationFrame(function() { toast.classList.add('toast-show'); });
    setTimeout(function() { toast.classList.remove('toast-show'); setTimeout(function() { toast.remove(); }, 300); }, 5000);
}

// --- Mobile Menu ---
function toggleMobileMenu() {
    var nav = document.getElementById('main-nav');
    var overlay = document.getElementById('mobile-overlay');
    if (nav) nav.classList.toggle('mobile-open');
    if (overlay) overlay.classList.toggle('active');
    document.body.classList.toggle('no-scroll');
}
window.toggleMobileMenu = toggleMobileMenu;

// A YYYY-MM-DD string for a date as the user sees it.
// toISOString() prints in UTC, so anywhere east of Greenwich a local midnight
// becomes the previous day. Every date the app shows or submits is a calendar
// date, not an instant, so it must be read in local terms.
function localDate(d) {
    d = d || new Date();
    return d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
}
window.localDate = localDate;

// --- View Switcher ---
function showView(viewId) {
    if (viewId !== 'view-invoice-view' && viewId !== 'view-quote-view') _viewCurrency = '';
    document.querySelectorAll('.view-section').forEach(function(el) {
        el.classList.remove('active');
        el.style.display = 'none';
    });
    var target = document.getElementById(viewId);
    if (target) {
        target.classList.add('active');
        target.style.display = 'block';
    }
    if (viewId === 'create-invoice-view') {
        var curHidden = document.getElementById('inv-currency');
        if (curHidden && curHidden.value !== _appCurrency) {
            setCurrencyPickerDisplay('invCurrency', _appCurrency);
        }
    }
    document.querySelectorAll('.nav-item').forEach(function(el) { el.classList.remove('active'); });
    var navMap = {
        'dashboard-view': 'nav-dashboard',
        'invoices-view': 'nav-invoices',
        'create-invoice-view': 'nav-invoices',
        'view-invoice-view': 'nav-invoices',
        'sales-pipeline-view': 'nav-pipeline',
        'recurring-view': 'nav-recurring',
        'customer-view': 'nav-contacts',
        'quotes-view': 'nav-quotes',
        'create-quote-view': 'nav-quotes',
        'view-quote-view': 'nav-quotes',
        'bills-view': 'nav-bills',
        'reports-view': 'nav-reports',
        'contacts-view': 'nav-contacts',
        'employees-view': 'nav-people',
        'employee-detail-view': 'nav-people',
        'departments-view': 'nav-people',
        'attendance-view': 'nav-people',
        'leave-view': 'nav-leave',
        'goals-view': 'nav-goals',
        'onboarding-hub-view': 'nav-onboarding',
        'recruitment-view': 'nav-recruitment',
        'payroll-view': 'nav-payroll',
        'payslip-detail-view': 'nav-payroll',
        'orgchart-view': 'nav-org',
        'wallet-view': 'nav-wallet',
        'settings-view': 'nav-settings'
    };
    var navId = navMap[viewId];
    if (navId) { var navEl = document.getElementById(navId); if (navEl) navEl.classList.add('active'); }
    if (viewId === 'invoices-view' && typeof fetchInvoices === 'function') fetchInvoices();
    if (viewId === 'quotes-view' && typeof fetchQuotes === 'function') fetchQuotes();
    if (viewId === 'sales-pipeline-view' && typeof loadSalesPipeline === 'function') loadSalesPipeline();
    if (viewId === 'recurring-view' && typeof loadRecurring === 'function') loadRecurring();
    if (viewId === 'create-invoice-view' && typeof fetchNextInvoiceNumber === 'function') fetchNextInvoiceNumber();
    if (viewId === 'create-invoice-view' && typeof setupContactAutocomplete === 'function') setupContactAutocomplete();
    if (viewId === 'settings-view' && typeof loadGmailStatus === 'function') loadGmailStatus();
    if (viewId === 'settings-view' && typeof loadSettings === 'function') loadSettings();
    if (viewId === 'settings-view' && typeof loadTaxRates === 'function') loadTaxRates();
    if (viewId === 'settings-view' && typeof loadTeam === 'function') loadTeam();
    if (viewId === 'settings-view' && typeof loadAuditLogs === 'function') loadAuditLogs();
    if (viewId === 'reports-view' && typeof loadReports === 'function') loadReports();
    // Close mobile menu
    var mainNav = document.getElementById('main-nav');
    var mobileOverlay = document.getElementById('mobile-overlay');
    if (mainNav) mainNav.classList.remove('mobile-open');
    if (mobileOverlay) mobileOverlay.classList.remove('active');
    document.body.classList.remove('no-scroll');
}
window.showView = showView;

// --- Dashboard drill-down -------------------------------------------------
// Every headline figure on the dashboard is a question ("who owes me?"), so
// each card navigates to the list that answers it, pre-filtered.

// Activates the tab button whose onclick targets the given filter, so the
// list view's own tab strip stays in sync with where we navigated from.
function activateTabForFilter(containerSelector, filterValue) {
    var container = document.querySelector(containerSelector);
    if (!container) return;
    var buttons = container.querySelectorAll('.tab');
    for (var i = 0; i < buttons.length; i++) {
        var attr = buttons[i].getAttribute('onclick') || '';
        if (attr.indexOf("'" + filterValue + "'") >= 0) {
            buttons[i].click();
            return;
        }
    }
}

function goToInvoices(filter) {
    showView('invoices-view');
    if (!filter || filter === 'all') return;
    // fetchInvoices() is kicked off by showView; wait for it before filtering.
    setTimeout(function () { activateTabForFilter('.invoices-tabs', filter); }, 250);
}
window.goToInvoices = goToInvoices;

function goToEmployees(statusFilter) {
    showView('employees-view');
    activateTabForFilter('#employee-tabs', statusFilter || '');
}
window.goToEmployees = goToEmployees;

function enforcePortalSeparation() {
    var isHrPortal = window.location.pathname.includes('hr.html');
    var targetPortal = isHrPortal ? 'hr' : 'invoicing';

    var navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(function(item) {
        var portal = item.getAttribute('data-portal');
        if (portal === targetPortal || portal === 'shared') {
            item.style.display = '';
        } else if (portal) {
            item.style.display = 'none';
        }
    });
}
window.enforcePortalSeparation = enforcePortalSeparation;

// --- Utility ---
var allInvoices = [];
var currentFilter = 'all';

function formatCurrency(amount, currency) {
    currency = currency || _viewCurrency || _appCurrency || 'GBP';
    try {
        return new Intl.NumberFormat('en-GB', { style: 'currency', currency: currency }).format(amount || 0);
    } catch (e) {
        return getCurrencyInfo(currency).symbol + (parseFloat(amount) || 0).toFixed(2);
    }
}

// --- Auth ---
async function checkAuthStatus() {
    var loginBtn = document.getElementById('login-btn');
    var userInfo = document.getElementById('user-info');
    try {
        var res = await fetch('/api/auth/me');
        var data = await res.json();
        if (data.user) {
            if (loginBtn) loginBtn.style.display = 'none';
            if (userInfo) {
                userInfo.style.display = 'flex';
                var name = data.user.name || data.user.email;
                var avatar = document.getElementById('user-avatar');
                if (avatar) { avatar.textContent = name[0].toUpperCase(); avatar.title = name; }
            }
        } else {
            if (loginBtn) loginBtn.style.display = 'inline-block';
            if (userInfo) userInfo.style.display = 'none';
        }
    } catch (e) {
        console.error("Auth check failed", e);
        if (loginBtn) loginBtn.style.display = 'inline-block';
        if (userInfo) userInfo.style.display = 'none';
    }
    try {
        var saRes = await fetch('/api/superadmin/me');
        if (saRes.ok) {
            var banner = document.getElementById('superadmin-impersonate-banner');
            if (banner) { banner.style.display = 'flex'; }
        }
    } catch (e) {}
}

function handleLogout() {
    window.location.href = '/api/auth/logout';
}
window.handleLogout = handleLogout;

// --- Dashboard ---
async function fetchDashboardData() {
    try {
        var response = await fetch('/api/dashboard-summary');
        if (!response.ok) {
            var container = document.getElementById('cash-flow-container');
            var loginLink = window.location.pathname.includes('hr.html') ? '/hr-login.html' : '/login.html';
            if (container) container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:40px;"><a href="' + loginLink + '" style="color:var(--accent-cyan);">Sign in</a> to view dashboard</div>';
            return;
        }
        renderDashboard(await response.json());
    } catch (error) {
        console.error('Dashboard load failed:', error);
        var container2 = document.getElementById('cash-flow-container');
        if (container2) container2.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:40px;">Failed to load</div>';
    }
}

// Small helper so a missing element on one portal's dashboard never aborts the
// rest of the render (app.html and hr.html share this code but differ slightly).
function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
}

// A headline figure, split by currency when the tenant bills in more than one.
// Adding pounds to rupees produces a number nobody can act on.
function setMoney(id, totals, fallbackAmount, baseCurrency) {
    var el = document.getElementById(id);
    if (!el) return;
    if (!totals || !totals.length) {
        el.textContent = formatCurrency(fallbackAmount || 0, baseCurrency);
        return;
    }
    el.innerHTML = totals.map(function (t) {
        return '<div>' + esc(formatCurrency(t.value, t.currency)) + '</div>';
    }).join('');
    el.classList.add('stat-money');
}

function renderDashboard(data) {
    var s = data.summary || {};
    var by = s.by_currency || {};
    var base = data.base_currency;
    setMoney('dash-total-invoiced', by.total_invoiced, s.total_invoiced, base);
    setMoney('dash-total-revenue', by.total_revenue, s.total_revenue, base);
    setMoney('dash-invoices-owed', by.invoices_owed, s.invoices_owed, base);
    setMoney('dash-overdue-amount', by.overdue_amount, s.overdue_amount, base);
    setText('dash-overdue-count', s.overdue_count || 0);
    setText('dash-total-count', s.total_count || 0);
    if (typeof renderInvoiceChart === 'function') {
        renderInvoiceChart(s.total_revenue || 0, s.invoices_owed || 0, s.total_count || 0);
    }
    
    

    setText('dash-paid-count', s.paid_count || 0);
    setText('dash-pending-count', s.pending_count || 0);
    setText('dash-draft-count', s.draft_count || 0);
    renderCashFlowChart(data.cash_flow);
    if (typeof loadAIInsights === 'function') loadAIInsights();
}

function renderCashFlowChart(cashFlowData) {
    var container = document.getElementById('cash-flow-container');
    if (!container || !cashFlowData || !cashFlowData.money_in) return;
    var maxTotal = Math.max.apply(null, cashFlowData.money_in.concat(cashFlowData.money_out)) || 1;
    var html = '<div class="chart-bars">';
    for (var i = 0; i < cashFlowData.months.length; i++) {
        var hIn = (cashFlowData.money_in[i] / maxTotal) * 100;
        var hOut = (cashFlowData.money_out[i] / maxTotal) * 100;
        html += '<div class="chart-month"><div class="bar-group"><div class="bar in" style="height:' + hIn + '%" title="In: ' + formatCurrency(cashFlowData.money_in[i]) + '"></div><div class="bar out" style="height:' + hOut + '%" title="Out: ' + formatCurrency(cashFlowData.money_out[i]) + '"></div></div><span class="month-label">' + esc(cashFlowData.months[i]) + '</span></div>';
    }
    html += '</div><div class="chart-legend"><div class="legend-item"><div class="legend-color in"></div><span>Money in</span></div><div class="legend-item"><div class="legend-color out"></div><span>Money out</span></div></div>';
    container.innerHTML = html;
}

// --- Invoices ---
async function fetchInvoices() {
    try {
        var response = await fetch('/api/invoices');
        if (!response.ok) throw new Error('Failed');
        allInvoices = await response.json();
        renderInvoices(allInvoices);
    } catch (error) {
        var tbody = document.getElementById('invoices-table-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="loading">Failed to load invoices.</td></tr>';
    }
}
window.fetchInvoices = fetchInvoices;

function renderInvoices(invoices) {
    var tbody = document.getElementById('invoices-table-body');
    var countSpan = document.getElementById('invoice-count');
    if (countSpan) countSpan.textContent = invoices.length + ' item' + (invoices.length !== 1 ? 's' : '');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (invoices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-secondary);">No invoices found.</td></tr>';
        return;
    }
    invoices.forEach(function(inv) {
        var statusClass = (inv.status || '').toLowerCase().replace(/\s+/g, '-');
        var opens = inv.open_count || 0;
        var openBadge = opens > 0 ? '<span style="color:var(--primary-color);font-weight:600;">' + opens + '</span>' : '<span style="color:var(--text-secondary);">0</span>';
        // An overdue invoice is the one thing a user must not miss in this list.
        var dueCell = esc(inv.due_date);
        if (inv.is_overdue) {
            dueCell = '<span style="color:var(--danger-color);font-weight:600;" title="' + inv.days_overdue +
                      ' days overdue">' + esc(inv.due_date) + ' &#9888;</span>';
        }
        tbody.insertAdjacentHTML('beforeend', '<tr><td><a href="#" class="link" onclick="event.preventDefault();viewInvoice(\'' + esc(inv.number) + '\')">' + esc(inv.number) + '</a></td><td>' + esc(inv.ref || '-') + '</td><td>' + esc(inv.to) + '</td><td>' + esc(inv.date) + '</td><td>' + dueCell + '</td><td class="text-right">' + formatCurrency(inv.paid, inv.currency) + '</td><td class="text-right">' + formatCurrency(inv.due, inv.currency) + '</td><td><span class="status-pill status-' + statusClass + '">' + esc(inv.status) + '</span></td><td class="text-right">' + openBadge + '</td><td>' + esc(inv.sent || '-') + '</td></tr>');
    });
}

function filterInvoices(status, btn) {
    currentFilter = status;
    document.querySelectorAll('.invoices-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var filtered;
    if (status === 'all') filtered = allInvoices;
    // "overdue" is derived from the due date, not stored as a status.
    else if (status === 'overdue') filtered = allInvoices.filter(function(inv) { return inv.is_overdue; });
    else filtered = allInvoices.filter(function(inv) { return (inv.status || '').toLowerCase() === status; });
    renderInvoices(filtered);
}
window.filterInvoices = filterInvoices;

function searchInvoices() {
    var q = (document.getElementById('invoice-search').value || '').toLowerCase();
    var filtered = allInvoices.filter(function(inv) {
        return (inv.number || '').toLowerCase().indexOf(q) >= 0 || (inv.to || '').toLowerCase().indexOf(q) >= 0 || (inv.ref || '').toLowerCase().indexOf(q) >= 0 || (inv.email || '').toLowerCase().indexOf(q) >= 0;
    });
    renderInvoices(filtered);
}
window.searchInvoices = searchInvoices;

var searchDebounce = null;
function handleGlobalSearch(e) {
    clearTimeout(searchDebounce);
    var q = e.target.value.trim().toLowerCase();
    if (e.key === 'Enter') {
        if (!q) return;
        runGlobalSearch(q);
        return;
    }
    searchDebounce = setTimeout(function() {
        if (q.length >= 2) runGlobalSearch(q);
        else hideSearchResults();
    }, 300);
}

async function runGlobalSearch(q) {
    // Server-side: the browser only ever held the lists you had already
    // opened, so employees were unfindable until you visited their tab and
    // quotes were never searched at all.
    try {
        var res = await fetch('/api/search?q=' + encodeURIComponent(q), {
            credentials: 'same-origin',
        });
        if (!res.ok) { hideSearchResults(); return; }
        var data = await res.json();
        showSearchResults(data.results || [], q);
    } catch (e) {
        hideSearchResults();
    }
}

// Where each kind of result goes when clicked. Landing on the list and making
// somebody scroll for what they just found is not finding it.
function openSearchResult(type, number, id) {
    hideSearchResults();
    var input = document.getElementById('global-search');
    if (input) input.value = '';

    if (type === 'invoice' && number) { showView('invoices-view'); viewInvoice(number); return; }
    if (type === 'quote' && number) { showView('quotes-view'); viewQuote(number); return; }
    if (type === 'employee' && id) { openEmployee(id); return; }
    if (type === 'recurring') { showView('recurring-view'); return; }
    if (type === 'payslip') { showView('payroll-view'); return; }
    if (type === 'contact') { if (id) { openCustomer(id); } else { showView('contacts-view'); } return; }
    showView('dashboard-view');
}
window.openSearchResult = openSearchResult;

function showSearchResults(results, q) {
    hideSearchResults();
    var bar = document.querySelector('.search-bar');
    if (!bar) return;
    var dropdown = document.createElement('div');
    dropdown.id = 'search-results-dropdown';
    dropdown.style.cssText = 'position:absolute;top:100%;left:0;right:0;margin-top:4px;background:rgba(17,24,39,0.98);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.12);border-radius:12px;max-height:400px;overflow-y:auto;z-index:9999;box-shadow:0 8px 32px rgba(0,0,0,0.5);';
    if (results.length === 0) {
        dropdown.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-secondary);font-size:0.85rem;">No results for "' + esc(q) + '"</div>';
    } else {
        var types = { invoice: 'Invoices', quote: 'Quotes', recurring: 'Recurring',
                      contact: 'Contacts', employee: 'Employees', payslip: 'Payroll' };
        var icons = { invoice: '&#128196;', quote: '&#128220;', recurring: '&#128257;',
                      contact: '&#128100;', employee: '&#128101;', payslip: '&#128176;' };
        var grouped = {};
        results.forEach(function(r) {
            if (!grouped[r.type]) grouped[r.type] = [];
            grouped[r.type].push(r);
        });
        var html = '';
        for (var type in grouped) {
            html += '<div style="padding:8px 14px 4px;font-size:0.72rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">' + (types[type] || type) + '</div>';
            grouped[type].slice(0, 5).forEach(function(r) {
                var highlight = esc(r.label).replace(new RegExp('(' + escapeRegex(esc(q)) + ')', 'gi'), '<strong style="color:var(--primary-color);">$1</strong>');
                html += '<div class="search-result-item" onclick="openSearchResult(\'' + r.type + '\', \'' + encodeURIComponent(r.number || '') + '\', ' + (r.id || 0) + ')" style="padding:8px 14px;cursor:pointer;display:flex;align-items:center;gap:10px;transition:background 0.15s;">' +
                    '<span style="font-size:1rem;">' + (icons[r.type] || '&#128269;') + '</span>' +
                    '<div style="min-width:0;">' +
                        '<div style="font-size:0.85rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + highlight + '</div>' +
                        (r.sub ? '<div style="font-size:0.75rem;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(r.sub) + '</div>' : '') +
                    '</div>' +
                    (r.status ? '<span style="margin-left:auto;font-size:0.7rem;padding:2px 6px;border-radius:8px;background:rgba(255,255,255,0.08);color:var(--text-secondary);">' + esc(r.status) + '</span>' : '') +
                '</div>';
            });
        }
        dropdown.innerHTML = html;
    }
    bar.style.position = 'relative';
    bar.appendChild(dropdown);
    var items = dropdown.querySelectorAll('.search-result-item');
    items.forEach(function(item) {
        item.addEventListener('mouseenter', function() { item.style.background = 'rgba(255,255,255,0.08)'; });
        item.addEventListener('mouseleave', function() { item.style.background = 'transparent'; });
    });
}

function hideSearchResults() {
    var existing = document.getElementById('search-results-dropdown');
    if (existing) existing.remove();
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.search-bar')) hideSearchResults();
});
window.handleGlobalSearch = handleGlobalSearch;

async function fetchNextInvoiceNumber() {
    try {
        var response = await fetch('/api/next-invoice-number');
        if (response.ok) {
            var data = await response.json();
            var numInput = document.getElementById('inv-number');
            if (numInput && !numInput.value) numInput.value = data.next_number;
            // The due date follows the tenant's own payment terms rather than
            // a fixed fortnight.
            var dueEl = document.getElementById('inv-due-date');
            var issueEl = document.getElementById('inv-issue-date');
            if (dueEl && issueEl && issueEl.value && data.payment_terms_days !== undefined) {
                var base = new Date(issueEl.value + 'T00:00:00');
                base.setDate(base.getDate() + (parseInt(data.payment_terms_days, 10) || 14));
                dueEl.value = localDate(base);
            }
        }
    } catch (e) { console.error(e); }
}
window.fetchNextInvoiceNumber = fetchNextInvoiceNumber;

// --- Logo ---
function loadSavedLogo() {
    var savedLogo = localStorage.getItem('company_logo');
    if (savedLogo) {
        var el = document.getElementById('logo-img-create');
        if (el) { el.src = savedLogo; el.style.display = 'block'; }
        var txt = document.getElementById('logo-upload-text');
        if (txt) txt.style.display = 'none';
    }
    fetch('/api/client/logo').then(function(r) { return r.json(); }).then(function(data) {
        if (data.logo_url) {
            localStorage.setItem('company_logo', data.logo_url);
            var el = document.getElementById('logo-img-create');
            if (el) { el.src = data.logo_url; el.style.display = 'block'; }
            var txt = document.getElementById('logo-upload-text');
            if (txt) txt.style.display = 'none';
        }
    }).catch(function() {});
}

function setupLogoUpload() {
    var logoUpload = document.getElementById('logo-upload');
    if (logoUpload) {
        logoUpload.addEventListener('change', function(e) {
            var file = e.target.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(event) {
                    var b64 = event.target.result;
                    localStorage.setItem('company_logo', b64);
                    fetch('/api/client/logo', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ logo_url: b64 })
                    }).catch(function() {});
                    var img = document.getElementById('logo-img-create');
                    if (img) { img.src = b64; img.style.display = 'block'; }
                    var txt = document.getElementById('logo-upload-text');
                    if (txt) txt.style.display = 'none';
                };
                reader.readAsDataURL(file);
            }
        });
    }
}

var _viewOutstanding = 0;

// Payment history + overdue banner, injected above the invoice actions so the
// state of an invoice is obvious without opening a report.
function renderInvoicePayments(inv) {
    var host = document.getElementById('view-inv-payments');
    if (!host) return;
    var payments = inv.payments || [];
    var sym = getCurrencySymbol();
    var html = '';
    if (inv.is_overdue) {
        html += '<div style="padding:10px 14px;border-radius:8px;background:rgba(239,68,68,0.12);' +
                'border:1px solid rgba(239,68,68,0.35);color:var(--danger-color);font-size:0.85rem;' +
                'font-weight:600;margin-bottom:10px;">Overdue by ' + inv.days_overdue +
                ' day' + (inv.days_overdue === 1 ? '' : 's') + ' — ' + sym + (inv.due || 0).toFixed(2) + ' outstanding</div>';
    }
    if (payments.length) {
        html += '<div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;' +
                'color:var(--text-secondary);margin-bottom:6px;">Payments received</div>';
        html += '<table style="width:100%;font-size:0.85rem;border-collapse:collapse;">';
        payments.forEach(function(p) {
            html += '<tr style="border-bottom:1px solid var(--border-color);">' +
                    '<td style="padding:6px 0;">' + esc(p.paid_on || '') + '</td>' +
                    '<td style="padding:6px 0;color:var(--text-secondary);">' + esc(p.method || '') +
                    (p.reference ? ' &middot; ' + esc(p.reference) : '') + '</td>' +
                    '<td style="padding:6px 0;text-align:right;font-weight:600;">' + sym + (p.amount || 0).toFixed(2) + '</td>' +
                    '<td style="padding:6px 0;text-align:right;width:32px;">' +
                    '<button type="button" title="Reverse payment" style="background:none;border:none;cursor:pointer;color:var(--danger-color);" ' +
                    'onclick="reversePayment(\'' + esc(inv.number) + '\',' + p.id + ')">&times;</button></td></tr>';
        });
        html += '<tr><td colspan="2" style="padding:6px 0;font-weight:700;">Outstanding</td>' +
                '<td colspan="2" style="padding:6px 0;text-align:right;font-weight:700;">' + sym + (inv.due || 0).toFixed(2) + '</td></tr>';
        html += '</table>';
    }
    host.innerHTML = html;
    host.style.display = html ? 'block' : 'none';
}
window.renderInvoicePayments = renderInvoicePayments;

// --- View Invoice ---
async function viewInvoice(number) {
    try {
        var response = await fetch('/api/invoices/' + encodeURIComponent(number));
        if (!response.ok) throw new Error('Failed');
        var inv = await response.json();
        _viewCurrency = inv.currency || '';
        _viewOutstanding = inv.due || 0;
        renderInvoicePayments(inv);
        document.getElementById('view-inv-title').textContent = 'Invoice ' + inv.number;
        document.getElementById('view-inv-number-val').textContent = inv.number;
    document.getElementById('view-inv-ref').textContent = inv.reference || '-';
    if(document.getElementById('view-inv-ref-container')) document.getElementById('view-inv-ref-container').style.display = inv.reference ? 'block' : 'none';

        document.getElementById('view-inv-status').textContent = inv.status;
        document.getElementById('view-inv-status').className = 'status-pill status-' + (inv.status || '').toLowerCase().replace(/\s+/g, '-');
        document.getElementById('view-inv-contact').textContent = inv.to;
        var emailD = document.getElementById('view-inv-email-display');
        if (emailD) emailD.textContent = inv.email || 'No email';
        var phoneD = document.getElementById('view-inv-phone-display');
        if (phoneD) phoneD.textContent = inv.phone_number || 'No phone';
        document.getElementById('view-inv-issue-date').textContent = inv.date;
        document.getElementById('view-inv-due-date').textContent = inv.due_date;
        var dueVal = document.getElementById('view-inv-due-val');
        if (dueVal) dueVal.textContent = (inv.due || 0).toFixed(2);
        var dueCurr = document.getElementById('view-inv-due-currency');
        if (dueCurr) dueCurr.textContent = getCurrencySymbol();

        var openTracking = document.getElementById('view-inv-open-tracking');
        var openCountEl = document.getElementById('view-inv-open-count');
        var lastOpenedEl = document.getElementById('view-inv-last-opened');
        if (openTracking && inv.open_count !== undefined) {
            if (inv.open_count > 0) {
                openTracking.style.display = 'flex';
                if (openCountEl) openCountEl.textContent = inv.open_count;
                if (lastOpenedEl) lastOpenedEl.textContent = inv.last_opened || 'Never';
            } else {
                openTracking.style.display = 'none';
            }
        }

        var savedLogo = localStorage.getItem('company_logo');
        var logoV = document.getElementById('logo-preview-view');
        if (savedLogo && logoV) { logoV.src = savedLogo; logoV.style.display = 'block'; }
        else if (logoV) {
            fetch('/api/client/logo').then(function(r) { return r.json(); }).then(function(data) {
                if (data.logo_url && logoV) { logoV.src = data.logo_url; logoV.style.display = 'block'; localStorage.setItem('company_logo', data.logo_url); }
                else if (logoV) logoV.style.display = 'none';
            }).catch(function() { logoV.style.display = 'none'; });
        }

        // Company details
        var companyDetails = document.getElementById('view-inv-company-details');
        if (inv.company && inv.company.name) {
            companyDetails.style.display = 'block';
            document.getElementById('view-inv-company-name').textContent = inv.company.name;
            document.getElementById('view-inv-company-address').textContent = inv.company.address || '';
            document.getElementById('view-inv-company-email').textContent = inv.company.email ? 'Email: ' + inv.company.email : '';
            document.getElementById('view-inv-company-phone').textContent = inv.company.phone_number ? 'Phone: ' + inv.company.phone_number : '';
            document.getElementById('view-inv-company-abn').textContent = inv.company.abn ? 'ABN: ' + inv.company.abn : '';
        } else {
            companyDetails.style.display = 'none';
        }

        var tbody = document.getElementById('view-line-items-body');
        tbody.innerHTML = '';
        var subtotal = 0, vat = 0;
        if (inv.line_items) {
            var taxType = inv.tax_type || 'exclusive';
            inv.line_items.forEach(function(item) {
                var t = lineTotals(item.qty, item.price, item.disc, item.tax_rate, taxType);
                subtotal += t.net; vat += t.vat;
                tbody.insertAdjacentHTML('beforeend', '<tr><td style="padding:12px 16px;word-wrap:break-word;overflow-wrap:break-word;max-width:200px;vertical-align:top;">' + esc(item.name || '') + '</td><td style="padding:12px 16px;word-wrap:break-word;overflow-wrap:break-word;max-width:280px;vertical-align:top;">' + esc(item.description) + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + item.qty + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + item.price.toFixed(2) + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + (item.disc || 0) + '%</td><td style="padding:12px 16px;vertical-align:top;">' + esc(item.tax_rate || 'No Tax') + '</td><td style="padding:12px 16px;text-align:right;font-weight:600;vertical-align:top;">' + t.net.toFixed(2) + '</td></tr>');
            });
        }
        var bankView = document.getElementById('view-inv-bank-details');
        if (inv.bank_details) {
            document.getElementById('view-inv-bank-content').textContent = inv.bank_details;
            if (bankView) bankView.style.display = 'block';
        } else {
            if (bankView) bankView.style.display = 'none';
        }
        document.getElementById('view-summary-subtotal').textContent = subtotal.toFixed(2);
        document.getElementById('view-summary-vat').textContent = vat.toFixed(2);
        document.getElementById('view-summary-total').textContent = (subtotal + vat).toFixed(2) + ' ' + (_viewCurrency || _appCurrency);

        document.getElementById('view-invoice-delete-btn').dataset.number = inv.number;
        document.getElementById('view-invoice-paid-btn').dataset.number = inv.number;
        var payBtn = document.getElementById('view-invoice-payment-btn');
        if (payBtn) {
            payBtn.dataset.number = inv.number;
            payBtn.disabled = (inv.due || 0) <= 0;
            payBtn.style.opacity = payBtn.disabled ? '0.45' : '1';
        }

        var backBtn = document.getElementById('preview-back-btn');
        if (backBtn) backBtn.style.display = 'none';
        document.querySelectorAll('.invoice-action-btn').forEach(function(btn) { btn.style.display = 'inline-block'; });
        showView('view-invoice-view');
    } catch (e) {
        showToast('Failed to load invoice', 'error');
    }
}
window.viewInvoice = viewInvoice;

// --- Generate PDF ---

// --- INVOICE BUILDER LOGIC ---
var defaultInvoiceLayout = [
    { id: 'header', visible: true, label: 'Header (Logo & Title)' },
    { id: 'company_info', visible: true, label: 'Company Info' },
    { id: 'customer_info', visible: true, label: 'Customer Info' },
    { id: 'invoice_details', visible: true, label: 'Invoice Details' },
    { id: 'line_items', visible: true, label: 'Line Items' },
    { id: 'totals', visible: true, label: 'Totals' },
    { id: 'bank_details', visible: true, label: 'Bank Details' },
    { id: 'terms_conditions', visible: true, label: 'Terms & Conditions' },
    { id: 'signature', visible: true, label: 'Signature' },
    { id: 'payment_stub', visible: true, label: 'Payment Stub' }
];

window._invoiceLayout = JSON.parse(JSON.stringify(defaultInvoiceLayout));

function initTemplateBuilder(layoutData) {
    if (layoutData) {
        try {
            var parsed = JSON.parse(layoutData);
            if (Array.isArray(parsed) && parsed.length > 0) {
                window._invoiceLayout = parsed;
            } else {
                window._invoiceLayout = JSON.parse(JSON.stringify(defaultInvoiceLayout));
            }
        } catch(e) {
            window._invoiceLayout = JSON.parse(JSON.stringify(defaultInvoiceLayout));
        }
    } else {
        window._invoiceLayout = JSON.parse(JSON.stringify(defaultInvoiceLayout));
    }
    if (!Array.isArray(window._invoiceLayout)) {
        window._invoiceLayout = JSON.parse(JSON.stringify(defaultInvoiceLayout));
    }
    renderTemplateBuilder();
}

function renderTemplateBuilder() {
    var container = document.getElementById('invoice-builder-container');
    if (!container) return;
    container.innerHTML = '';
    
    window._invoiceLayout.forEach(function(block, index) {
        var el = document.createElement('div');
        el.className = 'builder-block';
        el.style.display = 'flex';
        el.style.alignItems = 'center';
        el.style.justifyContent = 'space-between';
        el.style.padding = '12px 16px';
        el.style.background = 'rgba(255,255,255,0.05)';
        el.style.border = '1px solid var(--border-color)';
        el.style.borderRadius = 'var(--radius-md)';
        el.style.cursor = 'grab';
        el.draggable = true;
        el.dataset.id = block.id;
        el.dataset.index = index;
        
        var leftDiv = document.createElement('div');
        leftDiv.style.display = 'flex';
        leftDiv.style.alignItems = 'center';
        leftDiv.style.gap = '12px';
        
        var dragIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:#cbd5e1;"><circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/></svg>';
        leftDiv.innerHTML = dragIcon + '<span style="font-weight:500;color:var(--text-primary);' + (!block.visible ? 'text-decoration:line-through;opacity:0.5;' : '') + '">' + block.label + '</span>';
        
        var rightDiv = document.createElement('div');
        var eyeIcon = block.visible ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>' : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>';
        
        var toggleBtn = document.createElement('button');
        toggleBtn.className = 'btn-icon';
        toggleBtn.style.color = block.visible ? 'var(--primary)' : 'var(--text-secondary)';
        toggleBtn.innerHTML = eyeIcon;
        toggleBtn.onclick = function() {
            block.visible = !block.visible;
            renderTemplateBuilder();
        };
        rightDiv.appendChild(toggleBtn);
        
        el.appendChild(leftDiv);
        el.appendChild(rightDiv);
        
        // Drag events
        el.addEventListener('dragstart', function(e) {
            e.dataTransfer.setData('text/plain', index);
            setTimeout(function() { el.style.opacity = '0.4'; }, 0);
        });
        el.addEventListener('dragend', function(e) {
            el.style.opacity = '1';
        });
        el.addEventListener('dragover', function(e) {
            e.preventDefault();
            el.style.border = '2px dashed var(--primary)';
        });
        el.addEventListener('dragleave', function(e) {
            el.style.border = '1px solid var(--border-color)';
        });
        el.addEventListener('drop', function(e) {
            e.preventDefault();
            el.style.border = '1px solid var(--border-color)';
            var fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
            var toIndex = index;
            if (fromIndex === toIndex) return;
            var moved = window._invoiceLayout.splice(fromIndex, 1)[0];
            window._invoiceLayout.splice(toIndex, 0, moved);
            renderTemplateBuilder();
        });
        
        container.appendChild(el);
    });
}
window.initTemplateBuilder = initTemplateBuilder;

function saveTemplateLayout() {
    var layoutStr = JSON.stringify(window._invoiceLayout);
    fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ invoice_layout: layoutStr })
    }).then(r => r.json()).then(data => {
        showToast('Template layout saved!', 'success');
    }).catch(err => showToast('Failed to save layout', 'error'));
}
window.saveTemplateLayout = saveTemplateLayout;

function openAITemplateModal() {
    document.getElementById('ai-template-modal').style.display = 'flex';
}
window.openAITemplateModal = openAITemplateModal;

function closeAITemplateModal() {
    document.getElementById('ai-template-modal').style.display = 'none';
}
window.closeAITemplateModal = closeAITemplateModal;

function generateTemplateWithAI() {
    var prompt = document.getElementById('ai-template-prompt').value.toLowerCase();
    if (!prompt) return;
    var btn = document.getElementById('ai-template-btn');
    btn.innerHTML = 'Generating...';
    btn.disabled = true;
    
    // Simple local simulated AI logic
    setTimeout(function() {
        // Reset visibility
        window._invoiceLayout.forEach(b => b.visible = true);
        
        if (prompt.includes('hide company') || prompt.includes('no company')) {
            var b = window._invoiceLayout.find(x => x.id === 'company_info');
            if (b) b.visible = false;
        }
        if (prompt.includes('bank details at the top') || prompt.includes('bank details top')) {
            var idx = window._invoiceLayout.findIndex(x => x.id === 'bank_details');
            if (idx > -1) {
                var b = window._invoiceLayout.splice(idx, 1)[0];
                window._invoiceLayout.splice(0, 0, b);
            }
        }
        if (prompt.includes('signature at the bottom') || prompt.includes('signature bottom')) {
            var idx = window._invoiceLayout.findIndex(x => x.id === 'signature');
            if (idx > -1) {
                var b = window._invoiceLayout.splice(idx, 1)[0];
                window._invoiceLayout.push(b);
            }
        }
        if (prompt.includes('hide stub') || prompt.includes('no stub')) {
            var b = window._invoiceLayout.find(x => x.id === 'payment_stub');
            if (b) b.visible = false;
        }
        
        renderTemplateBuilder();
        btn.innerHTML = 'Generate';
        btn.disabled = false;
        closeAITemplateModal();
        showToast('AI layout generated successfully!', 'success');
    }, 1500);
}
window.generateTemplateWithAI = generateTemplateWithAI;

// Open a generated PDF in a new tab.
//
// This used to write an <iframe src="data:application/pdf;base64,..."> into a
// blank window. Chrome has refused to render PDFs from data: URLs for years,
// so the tab opened, was titled, and stayed blank. A blob URL goes straight to
// the browser's own PDF viewer.
function openPdfPreview(doc, title) {
    var url;
    try {
        url = URL.createObjectURL(doc.output('blob'));
    } catch (e) {
        showToast('Could not build the preview: ' + e.message, 'error');
        return;
    }
    var win = window.open(url, '_blank');
    if (!win) {
        URL.revokeObjectURL(url);
        showToast('Popup blocked - allow popups for this site to preview', 'error');
        return;
    }
    try { win.document.title = title || 'Preview'; } catch (e) { /* cross-origin once the PDF loads */ }
    // Revoked on a delay: doing it immediately pulls the file out from under
    // the tab before the viewer has finished reading it.
    setTimeout(function () { URL.revokeObjectURL(url); }, 120000);
}
window.openPdfPreview = openPdfPreview;

function previewInvoiceTemplate() {
    // Sample data, so the tenant can see their template before issuing anything.
    try {
        openPdfPreview(generateInvoicePDF(true), 'Template preview');
    } catch (e) {
        console.error('previewInvoiceTemplate error:', e);
        showToast('Preview failed: ' + e.message, 'error');
    }
}
window.previewInvoiceTemplate = previewInvoiceTemplate;

// --- DYNAMIC GENERATE INVOICE PDF ---
// Currency sanitizer shared by the invoice and payslip PDFs. jsPDF's built-in
// fonts are Latin-1 only, so symbols outside that range are transliterated
// rather than rendered as garbage.
function pdfSym(sym) {
    var map = {
        '₹': 'Rs.', '₩': 'W', '₪': 'ILS',
        '₦': 'N',   '₫': 'D', '₭': 'K',
        '₮': 'T',   '₱': 'P', '₲': 'G',
        '₴': 'grn', '₵': 'GH','₸': 'T',
        '₺': 'TL',  '₼': 'M', '₽': 'R'
    };
    return map[sym] !== undefined ? map[sym] : sym;
}
window.pdfSym = pdfSym;

// A quote and an invoice are the same document with different words on it, so
// they share one generator. `p`/`s`/`body` are the element id prefixes each
// view uses; a quote has no payment advice slip to tear off.
// The heading for the tax line on a PDF. Taken from the labels actually used
// on the document, so it follows whatever the tenant named their taxes; falls
// back to a neutral word when the lines disagree.
function documentTaxLabel(cfg) {
    var names = [];
    document.querySelectorAll('#' + cfg.body + ' tr').forEach(function (tr) {
        var cells = tr.querySelectorAll('td');
        if (cells.length < 6) return;
        var label = (cells[5].textContent || '').trim();
        // "18% GST" -> "GST"; a label with no percentage is a no-tax entry.
        var m = label.match(/^\s*[\d.]+%\s*(.+)$/);
        if (m && names.indexOf(m[1]) === -1) names.push(m[1]);
    });
    return names.length === 1 ? names[0] : 'Tax';
}

var PDF_DOC_TYPES = {
    invoice: {
        p: 'view-inv-', s: 'view-summary-', body: 'view-line-items-body',
        heading: 'TAX INVOICE', dateLabel: 'Invoice Date',
        numberLabel: 'Invoice Number', totalLabel: 'Amount Due',
        dateOutLabel: 'Due Date', bank: true, paymentAdvice: true,
    },
    quote: {
        p: 'view-quote-', s: 'view-quote-summary-', body: 'view-quote-line-items-body',
        heading: 'QUOTE', dateLabel: 'Quote Date',
        numberLabel: 'Quote Number', totalLabel: 'Quote Total',
        // The quote's expiry occupies the slot an invoice uses for its due date.
        dateOutLabel: 'Valid Until', bank: false, paymentAdvice: false,
    },
};

function generateInvoicePDF(isDummy, kind) {
    var cfg = PDF_DOC_TYPES[kind] || PDF_DOC_TYPES.invoice;
    var _jsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    if (!_jsPDF) { throw new Error('jsPDF is not loaded'); }
    var doc = new _jsPDF('p', 'pt', 'a4');
    var w = doc.internal.pageSize.width;   // 595.28
    var h = doc.internal.pageSize.height;  // 841.89
    var ml = 45, mr = w - 45;
    var y = 0;
    var pageBottom = h - 80;
    var pageNum = 1;


    // ── Helpers ──────────────────────────────────────────────────
    function lh(x1, x2, yy, w2) { doc.setLineWidth(w2||0.5); doc.line(x1, yy, x2, yy); }
    function breakLong(txt, max) {
        if (!txt) return '';
        return txt.split(' ').map(function(w2) {
            return w2.length > max ? w2.match(new RegExp('.{1,'+max+'}','g')).join(' ') : w2;
        }).join(' ');
    }

    // Track whether we are inside the line-items table
    var _inTable = false;

    // Check _invoiceLayout visibility for a section (defaults true if not found)
    function isVisible(blockId) {
        if (!window._invoiceLayout || !Array.isArray(window._invoiceLayout)) return true;
        var block = window._invoiceLayout.find(function(b) { return b.id === blockId; });
        return block ? block.visible !== false : true;
    }

    function drawTableHeader() {
        doc.setFontSize(8.5); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
        lh(ml, mr, y, 0.8); y += 8;
        doc.text('Description',            col.desc,  y + 10);
        doc.text('Quantity',               col.qty,   y + 10, { align:'right' });
        doc.text('Unit Price',             col.price, y + 10, { align:'right' });
        doc.text('Amount ' + currLabel,    col.amt,   y + 10, { align:'right' });
        y += 14;
        lh(ml, mr, y, 0.8); y += 6;
    }

    function checkPageBreak(need) {
        if (y + need > pageBottom) {
            drawFooter();
            doc.addPage();
            doc.setFillColor(255,255,255); doc.rect(0,0,w,h,'F');
            pageNum++;
            y = 45;
            // If we are mid-table, reprint the column headers on the new page
            if (_inTable) {
                drawTableHeader();
            }
        }
    }
    function drawFooter() {
        doc.setFontSize(8); doc.setFont('helvetica','normal');
        doc.setTextColor(150,150,150);
        doc.text('Page ' + pageNum, w/2, h - 25, { align:'center' });
    }

    // ── White page ───────────────────────────────────────────────
    doc.setFillColor(255,255,255); doc.rect(0,0,w,h,'F');

    // ── Data Extraction ──────────────────────────────────────────
    var contact    = isDummy ? 'Mr Frederick William Harris\n54 Cheshire Field Close\nWest Heath, Birmingham, B31 3TR' : (document.getElementById(cfg.p + 'contact') ? document.getElementById(cfg.p + 'contact').textContent : '');
    var custEmail  = isDummy ? 'demo@example.com' : (document.getElementById(cfg.p + 'email-display') ? document.getElementById(cfg.p + 'email-display').textContent : '');
    var custPhone  = isDummy ? '+44 121 000 0000' : (document.getElementById(cfg.p + 'phone-display') ? document.getElementById(cfg.p + 'phone-display').textContent : '');
    var issueDate  = isDummy ? '26 May 2026' : (document.getElementById(cfg.p + 'issue-date') ? document.getElementById(cfg.p + 'issue-date').textContent : '');
    var dueDate    = isDummy ? '2 Jun 2026'  : (document.getElementById(cfg.p + 'due-date') ? document.getElementById(cfg.p + 'due-date').textContent : '');
    var numberText = isDummy ? 'INV-0273' : (document.getElementById(cfg.p + 'number-val') ? document.getElementById(cfg.p + 'number-val').textContent : '');
    var bankContent= isDummy ? 'Account No: 00096345, sort code: 77-07-08' : (document.getElementById(cfg.p + 'bank-content') ? document.getElementById(cfg.p + 'bank-content').textContent : '');
    var refText    = isDummy ? '' : (document.getElementById(cfg.p + 'ref') ? document.getElementById(cfg.p + 'ref').textContent : '');
    if (refText === '-') refText = '';
    var rawSym     = isDummy ? '\u00A3' : (document.getElementById(cfg.p + 'due-currency') ? document.getElementById(cfg.p + 'due-currency').textContent : '\u00A3');
    var cs         = pdfSym(rawSym);
    var subtotal   = isDummy ? '168.00' : (document.getElementById(cfg.s + 'subtotal') ? document.getElementById(cfg.s + 'subtotal').textContent : '0.00');
    var vatAmt     = isDummy ? '0.00' : (document.getElementById(cfg.s + 'vat') ? document.getElementById(cfg.s + 'vat').textContent : '0.00');
    var total      = isDummy ? '168.00' : (document.getElementById(cfg.s + 'total') ? document.getElementById(cfg.s + 'total').textContent : '0.00');
    var company    = isDummy ? 'Be care LTD T/S British Elderly Care' : (document.getElementById(cfg.p + 'company-name') ? document.getElementById(cfg.p + 'company-name').textContent : '');
    var compAddr   = isDummy ? '53 Newbridge Cres\nWolverhampton, West Midlands\nWV6 6LH, UNITED KINGDOM' : (document.getElementById(cfg.p + 'company-address') ? document.getElementById(cfg.p + 'company-address').textContent : '');
    var compEmail  = isDummy ? '' : (document.getElementById(cfg.p + 'company-email') ? document.getElementById(cfg.p + 'company-email').textContent.replace('Email: ','') : '');
    var compPhone  = isDummy ? 'Tel: 01902521476' : (document.getElementById(cfg.p + 'company-phone') ? document.getElementById(cfg.p + 'company-phone').textContent.replace('Phone: ','') : '');
    var compAbn    = isDummy ? '' : (document.getElementById(cfg.p + 'company-abn') ? document.getElementById(cfg.p + 'company-abn').textContent.replace('ABN: ','') : '');
    var savedLogo      = localStorage.getItem('company_logo') || '';
    var savedSignature = localStorage.getItem('company_signature') || '';
    var savedTerms     = localStorage.getItem('company_terms') || '';
    var currencyCode   = rawSym === cs ? '' : rawSym; // e.g. for "INR" label in Amount column header

    // Determine column currency label for table header (e.g. "Amount GBP")
    var _viewCur = typeof _viewCurrency !== 'undefined' ? _viewCurrency : (typeof _appCurrency !== 'undefined' ? _appCurrency : '');
    var currLabel = _viewCur || 'GBP';

    // ════════════════════════════════════════════════════════
    //  HEADER — three columns
    //  Left: TAX INVOICE + customer address
    //  Centre: Invoice Date / Invoice Number
    //  Right: Logo + Company details
    // ════════════════════════════════════════════════════════
    y = 45;

    // ── Right column: Logo ──
    var logoX = mr - 65, logoY = y - 5, logoW = 65, logoH = 65;
    if (savedLogo) {
        try { doc.addImage(savedLogo, undefined, logoX, logoY, logoW, logoH); } catch(e) {}
    } else {
        // placeholder box
        doc.setDrawColor(100,150,200); doc.setLineWidth(1);
        doc.rect(logoX, logoY, logoW, logoH);
        doc.setFontSize(7); doc.setFont('helvetica','normal'); doc.setTextColor(120,150,180);
        doc.text('LOGO', logoX + logoW/2, logoY + logoH/2 + 3, { align:'center' });
    }

    // ── Right column: Company details (below logo) ──
    var compX = logoX;
    var compRightY = logoY + logoH + 8;
    var compLines = [];
    if (company) compLines.push(company);
    if (compAddr) compAddr.split('\n').forEach(function(l) { if(l.trim()) compLines.push(l.trim()); });
    if (compPhone) compLines.push(compPhone.startsWith('Tel') ? compPhone : 'Tel: ' + compPhone);
    if (compEmail) compLines.push(compEmail);
    if (compAbn)   compLines.push('ABN: ' + compAbn);

    doc.setFontSize(7.5); doc.setFont('helvetica','normal'); doc.setTextColor(30,30,30);
    compLines.forEach(function(line) {
        // wrap long lines
        var wrapped = doc.splitTextToSize(line, logoW + 10);
        wrapped.forEach(function(wl) {
            doc.text(wl, mr, compRightY, { align:'right' });
            compRightY += 10;
        });
    });

    // ── Left column: TAX INVOICE heading ──
    doc.setFontSize(26); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
    doc.text(cfg.heading, ml, y + 18);

    // ── Centre column: Invoice meta ──
    var centreX = w / 2 - 40;
    var metaY = y;
    doc.setFontSize(8); doc.setFont('helvetica','normal'); doc.setTextColor(80,80,80);
    doc.text(cfg.dateLabel, centreX, metaY + 8);
    doc.setFontSize(9); doc.setFont('helvetica','normal'); doc.setTextColor(0,0,0);
    doc.text(issueDate || '-', centreX, metaY + 19);
    metaY += 28;
    doc.setFontSize(8); doc.setFont('helvetica','normal'); doc.setTextColor(80,80,80);
    doc.text(cfg.numberLabel, centreX, metaY + 8);
    doc.setFontSize(9); doc.setFont('helvetica','normal'); doc.setTextColor(0,0,0);
    doc.text(numberText || '-', centreX, metaY + 19);
    if (refText) {
        metaY += 28;
        doc.setFontSize(8); doc.setTextColor(80,80,80); doc.text('Reference', centreX, metaY + 8);
        doc.setFontSize(9); doc.setTextColor(0,0,0); doc.text(refText, centreX, metaY + 19);
    }

    // ── Customer address (below heading) ──
    var custY = y + 32;
    var custLines = [];
    if (contact) {
        contact.split('\n').forEach(function(l) { if(l.trim()) custLines.push(l.trim()); });
        if (custLines.length === 1) {
            // single line — try to display as-is
        }
    }
    if (custEmail && custEmail !== 'No email') custLines.push(custEmail);
    if (custPhone && custPhone !== 'No phone') custLines.push(custPhone);

    doc.setFontSize(8.5); doc.setFont('helvetica','normal'); doc.setTextColor(30,30,30);
    custLines.forEach(function(line) {
        var wl = doc.splitTextToSize(breakLong(line, 45), centreX - ml - 10);
        wl.forEach(function(ll) {
            doc.text(ll, ml, custY);
            custY += 11;
        });
    });

    y = Math.max(custY, compRightY) + 18;

    // ════════════════════════════════════════════════════════
    //  LINE ITEMS TABLE
    // ════════════════════════════════════════════════════════
    doc.setTextColor(0,0,0); doc.setDrawColor(0,0,0);

    // Column definitions (must be before drawTableHeader is called)
    // We add col widths for border drawing
    var col = {
        desc:  ml,
        qty:   w - 230,
        price: w - 160,
        amt:   mr - 60
    };
    var cw = {
        desc: col.qty - col.desc,
        qty: col.price - col.qty,
        price: col.amt - col.price,
        amt: mr - col.amt
    };

    // Helper to draw vertical borders for the current row segment
    function drawRowBorders(startY, endY) {
        doc.setDrawColor(200, 200, 200);
        doc.setLineWidth(0.5);
        // Outer borders
        doc.line(ml, startY, ml, endY);
        doc.line(mr, startY, mr, endY);
        // Inner borders
        doc.line(col.qty, startY, col.qty, endY);
        doc.line(col.price, startY, col.price, endY);
        doc.line(col.amt, startY, col.amt, endY);
    }

    var _inTable = false;
    var _tableTopY = y;
    
    // We overwrite the table header drawer to include borders
    function drawTableHeader() {
        doc.setFontSize(8.5); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
        doc.setDrawColor(0,0,0);
        lh(ml, mr, y, 0.8); 
        var hTop = y;
        y += 8;
        doc.text('Item / Description',       col.desc + 4,  y + 10);
        doc.text('Quantity',               col.qty + cw.qty - 4,   y + 10, { align:'right' });
        doc.text('Unit Price',             col.price + cw.price - 4, y + 10, { align:'right' });
        doc.text('Amount ' + currLabel,    col.amt + cw.amt - 4,   y + 10, { align:'right' });
        y += 14;
        doc.setDrawColor(0,0,0);
        lh(ml, mr, y, 0.8);
        drawRowBorders(hTop, y);
        _tableTopY = y;
    }

    // Overwrite checkPageBreak to handle closing borders before break and opening after
    function checkPageBreak(need) {
        if (y + need > pageBottom) {
            if (_inTable) {
                // close borders at bottom of page
                drawRowBorders(_tableTopY, y);
                doc.setDrawColor(0,0,0);
                lh(ml, mr, y, 0.8);
            }
            drawFooter();
            doc.addPage();
            doc.setFillColor(255,255,255); doc.rect(0,0,w,h,'F');
            pageNum++;
            y = 45;
            if (_inTable) {
                drawTableHeader();
            }
        }
    }

    // Draw the initial table header
    drawTableHeader();

    // Rows
    var rows = [];
    if (isDummy) {
        rows = [{
            name:'Client Service', desc:'Monthly retainer for premium client services including support and maintenance.', qty:'8.00', price:'21.00', disc:'0', tax:'0', amount:'168.00'
        }];
    } else {
        document.querySelectorAll('#' + cfg.body + ' tr').forEach(function(tr) {
            var cells = tr.querySelectorAll('td');
            if (cells.length >= 7) {
                rows.push({
                    name:   cells[0].textContent.trim(),
                    desc:   cells[1].textContent.trim(),
                    qty:    cells[2].textContent.trim(),
                    price:  cells[3].textContent.trim(),
                    disc:   (cells[4].textContent||'0').replace('%','').trim(),
                    tax:    (cells[5]?cells[5].textContent:'0').replace('%','').trim(),
                    amount: cells[6].textContent.trim()
                });
            }
        });
    }

    _inTable = true;
    rows.forEach(function(row) {
        var nameLines = doc.splitTextToSize(breakLong(row.name||'-', 50), cw.desc - 8);
        var descLines = row.desc ? doc.splitTextToSize(breakLong(row.desc, 60), cw.desc - 8) : [];
        
        // We will process line by line to handle breaks mid-row
        var allLines = [];
        nameLines.forEach(function(l) { allLines.push({ text: l, isName: true }); });
        descLines.forEach(function(l) { allLines.push({ text: l, isName: false }); });
        
        if (allLines.length === 0) allLines.push({text: '-', isName: true});

        var rowStartY = y;
        var padding = 6;
        y += padding;

        var i = 0;
        var firstLineOfRow = true;
        
        while (i < allLines.length) {
            checkPageBreak(12); // Need space for at least one line
            
            // Re-record rowStartY if we just page-broke
            if (y === _tableTopY) {
                rowStartY = y;
                y += padding;
            }

            var lObj = allLines[i];
            doc.setFont('helvetica', lObj.isName ? 'bold' : 'normal');
            doc.setTextColor(lObj.isName ? 0 : 80, lObj.isName ? 0 : 80, lObj.isName ? 0 : 80);
            doc.setFontSize(8.5);
            
            doc.text(lObj.text, col.desc + 4, y + 8);
            
            // Print qty/price/amount only on the first physical line of this item on the current page
            if (firstLineOfRow) {
                doc.setFont('helvetica','normal'); doc.setTextColor(0,0,0);
                doc.text(row.qty,   col.qty + cw.qty - 4,   y + 8, { align:'right' });
                doc.text(row.price, col.price + cw.price - 4, y + 8, { align:'right' });
                doc.text(row.amount, col.amt + cw.amt - 4,  y + 8, { align:'right' });
                firstLineOfRow = false;
            }
            
            y += 11;
            i++;
            
            // If we are at the end of the page and still have lines, close the borders
            if (y + 12 > pageBottom && i < allLines.length) {
                y += padding;
                drawRowBorders(rowStartY, y);
                doc.setDrawColor(0,0,0); lh(ml, mr, y, 0.8);
                // The next loop iteration will trigger checkPageBreak
            }
        }
        
        y += padding;
        drawRowBorders(rowStartY, y);
        doc.setDrawColor(200, 200, 200);
        lh(ml, mr, y, 0.5); // inner horizontal border
    });

    _inTable = false;
    // Final bottom border of table
    doc.setDrawColor(0,0,0);
    lh(ml, mr, y, 0.8);
    
    if (rows.length === 0) {
        doc.setFontSize(8.5); doc.setTextColor(120,120,120);
        doc.text('No items.', col.desc + 4, y + 11); y += 18;
    }

    // Bank / account details note (below rows, before totals line)
    if (cfg.bank && bankContent && isVisible('bank_details')) {
        y += 4;
        doc.setFontSize(8); doc.setFont('helvetica','normal'); doc.setTextColor(50,50,50);
        var bkLines = doc.splitTextToSize('Account Details for payment: ' + bankContent.replace(/\n/g, ', '), mr - ml - 10);
        checkPageBreak(bkLines.length * 11 + 8);
        doc.text(bkLines, col.desc, y + 10);
        y += bkLines.length * 11 + 8;
    }

    // Separator line before totals
    lh(ml, mr, y, 0.5); y += 10;

    // ════════════════════════════════════════════════════════
    //  TOTALS — right-aligned
    // ════════════════════════════════════════════════════════
    checkPageBreak(70);
    var tLabelX = col.price;
    var tValX   = mr;

    function tRow(label, val, bold) {
        doc.setFontSize(8.5);
        doc.setFont('helvetica', bold ? 'bold' : 'normal');
        doc.setTextColor(0,0,0);
        doc.text(label, tLabelX, y + 10, { align:'right' });
        doc.text(val,   tValX,   y + 10, { align:'right' });
        y += 14;
    }

    tRow('Subtotal', subtotal);
    // Name the tax after what this document actually charges. A tenant using
    // GST should not read "VAT" on their own invoice.
    tRow(documentTaxLabel(cfg), vatAmt);
    lh(tLabelX - 60, tValX, y - 2, 0.5);
    y += 4;
    tRow('TOTAL  ' + currLabel, total, true);
    y += 10;

    // ════════════════════════════════════════════════════════
    //  DUE DATE + TERMS
    // ════════════════════════════════════════════════════════
    if (dueDate) {
        checkPageBreak(30);
        doc.setFontSize(9); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
        doc.text(cfg.dateOutLabel + ': ' + dueDate, ml, y + 12);
        y += 18;
    }

    if (savedTerms && isVisible('terms_conditions')) {
        var termLines = doc.splitTextToSize(savedTerms.trim(), mr - ml);
        checkPageBreak(termLines.length * 11 + 10);
        doc.setFontSize(8); doc.setFont('helvetica','normal'); doc.setTextColor(60,60,60);
        doc.text(termLines, ml, y + 11);
        y += termLines.length * 11 + 10;
    }

    // Signature
    if (savedSignature && isVisible('signature')) {
        checkPageBreak(70);
        y += 10;
        try { doc.addImage(savedSignature, 'PNG', mr - 140, y, 140, 45); } catch(e) {}
        lh(mr - 140, mr, y + 48, 0.5);
        doc.setFontSize(8); doc.setFont('helvetica','normal'); doc.setTextColor(80,80,80);
        doc.text('Authorised Signature', mr - 140, y + 58);
        y += 68;
    }

    y += 20;

    // ════════════════════════════════════════════════════════
    //  PAYMENT ADVICE  (dashed cut-here section)
    // ════════════════════════════════════════════════════════
    if (!cfg.paymentAdvice || !isVisible('payment_stub')) { drawFooter(); return doc; }
    checkPageBreak(90);
    doc.setDrawColor(0,0,0); doc.setLineWidth(0.5);
    doc.setLineDashPattern([4, 3], 0);
    doc.line(ml, y, mr, y);
    doc.setLineDashPattern([], 0);
    // Scissors icon (text approximation)
    doc.setFontSize(12); doc.setFont('helvetica','normal'); doc.setTextColor(0,0,0);
    doc.text('-X-', ml - 2, y - 3);
    y += 16;

    doc.setFontSize(18); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
    doc.text('PAYMENT ADVICE', ml, y + 14);
    y += 24;

    // Two-column payment advice detail
    var paRight = w / 2 + 10;
    doc.setFontSize(8); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
    doc.text('Customer',       ml,      y + 11);
    doc.text(cfg.numberLabel, paRight, y + 11);
    y += 13;
    doc.setFont('helvetica','normal'); doc.setTextColor(30,30,30);
    var paAddrLines = doc.splitTextToSize(contact || '-', paRight - ml - 20);
    doc.text(paAddrLines,  ml,      y + 10);
    doc.text(numberText || '-',     paRight, y + 10);
    var paAddrH = paAddrLines.length * 11;
    y += paAddrH + 8;

    doc.setFontSize(8); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
    doc.text(cfg.totalLabel,  ml,      y + 11);
    doc.text(cfg.dateOutLabel,    paRight, y + 11);
    y += 13;
    doc.setFontSize(10); doc.setFont('helvetica','bold'); doc.setTextColor(0,0,0);
    doc.text(cs + total,    ml,      y + 11);
    doc.setFontSize(9); doc.setFont('helvetica','normal');
    doc.text(dueDate || '-', paRight, y + 11);
    y += 20;

    drawFooter();
    return doc;
}

// Quotes reuse the invoice layout; only the wording and the missing payment
// slip differ.
function generateQuotePDF() {
    return generateInvoicePDF(false, 'quote');
}
window.generateQuotePDF = generateQuotePDF;

// --- Send Email ---
async function sendEmail() {
    var number = document.getElementById('view-inv-number-val').textContent;
    if (!number) { showToast('No invoice loaded', 'error'); return; }

    var logoData = localStorage.getItem('company_logo') || '';

    var pdfB64 = '';
    try {
        var doc = generateInvoicePDF(false);
        var dataUri = doc.output('datauristring');
        pdfB64 = dataUri.split('base64,')[1] || '';
        if (!pdfB64) console.warn('sendEmail: PDF base64 extraction failed, dataUri prefix:', dataUri.substring(0, 60));
        else console.log('sendEmail: PDF ready, size ~' + Math.round(pdfB64.length / 1024) + 'KB');
    } catch (e) {
        console.error('PDF generation failed:', e);
        showToast('PDF generation failed: ' + e.message, 'error');
        return;
    }

    try {
        showToast('Sending email...', 'info');
        var res = await fetch('/api/invoices/' + encodeURIComponent(number) + '/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logo_data: logoData, pdf_data: pdfB64 })
        });
        var data = await res.json();
        if (res.ok) {
            showToast('Email sent via Gmail API with PDF attached!', 'success');
            fetchInvoices();
            viewInvoice(number);
        } else {
            reportApiError(res, data, 'Could not send the email');
        }
    } catch (e) {
        showToast('Failed to send email: ' + e, 'error');
    }
}
window.sendEmail = sendEmail;

// --- Send WhatsApp ---
async function sendWhatsApp() {
    var number = document.getElementById('view-inv-number-val').textContent;
    if (!number) return;
    try {
        var res = await fetch('/api/invoices/' + encodeURIComponent(number) + '/send-whatsapp', { method: 'POST' });
        var data = await res.json();
        if (res.ok) { showToast('WhatsApp sent!', 'success'); fetchInvoices(); }
        else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.sendWhatsApp = sendWhatsApp;

// --- Delete Invoice ---
async function deleteInvoice(number) {
    if (!confirm('Delete invoice ' + number + '?')) return;
    try {
        var res = await fetch('/api/invoices/' + encodeURIComponent(number), { method: 'DELETE' });
        if (res.ok) { showToast('Invoice deleted', 'success'); fetchInvoices(); showView('invoices-view'); }
        else { var data = await res.json(); showToast('Delete failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Delete failed: ' + e, 'error'); }
}
window.deleteInvoice = deleteInvoice;

// --- Mark as Paid ---
async function markAsPaid(number) {
    if (!confirm('Mark invoice ' + number + ' as paid?')) return;
    try {
        var res = await fetch('/api/invoices/' + encodeURIComponent(number) + '/mark-paid', { method: 'POST' });
        if (res.ok) { showToast('Marked as paid', 'success'); fetchInvoices(); viewInvoice(number); }
        else { var data = await res.json(); showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.markAsPaid = markAsPaid;

// --- Part payments ---
// Invoices are rarely settled in one hit; this records a receipt against the
// outstanding balance and lets the server move the status.
async function recordPayment(number) {
    number = number || (document.getElementById('view-inv-number-val') || {}).textContent;
    if (!number) return;
    var outstanding = _viewOutstanding || 0;
    var raw = prompt('Payment amount' + (outstanding ? ' (outstanding: ' + outstanding.toFixed(2) + ')' : '') + ':',
                     outstanding ? outstanding.toFixed(2) : '');
    if (raw === null) return;
    var amount = parseFloat(raw);
    if (isNaN(amount) || amount <= 0) { showToast('Enter a valid amount', 'error'); return; }
    var reference = prompt('Reference (optional):', '') || '';
    try {
        var res = await fetch('/api/invoices/' + encodeURIComponent(number) + '/payments', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: amount, reference: reference })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Payment recorded — ' + data.status, 'success');
        fetchInvoices();
        viewInvoice(number);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.recordPayment = recordPayment;

async function reversePayment(number, paymentId) {
    if (!confirm('Reverse this payment?')) return;
    try {
        var res = await fetch('/api/invoices/' + encodeURIComponent(number) + '/payments/' + paymentId, { method: 'DELETE' });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Payment reversed', 'success');
        fetchInvoices();
        viewInvoice(number);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.reversePayment = reversePayment;

// --- Invoice Calculations ---
// Mirror of backend parse_tax_rate: derive the rate from the line's own label
// ("20% VAT", "5% VAT", "0% Zero Rated", "No Tax") instead of assuming 20%.
function parseTaxRate(label, fallback) {
    if (fallback === undefined) fallback = 0.20;
    var s = String(label == null ? '' : label).trim();
    if (!s) return fallback;
    var m = s.match(/(\d+(?:\.\d+)?)\s*%/);
    if (m) { var v = parseFloat(m[1]); return isNaN(v) ? fallback : Math.max(0, v) / 100; }
    var low = s.toLowerCase();
    if (low.indexOf('no tax') >= 0 || low.indexOf('none') >= 0 || low.indexOf('zero') >= 0 ||
        low.indexOf('exempt') >= 0 || low.indexOf('outside') >= 0) return 0;
    return fallback;
}
window.parseTaxRate = parseTaxRate;

// Net amount and tax for one line, given the invoice-level tax treatment.
function lineTotals(qty, price, disc, taxLabel, taxType) {
    var amount = (parseFloat(qty) || 0) * (parseFloat(price) || 0);
    var d = parseFloat(disc) || 0;
    if (d > 0) amount *= (1 - d / 100);
    var rate = parseTaxRate(taxLabel);
    var vat = 0;
    if (taxType === 'exclusive') {
        vat = amount * rate;
    } else if (taxType === 'inclusive') {
        var net = rate ? amount / (1 + rate) : amount;
        vat = amount - net;
        amount = net;
    }
    return { net: amount, vat: vat, rate: rate };
}
window.lineTotals = lineTotals;

// Which elements the line-item editor drives. Two forms use it - invoices and
// quotes - and totals must never mix rows from both.
var DOC_FORM_SCOPES = {
    invoice: {
        body: 'line-items-body', taxType: 'tax-type', currency: 'inv-currency',
        subtotal: 'summary-subtotal', vat: 'summary-vat', total: 'summary-total',
    },
    quote: {
        body: 'quote-line-items-body', taxType: 'quote-tax-type', currency: 'quote-currency',
        subtotal: 'quote-summary-subtotal', vat: 'quote-summary-vat', total: 'quote-summary-total',
    },
};

function docFormScope(name) {
    return DOC_FORM_SCOPES[name] || DOC_FORM_SCOPES.invoice;
}

// The rows of one form only.
function scopedLineRows(name) {
    var host = document.getElementById(docFormScope(name).body);
    return host ? Array.prototype.slice.call(host.querySelectorAll('.line-item-row')) : [];
}
window.scopedLineRows = scopedLineRows;

function calculateTotals(scope) {
    var cfg = docFormScope(scope);
    var subtotal = 0, totalVat = 0;
    var taxType = (document.getElementById(cfg.taxType) || {}).value || 'exclusive';
    scopedLineRows(scope).forEach(function(row) {
        var qty = row.querySelector('.item-qty') ? row.querySelector('.item-qty').value : 0;
        var price = row.querySelector('.item-price') ? row.querySelector('.item-price').value : 0;
        var disc = row.querySelector('.item-disc') ? row.querySelector('.item-disc').value : 0;
        var taxLabel = row.querySelector('.item-tax-rate') ? row.querySelector('.item-tax-rate').value : '';
        var t = lineTotals(qty, price, disc, taxLabel, taxType);
        var amountEl = row.querySelector('.item-amount');
        var taxEl = row.querySelector('.item-tax-amount');
        if (amountEl) amountEl.textContent = t.net.toFixed(2);
        if (taxEl) taxEl.textContent = t.vat.toFixed(2);
        subtotal += t.net;
        totalVat += t.vat;
    });
    var subEl = document.getElementById(cfg.subtotal);
    var vatEl = document.getElementById(cfg.vat);
    var totalEl = document.getElementById(cfg.total);
    var curEl = document.getElementById(cfg.currency);
    var curCode = curEl ? (curEl.value || _appCurrency) : _appCurrency;
    if (subEl) subEl.textContent = subtotal.toFixed(2);
    if (vatEl) vatEl.textContent = totalVat.toFixed(2);
    if (totalEl) totalEl.textContent = (subtotal + totalVat).toFixed(2) + ' ' + curCode;
}
window.calculateTotals = calculateTotals;

function addLineItemRow(scope) {
    var tbody = document.getElementById(docFormScope(scope).body);
    if (!tbody) return;
    var html = '<tr class="line-item-row" style="border-bottom:1px solid var(--border-color);background:var(--surface-color);">' +
        '<td style="padding:8px;text-align:center;color:var(--text-secondary);cursor:grab;">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
        '<circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/>' +
        '<circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/>' +
        '</svg></td>' +
        '<td style="padding:0;"><input type="text" class="table-input item-name" style="width:100%;" placeholder="Item name"></td>' +
        '<td style="padding:0;"><textarea class="table-input item-desc" rows="1" style="width:100%;resize:vertical;min-height:32px;overflow:hidden;line-height:1.4;" ' +
        'oninput="this.style.height=\'auto\';this.style.height=this.scrollHeight+\'px\';"></textarea></td>' +
        '<td style="padding:0;"><input type="number" class="table-input item-qty" style="width:100%;text-align:right;" value="0" step="1" min="0"></td>' +
        '<td style="padding:0;"><input type="number" class="table-input item-price" style="width:100%;text-align:right;" value="0" step="0.01" min="0"></td>' +
        '<td style="padding:0;"><input type="number" class="table-input item-disc" style="width:100%;text-align:right;" placeholder="0" step="1" min="0" max="100"></td>' +
        '<td style="padding:0;"><select class="table-input item-account" style="width:100%;">' + 
        '<option>200 - Sales</option>' + 
        '<option>230 - Services</option>' + 
        '<option>260 - Consulting</option>' + 
        '<option>400 - Other Revenue</option>' + 
        '<option>420 - Interest Income</option>' + 
        '<option>800 - Product Sales</option>' + 
        '</select></td>' +
        '<td style="padding:0;"><select class="table-input item-tax-rate" style="width:100%;">' + 
        taxOptionsHtml() +
        '</select></td>' +
        '<td style="display:none;" class="item-tax-amount">0.00</td>' +
        '<td style="padding:12px 8px;text-align:right;font-weight:500;" class="item-amount">0.00</td>' +
        '<td style="padding:8px;text-align:center;white-space:nowrap;">' +
        '<button type="button" class="btn-icon ai-desc" title="Tidy this description with AI" ' +
        'onclick="aiDescribeLineItem(this)" style="color:var(--primary-color);cursor:pointer;background:none;border:none;">&#10022;</button>' +
        '<button type="button" class="btn-icon delete-row" style="color:var(--danger-color);cursor:pointer;background:none;border:none;">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
        '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button></td></tr>';
    tbody.insertAdjacentHTML('beforeend', html);
}
window.addLineItemRow = addLineItemRow;

// --- Preview Invoice ---
function previewInvoice() {
    var contact = document.getElementById('inv-contact').value || 'Draft';
    var email = document.getElementById('inv-email') ? document.getElementById('inv-email').value : '';
    var phone = document.getElementById('inv-phone') ? document.getElementById('inv-phone').value : '';
    var issue_date = document.getElementById('inv-issue-date').value || '';
    var due_date = document.getElementById('inv-due-date').value || '';
    var invoice_number = document.getElementById('inv-number').value || 'DRAFT';

    document.getElementById('view-inv-title').textContent = 'Invoice ' + invoice_number;
    document.getElementById('view-inv-status').textContent = 'Preview';
    document.getElementById('view-inv-status').className = 'status-pill';
    document.getElementById('view-inv-contact').textContent = contact;
    var emailD = document.getElementById('view-inv-email-display');
    if (emailD) emailD.textContent = email || 'No email';
    var phoneD = document.getElementById('view-inv-phone-display');
    if (phoneD) phoneD.textContent = phone || 'No phone';
    document.getElementById('view-inv-issue-date').textContent = issue_date;
    document.getElementById('view-inv-due-date').textContent = due_date;
    document.getElementById('view-inv-number-val').textContent = invoice_number;
    var refVal = document.getElementById('inv-ref') ? document.getElementById('inv-ref').value : '';
    document.getElementById('view-inv-ref').textContent = refVal || '-';
    if(document.getElementById('view-inv-ref-container')) document.getElementById('view-inv-ref-container').style.display = refVal ? 'block' : 'none';


    var tbody = document.getElementById('view-line-items-body');
    tbody.innerHTML = '';
    var taxType = (document.getElementById('tax-type') || {}).value || 'exclusive';

    scopedLineRows('invoice').forEach(function(row) {
        var name = row.querySelector('.item-name') ? row.querySelector('.item-name').value : '';
        var desc = row.querySelector('.item-desc') ? row.querySelector('.item-desc').value : '';
        var qty = parseFloat(row.querySelector('.item-qty') ? row.querySelector('.item-qty').value : 0) || 0;
        var price = parseFloat(row.querySelector('.item-price') ? row.querySelector('.item-price').value : 0) || 0;
        var disc = parseFloat(row.querySelector('.item-disc') ? row.querySelector('.item-disc').value : 0) || 0;
        var taxLabel = row.querySelector('.item-tax-rate') ? row.querySelector('.item-tax-rate').value : '';
        if (name || desc || qty > 0 || price > 0) {
            var t = lineTotals(qty, price, disc, taxLabel, taxType);
            tbody.insertAdjacentHTML('beforeend', '<tr><td style="padding:12px 16px;vertical-align:top;">' + esc(name) + '</td><td style="padding:12px 16px;word-wrap:break-word;overflow-wrap:break-word;max-width:280px;vertical-align:top;">' + esc(desc) + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + qty + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + price.toFixed(2) + '</td><td style="padding:12px 16px;text-align:right;vertical-align:top;">' + disc + '%</td><td style="padding:12px 16px;vertical-align:top;">' + esc(taxLabel || 'No Tax') + '</td><td style="padding:12px 16px;text-align:right;font-weight:600;vertical-align:top;">' + t.net.toFixed(2) + '</td></tr>');
        }
    });

    document.getElementById('view-summary-subtotal').textContent = document.getElementById('summary-subtotal').textContent;
    document.getElementById('view-summary-vat').textContent = document.getElementById('summary-vat').textContent;
    document.getElementById('view-summary-total').textContent = document.getElementById('summary-total').textContent;

    var backBtn = document.getElementById('preview-back-btn');
    if (backBtn) backBtn.style.display = 'inline-block';
    document.querySelectorAll('.invoice-action-btn').forEach(function(btn) { btn.style.display = 'none'; });
    showView('view-invoice-view');
}
window.previewInvoice = previewInvoice;

// --- Submit Invoice ---
async function submitComplexInvoice(status) {
    status = status || 'Awaiting Payment';
    var contact = document.getElementById('inv-contact').value;
    if (!contact) { showToast('Customer name is required', 'error'); return; }

    var line_items = [];
    scopedLineRows('invoice').forEach(function(row) {
        var name = row.querySelector('.item-name') ? row.querySelector('.item-name').value : '';
        var desc = row.querySelector('.item-desc') ? row.querySelector('.item-desc').value : '';
        var qty = parseFloat(row.querySelector('.item-qty') ? row.querySelector('.item-qty').value : 0) || 0;
        var price = parseFloat(row.querySelector('.item-price') ? row.querySelector('.item-price').value : 0) || 0;
        var disc = parseFloat(row.querySelector('.item-disc') ? row.querySelector('.item-disc').value : 0) || 0;
        var account = row.querySelector('.item-account') ? row.querySelector('.item-account').value : '200 - Sales';
        var tax_rate = row.querySelector('.item-tax-rate') ? row.querySelector('.item-tax-rate').value : 'No Tax';
        if (name || desc || qty > 0 || price > 0) {
            line_items.push({ name: name, description: desc, qty: qty, price: price, disc: disc, account: account, tax_rate: tax_rate });
        }
    });
    if (line_items.length === 0) { showToast('Add at least one line item', 'error'); return; }

    var payload = {
        contact: contact,
        email: document.getElementById('inv-email') ? document.getElementById('inv-email').value : '',
        phone_number: document.getElementById('inv-phone') ? document.getElementById('inv-phone').value : '',
        issue_date: document.getElementById('inv-issue-date').value,
        due_date: document.getElementById('inv-due-date').value,
        invoice_number: document.getElementById('inv-number').value,
        reference: document.getElementById('inv-ref').value,
        line_items: line_items,
        tax_type: (document.getElementById('tax-type') || {}).value || 'exclusive',
        status: status,
        currency: document.getElementById('inv-currency') ? document.getElementById('inv-currency').value : (_appCurrency || 'GBP'),
        bank_details: document.getElementById('inv-bank-account') ? document.getElementById('inv-bank-account').value : ''
    };

    try {
        var response = await fetch('/api/invoices', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!response.ok) { var err = await response.json(); throw new Error(err.detail || 'Failed'); }
        var invData = await response.json();
        document.getElementById('complex-invoice-form').reset();
        document.getElementById('line-items-body').innerHTML = '';
        addLineItemRow();
        calculateTotals();

        if (status === 'Awaiting Payment' && payload.email) {
            showToast('Invoice created! Sending email...', 'info');
            await viewInvoice(invData.number);
            await sendEmail();
        } else if (status === 'Awaiting Payment' && !payload.email) {
            showToast('Invoice created! No email address — add one to send.', 'warning');
            showView('invoices-view');
        } else {
            showToast('Invoice saved as draft', 'success');
            showView('invoices-view');
        }
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.submitComplexInvoice = submitComplexInvoice;

// --- PDF Download ---
function downloadPDF() {
    var number = document.getElementById('view-inv-number-val').textContent || 'invoice';
    var doc = generateInvoicePDF();
    doc.save(number + '.pdf');
}
window.downloadPDF = downloadPDF;

// --- PDF Preview ---
function previewPDF() {
    try {
        openPdfPreview(generateInvoicePDF(false), 'Invoice preview');
    } catch (e) {
        console.error('previewPDF error:', e);
        showToast('Preview failed: ' + e.message, 'error');
    }
}
window.previewPDF = previewPDF;

// --- Reports ---
async function loadReports() {
    try {
        var res = await fetch('/api/invoices');
        if (!res.ok) throw new Error('Failed');
        var invoices = await res.json();
        var statusCounts = {};
        invoices.forEach(function(inv) { statusCounts[inv.status] = (statusCounts[inv.status] || 0) + 1; });
        var chartEl = document.getElementById('reports-status-chart');
        if (chartEl) {
            var html = '<div style="display:flex;flex-direction:column;gap:12px;">';
            var colors = { 'Draft': '#94a3b8', 'Sent': '#00f0ff', 'Awaiting Payment': '#fcd34d', 'Paid': '#39ff14' };
            for (var status in statusCounts) {
                var pct = Math.round((statusCounts[status] / invoices.length) * 100);
                html += '<div><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span>' + status + '</span><span>' + statusCounts[status] + ' (' + pct + '%)</span></div><div style="height:8px;background:rgba(255,255,255,0.1);border-radius:4px;overflow:hidden;"><div style="height:100%;width:' + pct + '%;background:' + (colors[status] || '#94a3b8') + ';border-radius:4px;"></div></div></div>';
            }
            html += '</div>';
            chartEl.innerHTML = html;
        }
        // Revenue chart
        var revEl = document.getElementById('reports-chart-container');
        if (revEl) {
            var monthly = {};
            invoices.forEach(function(inv) { var m = inv.date ? inv.date.substring(0, 7) : 'Unknown'; monthly[m] = (monthly[m] || 0) + inv.due; });
            var months = Object.keys(monthly).sort();
            if (months.length === 0) { revEl.innerHTML = '<div class="loading">No revenue data</div>'; return; }
            var maxRev = Math.max.apply(null, Object.values(monthly));
            var barHtml = '<div class="chart-bars" style="height:150px;">';
            months.forEach(function(m) {
                var h = (monthly[m] / maxRev) * 100;
                barHtml += '<div class="chart-month"><div class="bar-group"><div class="bar in" style="height:' + h + '%"></div></div><span class="month-label">' + m + '</span></div>';
            });
            barHtml += '</div>';
            revEl.innerHTML = barHtml;
        }
    } catch (e) { console.error('Reports error:', e); }
}
window.loadReports = loadReports;

// --- Gmail API Status ---
async function loadGmailStatus() {
    try {
        var res = await fetch('/api/gmail/status');
        var data = await res.json();
        var statusEl = document.getElementById('gmail-status');
        var loginBtn = document.getElementById('gmail-login-btn');
        var emailEl = document.getElementById('gmail-email');
        var disconnectBtn = document.getElementById('gmail-disconnect-btn');
        var demoSection = document.getElementById('demo-email-section');
        if (!statusEl) return;
        if (data.gmail_ready) {
            var authEmail = data.gmail_authorized_email || data.user_email || 'Connected';
            statusEl.textContent = 'Connected';
            statusEl.style.color = 'var(--success-color)';
            emailEl.textContent = 'Sending as: ' + authEmail;
            emailEl.style.display = 'block';
            emailEl.style.color = 'var(--warning-color)';
            emailEl.style.fontWeight = '600';
            loginBtn.style.display = 'none';
            if (disconnectBtn) disconnectBtn.style.display = 'inline-block';
            if (demoSection) demoSection.style.display = 'block';
        } else if (data.logged_in) {
            statusEl.textContent = 'Logged in (re-login for refresh token)';
            statusEl.style.color = 'var(--warning-color)';
            emailEl.textContent = data.user_email || '';
            emailEl.style.display = data.user_email ? 'block' : 'none';
            loginBtn.style.display = 'inline-block';
            if (disconnectBtn) disconnectBtn.style.display = 'none';
            if (demoSection) demoSection.style.display = 'none';
        } else {
            statusEl.textContent = 'Not connected';
            statusEl.style.color = 'var(--danger-color)';
            emailEl.style.display = 'none';
            loginBtn.style.display = 'inline-block';
            if (disconnectBtn) disconnectBtn.style.display = 'none';
            if (demoSection) demoSection.style.display = 'none';
        }
    } catch (e) { var s = document.getElementById('gmail-status'); if (s) s.textContent = 'Error'; }
}
window.loadGmailStatus = loadGmailStatus;

async function disconnectGmail() {
    if (!confirm('Disconnect Gmail? Emails will stop sending until you re-authorize with the correct Google account.')) return;
    try {
        var res = await fetch('/api/gmail/disconnect', { method: 'POST' });
        if (res.ok) {
            showToast('Gmail disconnected. Re-authorize with your Google account.', 'success');
            loadGmailStatus();
        } else {
            showToast('Failed to disconnect', 'error');
        }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.disconnectGmail = disconnectGmail;

async function testGmailSend() {
    var toEmail = document.getElementById('demo-email').value;
    var btn = document.getElementById('send-demo-btn');
    if (!toEmail) { showToast('Enter a recipient email', 'error'); return; }
    if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
    try {
        var res = await fetch('/api/send-test-email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to_email: toEmail, subject: 'Test Invoice - aniprotech', body: 'Test email from aniprotech via Gmail API.' }) });
        var data = await res.json();
        if (res.ok) showToast('Email sent!', 'success');
        else showToast('Failed: ' + (data.detail || 'Error'), 'error');
    } catch (e) { showToast('Failed: ' + e, 'error'); }
    if (btn) { btn.disabled = false; btn.textContent = 'Send 10'; }
}
window.testGmailSend = testGmailSend;

async function sendDemoEmail(count) {
    count = count || 1;
    var toEmail = document.getElementById('demo-email').value || 'udayyyv@gmail.com';
    var btn = document.getElementById('send-demo-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending ' + count + '...'; }
    var success = 0, fail = 0;
    for (var i = 0; i < count; i++) {
        try {
            var res = await fetch('/api/send-test-email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to_email: toEmail, subject: 'Demo Invoice #' + (i + 1), body: 'Demo email ' + (i + 1) + ' of ' + count + ' from aniprotech via Gmail API.' }) });
            if (res.ok) success++; else fail++;
        } catch (e) { fail++; }
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Send ' + count; }
    if (fail > 0) showToast('Sent ' + success + '/' + count + ' (' + fail + ' failed). Ensure you are logged in with Google.', 'warning');
    else showToast(success + ' emails sent to ' + toEmail, 'success');
}
window.sendDemoEmail = sendDemoEmail;

// --- Settings ---
async function saveCompanyDetails() {
    var payload = {
        company_name: document.getElementById('settings-company-name') ? document.getElementById('settings-company-name').value : '',
        email: document.getElementById('settings-company-email') ? document.getElementById('settings-company-email').value : '',
        phone_number: document.getElementById('settings-company-phone') ? document.getElementById('settings-company-phone').value : '',
        company_address: document.getElementById('settings-company-address') ? document.getElementById('settings-company-address').value : '',
        company_abn: document.getElementById('settings-company-abn') ? document.getElementById('settings-company-abn').value : '',
        company_website: document.getElementById('settings-company-website') ? document.getElementById('settings-company-website').value : '',
        currency: document.getElementById('setting-currency') ? document.getElementById('setting-currency').value : 'GBP',
        bank_details: JSON.stringify(Array.from(document.querySelectorAll('.bank-detail-slot')).map(function(slot) {
            return {
                bank_name: slot.querySelector('.bank-name').value,
                account_name: slot.querySelector('.account-name').value,
                account_number: slot.querySelector('.account-number').value,
                sort_code: slot.querySelector('.sort-code').value
            };
        }).filter(function(b) { return b.bank_name || b.account_number; }))
    };
    _appCurrency = payload.currency || _appCurrency;
    try {
        var res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (res.ok) {
            showToast('Company details saved successfully!', 'success');
        } else {
            showToast('Failed to save: ' + (data.detail || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Failed to save: ' + e, 'error');
    }
}
window.saveCompanyDetails = saveCompanyDetails;

async function saveSettings() {
    var payload = {
        company_name: document.getElementById('settings-company-name') ? document.getElementById('settings-company-name').value : '',
        email: document.getElementById('settings-company-email') ? document.getElementById('settings-company-email').value : '',
        phone_number: document.getElementById('settings-company-phone') ? document.getElementById('settings-company-phone').value : '',
        company_address: document.getElementById('settings-company-address') ? document.getElementById('settings-company-address').value : '',
        company_abn: document.getElementById('settings-company-abn') ? document.getElementById('settings-company-abn').value : '',
        company_website: document.getElementById('settings-company-website') ? document.getElementById('settings-company-website').value : '',
        currency: document.getElementById('setting-currency') ? document.getElementById('setting-currency').value : 'USD',
        invoice_prefix: document.getElementById('setting-invoice-prefix')
            ? (document.getElementById('setting-invoice-prefix').value || 'INV-') : 'INV-',
        default_payment_terms: document.getElementById('setting-payment-terms')
            ? (document.getElementById('setting-payment-terms').value || '14') : '14'
    };
    _appCurrency = payload.currency || _appCurrency;
    try {
        var res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (res.ok) {
            showToast('Settings saved successfully!', 'success');
        } else {
            showToast('Failed to save settings: ' + (data.detail || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Failed to save settings: ' + e, 'error');
    }
}
window.saveSettings = saveSettings;

async function loadSettings() {
    try {
        var res = await fetch('/api/settings');
        if (!res.ok) return;
        var data = await res.json();
        initTemplateBuilder(data.invoice_layout || null);
        if (data.company_name !== undefined) { var el = document.getElementById('settings-company-name'); if (el) el.value = data.company_name; }
        if (data.email !== undefined) { var el = document.getElementById('settings-company-email'); if (el) el.value = data.email; }
        if (data.phone_number !== undefined) { var el = document.getElementById('settings-company-phone'); if (el) el.value = data.phone_number; }
        if (data.company_address !== undefined) { var el = document.getElementById('settings-company-address'); if (el) el.value = data.company_address; }
        if (data.company_abn !== undefined) { var el = document.getElementById('settings-company-abn'); if (el) el.value = data.company_abn; }
        if (data.company_website !== undefined) { var el = document.getElementById('settings-company-website'); if (el) el.value = data.company_website; }
        if (data.currency !== undefined) { var el = document.getElementById('setting-currency'); if (el) el.value = data.currency; if (_curPickers['settingsCurrency']) setCurrencyPickerDisplay('settingsCurrency', data.currency); }
        var prefixEl = document.getElementById('setting-invoice-prefix');
        if (prefixEl) prefixEl.value = data.invoice_prefix || 'INV-';
        var termsEl = document.getElementById('setting-payment-terms');
        if (termsEl) termsEl.value = data.default_payment_terms || 14;
        
        // Render bank details
        var bankContainer = document.getElementById('settings-bank-details-container');
        if (bankContainer) {
            bankContainer.innerHTML = '';
            var banks = [];
            try {
                if (data.bank_details) banks = JSON.parse(data.bank_details);
            } catch(e) {}
            window._savedBankDetails = banks;
            
            if (banks.length === 0) {
                addBankDetailSlot();
            } else {
                banks.forEach(function(b) { addBankDetailSlot(b); });
            }
            
            // Populate Create Invoice dropdown if it exists
            var invBankSelect = document.getElementById('inv-bank-account');
            if (invBankSelect) {
                invBankSelect.innerHTML = '<option value="">No bank selected</option>';
                banks.forEach(function(b) {
                    var opt = document.createElement('option');
                    var display = b.bank_name + ' - ' + b.account_number;
                    opt.value = b.bank_name + '\n' + 'Acc Name: ' + b.account_name + '\n' + 'Acc No: ' + b.account_number + '\n' + 'Sort Code: ' + b.sort_code;
                    opt.textContent = display;
                    invBankSelect.appendChild(opt);
                });
            }
        }
    } catch (e) { console.error('Failed to load settings:', e); }
    fetch('/api/client/logo').then(function(r) { return r.json(); }).then(function(data) {
        if (data.logo_url) {
            var img = document.getElementById('settings-logo-img');
            var txt = document.getElementById('settings-logo-text');
            if (img) { img.src = data.logo_url; img.style.display = 'block'; }
            if (txt) txt.style.display = 'none';
            localStorage.setItem('company_logo', data.logo_url);
        }
    }).catch(function() {});
}
window.loadSettings = loadSettings;

async function loadAuditLogs() {
    var container = document.getElementById('audit-log-container');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary);">Loading...</div>';
    try {
        var res = await fetch('/api/audit-logs?limit=50');
        if (!res.ok) throw new Error('Failed');
        var logs = await res.json();
        if (!logs.length) {
            container.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary);">No activity recorded yet.</div>';
            return;
        }
        var actionIcons = {
            'invoice_created': { icon: '&#128196;', color: 'var(--primary-color)' },
            'invoice_sent': { icon: '&#9993;', color: 'var(--primary-color)' },
            'invoice_marked_paid': { icon: '&#9989;', color: 'var(--success-color)' },
            'invoice_deleted': { icon: '&#128465;', color: 'var(--danger-color)' },
            'employee_created': { icon: '&#128100;', color: 'var(--success-color)' },
            'employee_updated': { icon: '&#9998;', color: 'var(--primary-color)' },
            'employee_deleted': { icon: '&#128100;', color: 'var(--danger-color)' },
            'leave_approved': { icon: '&#9989;', color: 'var(--success-color)' },
            'leave_rejected': { icon: '&#10060;', color: 'var(--danger-color)' },
            'bill_created': { icon: '&#128196;', color: 'var(--warning-color)' },
            'bill_paid': { icon: '&#9989;', color: 'var(--success-color)' },
            'bill_deleted': { icon: '&#128465;', color: 'var(--danger-color)' },
            'payslip_marked_paid': { icon: '&#128176;', color: 'var(--success-color)' },
            'goal_assigned_dept': { icon: '&#127919;', color: 'var(--primary-color)' },
            'goal_saved_for_dept': { icon: '&#127919;', color: 'var(--warning-color)' },
        };
        container.innerHTML = '<div style="max-height:500px;overflow-y:auto;">' +
            logs.map(function(log) {
                var a = actionIcons[log.action] || { icon: '&#8226;', color: 'var(--text-secondary)' };
                var actionLabel = log.action.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
                return '<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-color);">' +
                    '<div style="width:32px;height:32px;border-radius:8px;background:' + a.color + '15;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:1rem;">' + a.icon + '</div>' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div style="font-size:0.85rem;font-weight:500;">' + esc(actionLabel) + (log.entity_name ? ' — <span style="color:var(--primary-color);">' + esc(log.entity_name) + '</span>' : '') + '</div>' +
                        (log.details ? '<div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(log.details) + '</div>' : '') +
                    '</div>' +
                    '<div style="font-size:0.75rem;color:var(--text-secondary);white-space:nowrap;flex-shrink:0;">' + esc(log.created_at || '') + '</div>' +
                '</div>';
            }).join('') + '</div>';
    } catch(e) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:var(--danger-color);">Failed to load activity log.</div>';
    }
}
window.loadAuditLogs = loadAuditLogs;

function handleSettingsLogoUpload(e) {
    var file = e.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { showToast('File too large. Max 2MB.', 'error'); return; }
    var reader = new FileReader();
    reader.onload = function(ev) {
        var b64 = ev.target.result;
        localStorage.setItem('company_logo', b64);
        fetch('/api/client/logo', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logo_url: b64 })
        }).then(function() {
            showToast('Logo saved!', 'success');
        }).catch(function() {
            showToast('Failed to save logo', 'error');
        });
        var img = document.getElementById('settings-logo-img');
        var txt = document.getElementById('settings-logo-text');
        if (img) { img.src = b64; img.style.display = 'block'; }
        if (txt) txt.style.display = 'none';
    };
    reader.readAsDataURL(file);
}
window.handleSettingsLogoUpload = handleSettingsLogoUpload;

// --- Contact Autocomplete ---
var contactDropdownTimeout = null;
// Keyed by input id, because the quote form wants the same behaviour and a
// single boolean would let whichever form ran first block the other.
var contactAutocompleteSetup = {};

function setupContactAutocomplete(inputId, dropdownId, emailId, phoneId) {
    inputId = inputId || 'inv-contact';
    dropdownId = dropdownId || 'contact-autocomplete-dropdown';
    emailId = emailId || (inputId === 'inv-contact' ? 'inv-email' : inputId.replace('-contact', '-email'));
    phoneId = phoneId || (inputId === 'inv-contact' ? 'inv-phone' : inputId.replace('-contact', '-phone'));

    if (contactAutocompleteSetup[inputId]) return;
    var input = document.getElementById(inputId);
    var dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;
    contactAutocompleteSetup[inputId] = true;

    input.addEventListener('input', function() {
        var val = input.value.trim();
        clearTimeout(contactDropdownTimeout);
        if (val.length < 1) { dropdown.classList.remove('show'); return; }
        contactDropdownTimeout = setTimeout(function() {
            fetch('/api/contacts/search?q=' + encodeURIComponent(val))
                .then(function(r) { return r.json(); })
                .then(function(contacts) {
                    dropdown.innerHTML = '';
                    contacts.forEach(function(c) {
                        var div = document.createElement('div');
                        div.className = 'contact-autocomplete-item';
                        var initial = (c.name || '?')[0].toUpperCase();
                        div.innerHTML = '<div class="ca-icon">' + initial + '</div><div><div class="ca-name">' + esc(c.name) + '</div>' + (c.email ? '<div class="ca-email">' + esc(c.email) + '</div>' : '') + '</div>';
                        div.addEventListener('click', function() {
                            input.value = c.name;
                            var emailEl = document.getElementById(emailId);
                            if (emailEl && c.email) emailEl.value = c.email;
                            var phoneEl = document.getElementById(phoneId);
                            if (phoneEl && c.phone_number) phoneEl.value = c.phone_number;
                            dropdown.classList.remove('show');
                        });
                        dropdown.appendChild(div);
                    });
                    if (val.length > 0) {
                        var newDiv = document.createElement('div');
                        newDiv.className = 'contact-autocomplete-new';
                        newDiv.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Create new contact: <strong>' + esc(val) + '</strong>';
                        newDiv.addEventListener('click', function() {
                            input.value = val;
                            dropdown.classList.remove('show');
                        });
                        dropdown.appendChild(newDiv);
                    }
                    dropdown.classList.add('show');
                });
        }, 200);
    });

    input.addEventListener('blur', function() {
        setTimeout(function() { dropdown.classList.remove('show'); }, 200);
    });

    input.addEventListener('focus', function() {
        if (input.value.trim().length > 0) {
            input.dispatchEvent(new Event('input'));
        }
    });
}

// ============================================================
// HR MODULE
// ============================================================

var allContacts = [];
var allEmployees = [];
var allPayslips = [];
var currentEmpFilter = '';
var currentPsFilter = '';
var currentEmployeeId = null;
var currentPayslipId = null;

async function preloadSearchData() {
    try {
        var [cRes, empRes, psRes] = await Promise.all([
            fetch('/api/contacts').then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
            fetch('/api/employees').then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
            fetch('/api/payslips').then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; })
        ]);
        allContacts = cRes || [];
        allEmployees = empRes || [];
        allPayslips = psRes || [];
    } catch (e) { console.error('Search data preload failed:', e); }
}
async function loadHRStats() {
    try {
        var res = await fetch('/api/hr/stats');
        if (!res.ok) return;
        var s = await res.json();
        var el = function(id) { return document.getElementById(id); };
        if (el('hr-total')) el('hr-total').textContent = s.total_employees || 0;
        if (el('hr-active')) el('hr-active').textContent = s.active || 0;
        if (el('hr-onboarding')) el('hr-onboarding').textContent = s.onboarding || 0;
        if (el('hr-offboarding')) el('hr-offboarding').textContent = s.offboarding || 0;
        if (el('hr-depts')) el('hr-depts').textContent = s.departments || 0;
    } catch (e) { console.error('HR stats error:', e); }
}

// --- Employees ---
async function fetchEmployees(statusFilter) {
    try {
        var url = '/api/employees';
        if (statusFilter) url += '?status=' + encodeURIComponent(statusFilter);
        var res = await fetch(url);
        if (!res.ok) throw new Error('Failed');
        allEmployees = await res.json();
        renderEmployees(allEmployees);
        var countEl = document.getElementById('employee-count');
        if (countEl) countEl.textContent = allEmployees.length + ' item' + (allEmployees.length !== 1 ? 's' : '');
    } catch (e) {
        var tbody = document.getElementById('employees-table-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="loading">Failed to load employees.</td></tr>';
    }
}

function renderEmployees(employees) {
    var tbody = document.getElementById('employees-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    
    if (employees.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">No employees found.</td></tr>';
        return;
    }
    employees.forEach(function(e) {
        var statusClass = (e.status || '').toLowerCase().replace(/\s+/g, '-');
        var typeLabel = (e.employment_type || '').replace('_', ' ');
        tbody.insertAdjacentHTML('beforeend', '<tr><td><a href="#" class="link" onclick="event.preventDefault();viewEmployee(' + e.id + ')">' + esc(e.first_name) + ' ' + esc(e.last_name) + '</a>' + levelBadge(e.level) + '<br><span style="font-size:0.78rem;color:var(--text-secondary);">' + esc(e.email || '') + '</span></td><td>' + esc(e.employee_id || '-') + '</td><td>' + esc(e.department_name || '-') + '</td><td>' + esc(e.job_title || '-') + '<br><span style="font-size:0.72rem;color:var(--text-secondary);">' + esc(roleLabel(e.role)) + '</span></td><td>' + esc(typeLabel) + '</td><td>' + esc(e.start_date || '-') + '</td><td><span class="status-pill status-' + statusClass + '">' + esc(e.status) + '</span></td><td class="text-right"><button class="btn btn-outline btn-sm" onclick="viewEmployee(' + e.id + ')">View</button></td></tr>');
    });
}

function filterEmployees(status, btn) {
    currentEmpFilter = status;
    document.querySelectorAll('#employee-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    if (status) {
        var filtered = allEmployees.filter(function(e) { return e.status === status; });
        renderEmployees(filtered);
    } else {
        renderEmployees(allEmployees);
    }
}
window.filterEmployees = filterEmployees;

function searchEmployees() {
    var q = (document.getElementById('employee-search').value || '').toLowerCase();
    var filtered = allEmployees.filter(function(e) {
        return ((e.first_name + ' ' + e.last_name).toLowerCase().indexOf(q) >= 0 ||
            (e.email || '').toLowerCase().indexOf(q) >= 0 ||
            (e.employee_id || '').toLowerCase().indexOf(q) >= 0 ||
            (e.job_title || '').toLowerCase().indexOf(q) >= 0 ||
            (e.department_name || '').toLowerCase().indexOf(q) >= 0);
    });
    renderEmployees(filtered);
}
window.searchEmployees = searchEmployees;

// --- View Employee ---
async function viewEmployee(empId) {
    currentEmployeeId = empId;
    try {
        var res = await fetch('/api/employees/' + empId);
        if (!res.ok) throw new Error('Failed');
        var emp = await res.json();
        // Kept so the edit toggle can preselect the current band and role.
        _currentEmployee = emp;
        await loadHrLevels();
        document.getElementById('emp-detail-name').textContent = emp.full_name;
        document.getElementById('emp-detail-status').textContent = emp.status;
        document.getElementById('emp-detail-status').className = 'status-pill status-' + (emp.status || '').toLowerCase().replace(/\s+/g, '-');
        document.getElementById('emp-detail-eid').textContent = emp.employee_id || '-';
        document.getElementById('emp-detail-email').textContent = emp.email || '-';
        var roMap = { 'phone': emp.phone, 'title': emp.job_title, 'dept': emp.department_name, 'mgr': emp.manager_name, 'type': (emp.employment_type || '').replace('_', ' '), 'payfreq': emp.pay_frequency || '-', 'salary': emp.salary ? formatCurrency(emp.salary) : '-', 'start': emp.start_date || '-', 'level': emp.level || '-', 'role': roleLabel(emp.role), 'taxrate': emp.tax_rate ? emp.tax_rate + '%' : '-', 'emergency': emp.emergency_contact ? emp.emergency_contact + (emp.emergency_phone ? ' (' + emp.emergency_phone + ')' : '') : '-' };
        Object.keys(roMap).forEach(function(k) {
            var roEl = document.getElementById('emp-detail-' + k + '-ro');
            if (roEl) roEl.textContent = roMap[k] || '-';
        });
        var inputMap = { 'phone': emp.phone || '', 'title': emp.job_title || '', 'salary': emp.salary || 0, 'start': emp.start_date || '', 'taxrate': emp.tax_rate || 0, 'emergency': emp.emergency_contact || '' };
        Object.keys(inputMap).forEach(function(k) {
            var inp = document.getElementById('emp-detail-' + k);
            if (inp) inp.value = inputMap[k];
        });
        renderEmployeeLeavePanel(emp);
        renderEmployeeAttendancePanel(emp);
        renderEmployeeDocRequests(emp);
        var typeEl = document.getElementById('emp-detail-type');
        if (typeEl) typeEl.value = emp.employment_type || 'full_time';
        var payfreqEl = document.getElementById('emp-detail-payfreq');
        if (payfreqEl) payfreqEl.value = emp.pay_frequency || 'monthly';

        var offboardBtn = document.getElementById('emp-offboard-btn');
        if (offboardBtn) offboardBtn.style.display = (emp.status === 'active' || emp.status === 'onboarding') ? 'inline-flex' : 'none';

        // Onboarding
        var items = emp.onboarding_items || [];
        var completed = items.filter(function(i) { return i.is_completed; }).length;
        var progressEl = document.getElementById('onboarding-progress');
        if (progressEl) progressEl.textContent = completed + '/' + items.length;
        var barFill = document.getElementById('onboarding-bar-fill');
        if (barFill) barFill.style.width = items.length ? Math.round((completed / items.length) * 100) + '%' : '0%';
        var listEl = document.getElementById('onboarding-items-list');
        if (listEl) {
            listEl.innerHTML = '';
            items.forEach(function(item) {
                var checkedAttr = item.is_completed ? 'checked' : '';
                var style = item.is_completed ? 'text-decoration:line-through;color:var(--text-secondary);' : '';
                listEl.insertAdjacentHTML('beforeend', '<label style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-color);cursor:pointer;font-size:0.9rem;' + style + '"><input type="checkbox" ' + checkedAttr + ' onchange="toggleOnbItem(' + item.id + ', this.checked)" style="margin-top:4px;accent-color:var(--primary-color);"><div><div style="font-weight:500;">' + esc(item.title) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(item.category || '') + ' &bull; ' + esc(item.assigned_to || '') + '</div></div></label>');
            });
        }

        // Payslips
        var payslips = emp.payslips || [];
        var totalPaid = payslips.filter(function(p) { return p.status === 'Paid'; }).reduce(function(s, p) { return s + (p.net_pay || 0); }, 0);
        var totalPaidEl = document.getElementById('emp-total-paid');
        if (totalPaidEl) totalPaidEl.textContent = formatCurrency(totalPaid);
        var psCountEl = document.getElementById('emp-payslip-count');
        if (psCountEl) psCountEl.textContent = payslips.length;
        var psListEl = document.getElementById('emp-payslips-list');
        if (psListEl) {
            psListEl.innerHTML = '';
            if (payslips.length === 0) {
                psListEl.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-secondary);font-size:0.85rem;">No payslips yet</div>';
            } else {
                payslips.forEach(function(p) {
                    var statusClass = (p.status || '').toLowerCase();
                    psListEl.insertAdjacentHTML('beforeend', '<div style="padding:12px 16px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;cursor:pointer;" onclick="viewPayslip(' + p.id + ')"><div><div style="font-weight:500;font-size:0.9rem;">' + esc(p.number) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(p.period_start) + ' to ' + esc(p.period_end) + '</div></div><div style="text-align:right;"><div style="font-weight:600;font-size:0.9rem;">' + formatCurrency(p.net_pay) + '</div><span class="status-pill status-' + statusClass + '" style="font-size:0.7rem;">' + esc(p.status) + '</span></div></div>');
                });
            }
        }

        showView('employee-detail-view');
        loadEmpGoals(empId);
        loadEmpDocs(empId);
    } catch (e) {
        showToast('Failed to load employee', 'error');
    }
}
window.viewEmployee = viewEmployee;

// --- Add Employee Modal ---
async function showAddEmployeeModal() {
    document.getElementById('add-employee-modal').style.display = 'flex';
    document.getElementById('add-employee-form').reset();
    var today = localDate(new Date());
    var startEl = document.getElementById('emp-start-date');
    if (startEl) startEl.value = today;
    // Load departments and employees for dropdowns
    try {
        var deptRes = await fetch('/api/departments');
        var depts = await deptRes.json();
        var deptSel = document.getElementById('emp-department');
        deptSel.innerHTML = '<option value="">None</option>';
        depts.forEach(function(d) { deptSel.insertAdjacentHTML('beforeend', '<option value="' + d.id + '">' + esc(d.name) + '</option>'); });
        var empRes = await fetch('/api/employees');
        var emps = await empRes.json();
        var mgrSel = document.getElementById('emp-reports-to');
        mgrSel.innerHTML = '<option value="">None</option>';
        emps.forEach(function(e) { mgrSel.insertAdjacentHTML('beforeend', '<option value="' + e.id + '">' + esc(e.first_name) + ' ' + esc(e.last_name) + '</option>'); });
        await populateLevelRoleSelects('emp-level', 'emp-role');
    } catch (e) { console.error(e); }
}
window.showAddEmployeeModal = showAddEmployeeModal;

// --- Seniority levels and reporting roles ---------------------------------
// The catalogue is served by the API so the vocabulary has one definition
// rather than being duplicated in every picker.
var _hrLevels = null;

async function loadHrLevels() {
    if (_hrLevels) return _hrLevels;
    try {
        var res = await fetch('/api/hr/levels');
        if (!res.ok) return { levels: [], roles: [] };
        _hrLevels = await res.json();
    } catch (e) { _hrLevels = { levels: [], roles: [] }; }
    return _hrLevels;
}
window.loadHrLevels = loadHrLevels;

async function populateLevelRoleSelects(levelId, roleId, currentLevel, currentRole) {
    var data = await loadHrLevels();
    var lvlSel = document.getElementById(levelId);
    if (lvlSel) {
        lvlSel.innerHTML = '<option value="">Not set</option>';
        (data.levels || []).forEach(function (l) {
            lvlSel.insertAdjacentHTML('beforeend',
                '<option value="' + esc(l.code) + '">' + esc(l.label) + '</option>');
        });
        if (currentLevel) lvlSel.value = currentLevel;
    }
    var roleSel = document.getElementById(roleId);
    if (roleSel) {
        roleSel.innerHTML = '';
        (data.roles || []).forEach(function (r) {
            roleSel.insertAdjacentHTML('beforeend',
                '<option value="' + esc(r.code) + '">' + esc(r.label) + '</option>');
        });
        roleSel.value = currentRole || 'employee';
    }
}
window.populateLevelRoleSelects = populateLevelRoleSelects;

// Compact badge used in the employee list and org chart.
function levelBadge(level) {
    if (!level) return '';
    return '<span style="display:inline-block;padding:2px 7px;border-radius:5px;font-size:0.7rem;' +
           'font-weight:700;background:rgba(0,240,255,0.15);color:var(--primary-color);' +
           'margin-left:6px;">' + esc(level) + '</span>';
}
window.levelBadge = levelBadge;

function roleLabel(code) {
    var roles = (_hrLevels && _hrLevels.roles) || [];
    for (var i = 0; i < roles.length; i++) if (roles[i].code === code) return roles[i].label;
    return code || 'Employee';
}
window.roleLabel = roleLabel;

function closeAddEmployeeModal() {
    document.getElementById('add-employee-modal').style.display = 'none';
}
window.closeAddEmployeeModal = closeAddEmployeeModal;

async function submitNewEmployee() {
    var firstName = document.getElementById('emp-first-name').value.trim();
    var lastName = document.getElementById('emp-last-name').value.trim();
    var email = document.getElementById('emp-email').value.trim();
    if (!firstName || !lastName || !email) { showToast('First name, last name, and email are required', 'error'); return; }
    var password = document.getElementById('emp-password').value.trim();
    if (!password) { showToast('Password is required for employee login', 'error'); return; }
    var deptVal = document.getElementById('emp-department').value;
    var mgrVal = document.getElementById('emp-reports-to').value;
    var payload = {
        first_name: firstName, last_name: lastName, email: email,
        password: password,
        phone: document.getElementById('emp-phone').value,
        job_title: document.getElementById('emp-job-title').value,
        department_id: deptVal ? parseInt(deptVal) : null,
        reports_to: mgrVal ? parseInt(mgrVal) : null,
        level: (document.getElementById('emp-level') || {}).value || '',
        role: (document.getElementById('emp-role') || {}).value || 'employee',
        employment_type: document.getElementById('emp-type').value,
        pay_frequency: document.getElementById('emp-pay-freq').value,
        salary: parseFloat(document.getElementById('emp-salary').value) || 0,
        tax_rate: parseFloat(document.getElementById('emp-tax-rate').value) || 0,
        start_date: document.getElementById('emp-start-date').value,
        emergency_contact: document.getElementById('emp-emergency-contact').value,
        emergency_phone: document.getElementById('emp-emergency-phone').value,
    };
    try {
        var res = await fetch('/api/employees', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Employee created', 'success');
            if (window._aiOnboardingItems && window._aiOnboardingItems.length && data.id) {
                try {
                    await fetch('/api/employees/' + data.id + '/onboarding/bulk', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ items: window._aiOnboardingItems })
                    });
                } catch(e) { console.error('Failed to save AI onboarding items:', e); }
                window._aiOnboardingItems = null;
            }
            closeAddEmployeeModal();
            hrDataChanged('employees');
        } else {
            showToast('Failed: ' + (data.detail || 'Error'), 'error');
        }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.submitNewEmployee = submitNewEmployee;

async function startOffboarding() {
    if (!currentEmployeeId) return;
    if (!confirm('Start offboarding for this employee?')) return;
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId + '/offboard', { method: 'POST' });
        if (res.ok) { showToast('Offboarding started', 'success'); hrDataChanged('employees', { employeeId: currentEmployeeId }); }
        else { var data = await res.json(); showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.startOffboarding = startOffboarding;

async function resetEmpPassword() {
    if (!currentEmployeeId) return;
    var newPass = prompt('Enter new password for this employee:');
    if (!newPass || newPass.length < 4) { showToast('Password must be at least 4 characters', 'error'); return; }
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId + '/reset-password', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPass })
        });
        var data = await res.json();
        if (res.ok) { showToast('Password updated', 'success'); }
        else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.resetEmpPassword = resetEmpPassword;

// --- Employee Edit ---
var _currentEmployee = null;
var _empEditOriginal = {};
function toggleEmpEdit() {
    var editBtn = document.getElementById('emp-edit-btn');
    var saveBtn = document.getElementById('emp-save-btn');
    var cancelBtn = document.getElementById('emp-cancel-edit-btn');
    if (editBtn) editBtn.style.display = 'none';
    if (saveBtn) saveBtn.style.display = 'inline-flex';
    if (cancelBtn) cancelBtn.style.display = 'inline-flex';
    _empEditOriginal = {};
    var fields = ['phone', 'title', 'dept', 'mgr', 'level', 'role', 'type', 'payfreq', 'salary', 'start', 'taxrate', 'emergency'];
    var inputIds = ['emp-detail-phone', 'emp-detail-title', 'emp-detail-dept', 'emp-detail-mgr', 'emp-detail-level', 'emp-detail-role', 'emp-detail-type', 'emp-detail-payfreq', 'emp-detail-salary', 'emp-detail-start', 'emp-detail-taxrate', 'emp-detail-emergency'];
    var roIds = ['emp-detail-phone-ro', 'emp-detail-title-ro', 'emp-detail-dept-ro', 'emp-detail-mgr-ro', 'emp-detail-level-ro', 'emp-detail-role-ro', 'emp-detail-type-ro', 'emp-detail-payfreq-ro', 'emp-detail-salary-ro', 'emp-detail-start-ro', 'emp-detail-taxrate-ro', 'emp-detail-emergency-ro'];
    fields.forEach(function(f, i) {
        var input = document.getElementById(inputIds[i]);
        var ro = document.getElementById(roIds[i]);
        if (input && ro) {
            _empEditOriginal[f] = ro.textContent;
            input.style.display = 'block';
            ro.style.display = 'none';
        }
    });
    loadEmpEditDropdowns();
    // Preselect the employee's current band/role once the options exist.
    populateLevelRoleSelects('emp-detail-level', 'emp-detail-role',
        _currentEmployee && _currentEmployee.level, _currentEmployee && _currentEmployee.role);
}
window.toggleEmpEdit = toggleEmpEdit;

async function loadEmpEditDropdowns() {
    try {
        var res = await fetch('/api/employees');
        var emps = await res.json();
        var deptRes = await fetch('/api/departments');
        var depts = await deptRes.json();
        var deptSel = document.getElementById('emp-detail-dept');
        var mgrSel = document.getElementById('emp-detail-mgr');
        if (deptSel) {
            deptSel.innerHTML = '<option value="">None</option>';
            depts.forEach(function(d) { deptSel.innerHTML += '<option value="' + d.id + '">' + esc(d.name) + '</option>'; });
            var currentDept = document.getElementById('emp-detail-dept-ro').textContent;
            deptSel.value = '';
        }
        if (mgrSel) {
            mgrSel.innerHTML = '<option value="">None</option>';
            emps.forEach(function(e) { mgrSel.innerHTML += '<option value="' + e.id + '">' + esc(e.first_name + ' ' + e.last_name) + '</option>'; });
        }
    } catch(e) { console.error('Failed to load edit dropdowns:', e); }
}

async function saveEmpEdit() {
    if (!currentEmployeeId) return;
    var payload = {
        phone: document.getElementById('emp-detail-phone').value,
        job_title: document.getElementById('emp-detail-title').value,
        department_id: document.getElementById('emp-detail-dept').value ? parseInt(document.getElementById('emp-detail-dept').value) : null,
        reports_to: document.getElementById('emp-detail-mgr').value ? parseInt(document.getElementById('emp-detail-mgr').value) : null,
        employment_type: document.getElementById('emp-detail-type').value,
        pay_frequency: document.getElementById('emp-detail-payfreq').value,
        salary: parseFloat(document.getElementById('emp-detail-salary').value) || 0,
        start_date: document.getElementById('emp-detail-start').value,
        tax_rate: parseFloat(document.getElementById('emp-detail-taxrate').value) || 0,
        emergency_contact: document.getElementById('emp-detail-emergency').value,
        level: (document.getElementById('emp-detail-level') || {}).value || '',
        role: (document.getElementById('emp-detail-role') || {}).value || 'employee',
    };
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json().catch(function () { return {}; });
        // Surface the server's reason (bad level, reporting loop) rather than
        // a generic failure.
        if (res.ok) { showToast('Employee updated', 'success'); cancelEmpEdit(); hrDataChanged('employees', { employeeId: currentEmployeeId }); }
        else { showToast(data.detail || 'Failed to update', 'error'); }
    } catch(e) { showToast('Error', 'error'); }
}
window.saveEmpEdit = saveEmpEdit;

function cancelEmpEdit() {
    var el;
    el = document.getElementById('emp-edit-btn'); if (el) el.style.display = 'inline-flex';
    el = document.getElementById('emp-save-btn'); if (el) el.style.display = 'none';
    el = document.getElementById('emp-cancel-edit-btn'); if (el) el.style.display = 'none';
    var inputIds = ['emp-detail-phone', 'emp-detail-title', 'emp-detail-dept', 'emp-detail-mgr', 'emp-detail-level', 'emp-detail-role', 'emp-detail-type', 'emp-detail-payfreq', 'emp-detail-salary', 'emp-detail-start', 'emp-detail-taxrate', 'emp-detail-emergency'];
    var roIds = ['emp-detail-phone-ro', 'emp-detail-title-ro', 'emp-detail-dept-ro', 'emp-detail-mgr-ro', 'emp-detail-level-ro', 'emp-detail-role-ro', 'emp-detail-type-ro', 'emp-detail-payfreq-ro', 'emp-detail-salary-ro', 'emp-detail-start-ro', 'emp-detail-taxrate-ro', 'emp-detail-emergency-ro'];
    inputIds.forEach(function(id, i) {
        var input = document.getElementById(id);
        var ro = document.getElementById(roIds[i]);
        if (input) input.style.display = 'none';
        if (ro) ro.style.display = 'inline';
    });
}
window.cancelEmpEdit = cancelEmpEdit;

// --- Password Reset Modal ---
function showResetPasswordModal() {
    document.getElementById('reset-pass-input').value = '';
    document.getElementById('reset-password-modal').style.display = 'flex';
    document.getElementById('reset-pass-input').focus();
}
window.showResetPasswordModal = showResetPasswordModal;

async function confirmResetPassword() {
    if (!currentEmployeeId) return;
    var pass = document.getElementById('reset-pass-input').value.trim();
    if (!pass || pass.length < 4) { showToast('Password must be at least 4 characters', 'error'); return; }
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId + '/reset-password', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pass })
        });
        var data = await res.json();
        if (res.ok) { showToast('Password updated', 'success'); document.getElementById('reset-password-modal').style.display = 'none'; }
        else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch(e) { showToast('Error', 'error'); }
}
window.confirmResetPassword = confirmResetPassword;

async function deleteCurrentEmployee() {
    if (!currentEmployeeId) return;
    if (!confirm('Delete this employee and all related data?')) return;
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId, { method: 'DELETE' });
        if (res.ok) { showToast('Employee deleted', 'success'); showView('employees-view'); hrDataChanged('employees'); }
        else { var data = await res.json(); showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.deleteCurrentEmployee = deleteCurrentEmployee;

// --- Departments ---
var deptIcons = [
    { id: 'building', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="22" x2="9" y2="17"/><line x1="15" y1="22" x2="15" y2="17"/><line x1="9" y1="12" x2="9" y2="12.01"/><line x1="15" y1="12" x2="15" y2="12.01"/><line x1="9" y1="8" x2="9" y2="8.01"/><line x1="15" y1="8" x2="15" y2="8.01"/><line x1="9" y1="17" x2="9" y2="22"/><line x1="15" y1="17" x2="15" y2="22"/></svg>' },
    { id: 'code', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>' },
    { id: 'users', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' },
    { id: 'chart', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>' },
    { id: 'star', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>' },
    { id: 'shield', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>' },
    { id: 'heart', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>' },
    { id: 'rocket', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/></svg>' },
];
var deptColors = ['#00f0ff','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#f97316','#06b6d4','#84cc16','#6366f1'];
var editingDeptId = null;
var selectedDeptColor = '#00f0ff';
var selectedDeptIcon = 'building';

var allDepartments = [];
async function fetchDepartments() {
    try {
        var res = await fetch('/api/departments');
        if (!res.ok) throw new Error('Failed');
        allDepartments = await res.json();
        renderDepartments(allDepartments);
    } catch (e) {
        var grid = document.getElementById('dept-cards-grid');
        if (grid) grid.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">Failed to load departments.</div>';
    }
}

function renderDepartments(depts) {
    var grid = document.getElementById('dept-cards-grid');
    var empty = document.getElementById('dept-empty');
    if (!grid) return;
    grid.innerHTML = '';
    if (depts.length === 0) {
        if (empty) empty.style.display = 'block';
        grid.style.display = 'none';
        return;
    }
    if (empty) empty.style.display = 'none';
    grid.style.display = 'grid';
    depts.forEach(function(d) {
        var iconObj = deptIcons.find(function(i) { return i.id === d.icon; }) || deptIcons[0];
        var color = d.color || '#00f0ff';
        grid.insertAdjacentHTML('beforeend',
            '<div class="dept-card" onclick="openDeptDetail(' + d.id + ')" style="background:var(--surface-color);border:1px solid var(--border-color);border-radius:var(--radius-lg);padding:24px;cursor:pointer;transition:all 0.2s;border-top:3px solid ' + color + ';">' +
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
                    '<div style="width:44px;height:44px;border-radius:12px;background:' + color + '20;color:' + color + ';display:flex;align-items:center;justify-content:center;">' + iconObj.svg + '</div>' +
                    '<div><div style="font-weight:600;font-size:1rem;">' + esc(d.name) + '</div>' +
                    '<div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(d.description || 'No description') + '</div></div>' +
                '</div>' +
                '<div style="display:flex;align-items:center;gap:8px;">' +
                    '<div style="width:32px;height:32px;border-radius:8px;background:rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;font-size:0.85rem;font-weight:600;">' + (d.employee_count || 0) + '</div>' +
                    '<div style="font-size:0.82rem;color:var(--text-secondary);">' + (d.employee_count === 1 ? 'employee' : 'employees') + '</div>' +
                '</div>' +
                '</div>'
            );
        });
}

function searchDepts() {
    var q = (document.getElementById('dept-search').value || '').toLowerCase();
    var filtered = allDepartments.filter(function(d) {
        if (!q) return true;
        return (d.name || '').toLowerCase().includes(q) || (d.description || '').toLowerCase().includes(q);
    });
    renderDepartments(filtered);
}
window.searchDepts = searchDepts;

function openDeptModal(dept) {
    editingDeptId = dept ? dept.id : null;
    document.getElementById('dept-modal-title').textContent = dept ? 'Edit Department' : 'Add Department';
    document.getElementById('dept-name').value = dept ? dept.name : '';
    document.getElementById('dept-desc').value = dept ? (dept.description || '') : '';
    selectedDeptColor = dept ? (dept.color || '#00f0ff') : '#00f0ff';
    selectedDeptIcon = dept ? (dept.icon || 'building') : 'building';
    renderDeptColorPicker();
    renderDeptIconPicker();
    document.getElementById('dept-modal').style.display = 'flex';
}
window.openDeptModal = openDeptModal;

function closeDeptModal() {
    document.getElementById('dept-modal').style.display = 'none';
    editingDeptId = null;
}
window.closeDeptModal = closeDeptModal;

function renderDeptColorPicker() {
    var el = document.getElementById('dept-color-picker');
    el.innerHTML = '';
    deptColors.forEach(function(c) {
        el.insertAdjacentHTML('beforeend',
            '<div onclick="selectDeptColor(\'' + c + '\')" style="width:32px;height:32px;border-radius:8px;background:' + c + ';cursor:pointer;border:3px solid ' + (c === selectedDeptColor ? 'white' : 'transparent') + ';transition:border 0.15s;"></div>'
        );
    });
}
window.renderDeptColorPicker = renderDeptColorPicker;

function selectDeptColor(c) {
    selectedDeptColor = c;
    renderDeptColorPicker();
}
window.selectDeptColor = selectDeptColor;

function renderDeptIconPicker() {
    var el = document.getElementById('dept-icon-picker');
    el.innerHTML = '';
    deptIcons.forEach(function(i) {
        var isSelected = i.id === selectedDeptIcon;
        el.insertAdjacentHTML('beforeend',
            '<div onclick="selectDeptIcon(\'' + i.id + '\')" style="width:36px;height:36px;border-radius:8px;background:' + (isSelected ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.05)') + ';display:flex;align-items:center;justify-content:center;cursor:pointer;border:2px solid ' + (isSelected ? selectedDeptColor : 'transparent') + ';transition:all 0.15s;">' + i.svg + '</div>'
        );
    });
}
window.renderDeptIconPicker = renderDeptIconPicker;

function selectDeptIcon(id) {
    selectedDeptIcon = id;
    renderDeptIconPicker();
}
window.selectDeptIcon = selectDeptIcon;

async function saveDept() {
    var name = document.getElementById('dept-name').value.trim();
    if (!name) { showToast('Department name is required', 'error'); return; }
    var desc = document.getElementById('dept-desc').value.trim();
    var payload = { name: name, description: desc, color: selectedDeptColor, icon: selectedDeptIcon };
    try {
        var url = editingDeptId ? '/api/departments/' + editingDeptId : '/api/departments';
        var method = editingDeptId ? 'PUT' : 'POST';
        var res = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        var data = await res.json();
        if (res.ok) { showToast(editingDeptId ? 'Department updated' : 'Department created', 'success'); closeDeptModal(); hrDataChanged('departments'); }
        else { showToast(data.detail || 'Error', 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.saveDept = saveDept;

var currentDeptDetailId = null;
async function openDeptDetail(id) {
    currentDeptDetailId = id;
    try {
        var res = await fetch('/api/departments/' + id);
        if (!res.ok) throw new Error('Failed');
        var d = await res.json();
        var iconObj = deptIcons.find(function(i) { return i.id === d.icon; }) || deptIcons[0];
        document.getElementById('dept-detail-icon').innerHTML = iconObj.svg;
        document.getElementById('dept-detail-icon').style.background = d.color + '20';
        document.getElementById('dept-detail-icon').style.color = d.color;
        document.getElementById('dept-detail-name').textContent = d.name;
        document.getElementById('dept-detail-desc').textContent = d.description || 'No description';
        document.getElementById('dept-detail-edit-btn').onclick = function() { closeDeptDetail(); openDeptModal(d); };
        document.getElementById('dept-detail-stats').innerHTML =
            '<div style="background:rgba(255,255,255,0.04);border-radius:10px;padding:14px;"><div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:4px;">Team Size</div><div style="font-size:1.4rem;font-weight:700;">' + d.employee_count + '</div></div>' +
            '<div style="background:rgba(255,255,255,0.04);border-radius:10px;padding:14px;"><div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:4px;">Created</div><div style="font-size:0.85rem;font-weight:500;">' + (d.created_at || 'Unknown').split(' ')[0] + '</div></div>';
        var empList = document.getElementById('dept-detail-employees');
        empList.innerHTML = '';
        if (d.employees.length === 0) {
            empList.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-secondary);font-size:0.85rem;">No employees in this department</div>';
        } else {
            d.employees.forEach(function(e) {
                var initial = (e.name || '?')[0].toUpperCase();
                empList.insertAdjacentHTML('beforeend',
                    '<div onclick="closeDeptDetail();viewEmployee(' + e.id + ')" style="display:flex;align-items:center;gap:12px;padding:10px;border-radius:8px;cursor:pointer;transition:background 0.15s;border-bottom:1px solid var(--border-color);">' +
                        '<div style="width:36px;height:36px;border-radius:8px;background:linear-gradient(135deg,' + d.color + '40,' + d.color + '20);color:' + d.color + ';display:flex;align-items:center;justify-content:center;font-weight:600;font-size:0.85rem;">' + initial + '</div>' +
                        '<div><div style="font-weight:500;font-size:0.9rem;">' + esc(e.name) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(e.job_title || '') + '</div></div>' +
                    '</div>'
                );
            });
        }
        document.getElementById('dept-detail-panel').style.display = 'flex';
    } catch (e) { showToast('Failed to load department', 'error'); }
}
window.openDeptDetail = openDeptDetail;

function closeDeptDetail() {
    document.getElementById('dept-detail-panel').style.display = 'none';
}
window.closeDeptDetail = closeDeptDetail;

async function deleteDepartment(id, name) {
    if (!confirm('Delete department "' + name + '"? Employees will be unassigned.')) return;
    try {
        var res = await fetch('/api/departments/' + id, { method: 'DELETE' });
        if (res.ok) { showToast('Department deleted', 'success'); hrDataChanged('departments'); }
        else { var data = await res.json(); showToast(data.detail || 'Error', 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.deleteDepartment = deleteDepartment;

// --- Onboarding Hub ---
var onboardingHubData = [];
var onboardingHubFilter = 'all';
var onboardingBulkItems = [];

async function loadOnboardingHub() {
    try {
        var res = await fetch('/api/onboarding/hub');
        if (!res.ok) throw new Error('Failed');
        onboardingHubData = await res.json();
        renderOnboardingHub();
    } catch (e) { console.error('Onboarding hub error:', e); }
}

function renderOnboardingHub() {
    var data = onboardingHubData;
    if (onboardingHubFilter === 'onboarding') data = data.filter(function(e) { return e.status === 'onboarding' && e.progress < 100; });
    else if (onboardingHubFilter === 'complete') data = data.filter(function(e) { return e.progress === 100; });
    else if (onboardingHubFilter === 'overdue') data = data.filter(function(e) { return e.overdue > 0; });

    var totalEmps = onboardingHubData.length;
    var inProgress = onboardingHubData.filter(function(e) { return e.status === 'onboarding' && e.progress < 100; }).length;
    var completed = onboardingHubData.filter(function(e) { return e.progress === 100; }).length;
    var overdue = onboardingHubData.filter(function(e) { return e.overdue > 0; }).length;

    document.getElementById('onboarding-hub-stats').innerHTML =
        '<div class="widget" style="padding:20px;"><div style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:8px;">Total</div><div style="font-size:1.5rem;font-weight:700;">' + totalEmps + '</div></div>' +
        '<div class="widget" style="padding:20px;"><div style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:8px;">In Progress</div><div style="font-size:1.5rem;font-weight:700;color:var(--primary-color);">' + inProgress + '</div></div>' +
        '<div class="widget" style="padding:20px;"><div style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:8px;">Completed</div><div style="font-size:1.5rem;font-weight:700;color:var(--success-color);">' + completed + '</div></div>' +
        '<div class="widget" style="padding:20px;"><div style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:8px;">Overdue</div><div style="font-size:1.5rem;font-weight:700;color:var(--danger-color);">' + overdue + '</div></div>';

    var list = document.getElementById('onboarding-hub-list');
    var empty = document.getElementById('onboarding-hub-empty');
    if (!list) return;
    list.innerHTML = '';
    if (data.length === 0) {
        if (empty) empty.style.display = 'block';
        return;
    }
    if (empty) empty.style.display = 'none';

    data.forEach(function(e) {
        var barColor = e.progress === 100 ? 'var(--success-color)' : e.overdue > 0 ? 'var(--danger-color)' : 'var(--primary-color)';
        list.insertAdjacentHTML('beforeend',
            '<div class="widget" style="padding:16px 20px;margin-bottom:12px;cursor:pointer;" onclick="openOnbEmpDetail(' + e.id + ')">' +
                '<div style="display:flex;align-items:center;gap:16px;">' +
                    '<div style="width:42px;height:42px;border-radius:10px;background:rgba(0,240,255,0.1);color:var(--primary-color);display:flex;align-items:center;justify-content:center;font-weight:600;">' + (e.name || '?')[0].toUpperCase() + '</div>' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">' +
                            '<span style="font-weight:600;font-size:0.95rem;">' + esc(e.name) + '</span>' +
                            '<span style="font-size:0.75rem;padding:2px 8px;border-radius:6px;background:rgba(255,255,255,0.08);color:var(--text-secondary);">' + esc(e.department || 'No dept') + '</span>' +
                            (e.overdue > 0 ? '<span style="font-size:0.72rem;padding:2px 8px;border-radius:6px;background:rgba(239,68,68,0.15);color:var(--danger-color);">' + e.overdue + ' overdue</span>' : '') +
                        '</div>' +
                        '<div style="display:flex;align-items:center;gap:12px;">' +
                            '<div style="flex:1;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;">' +
                                '<div style="height:100%;width:' + e.progress + '%;background:' + barColor + ';border-radius:3px;transition:width 0.4s;"></div>' +
                            '</div>' +
                            '<span style="font-size:0.82rem;font-weight:600;color:' + barColor + ';">' + e.completed + '/' + e.total + '</span>' +
                        '</div>' +
                    '</div>' +
                    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>' +
                '</div>' +
            '</div>'
        );
    });
}

function filterOnboardingHub(filter, btn) {
    onboardingHubFilter = filter;
    document.querySelectorAll('#onboarding-hub-view .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    renderOnboardingHub();
}
window.filterOnboardingHub = filterOnboardingHub;

async function openOnbEmpDetail(empId) {
    try {
        var [empRes, onbRes] = await Promise.all([
            fetch('/api/employees').then(function(r) { return r.ok ? r.json() : []; }),
            fetch('/api/employees/' + empId + '/onboarding').then(function(r) { return r.ok ? r.json() : { items: [], progress: 0 }; })
        ]);
        var emp = empRes.find(function(e) { return e.id === empId; });
        if (!emp) return;
        document.getElementById('onb-emp-name').textContent = (emp.first_name + ' ' + emp.last_name).trim();
        document.getElementById('onb-emp-meta').textContent = (emp.job_title || '') + (emp.department_name ? ' • ' + emp.department_name : '');
        var items = onbRes.items || [];
        var completed = items.filter(function(i) { return i.is_completed; }).length;
        var pct = items.length ? Math.round((completed / items.length) * 100) : 0;
        var barColor = pct === 100 ? 'var(--success-color)' : 'var(--primary-color)';
        document.getElementById('onb-emp-progress').innerHTML =
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">' +
                '<span style="font-size:0.85rem;color:var(--text-secondary);">Progress</span>' +
                '<span style="font-weight:600;color:' + barColor + ';">' + pct + '% (' + completed + '/' + items.length + ')</span>' +
            '</div>' +
            '<div style="height:8px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden;">' +
                '<div style="height:100%;width:' + pct + '%;background:' + barColor + ';border-radius:4px;transition:width 0.4s;"></div>' +
            '</div>';
        var list = document.getElementById('onb-emp-items');
        list.innerHTML = '';
        var categories = {};
        items.forEach(function(i) {
            var cat = i.category || 'General';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(i);
        });
        for (var cat in categories) {
            list.insertAdjacentHTML('beforeend', '<div style="font-weight:600;font-size:0.82rem;color:var(--text-secondary);margin:12px 0 6px;text-transform:uppercase;letter-spacing:0.5px;">' + cat + '</div>');
            categories[cat].forEach(function(item) {
                var isOverdue = !item.is_completed && item.due_date && item.due_date < localDate(new Date());
                list.insertAdjacentHTML('beforeend',
                    '<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:6px;background:rgba(255,255,255,0.02);">' +
                        '<input type="checkbox" ' + (item.is_completed ? 'checked' : '') + ' onchange="toggleOnbItem(' + item.id + ', this.checked)" style="accent-color:var(--primary-color);cursor:pointer;">' +
                        '<div style="flex:1;min-width:0;">' +
                            '<div style="font-size:0.9rem;' + (item.is_completed ? 'text-decoration:line-through;color:var(--text-secondary);' : '') + '">' + item.title + '</div>' +
                            '<div style="font-size:0.75rem;color:var(--text-secondary);">' + (item.assigned_to || '') + (item.due_date ? ' • Due ' + item.due_date : '') + (isOverdue ? ' <span style="color:var(--danger-color);">OVERDUE</span>' : '') + '</div>' +
                        '</div>' +
                        '<button onclick="deleteOnbItem(' + item.id + ')" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:4px;" title="Delete">' +
                            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
                        '</button>' +
                    '</div>'
                );
            });
        }
        if (items.length === 0) {
            list.innerHTML = '<div style="text-align:center;padding:32px;color:var(--text-secondary);">No onboarding items yet. Click "+ Add Item" to get started.</div>';
        }
        document.getElementById('onb-emp-modal').dataset.empId = empId;
        document.getElementById('onb-emp-modal').style.display = 'flex';
    } catch (e) { showToast('Failed to load details', 'error'); }
}
window.openOnbEmpDetail = openOnbEmpDetail;

function closeOnbEmpModal() {
    document.getElementById('onb-emp-modal').style.display = 'none';
}
window.closeOnbEmpModal = closeOnbEmpModal;

async function toggleOnbItem(itemId, isCompleted) {
    try {
        await fetch('/api/onboarding/' + itemId, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_completed: isCompleted }) });
        var empId = document.getElementById('onb-emp-modal').dataset.empId;
        if (empId) openOnbEmpDetail(parseInt(empId));
        loadOnboardingHub();
    } catch (e) { showToast('Failed to update', 'error'); }
}
window.toggleOnbItem = toggleOnbItem;

async function deleteOnbItem(itemId) {
    if (!confirm('Delete this item?')) return;
    try {
        await fetch('/api/onboarding/' + itemId, { method: 'DELETE' });
        var empId = document.getElementById('onb-emp-modal').dataset.empId;
        if (empId) openOnbEmpDetail(parseInt(empId));
        loadOnboardingHub();
    } catch (e) { showToast('Failed to delete', 'error'); }
}
window.deleteOnbItem = deleteOnbItem;

async function addOnbItemToEmp() {
    var empId = document.getElementById('onb-emp-modal').dataset.empId;
    if (!empId) return;
    var title = prompt('Task title:');
    if (!title) return;
    var category = prompt('Category (e.g. Legal, IT, General):') || 'General';
    var assignee = prompt('Assigned to:') || '';
    var dueDate = prompt('Due date (YYYY-MM-DD, optional):') || '';
    try {
        await fetch('/api/employees/' + empId + '/onboarding', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title, category: category, assigned_to: assignee, due_date: dueDate })
        });
        openOnbEmpDetail(parseInt(empId));
        loadOnboardingHub();
    } catch (e) { showToast('Failed to add item', 'error'); }
}
window.addOnbItemToEmp = addOnbItemToEmp;

async function showBulkOnboardModal() {
    try {
        var res = await fetch('/api/employees?status=onboarding');
        var emps = await res.json();
        var select = document.getElementById('bulk-emp-select');
        select.innerHTML = '';
        emps.forEach(function(e) {
            select.insertAdjacentHTML('beforeend',
                '<label style="display:flex;align-items:center;gap:8px;padding:8px;border-radius:6px;cursor:pointer;transition:background 0.15s;">' +
                    '<input type="checkbox" value="' + e.id + '" class="bulk-emp-check" style="accent-color:var(--primary-color);">' +
                    '<span style="font-size:0.9rem;">' + (e.first_name + ' ' + e.last_name).trim() + '</span>' +
                    '<span style="font-size:0.75rem;color:var(--text-secondary);">' + (e.department_name || '') + '</span>' +
                '</label>'
            );
        });
        if (emps.length === 0) {
            select.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-secondary);">No onboarding employees found</div>';
        }
        onboardingBulkItems = [];
        document.getElementById('bulk-items-preview').style.display = 'none';
        document.getElementById('bulk-onboard-modal').style.display = 'flex';
    } catch (e) { showToast('Failed to load employees', 'error'); }
}
window.showBulkOnboardModal = showBulkOnboardModal;

function closeBulkOnboardModal() {
    document.getElementById('bulk-onboard-modal').style.display = 'none';
}
window.closeBulkOnboardModal = closeBulkOnboardModal;

function loadBulkDefault() {
    onboardingBulkItems = [
        { title: 'Sign employment contract', category: 'Legal', assigned_to: 'HR' },
        { title: 'Provide government-issued ID', category: 'Legal', assigned_to: 'HR' },
        { title: 'Submit bank details for payroll', category: 'Finance', assigned_to: 'Finance' },
        { title: 'Provide emergency contact information', category: 'General', assigned_to: 'HR' },
        { title: 'Company policy acknowledgment', category: 'Compliance', assigned_to: 'HR' },
        { title: 'IT equipment setup', category: 'Technical', assigned_to: 'IT' },
        { title: 'Email and system access setup', category: 'Technical', assigned_to: 'IT' },
        { title: 'Introduction to team members', category: 'Social', assigned_to: 'Manager' },
        { title: 'Complete tax withholding forms', category: 'Finance', assigned_to: 'Finance' },
        { title: 'Review employee handbook', category: 'Compliance', assigned_to: 'HR' },
    ];
    renderBulkItemsPreview();
}
window.loadBulkDefault = loadBulkDefault;

async function loadBulkFromTemplate() {
    try {
        var res = await fetch('/api/onboarding/templates');
        var templates = await res.json();
        if (templates.length === 0) { showToast('No templates found. Create one first.', 'error'); return; }
        var names = templates.map(function(t, i) { return (i + 1) + '. ' + t.name; }).join('\n');
        var choice = prompt('Choose template:\n' + names + '\nEnter number:');
        if (!choice) return;
        var idx = parseInt(choice) - 1;
        if (idx >= 0 && idx < templates.length) {
            onboardingBulkItems = templates[idx].items || [];
            renderBulkItemsPreview();
        }
    } catch (e) { showToast('Failed to load templates', 'error'); }
}
window.loadBulkFromTemplate = loadBulkFromTemplate;

function renderBulkItemsPreview() {
    var preview = document.getElementById('bulk-items-preview');
    var list = document.getElementById('bulk-items-list');
    preview.style.display = 'block';
    list.innerHTML = '';
    onboardingBulkItems.forEach(function(item) {
        list.insertAdjacentHTML('beforeend',
            '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;font-size:0.85rem;border-bottom:1px solid var(--border-color);">' +
                '<span style="color:var(--primary-color);">&#10003;</span>' +
                '<span style="flex:1;">' + esc(item.title) + '</span>' +
                '<span style="font-size:0.72rem;color:var(--text-secondary);">' + esc(item.category || '') + '</span>' +
            '</div>'
        );
    });
}
window.renderBulkItemsPreview = renderBulkItemsPreview;

async function applyBulkOnboard() {
    var empIds = [];
    document.querySelectorAll('.bulk-emp-check:checked').forEach(function(cb) { empIds.push(parseInt(cb.value)); });
    if (empIds.length === 0) { showToast('Select at least one employee', 'error'); return; }
    if (onboardingBulkItems.length === 0) { showToast('Load a checklist first', 'error'); return; }
    try {
        var res = await fetch('/api/onboarding/apply-template', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employee_ids: empIds, items: onboardingBulkItems })
        });
        var data = await res.json();
        if (res.ok) { showToast(data.message, 'success'); closeBulkOnboardModal(); loadOnboardingHub(); }
        else { showToast(data.detail || 'Error', 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.applyBulkOnboard = applyBulkOnboard;

async function showOnboardingTemplates() {
    try {
        var res = await fetch('/api/onboarding/templates');
        var templates = await res.json();
        var list = document.getElementById('onb-templates-list');
        list.innerHTML = '';
        if (templates.length === 0) {
            list.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-secondary);">No templates yet. Create one to reuse checklists.</div>';
        } else {
            templates.forEach(function(t) {
                list.insertAdjacentHTML('beforeend',
                    '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;">' +
                        '<div><div style="font-weight:600;">' + esc(t.name) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + (t.items ? t.items.length : 0) + ' items</div></div>' +
                        '<button onclick="deleteOnbTemplate(' + t.id + ')" style="background:none;border:none;color:var(--danger-color);cursor:pointer;padding:4px;" title="Delete">' +
                            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
                        '</button>' +
                    '</div>'
                );
            });
        }
        document.getElementById('onb-templates-modal').style.display = 'flex';
    } catch (e) { showToast('Failed to load templates', 'error'); }
}
window.showOnboardingTemplates = showOnboardingTemplates;

function closeOnbTemplatesModal() {
    document.getElementById('onb-templates-modal').style.display = 'none';
}
window.closeOnbTemplatesModal = closeOnbTemplatesModal;

async function createNewTemplate() {
    var name = prompt('Template name:');
    if (!name) return;
    var itemsJson = prompt('Enter items (one per line, format: Title | Category | Assigned To):');
    if (!itemsJson) return;
    var items = itemsJson.split('\n').map(function(line) {
        var parts = line.split('|').map(function(s) { return s.trim(); });
        return { title: parts[0] || '', category: parts[1] || 'General', assigned_to: parts[2] || '' };
    }).filter(function(i) { return i.title; });
    try {
        var res = await fetch('/api/onboarding/templates', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, items: items })
        });
        if (res.ok) { showToast('Template created', 'success'); showOnboardingTemplates(); }
        else { showToast('Failed', 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.createNewTemplate = createNewTemplate;

async function deleteOnbTemplate(id) {
    if (!confirm('Delete this template?')) return;
    try {
        await fetch('/api/onboarding/templates/' + id, { method: 'DELETE' });
        showOnboardingTemplates();
    } catch (e) { showToast('Failed', 'error'); }
}
window.deleteOnbTemplate = deleteOnbTemplate;

// --- Payslips ---
async function fetchPayslips(statusFilter) {
    try {
        var url = '/api/payslips';
        if (statusFilter) url += '?status=' + encodeURIComponent(statusFilter);
        var res = await fetch(url);
        if (!res.ok) throw new Error('Failed');
        allPayslips = await res.json();
        renderPayslips(allPayslips);
        var countEl = document.getElementById('payslip-count');
        if (countEl) countEl.textContent = allPayslips.length + ' item' + (allPayslips.length !== 1 ? 's' : '');
    } catch (e) {
        var tbody = document.getElementById('payslips-table-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="loading">Failed to load payslips.</td></tr>';
    }
}

function searchPayslips() {
    var q = (document.getElementById('payslip-search').value || '').toLowerCase();
    var filtered = allPayslips.filter(function(p) {
        if (!q) return true;
        return (p.number || '').toLowerCase().includes(q) || (p.employee_name || '').toLowerCase().includes(q) || (p.status || '').toLowerCase().includes(q);
    });
    renderPayslips(filtered);
    var countEl = document.getElementById('payslip-count');
    if (countEl) countEl.textContent = filtered.length + ' item' + (filtered.length !== 1 ? 's' : '');
}
window.searchPayslips = searchPayslips;

// Runs the whole pay period server-side in one transaction. The old version
// looped one HTTP request per employee from the browser, which had no
// atomicity, ignored worked hours, and reported failures only as a count.
async function batchGeneratePayslips() {
    var today = localDate(new Date());
    var firstOfMonth = today.slice(0, 8) + '01';
    var periodStart = prompt('Period start date (YYYY-MM-DD):', firstOfMonth);
    if (!periodStart) return;
    var periodEnd = prompt('Period end date (YYYY-MM-DD):', today);
    if (!periodEnd) return;
    var payDate = prompt('Pay date (YYYY-MM-DD):', today);
    if (!payDate) return;
    if (!confirm('Run payroll for all active employees, ' + periodStart + ' to ' + periodEnd + '?')) return;
    showToast('Running payroll...', 'info');
    try {
        var res = await fetch('/api/payroll/run', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                period_start: periodStart, period_end: periodEnd, pay_date: payDate,
                include_attendance_hours: true, skip_existing: true
            })
        });
        var data = await res.json();
        if (!res.ok) { reportApiError(res, data, 'Payroll run failed'); return; }
        var msg = data.created.length + ' payslip(s) created, net ' + getCurrencySymbol() + data.total_net.toFixed(2);
        if (data.skipped.length) msg += ' — ' + data.skipped.length + ' skipped (already paid for this period)';
        showToast(msg, data.created.length ? 'success' : 'warning');
        // Zero-value payslips nearly always mean missing hours, so make the
        // operator acknowledge them rather than shipping a silent nil payment.
        if (data.warnings && data.warnings.length) {
            alert('Check these payslips before approving:\n\n' +
                  data.warnings.map(function(w) { return '• ' + w.name + ' (' + w.number + '): ' + w.reason; }).join('\n'));
        }
        fetchPayslips(currentPsFilter);
    } catch (e) { showToast('Payroll run failed: ' + e.message, 'error'); }
}
window.batchGeneratePayslips = batchGeneratePayslips;

function renderPayslips(payslips) {
    var tbody = document.getElementById('payslips-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (payslips.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-secondary);">No payslips found.</td></tr>';
        return;
    }
    payslips.forEach(function(p) {
        var statusClass = (p.status || '').toLowerCase();
        var opens = p.open_count || 0;
        var openBadge = opens > 0 ? '<span style="color:var(--primary-color);font-weight:600;">' + opens + '</span>' : '<span style="color:var(--text-secondary);">0</span>';
        tbody.insertAdjacentHTML('beforeend', '<tr><td><a href="#" class="link" onclick="event.preventDefault();viewPayslip(' + p.id + ')">' + esc(p.number) + '</a></td><td>' + employeeLink(p.employee_id, p.employee_name || '-') + '</td><td>' + esc(p.period_start || '') + ' to ' + esc(p.period_end || '') + '</td><td>' + esc(p.pay_date || '-') + '</td><td class="text-right">' + formatCurrency(p.gross_pay) + '</td><td class="text-right">' + formatCurrency(p.total_deductions) + '</td><td class="text-right">' + formatCurrency(p.net_pay) + '</td><td><span class="status-pill status-' + statusClass + '">' + esc(p.status) + '</span></td><td>' + esc(p.sent || '-') + '</td><td class="text-right">' + openBadge + '</td></tr>');
    });
}

function filterPayslips(status, btn) {
    currentPsFilter = status;
    document.querySelectorAll('#payroll-view .invoices-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    if (status) {
        var filtered = allPayslips.filter(function(p) { return p.status === status; });
        renderPayslips(filtered);
    } else {
        renderPayslips(allPayslips);
    }
}
window.filterPayslips = filterPayslips;

// --- View Payslip ---
async function viewPayslip(psId) {
    currentPayslipId = psId;
    try {
        var res = await fetch('/api/payslips/' + psId);
        if (!res.ok) throw new Error('Failed');
        var ps = await res.json();
        // Keep the full record so the PDF can use fields the detail view does
        // not show (employee id, department, bank, tax id, YTD) instead of
        // scraping formatted text back out of the DOM.
        _currentPayslip = ps;
        document.getElementById('ps-detail-title').textContent = 'Payslip ' + ps.number;
        document.getElementById('ps-detail-status').textContent = ps.status;
        document.getElementById('ps-detail-status').className = 'status-pill status-' + (ps.status || '').toLowerCase();
        document.getElementById('ps-detail-number').textContent = ps.number;
        document.getElementById('ps-detail-emp-name').textContent = ps.employee ? ps.employee.full_name : '-';
        document.getElementById('ps-detail-period').textContent = ps.period_start + ' to ' + ps.period_end;
        document.getElementById('ps-detail-pay-date').textContent = ps.pay_date || '-';
        document.getElementById('ps-detail-net').textContent = (ps.net_pay || 0).toFixed(2);
        var currEl = document.getElementById('ps-detail-currency');
        if (currEl) currEl.textContent = getCurrencySymbol();
        document.getElementById('ps-detail-company').textContent = ps.company ? ps.company.name || '-' : '-';
        document.getElementById('ps-detail-company-addr').textContent = ps.company ? (ps.company.address || '') : '';

        document.getElementById('ps-detail-basic').textContent = (ps.basic_salary || 0).toFixed(2);
        document.getElementById('ps-detail-otpay').textContent = (ps.overtime_pay || 0).toFixed(2);
        document.getElementById('ps-detail-bonus').textContent = (ps.bonus || 0).toFixed(2);
        document.getElementById('ps-detail-allow').textContent = (ps.allowances || 0).toFixed(2);
        document.getElementById('ps-detail-gross').textContent = (ps.gross_pay || 0).toFixed(2);
        document.getElementById('ps-detail-tax').textContent = (ps.tax_amount || 0).toFixed(2);
        document.getElementById('ps-detail-ins').textContent = (ps.insurance || 0).toFixed(2);
        document.getElementById('ps-detail-ret').textContent = (ps.retirement || 0).toFixed(2);
        document.getElementById('ps-detail-other').textContent = (ps.other_deductions || 0).toFixed(2);
        // Shown only when there is one, so an ordinary payslip is not cluttered
        // with a zero row - but the four lines always add up to the total.
        var standing = ps.standing_deduction || 0;
        var standingRow = document.getElementById('ps-detail-standing-row');
        if (standingRow) {
            standingRow.style.display = standing > 0 ? '' : 'none';
            document.getElementById('ps-detail-standing').textContent = standing.toFixed(2);
        }
        document.getElementById('ps-detail-dedtotal').textContent = (ps.total_deductions || 0).toFixed(2);
        var netBigEl = document.getElementById('ps-detail-net-big');
        if (netBigEl) netBigEl.textContent = getCurrencySymbol() + (ps.net_pay || 0).toFixed(2);

        var notesEl = document.getElementById('ps-detail-notes');
        if (ps.notes) { notesEl.style.display = 'block'; document.getElementById('ps-detail-notes-text').textContent = ps.notes; }
        else { notesEl.style.display = 'none'; }

        var logoEl = document.getElementById('ps-logo');
        if (ps.company && ps.company.logo_url) { logoEl.src = ps.company.logo_url; logoEl.style.display = 'block'; }
        else { logoEl.style.display = 'none'; }

        showView('payslip-detail-view');
    } catch (e) {
        showToast('Failed to load payslip', 'error');
    }
}
window.viewPayslip = viewPayslip;

// --- Generate Payslip ---
async function showGeneratePayslipModal() {
    document.getElementById('generate-payslip-modal').style.display = 'flex';
    document.getElementById('generate-payslip-form').reset();
    document.getElementById('ps-preview').style.display = 'none';
    var empContainer = document.getElementById('ps-employee-id-container');
    if (empContainer) {
        empContainer.innerHTML = '<input type="hidden" id="ps-employee-id" value="' + (currentEmployeeId || '') + '">';
    }
    var today = new Date();
    var firstDay = localDate(new Date(today.getFullYear(), today.getMonth(), 1));
    var lastDay = localDate(new Date(today.getFullYear(), today.getMonth() + 1, 0));
    document.getElementById('ps-period-start').value = firstDay;
    document.getElementById('ps-period-end').value = lastDay;
    document.getElementById('ps-pay-date').value = localDate(today);
    if (currentEmployeeId) setTimeout(function() { autoFetchPayDetails(); }, 200);
}
window.showGeneratePayslipModal = showGeneratePayslipModal;

async function showGeneratePayslipModalForNew() {
    document.getElementById('generate-payslip-modal').style.display = 'flex';
    document.getElementById('generate-payslip-form').reset();
    document.getElementById('ps-preview').style.display = 'none';
    var today = new Date();
    var firstDay = localDate(new Date(today.getFullYear(), today.getMonth(), 1));
    var lastDay = localDate(new Date(today.getFullYear(), today.getMonth() + 1, 0));
    document.getElementById('ps-period-start').value = firstDay;
    document.getElementById('ps-period-end').value = lastDay;
    document.getElementById('ps-pay-date').value = localDate(today);
    var empContainer = document.getElementById('ps-employee-id-container');
    if (!empContainer) return;
    try {
        var empRes = await fetch('/api/employees');
        var emps = await empRes.json();
        empContainer.innerHTML = '<select id="ps-employee-id" class="form-control" onchange="autoFetchPayDetails()"><option value="">Select employee...</option></select>';
        var sel = document.getElementById('ps-employee-id');
        emps.forEach(function(e) { sel.insertAdjacentHTML('beforeend', '<option value="' + e.id + '">' + e.first_name + ' ' + e.last_name + '</option>'); });
    } catch (e) { console.error(e); empContainer.innerHTML = '<select id="ps-employee-id" class="form-control"><option value="">Failed to load employees</option></select>'; }
}
window.showGeneratePayslipModalForNew = showGeneratePayslipModalForNew;

function closeGeneratePayslipModal() {
    document.getElementById('generate-payslip-modal').style.display = 'none';
}
window.closeGeneratePayslipModal = closeGeneratePayslipModal;

var currentPayDetails = null;
async function autoFetchPayDetails() {
    var empId = document.getElementById('ps-employee-id').value;
    var periodStart = document.getElementById('ps-period-start').value;
    var periodEnd = document.getElementById('ps-period-end').value;
    if (!empId || !periodStart || !periodEnd) return;
    try {
        var url = '/api/employees/' + empId + '/pay-details?period_start=' + periodStart + '&period_end=' + periodEnd;
        var res = await fetch(url);
        if (!res.ok) return;
        currentPayDetails = await res.json();
        document.getElementById('ps-basic').value = currentPayDetails.salary || 0;
        document.getElementById('ps-hours').value = currentPayDetails.hours_worked || 0;
        document.getElementById('ps-ot-hours').value = currentPayDetails.overtime_hours || 0;
        document.getElementById('ps-ot-rate').value = currentPayDetails.overtime_rate || 0;
        document.getElementById('ps-bonus').value = currentPayDetails.bonus || 0;
        document.getElementById('ps-allowances').value = currentPayDetails.allowances || 0;
        recalcPayslip();
    } catch (e) { console.error('Failed to fetch pay details:', e); }
}
window.autoFetchPayDetails = autoFetchPayDetails;

function recalcPayslip() {
    var basic = parseFloat(document.getElementById('ps-basic').value) || 0;
    var otHours = parseFloat(document.getElementById('ps-ot-hours').value) || 0;
    var otRate = parseFloat(document.getElementById('ps-ot-rate').value) || 0;
    var bonus = parseFloat(document.getElementById('ps-bonus').value) || 0;
    var allowances = parseFloat(document.getElementById('ps-allowances').value) || 0;
    var insurance = parseFloat(document.getElementById('ps-insurance').value) || 0;
    var retirement = parseFloat(document.getElementById('ps-retirement').value) || 0;
    var otherDed = parseFloat(document.getElementById('ps-other-ded').value) || 0;
    var hoursWorked = parseFloat(document.getElementById('ps-hours').value) || 0;
    var otPay = otHours * otRate;
    var gross = basic + otPay + bonus + allowances;
    var taxRate = currentPayDetails ? (currentPayDetails.tax_rate || 0) : 0;
    var empDeductions = currentPayDetails ? (currentPayDetails.deductions || 0) : 0;
    var tax = Math.round(gross * (taxRate / 100) * 100) / 100;
    var totalDed = tax + empDeductions + insurance + retirement + otherDed;
    var net = Math.round((gross - totalDed) * 100) / 100;
    var cs = getCurrencySymbol();
    document.getElementById('prev-basic').textContent = cs + basic.toLocaleString();
    document.getElementById('prev-ot').textContent = cs + otPay.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('prev-bonus').textContent = cs + bonus.toLocaleString();
    document.getElementById('prev-allow').textContent = cs + allowances.toLocaleString();
    document.getElementById('prev-gross').textContent = cs + gross.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('prev-tax').textContent = cs + tax.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('prev-ded').textContent = cs + (empDeductions + insurance + retirement + otherDed).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('prev-net').textContent = cs + net.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('ps-preview').style.display = 'block';
    var attInfo = document.getElementById('prev-attendance');
    if (currentPayDetails && attInfo) {
        var parts = [];
        if (hoursWorked > 0) parts.push(hoursWorked + 'h worked');
        if (currentPayDetails.overtime_hours > 0) parts.push(currentPayDetails.overtime_hours + 'h overtime');
        attInfo.textContent = parts.length ? 'Attendance: ' + parts.join(', ') : 'No attendance records for this period';
    }
}
window.recalcPayslip = recalcPayslip;

async function submitGeneratePayslip() {
    var empIdVal = document.getElementById('ps-employee-id').value;
    if (!empIdVal) { showToast('Select an employee', 'error'); return; }
    var payload = {
        employee_id: parseInt(empIdVal),
        period_start: document.getElementById('ps-period-start').value,
        period_end: document.getElementById('ps-period-end').value,
        pay_date: document.getElementById('ps-pay-date').value,
        hours_worked: parseFloat(document.getElementById('ps-hours').value) || 0,
        basic_salary: parseFloat(document.getElementById('ps-basic').value) || 0,
        overtime_hours: parseFloat(document.getElementById('ps-ot-hours').value) || 0,
        overtime_rate: parseFloat(document.getElementById('ps-ot-rate').value) || 0,
        bonus: parseFloat(document.getElementById('ps-bonus').value) || 0,
        allowances: parseFloat(document.getElementById('ps-allowances').value) || 0,
        insurance: parseFloat(document.getElementById('ps-insurance').value) || 0,
        retirement: parseFloat(document.getElementById('ps-retirement').value) || 0,
        other_deductions: parseFloat(document.getElementById('ps-other-ded').value) || 0,
        notes: document.getElementById('ps-notes').value,
    };
    async function post(allowOverlap) {
        var url = '/api/payslips' + (allowOverlap ? '?allow_overlap=true' : '');
        var res = await fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return { res: res, data: await res.json() };
    }
    try {
        var out = await post(false);
        // 409 means an existing payslip already covers this period - let the
        // user knowingly override rather than silently double-paying.
        if (out.res.status === 409) {
            if (!confirm((out.data.detail || 'A payslip already covers this period.') + '\n\nCreate it anyway?')) return;
            out = await post(true);
        }
        if (out.res.ok) {
            showToast(out.data.message || 'Payslip created', 'success');
            closeGeneratePayslipModal();
            if (currentEmployeeId) viewEmployee(currentEmployeeId);
            fetchPayslips(currentPsFilter);
        } else {
            showToast('Failed: ' + (out.data.detail || 'Error'), 'error');
        }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.submitGeneratePayslip = submitGeneratePayslip;

// --- Payslip Actions ---
async function sendPayslipEmail() {
    if (!currentPayslipId) return;
    var logoData = localStorage.getItem('company_logo') || '';
    var pdfB64 = '';
    try {
        var doc = generatePayslipPDF();
        pdfB64 = doc.output('datauristring').split('base64,')[1];
    } catch (e) { console.error('PDF generation failed:', e); }
    try {
        var res = await fetch('/api/payslips/' + currentPayslipId + '/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logo_data: logoData, pdf_data: pdfB64 })
        });
        var data = await res.json();
        if (res.ok) { showToast('Payslip email sent with PDF!', 'success'); viewPayslip(currentPayslipId); }
        else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.sendPayslipEmail = sendPayslipEmail;

async function markPayslipPaid() {
    if (!currentPayslipId) return;
    if (!confirm('Mark payslip as paid?')) return;
    try {
        var res = await fetch('/api/payslips/' + currentPayslipId + '/mark-paid', { method: 'POST' });
        if (res.ok) { showToast('Marked as paid', 'success'); viewPayslip(currentPayslipId); }
        else { var data = await res.json(); showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.markPayslipPaid = markPayslipPaid;

async function deletePayslip() {
    if (!currentPayslipId) return;
    if (!confirm('Delete this payslip?')) return;
    try {
        var res = await fetch('/api/payslips/' + currentPayslipId, { method: 'DELETE' });
        if (res.ok) { showToast('Payslip deleted', 'success'); showView('payroll-view'); hrDataChanged('payroll'); }
        else { var data = await res.json(); showToast('Failed: ' + (data.detail || 'Error'), 'error'); }
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.deletePayslip = deletePayslip;

// --- Payslip PDF ---
// Full payslip record stashed by viewPayslip so the PDF can use fields the
// detail view does not render.
var _currentPayslip = null;

// Clean, white, print-ready payslip built in the same visual language as the
// invoice PDF: no dark fills, ruled tables, black type on white.
function generatePayslipPDF() {
    var jsPDF = window.jspdf.jsPDF;
    var doc = new jsPDF({ unit: 'pt', format: 'a4' });
    var W = doc.internal.pageSize.getWidth();
    var H = doc.internal.pageSize.getHeight();
    var ml = 40, mr = W - 40;
    var contentW = mr - ml;
    var ps = _currentPayslip || {};
    var emp = ps.employee || {};
    var co = ps.company || {};
    var ytd = ps.ytd || {};
    var cs = pdfSym(getCurrencySymbol());

    function money(v) {
        var n = parseFloat(v || 0);
        return cs + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
    function txt(s) { return pdfSym(String(s == null ? '' : s)); }

    // Horizontal rule
    function hr(y, weight, shade) {
        doc.setDrawColor(shade == null ? 200 : shade);
        doc.setLineWidth(weight || 0.5);
        doc.line(ml, y, mr, y);
    }

    var y = 46;

    // ── Header: title left, company right ────────────────────────────────
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(22);
    doc.setTextColor(0, 0, 0);
    doc.text('PAYSLIP', ml, y);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(90, 90, 90);
    doc.text(txt(ps.number || ''), ml, y + 15);

    var logo = localStorage.getItem('company_logo') || co.logo_url || '';
    var rightY = y - 8;
    if (logo) {
        try {
            doc.addImage(logo, 'PNG', mr - 100, rightY, 100, 32);
            rightY += 40;
        } catch (e) { /* unreadable logo must not break the document */ }
    }
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10.5);
    doc.setTextColor(0, 0, 0);
    if (co.name) { doc.text(txt(co.name), mr, rightY + 8, { align: 'right' }); rightY += 13; }
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(95, 95, 95);
    [co.address, co.email, co.phone, co.abn ? 'ABN/Tax ID: ' + co.abn : '']
        .filter(Boolean).forEach(function (line) {
            String(line).split('\n').forEach(function (part) {
                doc.text(txt(part), mr, rightY + 8, { align: 'right' });
                rightY += 11;
            });
        });

    y = Math.max(y + 26, rightY + 6);
    hr(y, 1.1, 0); y += 18;

    // ── Employee + period, two columns ───────────────────────────────────
    var colR = ml + contentW / 2 + 10;

    function fieldBlock(x, heading, rows) {
        var yy = y;
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(120, 120, 120);
        doc.text(heading, x, yy);
        yy += 14;
        rows.forEach(function (r) {
            if (!r[1]) return;
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(8.5);
            doc.setTextColor(115, 115, 115);
            doc.text(txt(r[0]), x, yy);
            doc.setFont('helvetica', 'bold');
            doc.setTextColor(20, 20, 20);
            var val = doc.splitTextToSize(txt(r[1]), contentW / 2 - 90);
            doc.text(val, x + 78, yy);
            yy += 13 * val.length;
        });
        return yy;
    }

    var leftEnd = fieldBlock(ml, 'EMPLOYEE', [
        ['Name', emp.full_name],
        ['Employee ID', emp.employee_id],
        ['Job title', emp.job_title],
        ['Department', emp.department_name],
        ['Level', emp.level],
        ['Tax ID', emp.tax_id]
    ]);
    var rightEnd = fieldBlock(colR, 'PAY PERIOD', [
        ['Period', (ps.period_start || '') + '  to  ' + (ps.period_end || '')],
        ['Pay date', ps.pay_date],
        ['Frequency', emp.pay_frequency],
        ['Bank', emp.bank_name],
        ['Account', emp.bank_account],
        ['Hours', ps.hours_worked ? String(ps.hours_worked) + ' h' : '']
    ]);

    y = Math.max(leftEnd, rightEnd) + 8;
    hr(y, 0.5); y += 20;

    // ── Earnings / deductions, side by side ──────────────────────────────
    var tableW = contentW / 2 - 10;

    function moneyTable(x, heading, rows, total, totalLabel) {
        var yy = y;
        doc.setFillColor(245, 246, 248);
        doc.rect(x, yy - 11, tableW, 20, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);
        doc.setTextColor(40, 40, 40);
        doc.text(heading, x + 8, yy + 2);
        doc.text('AMOUNT', x + tableW - 8, yy + 2, { align: 'right' });
        yy += 9;
        doc.setDrawColor(210);
        doc.setLineWidth(0.5);
        doc.line(x, yy, x + tableW, yy);
        yy += 16;

        rows.forEach(function (r) {
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(9);
            doc.setTextColor(55, 55, 55);
            doc.text(txt(r[0]), x + 8, yy);
            doc.setTextColor(20, 20, 20);
            doc.text(money(r[1]), x + tableW - 8, yy, { align: 'right' });
            doc.setDrawColor(235);
            doc.line(x, yy + 6, x + tableW, yy + 6);
            yy += 20;
        });

        yy += 2;
        doc.setDrawColor(150);
        doc.setLineWidth(0.7);
        doc.line(x, yy - 12, x + tableW, yy - 12);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(10);
        doc.setTextColor(0, 0, 0);
        doc.text(totalLabel, x + 8, yy + 2);
        doc.text(money(total), x + tableW - 8, yy + 2, { align: 'right' });
        return yy + 14;
    }

    var earnEnd = moneyTable(ml, 'EARNINGS', [
        ['Basic salary', ps.basic_salary],
        ['Overtime' + (ps.overtime_hours ? ' (' + ps.overtime_hours + ' h)' : ''), ps.overtime_pay],
        ['Bonus', ps.bonus],
        ['Allowances', ps.allowances]
    ], ps.gross_pay, 'Gross pay');

    // A standing deduction set on the employee record sits inside the total.
    // Without its own line the four rows did not add up to the total printed
    // underneath them, and nobody reading their payslip could see why.
    var dedRows = [
        ['Tax', ps.tax_amount],
        ['Insurance', ps.insurance],
        ['Retirement', ps.retirement],
        ['Other', ps.other_deductions]
    ];
    if ((ps.standing_deduction || 0) > 0) {
        dedRows.push(['Standing deduction', ps.standing_deduction]);
    }
    var dedEnd = moneyTable(colR, 'DEDUCTIONS', dedRows,
                            ps.total_deductions, 'Total deductions');

    y = Math.max(earnEnd, dedEnd) + 22;

    // ── Net pay, outlined rather than filled so it prints cleanly ────────
    doc.setDrawColor(0);
    doc.setLineWidth(1.2);
    doc.rect(ml, y, contentW, 54);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(90, 90, 90);
    doc.text('NET PAY', ml + 16, y + 21);
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.text('Amount transferred to the employee', ml + 16, y + 37);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(22);
    doc.setTextColor(0, 0, 0);
    doc.text(money(ps.net_pay), mr - 16, y + 34, { align: 'right' });
    y += 74;

    // ── Year to date ─────────────────────────────────────────────────────
    if (ytd && ytd.payslip_count) {
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(120, 120, 120);
        doc.text('YEAR TO DATE (' + txt(ytd.year || '') + ')', ml, y);
        y += 14;
        var cells = [
            ['Gross', ytd.gross_pay], ['Tax', ytd.tax_amount],
            ['Deductions', ytd.total_deductions], ['Net', ytd.net_pay]
        ];
        var cw = contentW / cells.length;
        doc.setDrawColor(220);
        doc.setLineWidth(0.5);
        doc.rect(ml, y - 10, contentW, 34);
        cells.forEach(function (c, i) {
            var cx = ml + cw * i;
            if (i > 0) doc.line(cx, y - 10, cx, y + 24);
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(120, 120, 120);
            doc.text(c[0], cx + 10, y + 2);
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(10);
            doc.setTextColor(20, 20, 20);
            doc.text(money(c[1]), cx + 10, y + 17);
        });
        y += 44;
    }

    // ── Notes ────────────────────────────────────────────────────────────
    if (ps.notes) {
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(120, 120, 120);
        doc.text('NOTES', ml, y);
        y += 13;
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        doc.setTextColor(70, 70, 70);
        var noteLines = doc.splitTextToSize(txt(ps.notes), contentW);
        // Trim rather than spill onto a second page for a one-page document.
        noteLines = noteLines.slice(0, 4);
        doc.text(noteLines, ml, y);
        y += noteLines.length * 11 + 8;
    }

    // ── Footer pinned to the bottom ──────────────────────────────────────
    var fy = H - 54;
    hr(fy, 0.5);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7.5);
    doc.setTextColor(130, 130, 130);
    doc.text('This is a computer-generated payslip and does not require a signature.', ml, fy + 14);
    doc.text('Private and confidential', mr, fy + 14, { align: 'right' });
    if (co.name) {
        doc.setTextColor(160, 160, 160);
        doc.text(txt(co.name), ml, fy + 26);
    }
    doc.text(txt(ps.number || ''), mr, fy + 26, { align: 'right' });

    return doc;
}

function downloadPayslipPDF() {
    var number = document.getElementById('ps-detail-number').textContent || 'payslip';
    var doc = generatePayslipPDF();
    doc.save(number + '.pdf');
}
window.downloadPayslipPDF = downloadPayslipPDF;

// ============================================================
// ATTENDANCE MODULE
// ============================================================

var allAttendance = [];

async function loadAttendanceStats() {
    try {
        var res = await fetch('/api/attendance/stats');
        if (!res.ok) return;
        var s = await res.json();
        var el = function(id) { return document.getElementById(id); };
        if (el('att-total')) el('att-total').textContent = s.total_employees || 0;
        if (el('att-present')) el('att-present').textContent = s.present || 0;
        if (el('att-absent')) el('att-absent').textContent = s.absent || 0;
        if (el('att-avg-hours')) el('att-avg-hours').textContent = (s.avg_hours || 0) + 'h';
    } catch (e) { console.error('Attendance stats error:', e); }
}

async function loadAttendanceButtons() {
    try {
        var res = await fetch('/api/employees');
        if (!res.ok) return;
        var emps = await res.json();
        var container = document.getElementById('att-employee-buttons');
        if (!container) return;
        container.innerHTML = '';
        var activeEmps = emps.filter(function(e) { return e.status === 'active' || e.status === 'onboarding'; });
        if (activeEmps.length === 0) {
            container.innerHTML = '<div style="color:var(--text-secondary);font-size:0.9rem;">No active employees. Add employees first.</div>';
            return;
        }
        activeEmps.forEach(function(e) {
            var initials = (e.first_name[0] || '') + (e.last_name[0] || '');
            container.insertAdjacentHTML('beforeend', '<div style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:rgba(255,255,255,0.03);border:1px solid var(--border-color);border-radius:var(--radius-md);min-width:280px;"><div style="width:40px;height:40px;border-radius:50%;background:var(--primary-color);color:#0b0f19;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.85rem;flex-shrink:0;">' + esc(initials) + '</div><div style="flex:1;min-width:0;"><div style="font-weight:600;font-size:0.9rem;">' + esc(e.first_name) + ' ' + esc(e.last_name) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(e.job_title || e.email || '') + '</div></div><button class="btn btn-outline btn-sm" onclick="clockInOut(' + e.id + ')" id="att-btn-' + e.id + '" style="flex-shrink:0;">Clock In</button></div>');
        });
    } catch (e) { console.error('Attendance buttons error:', e); }
}

async function clockInOut(empId) {
    var btn = document.getElementById('att-btn-' + empId);
    var now = new Date();
    var timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    var todayRecords = allAttendance.filter(function(r) { return r.employee_id === empId; });
    var todayRecord = todayRecords.find(function(r) { return r.date === localDate(new Date()); });
    try {
        if (!todayRecord || !todayRecord.clock_in) {
            var res = await fetch('/api/attendance/clock-in', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ employee_id: empId })
            });
            var data = await res.json();
            if (res.ok) { showToast(data.message, 'success'); }
            else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); return; }
        } else if (!todayRecord.clock_out) {
            var res = await fetch('/api/attendance/clock-out', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ employee_id: empId })
            });
            var data = await res.json();
            if (res.ok) { showToast(data.message + ' (' + data.total_hours + 'h)', 'success'); }
            else { showToast('Failed: ' + (data.detail || 'Error'), 'error'); return; }
        } else {
            showToast('Already clocked out today', 'warning');
            return;
        }
        loadAttendanceStats();
        loadAttendance();
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}
window.clockInOut = clockInOut;

async function loadAttendance() {
    var dateFilter = document.getElementById('att-date-filter');
    var date = dateFilter ? dateFilter.value : '';
    try {
        var url = '/api/attendance';
        if (date) url += '?date=' + encodeURIComponent(date);
        var res = await fetch(url);
        if (!res.ok) throw new Error('Failed');
        allAttendance = await res.json();
        renderAttendance(allAttendance);
        var countEl = document.getElementById('att-count');
        if (countEl) countEl.textContent = allAttendance.length + ' record' + (allAttendance.length !== 1 ? 's' : '');
    } catch (e) {
        var tbody = document.getElementById('attendance-table-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="loading">Failed to load attendance.</td></tr>';
    }
}
window.loadAttendance = loadAttendance;

function renderAttendance(records) {
    var tbody = document.getElementById('attendance-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--text-secondary);">No attendance records found.</td></tr>';
        return;
    }
    records.forEach(function(r) {
        var statusClass = r.status === 'completed' ? 'paid' : r.status === 'present' ? 'sent' : 'draft';
        var typeBadge = r.check_type ? '<span class="status-pill status-' + (r.check_type === 'office' ? 'sent' : r.check_type === 'remote' ? 'paid' : 'draft') + '">' + r.check_type + '</span>' : '-';
        tbody.insertAdjacentHTML('beforeend', '<tr><td><strong>' + employeeLink(r.employee_id, r.employee_name) + '</strong><br><span style="font-size:0.78rem;color:var(--text-secondary);">' + esc(r.employee_email || '') + '</span></td><td>' + esc(r.date) + '</td><td>' + esc(r.clock_in || '-') + '</td><td>' + esc(r.clock_out || '-') + '</td><td class="text-right">' + (r.total_hours ? r.total_hours + 'h' : '-') + '</td><td>' + typeBadge + '</td><td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + esc(r.location_label || '') + '">' + (r.location_label ? esc(r.location_label.substring(0, 30)) : '-') + '</td><td><span class="status-pill status-' + statusClass + '">' + esc(r.status) + '</span></td><td class="text-right">' + (!r.clock_out && r.clock_in ? '<button class="btn btn-outline btn-sm" onclick="clockInOut(' + r.employee_id + ')">Clock Out</button>' : '') + '</td></tr>');
    });
}

// --- View Switcher HR hooks ---
async function loadOrgChart() {
    try {
        var res = await fetch('/api/org-chart');
        if (!res.ok) throw new Error('Failed');
        var data = await res.json();
        var container = document.getElementById('orgchart-container');
        if (!container) return;
        container.innerHTML = '';
        if (data.total_employees === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:60px;">No employees to display. Add employees first.</div>';
            return;
        }
        var roots = data.roots || [];
        var departments = data.departments || {};
        if (roots.length > 0) {
            var rootSection = document.createElement('div');
            rootSection.style.textAlign = 'center';
            rootSection.style.marginBottom = '40px';
            rootSection.innerHTML = '<h3 style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:1px;margin-bottom:20px;">Leadership</h3>';
            var tree = document.createElement('div');
            tree.className = 'org-tree';
            roots.forEach(function(r) { tree.appendChild(renderOrgTreeNode(r)); });
            rootSection.appendChild(tree);
            container.appendChild(rootSection);
        }
        for (var deptName in departments) {
            var deptSection = document.createElement('div');
            deptSection.style.textAlign = 'center';
            deptSection.style.marginBottom = '40px';
            deptSection.innerHTML = '<h3 style="font-size:0.85rem;color:var(--primary-color);text-transform:uppercase;letter-spacing:1px;margin-bottom:20px;">' + esc(deptName) + '</h3>';
            var tree = document.createElement('div');
            tree.className = 'org-tree';
            departments[deptName].forEach(function(e) { tree.appendChild(renderOrgTreeNode(e)); });
            deptSection.appendChild(tree);
            container.appendChild(deptSection);
        }
    } catch (e) {
        var c = document.getElementById('orgchart-container');
        if (c) c.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:60px;">Failed to load org chart.</div>';
    }
}

function renderOrgTreeNode(emp, depth) {
    depth = depth || 0;
    // The server rejects reporting loops, but legacy rows could still contain
    // one. A hard depth cap keeps a bad record from hanging the browser.
    if (depth > 20) {
        var stop = document.createElement('div');
        stop.style.cssText = 'font-size:0.75rem;color:var(--danger-color);padding:8px;';
        stop.textContent = 'Reporting line too deep - check for a loop';
        return stop;
    }
    var hasChildren = emp.children && emp.children.length > 0;
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:inline-flex;flex-direction:column;align-items:center;position:relative;';
    var node = document.createElement('div');
    node.className = 'org-node';
    node.style.cssText = 'cursor:pointer;padding:14px 20px;border-radius:12px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);text-align:center;min-width:160px;transition:all 0.2s;';
    node.onmouseover = function() { this.style.borderColor = 'var(--primary-color)'; this.style.transform = 'translateY(-2px)'; };
    node.onmouseout = function() { this.style.borderColor = 'rgba(255,255,255,0.1)'; this.style.transform = 'none'; };
    node.setAttribute('onclick', 'viewEmployee(' + emp.id + ')');
    node.innerHTML = '<div class="org-name" style="font-weight:700;font-size:0.9rem;">' + esc(emp.name) + levelBadge(emp.level) + '</div>' +
        '<div class="org-title" style="font-size:0.78rem;color:var(--text-secondary);margin-top:2px;">' + esc(emp.job_title || '-') + '</div>' +
        (emp.role && emp.role !== 'employee' ? '<div style="font-size:0.7rem;color:var(--warning-color);margin-top:2px;">' + esc(roleLabel(emp.role)) + '</div>' : '') +
        (emp.department ? '<div class="org-dept" style="font-size:0.72rem;color:var(--primary-color);margin-top:4px;">' + esc(emp.department) + '</div>' : '');
    wrapper.appendChild(node);
    if (hasChildren) {
        var line = document.createElement('div');
        line.style.cssText = 'width:2px;height:20px;background:rgba(255,255,255,0.15);margin:0 auto;';
        wrapper.appendChild(line);
        var childrenRow = document.createElement('div');
        childrenRow.style.cssText = 'display:flex;gap:20px;justify-content:center;position:relative;';
        childrenRow.style.paddingTop = '10px';
        childrenRow.style.borderTop = '2px solid rgba(255,255,255,0.1)';
        emp.children.forEach(function(child) {
            childrenRow.appendChild(renderOrgTreeNode(child, depth + 1));
        });
        wrapper.appendChild(childrenRow);
    }
    return wrapper;
}

// --- View Switcher HR hooks ---
var origShowView = showView;
showView = function(viewId) {
    origShowView(viewId);
    if (viewId === 'employees-view') { fetchEmployees(currentEmpFilter); loadHRStats(); }
    if (viewId === 'leave-view') loadLeaveView();
    if (viewId === 'goals-view') loadGoalsView();
    if (viewId === 'departments-view') fetchDepartments();
    if (viewId === 'onboarding-hub-view') { loadOnboardingHub(); loadDocumentQueue(); loadExpiringDocuments(); loadOnboardingPipeline(); }
    if (viewId === 'payroll-view') { fetchPayslips(currentPsFilter); loadPayrollAnomalies(); }
    if (viewId === 'attendance-view') { loadAttendanceStats(); loadAttendanceButtons(); loadAttendance(); loadLiveAttendance(); loadAttendanceSettings(); switchAttTab('live'); }
    if (viewId === 'orgchart-view') loadOrgChart();
    if (viewId === 'recruitment-view') {
        loadRecAnalytics();
        var jobsTab = document.querySelector('#rec-tabs .tab');
        switchRecTab('jobs', jobsTab);
    }
    if (viewId === 'wallet-view') loadWallet();
    if (viewId === 'bills-view') loadBills();
    if (viewId === 'contacts-view') loadContacts();
};
window.showView = showView;

function showPeopleTab(tab) {
    // Leave tab removed — now a standalone view
}
window.showPeopleTab = showPeopleTab;

// --- Attendance Sub-Tabs ---
function switchAttTab(tab) {
    ['live','history','analytics','overtime','settings'].forEach(t => {
        var el = document.getElementById('att-sub-' + t);
        if (el) el.classList.add('d-none');
        var btn = document.getElementById('att-tab-' + t);
        if (btn) { btn.classList.remove('btn-primary'); btn.classList.add('btn-outline'); btn.style.fontWeight = '400'; }
    });
    var active = document.getElementById('att-sub-' + tab);
    if (active) active.classList.remove('d-none');
    var activeBtn = document.getElementById('att-tab-' + tab);
    if (activeBtn) { activeBtn.classList.remove('btn-outline'); activeBtn.classList.add('btn-primary'); activeBtn.style.fontWeight = '600'; }
    if (tab === 'analytics') loadAttendanceAnalytics();
    if (tab === 'settings') loadAttendanceSettings();
    if (tab === 'overtime') loadOvertimeTab();
}
window.switchAttTab = switchAttTab;

// --- Live Attendance Board ---
async function loadLiveAttendance() {
    try {
        var res = await fetch('/api/attendance/live');
        if (!res.ok) return;
        var data = await res.json();
        var grid = document.getElementById('live-attendance-grid');
        if (!grid) return;
        var colors = { present: '#10b981', absent: '#ef4444', completed: '#3b82f6' };
        var icons = { office: 'bi-building', remote: 'bi-house', field: 'bi-geo', manual: 'bi-clock' };
        var working = 0;
        grid.innerHTML = data.map(function(emp) {
            var isWorking = emp.clock_in && !emp.clock_out;
            if (isWorking) working++;
            var borderColor = isWorking ? '#10b981' : (emp.clock_out ? '#3b82f6' : '#e2e8f0');
            var statusColor = isWorking ? '#10b981' : (emp.clock_out ? '#3b82f6' : '#94a3b8');
            return '<div style="background:#fff;border:2px solid ' + borderColor + ';border-radius:12px;padding:16px;position:relative;">' +
                '<div style="position:absolute;top:12px;right:12px;width:10px;height:10px;border-radius:50%;background:' + statusColor + ';"></div>' +
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
                    '<div style="width:40px;height:40px;border-radius:50%;background:' + (isWorking ? '#d1fae5' : '#f1f5f9') + ';display:flex;align-items:center;justify-content:center;font-weight:700;color:' + statusColor + ';">' + esc(emp.full_name.charAt(0)) + '</div>' +
                    '<div><div style="font-weight:600;font-size:0.95rem;">' + esc(emp.full_name) + '</div>' +
                    '<div style="font-size:0.78rem;color:#64748b;">' + esc(emp.job_title || emp.department || 'Employee') + '</div></div>' +
                '</div>' +
                '<div style="display:flex;justify-content:space-between;font-size:0.82rem;color:#64748b;">' +
                    '<span><i class="bi bi-clock"></i> ' + esc(emp.clock_in || '--:--') + '</span>' +
                    '<span><i class="bi bi-clock-history"></i> ' + esc(emp.clock_out || '--:--') + '</span>' +
                    '<span><i class="bi bi-hourglass-split"></i> ' + (emp.total_hours || 0) + 'h</span>' +
                '</div>' +
                '<div style="margin-top:8px;display:flex;gap:8px;font-size:0.75rem;color:#64748b;">' +
                    (emp.check_type ? '<span><i class="bi ' + (icons[emp.check_type] || 'bi-geo') + '"></i> ' + esc(emp.check_type) + '</span>' : '') +
                    (emp.location_label ? '<span title="' + esc(emp.location_label) + '"><i class="bi bi-geo-alt"></i></span>' : '') +
                    (emp.ip_address ? '<span title="IP: ' + esc(emp.ip_address) + '"><i class="bi bi-wifi"></i></span>' : '') +
                '</div>' +
            '</div>';
        }).join('');
        var el = document.getElementById('att-working');
        if (el) el.textContent = working;
    } catch (e) { console.error('Live attendance load failed:', e); }
}
window.loadLiveAttendance = loadLiveAttendance;

// --- Attendance Analytics ---
async function loadAttendanceAnalytics() {
    try {
        var res = await fetch('/api/attendance/analytics?days=30');
        if (!res.ok) return;
        var data = await res.json();
        document.getElementById('ana-avg-hours').textContent = data.avg_daily_hours + 'h';
        document.getElementById('ana-late').textContent = data.late_arrivals;
        document.getElementById('ana-overtime').textContent = data.overtime_sessions;
        document.getElementById('ana-rate').textContent = data.avg_attendance_rate + '%';
        var chart = document.getElementById('analytics-chart');
        if (chart && data.daily) {
            var days = Object.entries(data.daily).slice(-14);
            var maxPresent = Math.max(...days.map(function(d) { return d[1].present; }), 1);
            chart.innerHTML = '<div style="display:flex;align-items:end;gap:4px;height:180px;padding:10px 0;">' +
                days.map(function(d) {
                    var pct = (d[1].present / maxPresent) * 100;
                    return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;">' +
                        '<div style="font-size:0.7rem;font-weight:600;color:#334155;">' + d[1].present + '</div>' +
                        '<div style="width:100%;height:' + pct + '%;background:linear-gradient(180deg,#4361ee,#3a56d4);border-radius:4px 4px 0 0;min-height:4px;"></div>' +
                        '<div style="font-size:0.65rem;color:#64748b;text-align:center;">' + d[0].slice(5) + '</div>' +
                    '</div>';
                }).join('') +
            '</div>';
        }
    } catch (e) { console.error('Attendance analytics load failed:', e); }
}

// --- Attendance Settings ---
async function loadAttendanceSettings() {
    try {
        var res = await fetch('/api/attendance/settings');
        if (!res.ok) return;
        var data = await res.json();
        document.getElementById('set-office-name').value = data.office_name || 'Head Office';
        document.getElementById('set-radius').value = data.geofence_radius || 200;
        document.getElementById('set-lat').value = data.office_lat || '';
        document.getElementById('set-lng').value = data.office_lng || '';
        document.getElementById('set-start').value = data.work_start || '09:00';
        document.getElementById('set-end').value = data.work_end || '17:30';
        document.getElementById('set-grace').value = data.grace_minutes || 15;
        document.getElementById('set-auto-co').value = data.auto_clockout_hours || 10;
        document.getElementById('set-max-ot').value = data.max_overtime_hours || 4;
        document.getElementById('set-allow-remote').checked = data.allow_remote !== false;
        document.getElementById('set-require-loc').checked = data.require_location !== false;
        var days = String(data.working_days || '1,2,3,4,5').split(',');
        document.querySelectorAll('#set-working-days .work-day').forEach(function (box) {
            box.checked = days.indexOf(box.value) !== -1;
        });
        var auto = document.getElementById('set-auto-clock-in');
        if (auto) auto.checked = data.auto_clock_in !== false;
    } catch (e) { console.error('Attendance settings load failed:', e); }
}

// Ticked days, as the ISO numbers the server stores. An empty selection would
// mean nobody ever works, so it falls back to a normal week.
function collectWorkingDays() {
    var picked = [];
    document.querySelectorAll('#set-working-days .work-day').forEach(function (box) {
        if (box.checked) picked.push(box.value);
    });
    return picked.length ? picked.join(',') : '1,2,3,4,5';
}
window.collectWorkingDays = collectWorkingDays;

async function saveAttendanceSettings() {
    try {
        var body = {
            office_name: document.getElementById('set-office-name').value,
            geofence_radius: parseFloat(document.getElementById('set-radius').value) || 200,
            office_lat: parseFloat(document.getElementById('set-lat').value) || 0,
            office_lng: parseFloat(document.getElementById('set-lng').value) || 0,
            work_start: document.getElementById('set-start').value,
            work_end: document.getElementById('set-end').value,
            grace_minutes: parseFloat(document.getElementById('set-grace').value) || 15,
            auto_clockout_hours: parseFloat(document.getElementById('set-auto-co').value) || 10,
            max_overtime_hours: parseFloat(document.getElementById('set-max-ot').value) || 4,
            allow_remote: document.getElementById('set-allow-remote').checked,
            require_location: document.getElementById('set-require-loc').checked,
            working_days: collectWorkingDays(),
            auto_clock_in: document.getElementById('set-auto-clock-in')
                ? document.getElementById('set-auto-clock-in').checked : true,
        };
        var res = await fetch('/api/attendance/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (res.ok) showToast('Settings saved successfully', 'success');
        else showToast('Failed to save settings', 'error');
    } catch (e) { showToast('Error saving settings', 'error'); }
}
window.saveAttendanceSettings = saveAttendanceSettings;

// --- Overtime Management ---
async function loadOvertimeTab() {
    try {
        var empRes = await fetch('/api/employees');
        var emps = await empRes.json();
        var sel = document.getElementById('ot-employee');
        if (sel) {
            sel.innerHTML = '<option value="">Select employee...</option>';
        emps.forEach(function(e) { sel.insertAdjacentHTML('beforeend', '<option value="' + e.id + '">' + esc(e.first_name) + ' ' + esc(e.last_name) + '</option>'); });
        }
        var otDate = document.getElementById('ot-date');
        if (otDate && !otDate.value) otDate.value = localDate(new Date());
        loadOvertimeLogs();
    } catch (e) { console.error(e); }
}

async function announceOvertime() {
    var empId = document.getElementById('ot-employee').value;
    var date = document.getElementById('ot-date').value;
    var hours = parseFloat(document.getElementById('ot-hours').value);
    var reason = document.getElementById('ot-reason').value;
    if (!empId) { showToast('Select an employee', 'error'); return; }
    if (!hours || hours <= 0) { showToast('Enter valid hours', 'error'); return; }
    try {
        var res = await fetch('/api/attendance/overtime/announce', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employee_id: parseInt(empId), date: date, hours: hours, reason: reason }),
        });
        var data = await res.json();
        if (res.ok) { showToast(data.message, 'success'); loadOvertimeLogs(); }
        else showToast(data.detail || 'Failed', 'error');
    } catch (e) { showToast('Failed: ' + e, 'error'); }
}

async function loadOvertimeLogs() {
    try {
        var res = await fetch('/api/attendance/overtime/logs');
        var logs = await res.json();
        var tbody = document.getElementById('overtime-log-body');
        if (!tbody) return;
        if (logs.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="padding:30px;color:var(--text-secondary);">No overtime logs</td></tr>'; return; }
        tbody.innerHTML = logs.map(function(l) {
            return '<tr><td><strong>' + employeeLink(l.employee_id, l.employee_name) + '</strong></td><td>' + esc(l.date) + '</td><td><strong>' + l.hours + 'h</strong></td><td>' + esc(l.reason || '-') + '</td><td>' + esc(l.announced_by || '-') + '</td><td><span class="status-pill status-sent">' + esc(l.status) + '</span></td></tr>';
        }).join('');
    } catch (e) { console.error('Overtime logs load failed:', e); }
}
window.announceOvertime = announceOvertime;

// --- Export Attendance ---
async function exportAttendance() {
    try {
        var dateFilter = document.getElementById('att-date-filter').value;
        var url = '/api/attendance/export' + (dateFilter ? '?start_date=' + dateFilter + '&end_date=' + dateFilter : '');
        var res = await fetch(url);
        if (!res.ok) return;
        var data = await res.json();
        if (!data.length) { showToast('No records to export', 'warning'); return; }
        var csv = Object.keys(data[0]).join(',') + '\n' + data.map(function(r) {
            return Object.values(r).map(function(v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
        }).join('\n');
        var blob = new Blob([csv], { type: 'text/csv' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'attendance-' + (dateFilter || 'all') + '.csv';
        a.click();
        showToast('Exported ' + data.length + ' records', 'success');
    } catch (e) { showToast('Export failed', 'error'); }
}
window.exportAttendance = exportAttendance;

// --- Event Listeners ---
// --- Authentication guard --------------------------------------------------
// Without this an unauthenticated visitor got the whole portal shell: every
// API call returned 401, the errors were swallowed, and the result was a
// fully-rendered page showing zeros and "Failed to load". That reads as a
// broken app rather than "you need to sign in".

function portalLoginPage() {
    return window.location.pathname.indexOf('hr.html') >= 0 ? '/hr-login.html' : '/login.html';
}

async function requireAuth() {
    try {
        var res = await fetch('/api/auth/me', { credentials: 'same-origin' });
        if (res.ok) {
            var data = await res.json();
            if (data && data.user) return true;
        }
    } catch (e) {
        // A network failure is not the same as being signed out; let the page
        // load and show its own error rather than bouncing to login.
        return true;
    }
    // Remember where they were headed so login can return them here.
    var next = window.location.pathname + window.location.search;
    window.location.replace(portalLoginPage() + '?next=' + encodeURIComponent(next));
    return false;
}
window.requireAuth = requireAuth;

document.addEventListener('DOMContentLoaded', async function() {
    // Nothing else runs until we know there is a session, so the page
    // never renders an empty shell behind a redirect.
    if (!(await requireAuth())) return;
    checkAuthStatus();
    handleTopUpReturn();
    loadSettings();
    fetchDashboardData();
    fetchInvoices();
    preloadSearchData();
    loadSavedLogo();
    setupLogoUpload();
    if (document.getElementById('inv-currency-display')) setupCurrencyPicker('invCurrency', 'inv-currency-display', 'inv-currency', 'inv-currency-list', 'inv-currency-search', 'inv-currency-items');
    if (document.getElementById('setting-currency-display')) setupCurrencyPicker('settingsCurrency', 'setting-currency-display', 'setting-currency', 'setting-currency-list', 'setting-currency-search', 'setting-currency-items');
    fetch('/api/settings').then(function(r){return r.json()}).then(function(d){if(d.currency){_appCurrency=d.currency;var el=document.getElementById('setting-currency');if(el)el.value=d.currency;if(_curPickers['settingsCurrency'])setCurrencyPickerDisplay('settingsCurrency',d.currency);}}).catch(function(){});
    // The first row is built before this resolves, so loadTaxRates() refreshes
    // the pickers once the tenant's own list arrives.
    if (typeof loadTaxRates === 'function') loadTaxRates();
    if (typeof loadAiStatus === 'function') loadAiStatus();
    if (typeof loadTeam === 'function') loadTeam();

    Object.keys(DOC_FORM_SCOPES).forEach(function(scope) {
        var body = document.getElementById(DOC_FORM_SCOPES[scope].body);
        if (!body) return;
        if (scopedLineRows(scope).length === 0) addLineItemRow(scope);
        body.addEventListener('input', function(e) {
            if (e.target.classList.contains('item-qty') || e.target.classList.contains('item-price') || e.target.classList.contains('item-disc')) {
                calculateTotals(scope);
            }
        });
        body.addEventListener('click', function(e) {
            if (e.target.closest('.delete-row')) {
                // Always leave one row; an empty editor has no way back.
                if (scopedLineRows(scope).length > 1) {
                    e.target.closest('.line-item-row').remove();
                    calculateTotals(scope);
                }
            }
        });
    });
    // Set default dates
    var today = localDate(new Date());
    var dueDate = localDate(new Date(Date.now() + 14 * 86400000));    
    var urlParams = new URLSearchParams(window.location.search);
    
    // Enforce portal separation based on the physical file
    enforcePortalSeparation();

    // Set initial view based on physical file
    if (window.location.pathname.includes('hr.html')) {
        showView('employees-view');
    } else {
        showView('dashboard-view');
    }
    
    var issueEl = document.getElementById('inv-issue-date');
    var dueEl = document.getElementById('inv-due-date');
    if (issueEl) issueEl.value = today;
    if (dueEl) dueEl.value = dueDate;

    // Auto-refresh live attendance every 30 seconds when on attendance view
    var attRefreshInterval = null;
    function startAttRefresh() {
        if (attRefreshInterval) return;
        attRefreshInterval = setInterval(function() {
            var attView = document.getElementById('attendance-view');
            if (attView && attView.style.display !== 'none') {
                var liveSub = document.getElementById('att-sub-live');
                if (liveSub && !liveSub.classList.contains('d-none')) {
                    loadLiveAttendance();
                    loadAttendanceStats();
                }
            } else {
                clearInterval(attRefreshInterval);
                attRefreshInterval = null;
            }
        }, 30000);
    }
    startAttRefresh();
});

// ============ RECRUITMENT ============
var recFormFields = [];
var recFormStages = [];
var recEditingFormId = null;
var recCurrentSubId = null;
var recFormsSubId = null;
var recFormsLookup = {};
var recCurrentPipelineStages = [];

async function loadRecruitmentForms() {
    try {
        var res = await fetch('/api/recruitment/forms');
        if (!res.ok) {
            var tbody = document.getElementById('rec-forms-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="loading" style="padding:24px;"><a href="/api/auth/login" style="color:var(--accent-cyan);">Sign in with Google</a> to manage recruitment forms.</td></tr>';
            return;
        }
        var forms = await res.json();
        recFormsLookup = {};
        var totalCandidates = 0;
        var totalPipeline = 0;
        var totalHired = 0;
        var openForms = 0;

        forms.forEach(function(f) { 
            recFormsLookup[f.id] = f; 
            totalCandidates += f.submission_count || 0;
            totalPipeline += f.pipeline_count || 0;
            totalHired += f.hired_count || 0;
            if (f.is_active) openForms++;
        });

        document.getElementById('rec-metric-forms').textContent = openForms;
        document.getElementById('rec-metric-candidates').textContent = totalCandidates;
        document.getElementById('rec-metric-pipeline').textContent = totalPipeline;
        document.getElementById('rec-metric-hired').textContent = totalHired;

        var tbody = document.getElementById('rec-forms-tbody');
        if (!forms.length) { tbody.innerHTML = '<tr><td colspan="6" class="loading">No forms yet</td></tr>'; return; }
        tbody.innerHTML = forms.map(function(f) {
            var fields = f.fields ? JSON.parse(f.fields) : [];
            var d = new Date(f.created_at);
            return '<tr>' +
                '<td><strong>' + esc(f.title) + '</strong>' + (f.description ? '<br><span style="font-size:0.8rem;color:var(--text-secondary)">' + esc(f.description) + '</span>' : '') + '</td>' +
                '<td>' + fields.length + '</td>' +
                '<td>' + f.submission_count + '</td>' +
                '<td>' + (f.is_active ? '<span style="color:var(--accent-success);font-weight:600;">Active</span>' : '<span style="color:var(--text-secondary);">Draft</span>') + '</td>' +
                '<td>' + d.toLocaleDateString() + '</td>' +
                '<td style="text-align:right;white-space:nowrap;">' +
                    '<button class="btn btn-outline btn-sm" onclick="showRecFormSubmissions(' + f.id + ')" style="margin-right:6px;">Submissions</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="copyRecFormLink(\'' + f.form_token + '\')" style="margin-right:6px;" title="Copy link">Link</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="editRecForm(' + f.id + ')" style="margin-right:6px;">Edit</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="toggleRecForm(' + f.id + ',' + f.is_active + ')">' + (f.is_active ? 'Deactivate' : 'Activate') + '</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="deleteRecForm(' + f.id + ')" style="color:var(--accent-danger);border-color:var(--accent-danger);">Delete</button>' +
                '</td></tr>';
        }).join('');
    } catch(e) { console.error('loadRecruitmentForms error:', e); }
}

function copyRecFormLink(token) {
    var url = window.location.origin + '/recruitment.html?token=' + token;
    navigator.clipboard.writeText(url).then(function() {
        showToast('Link copied! Share it with candidates.', 'success');
    }).catch(function() {
        prompt('Copy this link:', url);
    });
}

function showAddFormModal() {
    recEditingFormId = null;
    recFormFields = [];
    recFormStages = ['Applied', 'Screening', 'Interview', 'Offer', 'Hired'];
    document.getElementById('rec-form-modal-title').textContent = 'New Application Form';
    document.getElementById('rec-form-title').value = '';
    document.getElementById('rec-form-desc').value = '';
    renderRecFields();
    renderRecStages();
    document.getElementById('add-rec-form-modal').style.display = 'flex';
}

function editRecForm(id) {
    var f = recFormsLookup[id];
    if (!f) { showToast('Form not found', 'error'); return; }
    recEditingFormId = id;
    recFormFields = f.fields ? JSON.parse(f.fields) : [];
    recFormStages = f.pipeline_stages ? JSON.parse(f.pipeline_stages) : ['Applied', 'Screening', 'Interview', 'Offer', 'Hired'];
    document.getElementById('rec-form-modal-title').textContent = 'Edit Application Form';
    document.getElementById('rec-form-title').value = f.title || '';
    document.getElementById('rec-form-desc').value = f.description || '';
    renderRecFields();
    renderRecStages();
    document.getElementById('add-rec-form-modal').style.display = 'flex';
}

function closeRecFormModal() {
    document.getElementById('add-rec-form-modal').style.display = 'none';
}

function addRecStage() {
    recFormStages.push('New Stage');
    renderRecStages();
}

function removeRecStage(idx) {
    if (recFormStages.length <= 2) { showToast('Need at least 2 stages', 'error'); return; }
    recFormStages.splice(idx, 1);
    renderRecStages();
}

function renderRecStages() {
    var container = document.getElementById('rec-stages-list');
    if (!recFormStages.length) { container.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No stages defined.</p>'; return; }
    var stageColors = ['#6366f1', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#06b6d4'];
    container.innerHTML = recFormStages.map(function(s, i) {
        var color = stageColors[i % stageColors.length];
        return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 10px;">' +
            '<span style="width:12px;height:12px;border-radius:50%;background:' + color + ';flex-shrink:0;"></span>' +
            '<input type="text" value="' + esc(s) + '" class="form-control" style="flex:1;padding:4px 8px;font-size:0.85rem;" onchange="recFormStages[' + i + ']=this.value">' +
            (i > 0 ? '<button class="btn-icon" onclick="moveRecStageUp(' + i + ')" style="color:var(--text-secondary);font-size:0.9rem;" title="Move up">&#9650;</button>' : '<span style="width:24px;"></span>') +
            (i < recFormStages.length - 1 ? '<button class="btn-icon" onclick="moveRecStageDown(' + i + ')" style="color:var(--text-secondary);font-size:0.9rem;" title="Move down">&#9660;</button>' : '<span style="width:24px;"></span>') +
            '<button class="btn-icon" onclick="removeRecStage(' + i + ')" style="color:var(--accent-danger);font-size:1.1rem;">&times;</button>' +
            '</div>';
    }).join('');
}

function moveRecStageUp(idx) {
    if (idx <= 0) return;
    var temp = recFormStages[idx];
    recFormStages[idx] = recFormStages[idx - 1];
    recFormStages[idx - 1] = temp;
    renderRecStages();
}

function moveRecStageDown(idx) {
    if (idx >= recFormStages.length - 1) return;
    var temp = recFormStages[idx];
    recFormStages[idx] = recFormStages[idx + 1];
    recFormStages[idx + 1] = temp;
    renderRecStages();
}

function addRecField() {
    recFormFields.push({ label: '', type: 'text', required: true, options: '' });
    renderRecFields();
}

function removeRecField(idx) {
    recFormFields.splice(idx, 1);
    renderRecFields();
}

function renderRecFields() {
    var container = document.getElementById('rec-fields-list');
    if (!recFormFields.length) { container.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No fields added. Click "+ Add Field" to build your form.</p>'; return; }
    container.innerHTML = recFormFields.map(function(f, i) {
        return '<div style="display:grid;grid-template-columns:1fr 120px 80px 32px;gap:8px;margin-bottom:8px;align-items:center;">' +
            '<input type="text" value="' + esc(f.label) + '" placeholder="Field label" class="form-control" onchange="recFormFields[' + i + '].label=this.value">' +
            '<select class="form-control" onchange="recFormFields[' + i + '].type=this.value;renderRecFields();">' +
                '<option value="text"' + (f.type==='text'?' selected':'') + '>Text</option>' +
                '<option value="email"' + (f.type==='email'?' selected':'') + '>Email</option>' +
                '<option value="phone"' + (f.type==='phone'?' selected':'') + '>Phone</option>' +
                '<option value="textarea"' + (f.type==='textarea'?' selected':'') + '>Textarea</option>' +
                '<option value="select"' + (f.type==='select'?' selected':'') + '>Dropdown</option>' +
                '<option value="file"' + (f.type==='file'?' selected':'') + '>File Upload</option>' +
            '</select>' +
            '<label style="font-size:0.8rem;display:flex;align-items:center;gap:4px;">' +
                '<input type="checkbox"' + (f.required?' checked':'') + ' onchange="recFormFields[' + i + '].required=this.checked"> Req' +
            '</label>' +
            '<button class="btn-icon" onclick="removeRecField(' + i + ')" style="color:var(--accent-danger);font-size:1.2rem;">&times;</button>' +
            (f.type === 'select' ? '<div style="grid-column:1/-1;"><input type="text" value="' + esc(f.options||'') + '" placeholder="Options (comma separated)" class="form-control" onchange="recFormFields[' + i + '].options=this.value"></div>' : '') +
            '</div>';
    }).join('');
}

async function saveRecForm() {
    var title = document.getElementById('rec-form-title').value.trim();
    if (!title) { showToast('Form title is required', 'error'); return; }
    if (recFormStages.length < 2) { showToast('Need at least 2 pipeline stages', 'error'); return; }
    var body = {
        title: title,
        description: document.getElementById('rec-form-desc').value.trim(),
        fields: JSON.stringify(recFormFields),
        pipeline_stages: JSON.stringify(recFormStages),
    };
    try {
        var url = recEditingFormId ? '/api/recruitment/forms/' + recEditingFormId : '/api/recruitment/forms';
        var method = recEditingFormId ? 'PUT' : 'POST';
        var res = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!res.ok) {
            var err = await res.json().catch(function() { return {}; });
            showToast(err.detail || 'Failed to save form', 'error');
            return;
        }
        showToast(recEditingFormId ? 'Form updated!' : 'Form created!', 'success');
        closeRecFormModal();
        loadRecruitmentForms();
    } catch(e) { showToast('Error saving form: ' + e.message, 'error'); }
}

async function toggleRecForm(id, isActive) {
    try {
        var res = await fetch('/api/recruitment/forms/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: !isActive })
        });
        if (!res.ok) { showToast('Failed to update', 'error'); return; }
        showToast(isActive ? 'Form deactivated' : 'Form activated', 'success');
        loadRecruitmentForms();
    } catch(e) { showToast('Error', 'error'); }
}

async function deleteRecForm(id) {
    if (!confirm('Delete this form and all its submissions?')) return;
    try {
        var res = await fetch('/api/recruitment/forms/' + id, { method: 'DELETE' });
        if (!res.ok) { showToast('Failed to delete', 'error'); return; }
        showToast('Form deleted', 'success');
        loadRecruitmentForms();
    } catch(e) { showToast('Error', 'error'); }
}

async function showRecFormSubmissions(formId) {
    recFormsSubId = formId;
    var f = recFormsLookup[formId];
    document.getElementById('rec-sub-form-title').textContent = f ? f.title : 'Form';
    recCurrentPipelineStages = (f && f.pipeline_stages) ? JSON.parse(f.pipeline_stages) : ['Applied', 'Screening', 'Interview', 'Offer', 'Hired'];
    document.getElementById('rec-forms-list').style.display = 'none';
    document.getElementById('rec-submissions-list').style.display = 'block';
    document.getElementById('rec-sub-detail').style.display = 'none';
    switchRecView('table');
    loadRecSubmissions();
}

function switchRecView(view) {
    document.getElementById('rec-table-view').style.display = view === 'table' ? 'block' : 'none';
    document.getElementById('rec-pipeline-view').style.display = view === 'pipeline' ? 'block' : 'none';
    var tb = document.getElementById('rec-view-table-btn');
    var pb = document.getElementById('rec-view-pipeline-btn');
    if (view === 'table') { tb.className = 'btn btn-primary btn-sm'; pb.className = 'btn btn-outline btn-sm'; }
    else { tb.className = 'btn btn-outline btn-sm'; pb.className = 'btn btn-primary btn-sm'; loadRecPipeline(); }
}

var _allRecSubs = [];
async function loadRecSubmissions() {
    try {
        var res = await fetch('/api/recruitment/forms/' + recFormsSubId + '/submissions');
        if (!res.ok) { showToast('Failed to load', 'error'); return; }
        _allRecSubs = await res.json();
        renderRecSubs(_allRecSubs);
    } catch(e) { console.error(e); }
}

function renderRecSubs(subs) {
    var tbody = document.getElementById('rec-subs-tbody');
    if (!subs.length) { tbody.innerHTML = '<tr><td colspan="6" class="loading">No submissions found</td></tr>'; return; }
    tbody.innerHTML = subs.map(function(s) {
        var d = new Date(s.created_at);
        var stage = s.current_stage || 'Applied';
        var stageIdx = recCurrentPipelineStages.indexOf(stage);
        var stageColors = ['#6366f1', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#06b6d4'];
        var stageColor = stageColors[stageIdx >= 0 ? stageIdx % stageColors.length : 0];
        return '<tr>' +
            '<td>' + esc(s.candidate_name || '-') + '</td>' +
            '<td>' + esc(s.candidate_email || '-') + '</td>' +
            '<td>' + (s.file_name ? '<span style="font-size:0.85rem;">' + esc(s.file_name) + '</span>' : '<span style="color:var(--text-secondary)">—</span>') + '</td>' +
            '<td><span style="padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;background:' + stageColor + '20;color:' + stageColor + ';">' + esc(stage) + '</span></td>' +
            '<td>' + d.toLocaleDateString() + '</td>' +
            '<td style="text-align:right;white-space:nowrap;">' +
                '<button class="btn btn-outline btn-sm" onclick="showRecSubmissionDetail(' + s.id + ')" style="margin-right:4px;">View</button>' +
                '<button class="btn btn-outline btn-sm" onclick="showMoveStageMenu(' + s.id + ',\'' + esc(stage) + '\',-1)" title="Move to previous stage">&#8592;</button> ' +
                '<button class="btn btn-outline btn-sm" onclick="showMoveStageMenu(' + s.id + ',\'' + esc(stage) + '\',1)" title="Move to next stage">&#8594;</button>' +
            '</td></tr>';
    }).join('');
}

function searchRecSubmissions() {
    var q = (document.getElementById('rec-sub-search').value || '').toLowerCase();
    var filtered = _allRecSubs.filter(function(s) {
        if (!q) return true;
        return (s.candidate_name || '').toLowerCase().includes(q) || (s.candidate_email || '').toLowerCase().includes(q) || (s.current_stage || '').toLowerCase().includes(q);
    });
    renderRecSubs(filtered);
}
window.searchRecSubmissions = searchRecSubmissions;

async function loadRecPipeline() {
    try {
        var res = await fetch('/api/recruitment/forms/' + recFormsSubId + '/pipeline');
        if (!res.ok) { showToast('Failed to load pipeline', 'error'); return; }
        var data = await res.json();
        var stages = data.stages || recCurrentPipelineStages;
        var pipeline = data.pipeline || {};
        var board = document.getElementById('rec-pipeline-board');
        var stageColors = ['#6366f1', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#06b6d4'];
        board.innerHTML = stages.map(function(stage, i) {
            var color = stageColors[i % stageColors.length];
            var cards = pipeline[stage] || [];
            var stagesJson = JSON.stringify(stages).replace(/"/g, '&quot;');
            return '<div class="kanban-column">' +
                '<div style="padding:12px 16px;border-bottom:2px solid ' + color + ';display:flex;align-items:center;justify-content:space-between;">' +
                    '<div style="display:flex;align-items:center;gap:8px;">' +
                        '<span style="width:10px;height:10px;border-radius:50%;background:' + color + ';"></span>' +
                        '<strong style="font-size:0.85rem;">' + esc(stage) + '</strong>' +
                    '</div>' +
                    '<span style="background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:600;">' + cards.length + '</span>' +
                '</div>' +
                '<div style="padding:12px;display:flex;flex-direction:column;gap:12px;min-height:100px;">' +
                    cards.map(function(c) {
                        var email = c.candidate_email || '';
                        var name = c.candidate_name || email || 'Unknown';
                        var initial = name.charAt(0).toUpperCase();
                        return '<div class="kanban-card" onclick="showRecSubmissionDetail(' + c.id + ')">' +
                            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">' +
                                '<div class="kanban-avatar" style="background:' + color + ';">' + initial + '</div>' +
                                '<div style="font-weight:600;font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(name) + '</div>' +
                            '</div>' +
                            (email ? '<div style="font-size:0.78rem;color:var(--text-secondary);">' + esc(email) + '</div>' : '') +
                            (c.file_name ? '<div style="font-size:0.72rem;color:var(--primary-color);margin-top:4px;"><i class="bi bi-paperclip"></i> Resume Attached</div>' : '') +
                            '<div style="display:flex;gap:4px;margin-top:8px;">' +
                                (i > 0 ? '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();moveCandidateStage(' + c.id + ',' + JSON.stringify(stages[i-1]).replace(/"/g, '&quot;') + ',' + (i-1) + ')" style="font-size:0.7rem;padding:2px 6px;flex:1;">&#9664; Prev</button>' : '') +
                                (i < stages.length - 1 ? '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();moveCandidateStage(' + c.id + ',' + JSON.stringify(stages[i+1]).replace(/"/g, '&quot;') + ',' + (i+1) + ')" style="font-size:0.7rem;padding:2px 6px;flex:1;">Next &#9654;</button>' : '') +
                            '</div>' +
                        '</div>';
                    }).join('') +
                    (cards.length === 0 ? '<div style="text-align:center;color:var(--text-secondary);font-size:0.8rem;padding:24px 0;">No candidates</div>' : '') +
                '</div>' +
            '</div>';
        }).join('');
    } catch(e) { console.error(e); }
}

async function moveCandidateStage(subId, newStage, stageOrder) {
    try {
        var res = await fetch('/api/recruitment/submissions/' + subId + '/stage', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: newStage, stage_order: stageOrder })
        });
        if (!res.ok) { showToast('Failed to move candidate', 'error'); return; }
        showToast('Moved to ' + newStage, 'success');
        loadRecPipeline();
        loadRecSubmissions();
    } catch(e) { showToast('Error', 'error'); }
}

function showMoveStageMenu(subId, currentStage, direction) {
    var idx = recCurrentPipelineStages.indexOf(currentStage);
    var targetIdx = idx + (direction || 1);
    if (targetIdx >= 0 && targetIdx < recCurrentPipelineStages.length) {
        var targetStage = recCurrentPipelineStages[targetIdx];
        moveCandidateStage(subId, targetStage, targetIdx);
    } else {
        showToast(direction < 0 ? 'Already at first stage' : 'Already at final stage', 'info');
    }
}

function showRecFormsList() {
    document.getElementById('rec-forms-list').style.display = 'block';
    document.getElementById('rec-submissions-list').style.display = 'none';
    document.getElementById('rec-sub-detail').style.display = 'none';
}

function showRecSubmissions() {
    document.getElementById('rec-submissions-list').style.display = 'block';
    document.getElementById('rec-sub-detail').style.display = 'none';
}

var _recSubmissionResume = null;
async function showRecSubmissionDetail(subId) {
    recCurrentSubId = subId;
    document.getElementById('rec-submissions-list').style.display = 'none';
    document.getElementById('rec-sub-detail').style.display = 'block';
    try {
        var res = await fetch('/api/recruitment/forms/' + recFormsSubId + '/submissions');
        if (!res.ok) return;
        var subs = await res.json();
        var sub = subs.find(function(s) { return s.id === subId; });
        if (!sub) return;
        document.getElementById('rec-detail-status').value = sub.status || 'new';
        document.getElementById('rec-detail-notes').value = sub.notes || '';
        _recSubmissionResume = sub;
        var answers = {};
        try { answers = JSON.parse(sub.answers || '{}'); } catch(e) {}
        var answersHtml = Object.entries(answers).map(function(entry) {
            return '<div style="margin-bottom:12px;"><strong style="font-size:0.85rem;">' + esc(entry[0]) + '</strong><div style="color:var(--text-primary);margin-top:2px;">' + esc(String(entry[1])) + '</div></div>';
        }).join('');
        document.getElementById('rec-detail-answers').innerHTML = answersHtml || '<p style="color:var(--text-secondary);">No answers provided</p>';
        var stage = sub.current_stage || 'Applied';
        document.getElementById('rec-detail-stage').innerHTML = buildStageMoveHtml(sub.id, stage);
        renderCandidateRating(sub.rating || 0);
        await renderCandidateDocuments(subId);
        await renderCandidateInterviews(subId);
        await renderCandidateOffers(subId);
        await renderCandidateHistory(subId);
        // Reject and reopen are mutually exclusive.
        var rejected = sub.status === 'rejected';
        var rejectBtn = document.getElementById('rec-reject-btn');
        var reopenBtn = document.getElementById('rec-reopen-btn');
        var rejectNote = document.getElementById('rec-reject-note');
        if (rejectBtn) rejectBtn.style.display = rejected ? 'none' : 'inline-flex';
        if (reopenBtn) reopenBtn.style.display = rejected ? 'inline-flex' : 'none';
        if (rejectNote) {
            rejectNote.style.display = rejected ? 'block' : 'none';
            rejectNote.textContent = rejected ? 'Rejected: ' + (sub.rejected_reason || 'no reason recorded') : '';
        }
        var hireBtn = document.getElementById('rec-hire-btn');
        if (hireBtn) hireBtn.style.display = sub.hired_employee_id ? 'none' : 'inline-flex';
        var hiredNote = document.getElementById('rec-hired-note');
        if (hiredNote) {
            hiredNote.style.display = sub.hired_employee_id ? 'block' : 'none';
            hiredNote.textContent = sub.hired_employee_id ? 'Already added to the employee directory.' : '';
        }
    } catch(e) { console.error(e); }
}

// --- Candidate documents ---------------------------------------------------
// Payloads are fetched per file rather than shipped with the candidate list.
var _recDocuments = [];

async function renderCandidateDocuments(subId) {
    var host = document.getElementById('rec-detail-documents');
    if (!host) return;
    host.innerHTML = '<div style="color:var(--text-secondary);font-size:0.85rem;">Loading documents...</div>';
    try {
        var res = await fetch('/api/recruitment/submissions/' + subId + '/documents');
        _recDocuments = res.ok ? await res.json() : [];
    } catch (e) { _recDocuments = []; }
    if (!_recDocuments.length) {
        host.innerHTML = '<div style="color:var(--text-secondary);font-size:0.85rem;padding:12px;border:1px dashed var(--border-color);border-radius:8px;">No documents attached.</div>';
        return;
    }
    host.innerHTML = _recDocuments.map(function (d) {
        var kb = d.file_size ? (d.file_size / 1024).toFixed(0) + ' KB' : '';
        return '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;">' +
               '<span style="flex:1;min-width:140px;overflow-wrap:anywhere;">' + esc(d.file_name) +
               '<span style="display:block;font-size:0.72rem;color:var(--text-secondary);">' + esc(d.doc_type || '') + (kb ? ' &middot; ' + kb : '') + '</span></span>' +
               '<button class="btn btn-outline btn-sm" onclick="previewCandidateDoc(' + d.id + ')">Preview</button>' +
               '<button class="btn btn-outline btn-sm" onclick="downloadCandidateDoc(' + d.id + ')">Download</button>' +
               '</div>';
    }).join('');
}
window.renderCandidateDocuments = renderCandidateDocuments;

async function fetchCandidateDoc(docId) {
    var res = await fetch('/api/recruitment/documents/' + docId);
    if (!res.ok) { showToast('Could not load that document', 'error'); return null; }
    return await res.json();
}

async function previewCandidateDoc(docId) {
    var doc = await fetchCandidateDoc(docId);
    if (!doc) return;
    var host = document.getElementById('rec-detail-preview');
    if (!host) return;
    var mime = doc.file_type || 'application/octet-stream';
    var dataUrl = 'data:' + mime + ';base64,' + doc.file_data;
    if (mime === 'application/pdf') {
        host.innerHTML = '<iframe src="' + dataUrl + '" style="width:100%;height:500px;border:1px solid var(--border-color);border-radius:8px;"></iframe>';
    } else if (mime.indexOf('image/') === 0) {
        host.innerHTML = '<img src="' + dataUrl + '" style="max-width:100%;border-radius:8px;">';
    } else {
        host.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-secondary);border:1px dashed var(--border-color);border-radius:8px;">' +
                         esc(doc.file_name) + ' cannot be previewed in the browser &mdash; use Download.</div>';
    }
}
window.previewCandidateDoc = previewCandidateDoc;

async function downloadCandidateDoc(docId) {
    var doc = await fetchCandidateDoc(docId);
    if (!doc || !doc.file_data) { showToast('No file data available', 'error'); return; }
    var byteStr = atob(doc.file_data);
    var arr = new Uint8Array(byteStr.length);
    for (var i = 0; i < byteStr.length; i++) arr[i] = byteStr.charCodeAt(i);
    var blob = new Blob([arr], { type: doc.file_type || 'application/octet-stream' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = doc.file_name || 'document'; a.click();
    URL.revokeObjectURL(url);
}
window.downloadCandidateDoc = downloadCandidateDoc;

async function renderCandidateHistory(subId) {
    var host = document.getElementById('rec-detail-history');
    if (!host) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + subId + '/history');
        var events = res.ok ? await res.json() : [];
        host.innerHTML = events.length
            ? events.map(function (e) {
                return '<div style="display:flex;gap:10px;font-size:0.8rem;padding:6px 0;border-bottom:1px solid var(--border-color);">' +
                       '<span style="color:var(--text-secondary);white-space:nowrap;">' + esc((e.created_at || '').slice(0, 16)) + '</span>' +
                       '<span>' + (e.from_stage ? esc(e.from_stage) + ' &rarr; ' : '') + '<strong>' + esc(e.to_stage) + '</strong>' +
                       '<span style="color:var(--text-secondary);"> by ' + esc(e.actor || 'HR') + '</span>' +
                       (e.note ? '<div style="color:var(--text-secondary);">' + esc(e.note) + '</div>' : '') + '</span></div>';
              }).join('')
            : '<div style="color:var(--text-secondary);font-size:0.85rem;">No pipeline activity yet.</div>';
    } catch (e) { host.innerHTML = ''; }
}
window.renderCandidateHistory = renderCandidateHistory;

function renderCandidateRating(rating) {
    var host = document.getElementById('rec-detail-rating');
    if (!host) return;
    var html = '';
    for (var i = 1; i <= 5; i++) {
        html += '<button type="button" onclick="setCandidateRating(' + i + ')" aria-label="Rate ' + i + ' of 5" ' +
                'style="background:none;border:none;cursor:pointer;font-size:1.3rem;padding:2px 3px;min-width:32px;min-height:32px;' +
                'color:' + (i <= rating ? 'var(--warning-color)' : 'var(--text-secondary)') + ';">&#9733;</button>';
    }
    html += '<button type="button" onclick="setCandidateRating(0)" class="btn btn-outline btn-sm" style="margin-left:8px;font-size:0.72rem;">Clear</button>';
    host.innerHTML = html;
}
window.renderCandidateRating = renderCandidateRating;

async function setCandidateRating(rating) {
    if (!recCurrentSubId) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/rating', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating: rating })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        renderCandidateRating(data.rating);
        showToast('Rating saved', 'success');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.setCandidateRating = setCandidateRating;

// Turn a successful candidate into an employee without retyping their details.
async function hireCandidate() {
    if (!recCurrentSubId) return;
    var jobTitle = prompt('Job title for the new employee:', '');
    if (jobTitle === null) return;
    var startDate = prompt('Start date (YYYY-MM-DD):', localDate(new Date()));
    if (startDate === null) return;
    var salary = prompt('Salary per pay period (0 if hourly):', '0');
    if (salary === null) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/hire', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_title: jobTitle, start_date: startDate,
                salary: parseFloat(salary) || 0
            })
        });
        var data = await res.json();
        if (!res.ok) { reportApiError(res, data, 'Failed'); return; }
        showToast(data.message, 'success');
        showRecSubmissionDetail(recCurrentSubId);
        // A hire creates an employee and an onboarding checklist.
        hrDataChanged('recruitment');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.hireCandidate = hireCandidate;

function buildStageMoveHtml(subId, currentStage) {
    var stages = recCurrentPipelineStages;
    var stageColors = ['#6366f1', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#06b6d4'];
    var html = '<div style="display:flex;gap:6px;flex-wrap:wrap;">';
    stages.forEach(function(s, i) {
        var color = stageColors[i % stageColors.length];
        var isCurrent = s === currentStage;
        if (isCurrent) {
            html += '<span style="padding:5px 14px;border-radius:16px;font-size:0.8rem;font-weight:600;background:' + color + ';color:white;">' + esc(s) + '</span>';
        } else {
            html += '<button class="btn btn-outline btn-sm" onclick="moveCandidateStage(' + subId + ',' + JSON.stringify(s).replace(/"/g, '&quot;') + ',' + i + ')" style="font-size:0.75rem;padding:3px 10px;border-color:' + color + '40;color:' + color + ';">' + esc(s) + '</button>';
        }
    });
    html += '</div>';
    return html;
}

async function updateRecSubmission() {
    if (!recCurrentSubId) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                status: document.getElementById('rec-detail-status').value,
                notes: document.getElementById('rec-detail-notes').value,
            })
        });
        if (!res.ok) { showToast('Failed to update', 'error'); return; }
        showToast('Submission updated', 'success');
    } catch(e) { showToast('Error', 'error'); }
}

function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

window.showAddFormModal = showAddFormModal;
window.closeRecFormModal = closeRecFormModal;
window.addRecField = addRecField;
window.removeRecField = removeRecField;
window.saveRecForm = saveRecForm;
window.editRecForm = editRecForm;
window.toggleRecForm = toggleRecForm;
window.deleteRecForm = deleteRecForm;
window.copyRecFormLink = copyRecFormLink;
window.showRecFormSubmissions = showRecFormSubmissions;
window.showRecFormsList = showRecFormsList;
window.showRecSubmissions = showRecSubmissions;
window.showRecSubmissionDetail = showRecSubmissionDetail;
window.updateRecSubmission = updateRecSubmission;
window.switchRecView = switchRecView;
window.addRecStage = addRecStage;
window.removeRecStage = removeRecStage;
window.moveRecStageUp = moveRecStageUp;
window.moveRecStageDown = moveRecStageDown;
window.moveCandidateStage = moveCandidateStage;
window.showMoveStageMenu = showMoveStageMenu;

// ==================== LEAVE REQUESTS ====================

async function actionLeave(id, action, empName) {
    if (!confirm('Are you sure you want to ' + action + ' this leave request for ' + empName + '?')) return;
    try {
        var res = await fetch('/api/leave/requests/' + id + '/action', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ action: action })
        });
        var data = await res.json().catch(function () { return {}; });
        // Surface the server's reason (already decided, over entitlement)
        // instead of a generic failure.
        if (res.ok) {
            showToast('Leave request ' + action + 'd', 'success');
            hrDataChanged('leave');
        } else {
            showToast(data.detail || 'Failed to update leave', 'error');
        }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

window.actionLeave = actionLeave;

// --- Dedicated Leave View ---
var _leaveViewFilter = 'all';
async function loadLeaveView() {
    try {
        var res = await fetch('/api/leave/requests', { credentials: 'same-origin' });
        if (!res.ok) return;
        window._allLeaveViewData = await res.json();
        renderLeaveView();
    } catch(e) { console.error('Leave view load failed:', e); }
}
// Builds one row of the leave table.
function leaveRowHtml(l) {
    var statusClass = l.status === 'approved' ? 'status-active'
                    : l.status === 'rejected' ? 'status-terminated' : 'status-onboarding';
    var actions = l.status === 'pending'
        ? '<button class="btn btn-sm" style="background:var(--success-color);color:#fff;margin-right:4px;" ' +
          'onclick="actionLeave(' + l.id + ',\'approve\',\'' + esc(l.employee_name) + '\')">Approve</button>' +
          '<button class="btn btn-sm" style="background:var(--danger-color);color:#fff;" ' +
          'onclick="actionLeave(' + l.id + ',\'reject\',\'' + esc(l.employee_name) + '\')">Reject</button>'
        : '<span style="color:var(--text-secondary);font-size:0.82rem;">' + esc(l.approved_by || '') + '</span>';
    var type = String(l.leave_type || '');
    return '<tr><td><strong>' + employeeLink(l.employee_id, l.employee_name) + '</strong></td>' +
        '<td>' + esc(type.charAt(0).toUpperCase() + type.slice(1)) + '</td>' +
        '<td>' + esc(l.start_date) + '</td>' +
        '<td>' + esc(l.end_date) + '</td>' +
        '<td><strong>' + esc(l.days) + '</strong></td>' +
        '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" ' +
            'title="' + esc(l.reason || '') + '">' + esc(l.reason || '-') + '</td>' +
        '<td><span class="status-pill ' + statusClass + '">' + esc(l.status) + '</span></td>' +
        '<td class="text-right">' + actions + '</td></tr>';
}

function renderLeaveView() {
    var data = window._allLeaveViewData || [];
    
    // Calculate Metrics
    var pending = 0;
    var approved = 0;
    var rejected = 0;
    var awayToday = 0;
    var todayStr = localDate(new Date());

    data.forEach(function(l) {
        if (l.status === 'pending') pending++;
        if (l.status === 'approved') {
            approved++;
            if (todayStr >= l.start_date && todayStr <= l.end_date) awayToday++;
        }
        if (l.status === 'rejected') rejected++;
    });

    if (document.getElementById('leave-metric-pending')) {
        document.getElementById('leave-metric-pending').textContent = pending;
        document.getElementById('leave-metric-approved').textContent = approved;
        document.getElementById('leave-metric-away').textContent = awayToday;
        document.getElementById('leave-metric-rejected').textContent = rejected;
    }

    var filtered = _leaveViewFilter === 'all' ? data : data.filter(function(l) { return l.status === _leaveViewFilter; });
    var tbody = document.getElementById('leave-view-table-body');
    if (!tbody) return;
    if (filtered.length === 0) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">No leave requests found.</td></tr>'; return; }
    tbody.innerHTML = filtered.map(leaveRowHtml).join('');
}
function filterLeaveView(filter, btn) {
    _leaveViewFilter = filter;
    document.querySelectorAll('#leave-view-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    renderLeaveView();
}
window.loadLeaveView = loadLeaveView;
window.filterLeaveView = filterLeaveView;

// --- Dedicated Goals View ---
async function loadGoalsView() {
    var container = document.getElementById('goals-view-list');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">Loading goals...</div>';
    try {
        var empRes = await fetch('/api/employees?status=active');
        var emps = await empRes.json();
        var deptRes = await fetch('/api/departments');
        var depts = await deptRes.json();
        var deptMap = {};
        depts.forEach(function(d) { deptMap[d.id] = d.name; });
        var allGoals = [];
        for (var i = 0; i < emps.length; i++) {
            try {
                var gRes = await fetch('/api/employees/' + emps[i].id + '/goals');
                if (gRes.ok) {
                    var goals = await gRes.json();
                    goals.forEach(function(g) { g.employee_name = emps[i].first_name + ' ' + emps[i].last_name; g.employee_id = emps[i].id; g.department_name = deptMap[g.department_id] || (emps[i].department_id ? deptMap[emps[i].department_id] : '-'); });
                    allGoals = allGoals.concat(goals);
                }
            } catch(e) { console.error('Failed to load goals for employee:', e); }
        }
        var pendingGoals = [];
        try {
            var pgRes = await fetch('/api/goals/department-pending');
            if (pgRes.ok) pendingGoals = await pgRes.json();
        } catch(e) {}

        var html = '';
        if (pendingGoals.length > 0) {
            html += '<div class="glass-widget mb-24"><div class="widget-header"><h3>Pending Department Goals</h3></div><div class="widget-content" style="padding:0;"><div style="padding:12px 16px;font-size:0.82rem;color:var(--text-secondary);background:rgba(252,211,77,0.08);border-bottom:1px solid var(--border-color);">These goals will be auto-assigned to employees when they join their department.</div>' +
                '<table class="data-table"><thead><tr><th>Department</th><th>Goal</th><th>Target</th><th>Category</th><th>Priority</th><th>Due</th></tr></thead><tbody>' +
                pendingGoals.map(function(g) {
                    var pColor = g.priority === 'high' ? 'var(--danger-color)' : g.priority === 'low' ? 'var(--success-color)' : 'var(--warning-color)';
                    return '<tr>' +
                        '<td><strong>' + esc(g.department_name) + '</strong></td>' +
                        '<td>' + esc(g.title) + '<br><span style="font-size:0.75rem;color:var(--text-secondary);">' + esc(g.description || '') + '</span></td>' +
                        '<td>' + g.target_value + ' ' + esc(g.unit || '%') + '</td>' +
                        '<td><span style="font-size:0.8rem;">' + esc(g.category || '-') + '</span></td>' +
                        '<td><span style="font-size:0.8rem;color:' + pColor + ';">' + esc(g.priority || '-') + '</span></td>' +
                        '<td><span style="font-size:0.8rem;">' + (g.due_date || '-') + '</span></td>' +
                    '</tr>';
                }).join('') +
                '</tbody></table></div></div>';
        }

        if (allGoals.length === 0 && pendingGoals.length === 0) {
            container.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-secondary);"><div style="font-size:2rem;margin-bottom:12px;">&#127919;</div><div>No goals assigned yet. Click "Assign Department Goal" to add goals.</div></div>';
            return;
        }
        if (allGoals.length > 0) {
            html += '<div class="glass-widget"><div class="widget-content" style="padding:0;">' +
            '<table class="data-table"><thead><tr><th>Employee</th><th>Department</th><th>Goal</th><th>Progress</th><th>Category</th><th>Priority</th><th>Due</th><th>Status</th></tr></thead><tbody>' +
            allGoals.map(function(g) {
                var progress = g.target_value > 0 ? Math.min(Math.round(g.current_value / g.target_value * 100), 100) : 0;
                var pBadge = g.priority === 'high' ? 'badge-danger' : g.priority === 'low' ? 'badge-success' : 'badge-warning';
                var sBadge = g.status === 'completed' ? 'badge-success' : g.status === 'at_risk' ? 'badge-danger' : 'badge-primary';
                var sColor = g.status === 'completed' ? 'var(--success-color)' : g.status === 'at_risk' ? 'var(--danger-color)' : 'var(--primary-color)';
                return '<tr style="cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background=\'rgba(255,255,255,0.02)\'" onmouseout="this.style.background=\'transparent\'" onclick="viewEmployee(' + g.employee_id + ')">' +
                    '<td><strong>' + esc(g.employee_name) + '</strong></td>' +
                    '<td><span style="font-size:0.8rem;color:var(--text-secondary);">' + esc(g.department_name || '-') + '</span></td>' +
                    '<td><strong style="color:var(--text-color);">' + esc(g.title) + '</strong><br><span style="font-size:0.75rem;color:var(--text-secondary);">' + esc(g.description || '') + '</span></td>' +
                    '<td><div style="display:flex;align-items:center;gap:8px;"><div class="progress-track"><div class="progress-fill" style="width:' + progress + '%;background:' + sColor + ';"></div></div><span style="font-size:0.8rem;font-weight:600;min-width:35px;text-align:right;">' + progress + '%</span></div></td>' +
                    '<td><span class="badge badge-info">' + esc(g.category || '-') + '</span></td>' +
                    '<td><span class="badge ' + pBadge + '">' + esc(g.priority || '-') + '</span></td>' +
                    '<td><span style="font-size:0.85rem;font-weight:500;">' + (g.due_date || '-') + '</span></td>' +
                    '<td><span class="badge ' + sBadge + '">' + (g.status ? g.status.replace('_', ' ') : 'in progress') + '</span></td>' +
                '</tr>';
            }).join('') +
            '</tbody></table></div></div>';
        }
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--danger-color);">Failed to load goals.</div>';
    }
}
window.loadGoalsView = loadGoalsView;

// --- Department Goal Assignment ---
async function openDeptGoalModal() {
    var modal = document.getElementById('dept-goal-modal');
    var select = document.getElementById('dept-goal-dept');
    modal.style.display = 'flex';
    select.innerHTML = '<option value="">Select department...</option>';
    try {
        var res = await fetch('/api/departments');
        var depts = await res.json();
        depts.forEach(function(d) {
            select.innerHTML += '<option value="' + d.id + '">' + esc(d.name) + ' (' + d.employee_count + ' employees)</option>';
        });
    } catch(e) {
        select.innerHTML += '<option value="">Failed to load departments</option>';
    }
    document.getElementById('dept-goal-info').style.display = 'none';
}

async function assignDeptGoal() {
    var deptId = document.getElementById('dept-goal-dept').value;
    var title = document.getElementById('dept-goal-title').value.trim();
    if (!deptId || !title) {
        alert('Please select a department and enter a title');
        return;
    }
    var btn = document.querySelector('#dept-goal-modal .btn-primary');
    btn.disabled = true;
    btn.textContent = 'Assigning...';
    var info = document.getElementById('dept-goal-info');
    try {
        var res = await fetch('/api/goals/assign-department', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                department_id: parseInt(deptId),
                title: title,
                description: document.getElementById('dept-goal-desc').value.trim(),
                target_value: parseFloat(document.getElementById('dept-goal-target').value) || 100,
                unit: document.getElementById('dept-goal-unit').value || '%',
                category: document.getElementById('dept-goal-category').value,
                priority: document.getElementById('dept-goal-priority').value,
                due_date: document.getElementById('dept-goal-due').value || ''
            })
        });
        var data = await res.json();
        if (res.ok) {
            info.style.display = 'block';
            if (data.pending) {
                info.textContent = 'Goal saved! It will be auto-assigned when employees join ' + data.department + '.';
                info.style.background = 'rgba(252,211,77,0.1)';
                info.style.color = 'var(--warning-color)';
            } else {
                info.textContent = 'Goal assigned to ' + data.count + ' employee(s) in department!';
                info.style.background = 'rgba(0,255,0,0.1)';
                info.style.color = 'var(--success-color)';
            }
            setTimeout(function() {
                document.getElementById('dept-goal-modal').style.display = 'none';
                loadGoalsView();
            }, 2000);
        } else {
            throw new Error(data.detail || 'Failed to assign goal');
        }
    } catch(e) {
        info.style.display = 'block';
        info.textContent = 'Error: ' + e.message;
        info.style.background = 'rgba(255,0,0,0.1)';
        info.style.color = 'var(--danger-color)';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Assign to All';
    }
}
window.openDeptGoalModal = openDeptGoalModal;
window.assignDeptGoal = assignDeptGoal;

// ==================== EMPLOYEE GOALS ====================
var currentEmpGoals = [];

async function loadEmpGoals(empId) {
    try {
        var res = await fetch('/api/employees/' + empId + '/goals', { credentials: 'same-origin' });
        if (!res.ok) return;
        currentEmpGoals = await res.json();
        renderEmpGoals();
    } catch (e) { console.error('loadEmpGoals error:', e); }
}

function renderEmpGoals() {
    var el = document.getElementById('emp-goals-list');
    if (!el) return;
    if (currentEmpGoals.length === 0) { el.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No goals assigned yet.</p>'; return; }
    el.innerHTML = '';
    currentEmpGoals.forEach(function(g) {
        var progress = g.target_value > 0 ? Math.min(Math.round(g.current_value / g.target_value * 100), 100) : 0;
        var pColor = g.priority === 'high' ? 'var(--danger-color)' : g.priority === 'low' ? 'var(--success-color)' : 'var(--warning-color)';
        var sColor = g.status === 'completed' ? 'var(--success-color)' : 'var(--primary-color)';
        el.insertAdjacentHTML('beforeend', '<div style="padding:12px 0;border-bottom:1px solid var(--border-color);"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;"><strong style="font-size:0.9rem;">' + esc(g.title) + '</strong><span style="font-size:0.75rem;color:' + sColor + ';">' + g.status.replace('_', ' ') + '</span></div><div style="height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;"><div style="height:100%;width:' + progress + '%;background:' + sColor + ';border-radius:3px;"></div></div><div style="display:flex;justify-content:space-between;margin-top:4px;font-size:0.78rem;color:var(--text-secondary);"><span>' + g.current_value + ' / ' + g.target_value + ' ' + g.unit + '</span><span style="color:' + pColor + ';">' + g.priority + '</span></div></div>');
    });
}

function showCreateGoalModal() {
    document.getElementById('create-goal-modal').style.display = 'flex';
    document.getElementById('goal-title').value = '';
    document.getElementById('goal-desc').value = '';
    document.getElementById('goal-target').value = '100';
    document.getElementById('goal-unit').value = '%';
    document.getElementById('goal-due').value = '';
}

async function createGoal() {
    if (!currentEmployeeId) return showToast('No employee selected', 'error');
    var title = document.getElementById('goal-title').value.trim();
    if (!title) return showToast('Enter a goal title', 'error');
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId + '/goals', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({
                title: title, description: document.getElementById('goal-desc').value,
                target_value: parseFloat(document.getElementById('goal-target').value) || 100,
                unit: document.getElementById('goal-unit').value || '%',
                category: document.getElementById('goal-category').value,
                priority: document.getElementById('goal-priority').value,
                due_date: document.getElementById('goal-due').value,
            })
        });
        if (res.ok) { showToast('Goal created', 'success'); document.getElementById('create-goal-modal').style.display = 'none'; loadEmpGoals(currentEmployeeId); }
        else { showToast('Failed to create goal', 'error'); }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

window.showCreateGoalModal = showCreateGoalModal;
window.createGoal = createGoal;

// ==================== EMPLOYEE DOCUMENTS ====================
var currentEmpDocs = [];

async function loadEmpDocs(empId) {
    try {
        var res = await fetch('/api/employees/' + empId + '/documents', { credentials: 'same-origin' });
        if (!res.ok) return;
        currentEmpDocs = await res.json();
        renderEmpDocs();
    } catch (e) { console.error('loadEmpDocs error:', e); }
}

function renderEmpDocs() {
    var el = document.getElementById('emp-documents-list');
    if (!el) return;
    if (currentEmpDocs.length === 0) { el.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No documents uploaded yet.</p>'; return; }
    el.innerHTML = '';
    currentEmpDocs.forEach(function(d) {
        el.insertAdjacentHTML('beforeend', '<div style="padding:10px 0;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;"><div><div style="font-weight:500;font-size:0.9rem;">' + esc(d.title) + '</div><div style="font-size:0.78rem;color:var(--text-secondary);">' + d.doc_type + ' &bull; ' + d.file_name + ' &bull; ' + d.created_at + '</div></div></div>');
    });
}

function showUploadDocModal() {
    document.getElementById('upload-doc-modal').style.display = 'flex';
    document.getElementById('doc-title').value = '';
    document.getElementById('doc-file').value = '';
    document.getElementById('doc-file-info').textContent = '';
}

function previewDocFile() {
    var file = document.getElementById('doc-file').files[0];
    if (file) document.getElementById('doc-file-info').textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
}

async function uploadDocument() {
    if (!currentEmployeeId) return showToast('No employee selected', 'error');
    var title = document.getElementById('doc-title').value.trim();
    if (!title) return showToast('Enter a document title', 'error');
    var fileInput = document.getElementById('doc-file');
    if (!fileInput.files[0]) return showToast('Select a file', 'error');
    var file = fileInput.files[0];
    if (file.size > 10 * 1024 * 1024) return showToast('File too large (max 10MB)', 'error');
    try {
        var base64 = await new Promise(function(resolve) {
            var reader = new FileReader();
            reader.onload = function(e) { resolve(e.target.result.split(',')[1]); };
            reader.readAsDataURL(file);
        });
        var res = await fetch('/api/employees/' + currentEmployeeId + '/documents', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({
                title: title, doc_type: document.getElementById('doc-type').value,
                file_name: file.name, file_type: file.type, file_data: base64,
            })
        });
        if (res.ok) { showToast('Document uploaded', 'success'); document.getElementById('upload-doc-modal').style.display = 'none'; loadEmpDocs(currentEmployeeId); }
        else { showToast('Upload failed', 'error'); }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
}

window.showUploadDocModal = showUploadDocModal;
window.previewDocFile = previewDocFile;
window.uploadDocument = uploadDocument;

// ==================== AI FEATURES ====================

// --- AI: Resume Screening ---
async function aiScreenResume() {
    var el = document.getElementById('ai-screen-result');
    if (el) el.innerHTML = '<div style="padding:16px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> AI is analyzing resume...</div>';
    try {
        var form = recFormsLookup[recFormsSubId];
        var jobTitle = form ? form.title : 'Position';
        var jobDesc = form ? (form.description || '') : '';
        var candidateName = 'Candidate';
        var resumeText = '';
        var res2 = await fetch('/api/recruitment/forms/' + recFormsSubId + '/submissions', { credentials: 'same-origin' });
        if (res2.ok) {
            var subs = await res2.json();
            var sub = subs.find(function(s) { return s.id === recCurrentSubId; });
            if (sub) {
                candidateName = sub.candidate_name || 'Candidate';
                var answers = {};
                try { answers = JSON.parse(sub.answers || '{}'); } catch(e) {}
                resumeText = Object.entries(answers).map(function(e) { return e[0] + ': ' + e[1]; }).join('\n');
                if (sub.file_name) resumeText += '\n\nResume file: ' + sub.file_name;
            }
        }
        var res = await fetch('/api/ai/screen-resume', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ job_title: jobTitle, job_description: jobDesc, candidate_name: candidateName, resume_text: resumeText })
        });
        var data = await res.json();
        if (el) {
            var scoreColor = data.score >= 70 ? 'var(--success-color)' : data.score >= 40 ? 'var(--warning-color)' : 'var(--danger-color)';
            el.innerHTML = '<div style="padding:16px;">' +
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
                    '<div style="width:48px;height:48px;border-radius:50%;background:' + scoreColor + '20;display:flex;align-items:center;justify-content:center;font-size:1.1rem;font-weight:700;color:' + scoreColor + ';">' + data.score + '</div>' +
                    '<div><div style="font-weight:600;">AI Score: ' + data.score + '/100</div><div style="font-size:0.85rem;color:var(--text-secondary);">' + esc(data.recommendation || '') + '</div></div>' +
                '</div>' +
                (data.summary ? '<div style="margin-bottom:12px;font-size:0.9rem;">' + esc(data.summary) + '</div>' : '') +
                (data.strengths && data.strengths.length ? '<div style="margin-bottom:8px;"><strong style="font-size:0.8rem;color:var(--success-color);">STRENGTHS</strong><ul style="margin:4px 0 0 16px;font-size:0.85rem;">' + data.strengths.map(function(s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul></div>' : '') +
                (data.weaknesses && data.weaknesses.length ? '<div style="margin-bottom:8px;"><strong style="font-size:0.8rem;color:var(--danger-color);">WEAKNESSES</strong><ul style="margin:4px 0 0 16px;font-size:0.85rem;">' + data.weaknesses.map(function(s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul></div>' : '') +
                '<button class="btn btn-outline btn-sm" onclick="this.parentElement.remove()" style="margin-top:8px;">Dismiss</button>' +
            '</div>';
        }
    } catch(e) {
        if (el) el.innerHTML = '<div style="padding:16px;color:var(--danger-color);">AI screening unavailable. Check GROQ_API_KEY.</div>';
    }
}
window.aiScreenResume = aiScreenResume;

// --- AI: Onboarding Generator ---
async function aiGenerateOnboarding() {
    var title = document.getElementById('emp-job-title').value.trim();
    var deptEl = document.getElementById('emp-department');
    var dept = deptEl.options[deptEl.selectedIndex] ? deptEl.options[deptEl.selectedIndex].text : '';
    if (!title) return showToast('Enter a job title first', 'error');
    var btn = document.getElementById('ai-onboard-btn');
    if (btn) { btn.textContent = 'Generating...'; btn.disabled = true; }
    try {
        var res = await fetch('/api/ai/generate-onboarding', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ job_title: title, department: dept === 'None' ? '' : dept })
        });
        var data = await res.json();
        if (data.items && data.items.length) {
            showToast('Generated ' + data.items.length + ' onboarding items', 'success');
            window._aiOnboardingItems = data.items;
            var preview = document.getElementById('ai-onboard-preview');
            if (preview) {
                preview.innerHTML = '<div style="margin-top:12px;"><strong style="font-size:0.85rem;color:var(--primary-color);">AI-Generated Checklist (' + data.items.length + ' items):</strong>' +
                    data.items.map(function(item) {
                        return '<div style="padding:6px 0;border-bottom:1px solid var(--border-color);font-size:0.85rem;"><span style="color:var(--primary-color);font-weight:600;">' + esc(item.category || 'General') + ':</span> ' + esc(item.title) + (item.description ? ' <span style="color:var(--text-secondary);">— ' + esc(item.description) + '</span>' : '') + '</div>';
                    }).join('') + '</div>';
                preview.style.display = 'block';
            }
        } else {
            showToast('AI could not generate checklist', 'error');
        }
    } catch(e) { showToast(aiUnavailableText(), 'error'); }
    if (btn) { btn.textContent = 'AI Generate Checklist'; btn.disabled = false; }
}
window.aiGenerateOnboarding = aiGenerateOnboarding;

// --- AI: Invoice Email Personalization ---
async function aiPersonalizeEmail(invoiceNumber, clientName, total, dueDate) {
    var el = document.getElementById('ai-email-preview');
    if (el) el.innerHTML = '<div style="padding:12px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> AI generating personalized email...</div>';
    try {
        var res = await fetch('/api/ai/personalize-email', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ client_name: clientName, invoice_number: invoiceNumber, total: total, due_date: dueDate, is_first_time: false, tone: 'professional' })
        });
        var data = await res.json();
        // Held rather than threaded through an onclick attribute; the body is
        // multi-line free text and would not survive the quoting.
        _lastAiEmail = { subject: data.subject || '', body: data.body || '' };
        if (el) {
            el.innerHTML = '<div style="padding:12px;">' +
                '<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px;">Subject: ' + esc(data.subject || '') + '</div>' +
                '<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border-color);border-radius:8px;padding:12px;font-size:0.85rem;white-space:pre-wrap;">' + esc(data.body || '') + '</div>' +
                '<div style="display:flex;gap:8px;margin-top:8px;">' +
                    '<button class="btn btn-primary btn-sm" onclick="useAiEmail()">Copy Email</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="aiPersonalizeEmail(\'' + invoiceNumber + '\',\'' + esc(clientName) + '\',' + total + ',\'' + dueDate + '\')">Regenerate</button>' +
                '</div></div>';
            el.style.display = 'block';
        }
    } catch(e) {
        if (el) el.innerHTML = '<div style="padding:12px;color:var(--danger-color);">' + esc(aiUnavailableText()) + '</div>';
    }
}
window.aiPersonalizeEmail = aiPersonalizeEmail;

var _lastAiEmail = null;

function useAiEmail() {
    if (!_lastAiEmail) { showToast('Generate an email first', 'error'); return; }
    var text = 'Subject: ' + _lastAiEmail.subject + '\n\n' + _lastAiEmail.body;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
            showToast('Email copied to clipboard', 'success');
        }, function () {
            showToast('Could not copy - select the text above instead', 'error');
        });
    } else {
        showToast('Could not copy - select the text above instead', 'error');
    }
}

// --- AI: Overdue Follow-up ---
async function aiGenerateFollowup(invoiceNumber, clientName, total, daysOverdue) {
    var el = document.getElementById('ai-followup-result');
    if (el) el.innerHTML = '<div style="padding:12px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> AI generating follow-up...</div>';
    try {
        var res = await fetch('/api/ai/generate-followup', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ client_name: clientName, invoice_number: invoiceNumber, total: total, days_overdue: daysOverdue, tone: 'polite' })
        });
        var data = await res.json();
        if (el) {
            el.innerHTML = '<div style="padding:12px;">' +
                '<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px;">Subject: ' + esc(data.subject || '') + '</div>' +
                '<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border-color);border-radius:8px;padding:12px;font-size:0.85rem;white-space:pre-wrap;">' + esc(data.body || '') + '</div>' +
                '<button class="btn btn-outline btn-sm" onclick="this.parentElement.remove()" style="margin-top:8px;">Dismiss</button>' +
            '</div>';
            el.style.display = 'block';
        }
    } catch(e) {
        if (el) el.innerHTML = '<div style="padding:12px;color:var(--danger-color);">' + esc(aiUnavailableText()) + '</div>';
    }
}
window.aiGenerateFollowup = aiGenerateFollowup;

// --- AI: Payroll Anomalies ---
async function loadPayrollAnomalies() {
    var el = document.getElementById('payroll-anomalies');
    if (!el) return;
    el.innerHTML = '<div style="padding:16px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> Checking payroll data...</div>';
    try {
        var res = await fetch('/api/ai/payroll-anomalies', { credentials: 'same-origin' });
        var data = await res.json();
        if (!data.anomalies || !data.anomalies.length) {
            el.innerHTML = '<div style="padding:16px;color:var(--success-color);"><i class="bi bi-check-circle"></i> No payroll anomalies detected across ' + data.total_checked + ' employees.</div>';
            return;
        }
        el.innerHTML = '<div style="padding:16px;">' +
            '<div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px;">Found ' + data.anomalies.length + ' anomal' + (data.anomalies.length === 1 ? 'y' : 'ies') + ' across ' + data.total_checked + ' employees:</div>' +
            data.anomalies.map(function(a) {
                var color = a.direction === 'increased' ? 'var(--success-color)' : 'var(--danger-color)';
                return '<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-color);">' +
                    '<div style="width:8px;height:8px;border-radius:50%;background:' + color + ';flex-shrink:0;"></div>' +
                    '<div style="flex:1;"><strong>' + esc(a.employee_name) + '</strong><br><span style="font-size:0.8rem;color:var(--text-secondary);">' + getCurrencySymbol() + a.previous_net.toFixed(2) + ' → ' + getCurrencySymbol() + a.latest_net.toFixed(2) + ' (' + a.change_pct + '% ' + a.direction + ')</span></div>' +
                    '<span class="status-pill" style="background:' + color + '20;color:' + color + ';">' + a.change_pct + '%</span>' +
                '</div>';
            }).join('') + '</div>';
    } catch(e) { el.innerHTML = '<div style="padding:16px;color:var(--danger-color);">Failed to check anomalies.</div>'; }
}
window.loadPayrollAnomalies = loadPayrollAnomalies;

// --- AI: Attendance Alerts ---
async function loadAttendanceAlerts() {
    var el = document.getElementById('attendance-alerts');
    if (!el) return;
    el.innerHTML = '<div style="padding:16px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> Analyzing attendance patterns...</div>';
    try {
        var res = await fetch('/api/ai/attendance-alerts', { credentials: 'same-origin' });
        var data = await res.json();
        if (!data.alerts || !data.alerts.length) {
            el.innerHTML = '<div style="padding:16px;color:var(--success-color);"><i class="bi bi-check-circle"></i> No attendance alerts. All ' + data.employees_checked + ' employees look good over the last 30 days.</div>';
            return;
        }
        el.innerHTML = '<div style="padding:16px;">' +
            '<div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px;">' + data.alerts.length + ' employee' + (data.alerts.length === 1 ? '' : 's') + ' with alerts (' + data.employees_checked + ' checked):</div>' +
            data.alerts.map(function(a) {
                return '<div style="padding:10px 0;border-bottom:1px solid var(--border-color);">' +
                    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;"><strong>' + esc(a.employee_name) + '</strong><span style="font-size:0.78rem;color:var(--text-secondary);">' + a.total_hours_30d + 'h total</span></div>' +
                    a.alerts.map(function(al) {
                        var sevColor = al.severity === 'critical' ? 'var(--danger-color)' : 'var(--warning-color)';
                        return '<div style="display:flex;align-items:center;gap:6px;padding:2px 0;font-size:0.85rem;"><span style="width:6px;height:6px;border-radius:50%;background:' + sevColor + ';"></span>' + esc(al.message) + '</div>';
                    }).join('') + '</div>';
            }).join('') + '</div>';
    } catch(e) { el.innerHTML = '<div style="padding:16px;color:var(--danger-color);">Failed to load attendance alerts.</div>'; }
}
window.loadAttendanceAlerts = loadAttendanceAlerts;

// --- AI: Attendance Summary ---
async function loadAttendanceSummary() {
    var el = document.getElementById('ai-attendance-summary');
    if (!el) return;
    el.innerHTML = '<div style="padding:12px;color:var(--text-secondary);"><i class="bi bi-hourglass-split"></i> Generating AI summary...</div>';
    try {
        var res = await fetch('/api/ai/summarize-attendance', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: '{}' });
        var data = await res.json();
        el.innerHTML = '<div style="padding:12px;font-size:0.9rem;white-space:pre-wrap;">' + esc(data.summary || 'No summary available.') + '</div>';
    } catch(e) { el.innerHTML = '<div style="padding:12px;color:var(--danger-color);">AI summary unavailable.</div>'; }
}
window.loadAttendanceSummary = loadAttendanceSummary;

// --- Invoice AI helpers ---
function aiGenerateInvEmail() {
    var contact = document.getElementById('view-inv-contact').textContent || '';
    var number = document.getElementById('view-inv-number-val').textContent || '';
    var total = document.getElementById('view-inv-due-val').textContent || '0';
    var dueDate = document.getElementById('view-inv-due-date').textContent || '';

    aiPersonalizeEmail(number, contact, parseFloat(total) || 0, dueDate);
}

function aiGenerateInvFollowup() {
    var contact = document.getElementById('view-inv-contact').textContent || '';
    var number = document.getElementById('view-inv-number-val').textContent || '';
    var total = document.getElementById('view-inv-due-val').textContent || '0';
    var days = parseInt(document.getElementById('ai-followup-days').value) || 14;
    aiGenerateFollowup(number, contact, parseFloat(total) || 0, days);
}

window.aiGenerateInvEmail = aiGenerateInvEmail;
window.aiGenerateInvFollowup = aiGenerateInvFollowup;
window.useAiEmail = useAiEmail;

// ============================================================
// BILLS MODULE
// ============================================================
var allBills = [];
var currentBillFilter = '';

async function loadBills() {
    try {
        var res = await fetch('/api/bills', { credentials: 'same-origin' });
        if (!res.ok) { showToast('Failed to load bills', 'error'); return; }
        allBills = await res.json();
        renderBills(allBills);
    } catch(e) { showToast('Failed to load bills', 'error'); }
}
window.loadBills = loadBills;

function renderBills(bills) {
    var tbody = document.getElementById('bills-table-body');
    var countSpan = document.getElementById('bill-count');
    if (countSpan) countSpan.textContent = bills.length + ' item' + (bills.length !== 1 ? 's' : '');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (bills.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">No bills found.</td></tr>';
        return;
    }
    bills.forEach(function(b) {
        var statusClass = (b.status || '').toLowerCase().replace(/\s+/g, '-');
        tbody.insertAdjacentHTML('beforeend',
            '<tr>' +
            '<td><strong>' + esc(b.number || '-') + '</strong></td>' +
            '<td>' + esc(b.vendor_name || '-') + '</td>' +
            '<td>' + (b.issue_date || '-') + '</td>' +
            '<td>' + (b.due_date || '-') + '</td>' +
            '<td class="text-right">' + formatCurrency(b.total || 0) + '</td>' +
            '<td class="text-right">' + formatCurrency(b.amount_paid || 0) + '</td>' +
            '<td><span class="status-pill status-' + statusClass + '">' + esc(b.status || 'Draft') + '</span></td>' +
            '<td class="text-right">' +
                '<button class="btn btn-outline btn-sm" onclick="editBill(' + b.id + ')" style="margin-right:4px;">Edit</button>' +
                (b.status !== 'Paid' ? '<button class="btn btn-outline btn-sm" onclick="markBillPaid(' + b.id + ')" style="color:var(--success-color);border-color:var(--success-color);margin-right:4px;">Pay</button>' : '') +
                '<button class="btn btn-outline btn-sm" onclick="deleteBill(' + b.id + ', \'' + esc(b.number) + '\')" style="color:var(--danger-color);border-color:var(--danger-color);">Del</button>' +
            '</td></tr>'
        );
    });
}

function filterBills(status, btn) {
    currentBillFilter = status;
    document.querySelectorAll('#bills-view .invoices-tabs .tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var filtered = status === '' ? allBills : allBills.filter(function(b) {
        if (status === 'Unpaid') return b.status !== 'Paid' && b.status !== 'Draft';
        return (b.status || '').toLowerCase() === status.toLowerCase();
    });
    renderBills(filtered);
}
window.filterBills = filterBills;

function searchBills() {
    var q = (document.getElementById('bill-search').value || '').toLowerCase();
    var filtered = allBills.filter(function(b) {
        return (b.number || '').toLowerCase().indexOf(q) >= 0 || (b.vendor_name || '').toLowerCase().indexOf(q) >= 0 || (b.reference || '').toLowerCase().indexOf(q) >= 0;
    });
    renderBills(filtered);
}
window.searchBills = searchBills;

async function showAddBillModal() {
    document.getElementById('bill-edit-id').value = '';
    document.getElementById('bill-modal-title').textContent = 'New Bill';
    document.getElementById('bill-number').value = '';
    document.getElementById('bill-vendor').value = '';
    document.getElementById('bill-vendor-email').value = '';
    document.getElementById('bill-category').value = 'general';
    document.getElementById('bill-issue-date').value = localDate(new Date());
    document.getElementById('bill-due-date').value = '';
    document.getElementById('bill-amount').value = '0';
    document.getElementById('bill-tax').value = '0';
    document.getElementById('bill-total').value = '0';
    document.getElementById('bill-reference').value = '';
    document.getElementById('bill-notes').value = '';
    try {
        var res = await fetch('/api/next-bill-number', { credentials: 'same-origin' });
        var data = await res.json();
        document.getElementById('bill-number').value = data.number || 'BILL-0001';
    } catch(e) {}
    document.getElementById('add-bill-modal').style.display = 'flex';
}
window.showAddBillModal = showAddBillModal;

function closeAddBillModal() {
    document.getElementById('add-bill-modal').style.display = 'none';
}
window.closeAddBillModal = closeAddBillModal;


// Bills used to make you type the tax figure yourself, which ignored the rates
// the tenant had defined. The amount is still what gets stored; the picker
// just works it out.
function applyBillTaxRate() {
    var sel = document.getElementById('bill-tax-rate');
    var amountEl = document.getElementById('bill-amount');
    var taxEl = document.getElementById('bill-tax');
    if (!sel || !amountEl || !taxEl) return;
    var rate = parseFloat(sel.value);
    if (isNaN(rate)) return;                 // "Enter it myself"
    var amount = parseFloat(amountEl.value) || 0;
    taxEl.value = (amount * rate / 100).toFixed(2);
    calcBillTotal();
}
window.applyBillTaxRate = applyBillTaxRate;

function renderBillTaxRates() {
    var sel = document.getElementById('bill-tax-rate');
    if (!sel) return;
    var current = sel.value;
    var opts = '<option value="">Enter it myself</option>';
    (_taxRates || []).forEach(function (t) {
        opts += '<option value="' + esc(t.percent) + '">' + esc(t.label) + '</option>';
    });
    sel.innerHTML = opts;
    sel.value = current;
}
window.renderBillTaxRates = renderBillTaxRates;

function calcBillTotal() {
    // Keep the tax figure in step when the amount changes under a chosen rate.
    var rateSel = document.getElementById('bill-tax-rate');
    if (rateSel && rateSel.value !== '' && !calcBillTotal._reentrant) {
        calcBillTotal._reentrant = true;
        applyBillTaxRate();
        calcBillTotal._reentrant = false;
    }
    var amount = parseFloat(document.getElementById('bill-amount').value) || 0;
    var tax = parseFloat(document.getElementById('bill-tax').value) || 0;
    document.getElementById('bill-total').value = (amount + tax).toFixed(2);
}
window.calcBillTotal = calcBillTotal;

async function saveBill() {
    var editId = document.getElementById('bill-edit-id').value;
    var payload = {
        number: document.getElementById('bill-number').value.trim(),
        vendor_name: document.getElementById('bill-vendor').value.trim(),
        vendor_email: document.getElementById('bill-vendor-email').value.trim(),
        category: document.getElementById('bill-category').value,
        issue_date: document.getElementById('bill-issue-date').value,
        due_date: document.getElementById('bill-due-date').value,
        amount: parseFloat(document.getElementById('bill-amount').value) || 0,
        tax_amount: parseFloat(document.getElementById('bill-tax').value) || 0,
        total: parseFloat(document.getElementById('bill-total').value) || 0,
        reference: document.getElementById('bill-reference').value.trim(),
        notes: document.getElementById('bill-notes').value.trim(),
        status: 'Draft'
    };
    if (!payload.number || !payload.vendor_name) { showToast('Bill number and vendor name required', 'error'); return; }
    try {
        var url = editId ? '/api/bills/' + editId : '/api/bills';
        var method = editId ? 'PUT' : 'POST';
        var res = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify(payload) });
        var data = await res.json();
        if (res.ok) {
            showToast(editId ? 'Bill updated' : 'Bill created', 'success');
            closeAddBillModal();
            loadBills();
        } else {
            showToast(data.detail || 'Failed to save bill', 'error');
        }
    } catch(e) { showToast('Failed to save bill', 'error'); }
}
window.saveBill = saveBill;

async function editBill(id) {
    try {
        var res = await fetch('/api/bills/' + id, { credentials: 'same-origin' });
        var b = await res.json();
        document.getElementById('bill-edit-id').value = b.id;
        document.getElementById('bill-modal-title').textContent = 'Edit Bill';
        document.getElementById('bill-number').value = b.number || '';
        document.getElementById('bill-vendor').value = b.vendor_name || '';
        document.getElementById('bill-vendor-email').value = b.vendor_email || '';
        document.getElementById('bill-category').value = b.category || 'general';
        document.getElementById('bill-issue-date').value = b.issue_date || '';
        document.getElementById('bill-due-date').value = b.due_date || '';
        document.getElementById('bill-amount').value = b.amount || 0;
        document.getElementById('bill-tax').value = b.tax_amount || 0;
        document.getElementById('bill-total').value = b.total || 0;
        document.getElementById('bill-reference').value = b.reference || '';
        document.getElementById('bill-notes').value = b.notes || '';
        document.getElementById('add-bill-modal').style.display = 'flex';
    } catch(e) { showToast('Failed to load bill', 'error'); }
}
window.editBill = editBill;

async function markBillPaid(id) {
    if (!confirm('Mark this bill as paid?')) return;
    try {
        var res = await fetch('/api/bills/' + id + '/pay', { method: 'POST', credentials: 'same-origin' });
        if (res.ok) { showToast('Bill marked as paid', 'success'); loadBills(); }
        else showToast('Failed to mark paid', 'error');
    } catch(e) { showToast('Failed to mark paid', 'error'); }
}
window.markBillPaid = markBillPaid;

async function deleteBill(id, number) {
    if (!confirm('Delete bill ' + number + '?')) return;
    try {
        var res = await fetch('/api/bills/' + id, { method: 'DELETE', credentials: 'same-origin' });
        if (res.ok) { showToast('Bill deleted', 'success'); loadBills(); }
        else showToast('Failed to delete bill', 'error');
    } catch(e) { showToast('Failed to delete bill', 'error'); }
}
window.deleteBill = deleteBill;

// ============================================================
// CONTACTS MODULE
// ============================================================
var allContacts = typeof allContacts !== 'undefined' ? allContacts : [];

async function loadContacts() {
    try {
        var res = await fetch('/api/contacts', { credentials: 'same-origin' });
        if (!res.ok) { showToast('Failed to load contacts', 'error'); return; }
        allContacts = await res.json();
        renderContacts(allContacts);
    } catch(e) { showToast('Failed to load contacts', 'error'); }
}
window.loadContacts = loadContacts;

function renderContacts(contacts) {
    var tbody = document.getElementById('contacts-table-body');
    var countSpan = document.getElementById('contact-count');
    if (countSpan) countSpan.textContent = contacts.length + ' item' + (contacts.length !== 1 ? 's' : '');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (contacts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-secondary);">No contacts found.</td></tr>';
        return;
    }
    contacts.forEach(function(c) {
        tbody.insertAdjacentHTML('beforeend',
            // The name opens their history; the buttons still edit the record.
            '<tr>' +
            '<td style="cursor:pointer;" onclick="openCustomer(' + c.id + ')">' +
                '<strong style="color:var(--primary-color);">' + esc(c.name || '-') + '</strong></td>' +
            '<td>' + esc(c.email || '-') + '</td>' +
            '<td>' + esc(c.phone_number || c.phone || '-') + '</td>' +
            '<td class="text-right">' +
                '<button class="btn btn-outline btn-sm" onclick="editContact(' + c.id + ')" style="margin-right:4px;">Edit</button>' +
                '<button class="btn btn-outline btn-sm" onclick="deleteContact(' + c.id + ', \'' + esc(c.name) + '\')" style="color:var(--danger-color);border-color:var(--danger-color);">Del</button>' +
            '</td></tr>'
        );
    });
}

function searchContacts() {
    var q = (document.getElementById('contact-search').value || '').toLowerCase();
    var filtered = allContacts.filter(function(c) {
        return (c.name || '').toLowerCase().indexOf(q) >= 0 || (c.email || '').toLowerCase().indexOf(q) >= 0 || ((c.phone_number || c.phone || '') || '').toLowerCase().indexOf(q) >= 0;
    });
    renderContacts(filtered);
}
window.searchContacts = searchContacts;

function showAddContactModal() {
    document.getElementById('contact-edit-id').value = '';
    document.getElementById('contact-modal-title').textContent = 'New Contact';
    document.getElementById('contact-name').value = '';
    document.getElementById('contact-email').value = '';
    document.getElementById('contact-phone').value = '';
    document.getElementById('add-contact-modal').style.display = 'flex';
}
window.showAddContactModal = showAddContactModal;

function closeAddContactModal() {
    document.getElementById('add-contact-modal').style.display = 'none';
}
window.closeAddContactModal = closeAddContactModal;

async function saveContact() {
    var editId = document.getElementById('contact-edit-id').value;
    var name = document.getElementById('contact-name').value.trim();
    var email = document.getElementById('contact-email').value.trim();
    var phone = document.getElementById('contact-phone').value.trim();
    if (!name) { showToast('Contact name required', 'error'); return; }
    try {
        if (editId) {
            var res = await fetch('/api/contacts/' + editId, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify({ name: name, email: email, phone_number: phone }) });
            if (res.ok) { showToast('Contact updated', 'success'); }
            else { showToast('Failed to update contact', 'error'); return; }
        } else {
            var res = await fetch('/api/contacts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify({ name: name, email: email, phone_number: phone }) });
            if (res.ok) { showToast('Contact created', 'success'); }
            else { showToast('Failed to create contact', 'error'); return; }
        }
        closeAddContactModal();
        loadContacts();
    } catch(e) { showToast('Failed to save contact', 'error'); }
}
window.saveContact = saveContact;

async function editContact(id) {
    var c = allContacts.find(function(x) { return x.id === id; });
    if (!c) return;
    document.getElementById('contact-edit-id').value = c.id;
    document.getElementById('contact-modal-title').textContent = 'Edit Contact';
    document.getElementById('contact-name').value = c.name || '';
    document.getElementById('contact-email').value = c.email || '';
    document.getElementById('contact-phone').value = c.phone_number || c.phone || '';
    document.getElementById('add-contact-modal').style.display = 'flex';
}
window.editContact = editContact;

async function deleteContact(id, name) {
    if (!confirm('Delete contact "' + name + '"?')) return;
    try {
        var res = await fetch('/api/contacts/' + id, { method: 'DELETE', credentials: 'same-origin' });
        if (res.ok) { showToast('Contact deleted', 'success'); loadContacts(); }
        else showToast('Failed to delete contact', 'error');
    } catch(e) { showToast('Failed to delete contact', 'error'); }
}
window.deleteContact = deleteContact;

// ============================================================
// REPORTS MODULE
// ============================================================
function showReportsTab(tab) {
    ['reports-content', 'reports-pl-content', 'reports-bs-content', 'reports-cash-content'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    ['rpt-pl-btn', 'rpt-bs-btn', 'rpt-cash-btn'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) { el.style.fontWeight = 'normal'; el.classList.remove('btn-primary'); el.classList.add('btn-outline'); }
    });
    if (tab === 'pl') {
        var el = document.getElementById('reports-pl-content'); if (el) el.style.display = 'block';
        var btn = document.getElementById('rpt-pl-btn'); if (btn) { btn.style.fontWeight = '700'; }
    } else if (tab === 'bs') {
        var el = document.getElementById('reports-bs-content'); if (el) el.style.display = 'block';
        var btn = document.getElementById('rpt-bs-btn'); if (btn) { btn.style.fontWeight = '700'; }
    } else if (tab === 'cash') {
        var el = document.getElementById('reports-cash-content'); if (el) el.style.display = 'block';
        var btn = document.getElementById('rpt-cash-btn'); if (btn) { btn.style.fontWeight = '700'; }
    } else {
        var el = document.getElementById('reports-content'); if (el) el.style.display = 'block';
    }
}

// Reports are figured one currency at a time, because adding GBP to INR needs
// a rate we do not have. The headline numbers are the account's own currency;
// anything invoiced in another shows up here rather than vanishing.
function otherCurrencyNote(data, pick) {
    var others = (data && data.other_currencies) || [];
    if (!others.length) return '';
    var parts = others.map(function (block) {
        return '<span style="white-space:nowrap;"><strong>' +
            formatCurrency(pick(block), block.currency) + '</strong></span>';
    }).join(' &middot; ');
    return '<div style="margin-bottom:16px;padding:12px 14px;border-radius:8px;' +
        'background:rgba(255,255,255,0.03);border-left:3px solid var(--warning-color, #f0ad4e);' +
        'font-size:0.86rem;color:var(--text-secondary);">' +
        'Figures below are in <strong>' + (data.currency || '') + '</strong>. ' +
        'Invoiced separately: ' + parts +
        '<br><span style="opacity:0.75;">Currencies are never added together, as no exchange rate is set.</span>' +
        '</div>';
}

async function loadProfitLoss() {
    showReportsTab('pl');
    var body = document.getElementById('pl-report-body');
    var chart = document.getElementById('pl-chart');
    if (body) body.innerHTML = '<div style="padding:16px;color:var(--text-secondary);">Loading...</div>';
    try {
        var res = await fetch('/api/reports/profit-loss', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed');
        var data = await res.json();
        if (body) {
            body.innerHTML = otherCurrencyNote(data, function (b) { return b.total_revenue; }) + '<div class="grid-3 mb-24">' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Total Revenue</div><div style="font-size:1.5rem;font-weight:700;color:var(--success-color);">' + formatCurrency(data.total_revenue) + '</div></div>' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Total Expenses</div><div style="font-size:1.5rem;font-weight:700;color:var(--danger-color);">' + formatCurrency(data.total_expenses) + '</div></div>' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Net Profit</div><div style="font-size:1.5rem;font-weight:700;color:' + (data.net_profit >= 0 ? 'var(--success-color)' : 'var(--danger-color)') + ';">' + formatCurrency(data.net_profit) + '</div></div>' +
                '</div>';
        }
        if (chart && data.months && data.months.length > 0) {
            var maxVal = Math.max.apply(null, data.revenue.concat(data.expenses).concat([1]));
            var html = '<div class="chart-bars" style="height:180px;">';
            data.months.forEach(function(m, i) {
                var hRev = (data.revenue[i] / maxVal) * 100;
                var hExp = (data.expenses[i] / maxVal) * 100;
                html += '<div class="chart-month"><div class="bar-group"><div class="bar in" style="height:' + hRev + '%;" title="Revenue: ' + formatCurrency(data.revenue[i]) + '"></div><div class="bar out" style="height:' + hExp + '%;" title="Expenses: ' + formatCurrency(data.expenses[i]) + '"></div></div><span class="month-label">' + m + '</span></div>';
            });
            html += '</div><div class="chart-legend"><div class="legend-item"><div class="legend-color in"></div><span>Revenue</span></div><div class="legend-item"><div class="legend-color out"></div><span>Expenses</span></div></div>';
            chart.innerHTML = html;
        } else if (chart) { chart.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">No data yet</div>'; }
    } catch(e) { if (body) body.innerHTML = '<div style="padding:16px;color:var(--danger-color);">Failed to load P&L report</div>'; }
}
window.loadProfitLoss = loadProfitLoss;

async function loadBalanceSheet() {
    showReportsTab('bs');
    var body = document.getElementById('bs-report-body');
    if (body) body.innerHTML = '<div style="padding:16px;color:var(--text-secondary);">Loading...</div>';
    try {
        var res = await fetch('/api/reports/balance-sheet', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed');
        var data = await res.json();
        if (body) {
            body.innerHTML = otherCurrencyNote(data, function (b) { return b.total_assets; }) +
                '<div class="grid-3 gap-24">' +
                '<div>' +
                    '<h3 style="font-size:0.85rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;margin-bottom:16px;">Assets</h3>' +
                    '<div style="display:flex;flex-direction:column;gap:12px;">' +
                        '<div style="display:flex;justify-content:space-between;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;"><span style="color:var(--text-secondary);">Cash Collected</span><span style="font-weight:600;">' + formatCurrency(data.assets.cash_collected) + '</span></div>' +
                        '<div style="display:flex;justify-content:space-between;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;"><span style="color:var(--text-secondary);">Accounts Receivable</span><span style="font-weight:600;">' + formatCurrency(data.assets.accounts_receivable) + '</span></div>' +
                    '</div>' +
                    '<div style="display:flex;justify-content:space-between;padding:16px;margin-top:12px;border-top:2px solid var(--border-color);font-weight:700;"><span>Total Assets</span><span style="color:var(--primary-color);">' + formatCurrency(data.total_assets) + '</span></div>' +
                '</div>' +
                '<div>' +
                    '<h3 style="font-size:0.85rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;margin-bottom:16px;">Liabilities</h3>' +
                    '<div style="display:flex;flex-direction:column;gap:12px;">' +
                        '<div style="display:flex;justify-content:space-between;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;"><span style="color:var(--text-secondary);">Accounts Payable</span><span style="font-weight:600;">' + formatCurrency(data.liabilities.accounts_payable) + '</span></div>' +
                    '</div>' +
                    '<div style="display:flex;justify-content:space-between;padding:16px;margin-top:12px;border-top:2px solid var(--border-color);font-weight:700;"><span>Total Liabilities</span><span style="color:var(--warning-color);">' + formatCurrency(data.total_liabilities) + '</span></div>' +
                '</div>' +
                '<div>' +
                    '<h3 style="font-size:0.85rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;margin-bottom:16px;">Equity</h3>' +
                    '<div style="display:flex;flex-direction:column;gap:12px;">' +
                        '<div style="display:flex;justify-content:space-between;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;"><span style="color:var(--text-secondary);">Retained Earnings</span><span style="font-weight:600;">' + formatCurrency(data.equity.retained_earnings) + '</span></div>' +
                    '</div>' +
                    '<div style="display:flex;justify-content:space-between;padding:16px;margin-top:12px;border-top:2px solid var(--border-color);font-weight:700;"><span>Total Equity</span><span style="color:var(--success-color);">' + formatCurrency(data.total_equity) + '</span></div>' +
                '</div>' +
                '</div>';
        }
    } catch(e) { if (body) body.innerHTML = '<div style="padding:16px;color:var(--danger-color);">Failed to load balance sheet</div>'; }
}
window.loadBalanceSheet = loadBalanceSheet;

async function loadCashSummary() {
    showReportsTab('cash');
    var body = document.getElementById('cash-report-body');
    var chart = document.getElementById('cash-chart');
    if (body) body.innerHTML = '<div style="padding:16px;color:var(--text-secondary);">Loading...</div>';
    try {
        var res = await fetch('/api/reports/cash-summary', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed');
        var data = await res.json();
        var totalIn = 0, totalOut = 0;
        data.money_in.forEach(function(v) { totalIn += v; });
        data.money_out.forEach(function(v) { totalOut += v; });
        if (body) {
            body.innerHTML = otherCurrencyNote(data, function (b) { return (b.money_in || []).reduce(function (t, v) { return t + v; }, 0); }) + '<div class="grid-3 mb-24">' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Money In</div><div style="font-size:1.5rem;font-weight:700;color:var(--success-color);">' + formatCurrency(totalIn) + '</div></div>' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Money Out</div><div style="font-size:1.5rem;font-weight:700;color:var(--danger-color);">' + formatCurrency(totalOut) + '</div></div>' +
                '<div style="text-align:center;padding:20px;"><div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px;">Net Cash</div><div style="font-size:1.5rem;font-weight:700;color:' + ((totalIn - totalOut) >= 0 ? 'var(--success-color)' : 'var(--danger-color)') + ';">' + formatCurrency(totalIn - totalOut) + '</div></div>' +
                '</div>';
        }
        if (chart && data.months && data.months.length > 0) {
            var maxVal = Math.max.apply(null, data.money_in.concat(data.money_out).concat([1]));
            var html = '<div class="chart-bars" style="height:180px;">';
            data.months.forEach(function(m, i) {
                var hIn = (data.money_in[i] / maxVal) * 100;
                var hOut = (data.money_out[i] / maxVal) * 100;
                html += '<div class="chart-month"><div class="bar-group"><div class="bar in" style="height:' + hIn + '%;" title="In: ' + formatCurrency(data.money_in[i]) + '"></div><div class="bar out" style="height:' + hOut + '%;" title="Out: ' + formatCurrency(data.money_out[i]) + '"></div></div><span class="month-label">' + m + '</span></div>';
            });
            html += '</div><div class="chart-legend"><div class="legend-item"><div class="legend-color in"></div><span>Money In</span></div><div class="legend-item"><div class="legend-color out"></div><span>Money Out</span></div></div>';
            chart.innerHTML = html;
        } else if (chart) { chart.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary);">No data yet</div>'; }
    } catch(e) { if (body) body.innerHTML = '<div style="padding:16px;color:var(--danger-color);">Failed to load cash summary</div>'; }
}
window.loadCashSummary = loadCashSummary;


// --- FUTURISTIC CHARTS ---
let _invoiceChart = null;
function renderInvoiceChart(revenue, outstanding, invoices) {
    var ctx = document.getElementById('invoiceChart');
    if (!ctx) return;
    if (typeof Chart === 'undefined') return;
    
    if (_invoiceChart) _invoiceChart.destroy();
    
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Space Grotesk', sans-serif";
    
    _invoiceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Current'],
            datasets: [{
                label: 'Revenue Trajectory',
                data: [revenue*0.2, revenue*0.4, revenue*0.5, revenue*0.8, revenue],
                borderColor: '#00f0ff',
                backgroundColor: 'rgba(0, 240, 255, 0.1)',
                borderWidth: 2,
                pointBackgroundColor: '#0b0f19',
                pointBorderColor: '#00f0ff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.4
            },
            {
                label: 'Outstanding',
                data: [outstanding*0.9, outstanding*0.7, outstanding*0.8, outstanding*1.1, outstanding],
                borderColor: '#ff003c',
                backgroundColor: 'rgba(255, 0, 60, 0.1)',
                borderWidth: 2,
                pointBackgroundColor: '#0b0f19',
                pointBorderColor: '#ff003c',
                borderDash: [5, 5],
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#f8fafc', font: { family: "'Rajdhani', sans-serif", size: 14 } } },
                tooltip: { backgroundColor: 'rgba(15,23,42,0.9)', titleFont: { family: "'Rajdhani'" }, bodyFont: { family: "'Space Grotesk'" }, borderColor: '#00f0ff', borderWidth: 1 }
            },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, border: { dash: [4, 4] } },
                x: { grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

window.addBankDetailSlot = function(data) {
    data = data || {bank_name:'', account_name:'', account_number:'', sort_code:''};
    var container = document.getElementById('settings-bank-details-container');
    if (!container || container.children.length >= 5) return;
    var slot = document.createElement('div');
    slot.className = 'bank-detail-slot grid-2 gap-16';
    slot.style.padding = '16px';
    slot.style.background = 'rgba(255,255,255,0.02)';
    slot.style.border = '1px solid var(--border-color)';
    slot.style.borderRadius = 'var(--radius-md)';
    slot.innerHTML = `
        <div class="form-group"><label>Bank Name</label><input type="text" class="form-control bank-name" value="${data.bank_name}" placeholder="e.g. Chase"></div>
        <div class="form-group"><label>Account Name</label><input type="text" class="form-control account-name" value="${data.account_name}" placeholder="e.g. Company Ltd"></div>
        <div class="form-group"><label>Account Number</label><input type="text" class="form-control account-number" value="${data.account_number}"></div>
        <div class="form-group"><label>Sort Code / Routing</label><input type="text" class="form-control sort-code" value="${data.sort_code}"></div>
        <div style="grid-column:span 2;text-align:right;"><button class="btn btn-outline btn-sm" onclick="this.parentElement.parentElement.remove()">Remove</button></div>
    `;
    container.appendChild(slot);
};


// --- Legal Settings Logic ---
function handleSettingsSignatureUpload(event) {
    var file = event.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { alert('Signature image must be under 2MB.'); return; }
    var reader = new FileReader();
    reader.onload = function(e) {
        var b64 = e.target.result;
        var img = document.getElementById('settings-signature-img');
        var text = document.getElementById('settings-signature-text');
        if (img && text) {
            img.src = b64;
            img.style.display = 'block';
            text.style.display = 'none';
        }
        localStorage.setItem('company_signature', b64);
    };
    reader.readAsDataURL(file);
}

function saveLegalSettings() {
    var terms = document.getElementById('settings-terms') ? document.getElementById('settings-terms').value : '';
    
    // Save locally
    localStorage.setItem('company_terms', terms);
    
    // Save to backend
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([
            { key: 'company_terms', value: terms }
        ])
    }).then(res => res.json()).then(data => {
        showToast('Legal settings saved successfully', 'success');
    }).catch(err => {
        console.error(err);
        showToast('Failed to save legal settings', 'error');
    });
}

// ==========================================================================
// APPLICANT TRACKING — jobs, interviews, offers, candidate email, analytics
// ==========================================================================

var _recJobs = [];
var _recTab = 'jobs';
var _recBoardClientId = null;

function switchRecTab(tab, btn) {
    _recTab = tab;
    document.querySelectorAll('#rec-tabs .tab').forEach(function (t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var panels = {
        jobs: 'rec-jobs-panel', forms: 'rec-forms-list',
        pool: 'rec-pool-panel', interviews: 'rec-interviews-panel'
    };
    Object.keys(panels).forEach(function (k) {
        var el = document.getElementById(panels[k]);
        if (el) el.style.display = (k === tab) ? 'block' : 'none';
    });
    // The candidate drill-downs belong to the Forms tab only.
    ['rec-submissions-list', 'rec-sub-detail'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    if (tab === 'jobs') loadJobs();
    if (tab === 'forms') loadRecruitmentForms();
    if (tab === 'pool') loadTalentPool();
    if (tab === 'interviews') loadUpcomingInterviews();
}
window.switchRecTab = switchRecTab;

// --- Analytics -------------------------------------------------------------
async function loadRecAnalytics() {
    var host = document.getElementById('rec-analytics-cards');
    if (!host) return;
    try {
        var res = await fetch('/api/recruitment/analytics');
        if (!res.ok) return;
        var a = await res.json();
        var cards = [
            ['Open Roles', a.open_jobs, 'var(--primary-color)'],
            ['Candidates', a.total_applicants, ''],
            ['In Pipeline', a.in_progress, 'var(--warning-color)'],
            ['Hired', a.hired, 'var(--success-color)']
        ];
        host.innerHTML = cards.map(function (c) {
            return '<div class="stat-card is-centered" style="cursor:default;">' +
                   '<span class="stat-value lg"' + (c[2] ? ' style="color:' + c[2] + ';"' : '') + '>' + c[1] + '</span>' +
                   '<span class="stat-label">' + c[0] + '</span></div>';
        }).join('');
        // Second line of detail that only matters once there is data.
        if (a.total_applicants) {
            host.insertAdjacentHTML('beforeend',
                '<div style="grid-column:1/-1;display:flex;gap:20px;flex-wrap:wrap;font-size:0.82rem;' +
                'color:var(--text-secondary);padding:4px 2px;">' +
                '<span>Conversion <strong style="color:var(--text-primary);">' + a.conversion_rate + '%</strong></span>' +
                '<span>Offer acceptance <strong style="color:var(--text-primary);">' + a.offer_acceptance_rate + '%</strong></span>' +
                '<span>Avg days to hire <strong style="color:var(--text-primary);">' + a.avg_days_to_hire + '</strong></span>' +
                '<span>Interviews booked <strong style="color:var(--text-primary);">' + a.interviews_scheduled + '</strong></span>' +
                '</div>');
        }
    } catch (e) { /* the snapshot is optional; never block the page */ }
}
window.loadRecAnalytics = loadRecAnalytics;

// --- Jobs ------------------------------------------------------------------
async function loadJobs() {
    var tbody = document.getElementById('rec-jobs-tbody');
    if (!tbody) return;
    try {
        var res = await fetch('/api/recruitment/jobs');
        _recJobs = res.ok ? await res.json() : [];
    } catch (e) { _recJobs = []; }

    // The public board is keyed by tenant id, which the session endpoint knows.
    var link = document.getElementById('rec-board-link');
    if (link) {
        if (_recBoardClientId) {
            link.href = '/jobs.html?c=' + _recBoardClientId;
        } else {
            try {
                var me = await (await fetch('/api/client/me')).json();
                if (me && me.id) {
                    _recBoardClientId = me.id;
                    link.href = '/jobs.html?c=' + me.id;
                }
            } catch (e) { /* link stays inert rather than pointing somewhere wrong */ }
        }
    }

    if (!_recJobs.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                          'No jobs yet. Create one to start tracking a role.</td></tr>';
        return;
    }
    tbody.innerHTML = _recJobs.map(function (j) {
        var pill = '<span class="status-pill status-' + esc(j.status) + '" style="text-transform:capitalize;">' +
                   esc(String(j.status).replace('_', ' ')) + '</span>';
        return '<tr>' +
            '<td>' + esc(j.reference) + '</td>' +
            '<td><strong>' + esc(j.title) + '</strong>' + levelBadge(j.level) +
                '<br><span style="font-size:0.75rem;color:var(--text-secondary);">' +
                esc(String(j.work_mode).replace('_', ' ')) + ' &middot; ' + esc(String(j.employment_type).replace('_', ' ')) + '</span></td>' +
            '<td>' + esc(j.department_name || '-') + '</td>' +
            '<td>' + esc(j.location || '-') + '</td>' +
            '<td>' + esc(j.hiring_manager_name || '-') + '</td>' +
            '<td class="text-right">' + (j.applicant_count || 0) +
                '<span style="color:var(--text-secondary);font-size:0.75rem;"> / ' + (j.openings || 1) + ' open</span></td>' +
            '<td>' + pill + '</td>' +
            '<td class="text-right">' +
                '<button class="btn btn-outline btn-sm" onclick="openJobModal(' + j.id + ')">Edit</button> ' +
                '<button class="btn btn-outline btn-sm" onclick="deleteJob(' + j.id + ')" style="color:var(--danger-color);border-color:var(--danger-color);">Delete</button>' +
            '</td></tr>';
    }).join('');
}
window.loadJobs = loadJobs;

async function openJobModal(jobId) {
    var modal = document.getElementById('job-modal');
    if (!modal) return;
    document.getElementById('job-modal-title').textContent = jobId ? 'Edit Job' : 'New Job';
    document.getElementById('job-id').value = jobId || '';

    // Populate the pickers before filling values, or the selects have no options.
    try {
        var depts = await (await fetch('/api/departments')).json();
        var deptSel = document.getElementById('job-department');
        deptSel.innerHTML = '<option value="">None</option>';
        depts.forEach(function (d) { deptSel.insertAdjacentHTML('beforeend', '<option value="' + d.id + '">' + esc(d.name) + '</option>'); });
        var emps = await (await fetch('/api/employees')).json();
        var mgrSel = document.getElementById('job-manager');
        mgrSel.innerHTML = '<option value="">None</option>';
        emps.forEach(function (e) { mgrSel.insertAdjacentHTML('beforeend', '<option value="' + e.id + '">' + esc(e.first_name + ' ' + e.last_name) + '</option>'); });
    } catch (e) { /* pickers stay empty rather than blocking the modal */ }
    await populateLevelRoleSelects('job-level', null);

    var job = jobId ? _recJobs.filter(function (j) { return j.id === jobId; })[0] : null;
    function set(id, val) { var el = document.getElementById(id); if (el) el.value = val; }
    set('job-title', job ? job.title : '');
    set('job-location', job ? job.location : '');
    set('job-department', job && job.department_id ? job.department_id : '');
    set('job-manager', job && job.hiring_manager_id ? job.hiring_manager_id : '');
    set('job-mode', job ? job.work_mode : 'onsite');
    set('job-type', job ? job.employment_type : 'full_time');
    set('job-level', job ? job.level : '');
    set('job-openings', job ? job.openings : 1);
    set('job-salary-min', job ? job.salary_min : 0);
    set('job-salary-max', job ? job.salary_max : 0);
    set('job-closing', job ? job.closing_date : '');
    set('job-status', job ? job.status : 'draft');
    set('job-description', job ? job.description : '');
    set('job-requirements', job ? job.requirements : '');
    document.getElementById('job-show-salary').checked = job ? !!job.show_salary : true;
    modal.style.display = 'flex';
}
window.openJobModal = openJobModal;

function closeJobModal() {
    var m = document.getElementById('job-modal');
    if (m) m.style.display = 'none';
}
window.closeJobModal = closeJobModal;

async function saveJob() {
    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    var jobId = val('job-id');
    var payload = {
        title: val('job-title').trim(),
        location: val('job-location'),
        department_id: val('job-department') ? parseInt(val('job-department')) : null,
        hiring_manager_id: val('job-manager') ? parseInt(val('job-manager')) : null,
        work_mode: val('job-mode'),
        employment_type: val('job-type'),
        level: val('job-level'),
        openings: parseInt(val('job-openings')) || 1,
        salary_min: parseFloat(val('job-salary-min')) || 0,
        salary_max: parseFloat(val('job-salary-max')) || 0,
        closing_date: val('job-closing'),
        status: val('job-status'),
        description: val('job-description'),
        requirements: val('job-requirements'),
        show_salary: document.getElementById('job-show-salary').checked
    };
    if (!payload.title) { showToast('A job title is required', 'error'); return; }
    try {
        var res = await fetch('/api/recruitment/jobs' + (jobId ? '/' + jobId : ''), {
            method: jobId ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast(jobId ? 'Job updated' : 'Job created: ' + data.reference, 'success');
        closeJobModal();
        loadJobs();
        loadRecAnalytics();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.saveJob = saveJob;

async function deleteJob(jobId) {
    if (!confirm('Delete this job?')) return;
    try {
        var res = await fetch('/api/recruitment/jobs/' + jobId, { method: 'DELETE' });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Job deleted', 'success');
        loadJobs();
        loadRecAnalytics();
    } catch (e) { showToast(e.message, 'error'); }
}
window.deleteJob = deleteJob;

// --- Talent pool -----------------------------------------------------------
async function loadTalentPool() {
    var tbody = document.getElementById('rec-pool-tbody');
    if (!tbody) return;
    var q = (document.getElementById('rec-pool-search') || {}).value || '';
    try {
        var res = await fetch('/api/recruitment/talent-pool?q=' + encodeURIComponent(q));
        var rows = res.ok ? await res.json() : [];
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-secondary);">No candidates found.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (c) {
            var stars = c.rating ? '★'.repeat(c.rating) : '-';
            var statusColor = c.hired_employee_id ? 'var(--success-color)'
                            : (c.status === 'rejected' ? 'var(--danger-color)' : 'var(--text-secondary)');
            return '<tr>' +
                '<td><strong>' + esc(c.candidate_name || 'Unnamed') + '</strong><br>' +
                    '<span style="font-size:0.75rem;color:var(--text-secondary);">' + esc(c.candidate_email || '') + '</span></td>' +
                '<td>' + esc(c.form_title || '-') + '</td>' +
                '<td>' + esc(c.current_stage || '-') + '</td>' +
                '<td><span style="color:' + statusColor + ';text-transform:capitalize;">' + esc(c.status) + '</span></td>' +
                '<td class="text-right" style="color:var(--warning-color);">' + stars + '</td>' +
                '<td class="text-right">' + (c.applications > 1
                    ? '<span title="Has applied more than once" style="color:var(--primary-color);font-weight:700;">' + c.applications + '</span>'
                    : c.applications) + '</td>' +
                '</tr>';
        }).join('');
    } catch (e) { tbody.innerHTML = '<tr><td colspan="6" class="loading">Failed to load</td></tr>'; }
}
window.loadTalentPool = loadTalentPool;

// --- Upcoming interviews ---------------------------------------------------
async function loadUpcomingInterviews() {
    var host = document.getElementById('rec-upcoming-list');
    if (!host) return;
    try {
        var res = await fetch('/api/recruitment/interviews/upcoming?days=30');
        var rows = res.ok ? await res.json() : [];
        host.innerHTML = rows.length ? rows.map(function (i) {
            return '<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-color);">' +
                '<div style="min-width:130px;font-weight:700;">' + esc(i.scheduled_at) + '</div>' +
                '<div style="flex:1;min-width:160px;">' + esc(i.candidate_name || 'Candidate') +
                    '<span style="color:var(--text-secondary);"> &middot; ' + esc(i.round_name) + '</span></div>' +
                '<div style="color:var(--text-secondary);font-size:0.82rem;">' + esc(i.mode) +
                    (i.interviewer_name ? ' with ' + esc(i.interviewer_name) : '') + '</div>' +
                (i.meeting_link ? '<a class="link" href="' + esc(i.meeting_link) + '" target="_blank" rel="noopener">Join</a>' : '') +
                '</div>';
        }).join('') : '<p style="color:var(--text-secondary);font-size:0.88rem;">Nothing scheduled in the next 30 days.</p>';
    } catch (e) { host.innerHTML = ''; }
}
window.loadUpcomingInterviews = loadUpcomingInterviews;

// --- Interviews on a candidate --------------------------------------------
async function renderCandidateInterviews(subId) {
    var host = document.getElementById('rec-interview-list');
    if (!host) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + subId + '/interviews');
        var rows = res.ok ? await res.json() : [];
        host.innerHTML = rows.length ? rows.map(function (i) {
            var outcomeColor = i.outcome === 'pass' ? 'var(--success-color)'
                             : i.outcome === 'fail' ? 'var(--danger-color)' : 'var(--warning-color)';
            return '<div style="padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;">' +
                '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">' +
                    '<strong>' + esc(i.round_name) + '</strong>' +
                    '<span style="color:var(--text-secondary);font-size:0.82rem;">' + esc(i.scheduled_at) + ' &middot; ' + esc(i.mode) + '</span>' +
                    '<span style="margin-left:auto;font-size:0.75rem;text-transform:capitalize;color:var(--text-secondary);">' + esc(i.status) + '</span>' +
                '</div>' +
                (i.interviewer_name ? '<div style="font-size:0.78rem;color:var(--text-secondary);">with ' + esc(i.interviewer_name) + '</div>' : '') +
                (i.outcome ? '<div style="font-size:0.8rem;color:' + outcomeColor + ';text-transform:capitalize;">' +
                    esc(i.outcome) + (i.score ? ' · ' + i.score + '/5' : '') + '</div>' : '') +
                (i.feedback ? '<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:4px;">' + esc(i.feedback) + '</div>' : '') +
                '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">' +
                    '<button class="btn btn-outline btn-sm" onclick="recordInterviewOutcome(' + i.id + ')">Record Outcome</button>' +
                    '<button class="btn btn-outline btn-sm" onclick="deleteInterview(' + i.id + ')" style="color:var(--danger-color);border-color:var(--danger-color);">Remove</button>' +
                '</div></div>';
        }).join('') : '<p style="color:var(--text-secondary);font-size:0.85rem;">No interviews scheduled.</p>';
    } catch (e) { host.innerHTML = ''; }
}
window.renderCandidateInterviews = renderCandidateInterviews;

async function openInterviewModal() {
    if (!recCurrentSubId) return;
    var modal = document.getElementById('interview-modal');
    if (!modal) return;
    try {
        var emps = await (await fetch('/api/employees')).json();
        var sel = document.getElementById('iv-interviewer');
        sel.innerHTML = '<option value="">Unassigned</option>';
        emps.forEach(function (e) { sel.insertAdjacentHTML('beforeend', '<option value="' + e.id + '">' + esc(e.first_name + ' ' + e.last_name) + '</option>'); });
    } catch (e) { /* unassigned is a valid choice */ }
    modal.style.display = 'flex';
}
window.openInterviewModal = openInterviewModal;

function closeInterviewModal() {
    var m = document.getElementById('interview-modal');
    if (m) m.style.display = 'none';
}
window.closeInterviewModal = closeInterviewModal;

async function saveInterview() {
    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    if (!val('iv-when')) { showToast('Pick a date and time', 'error'); return; }
    var payload = {
        round_name: val('iv-round') || 'Interview',
        scheduled_at: val('iv-when'),          // datetime-local; the API accepts the T form
        duration_minutes: parseInt(val('iv-duration')) || 45,
        mode: val('iv-mode'),
        meeting_link: val('iv-link'),
        location: val('iv-location'),
        interviewer_id: val('iv-interviewer') ? parseInt(val('iv-interviewer')) : null
    };
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/interviews', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Interview scheduled', 'success');
        closeInterviewModal();
        renderCandidateInterviews(recCurrentSubId);
        renderCandidateHistory(recCurrentSubId);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.saveInterview = saveInterview;

async function recordInterviewOutcome(ivId) {
    var outcome = prompt('Outcome — pass, fail or hold:', 'pass');
    if (outcome === null) return;
    var score = prompt('Score out of 5:', '3');
    if (score === null) return;
    var feedback = prompt('Feedback (optional):', '') || '';
    try {
        var res = await fetch('/api/recruitment/interviews/' + ivId, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ outcome: outcome.trim().toLowerCase(), score: parseInt(score) || 0, feedback: feedback })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Outcome recorded', 'success');
        renderCandidateInterviews(recCurrentSubId);
        renderCandidateHistory(recCurrentSubId);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.recordInterviewOutcome = recordInterviewOutcome;

async function deleteInterview(ivId) {
    if (!confirm('Remove this interview?')) return;
    try {
        await fetch('/api/recruitment/interviews/' + ivId, { method: 'DELETE' });
        renderCandidateInterviews(recCurrentSubId);
    } catch (e) { showToast('Failed', 'error'); }
}
window.deleteInterview = deleteInterview;

// --- Offers ----------------------------------------------------------------
async function renderCandidateOffers(subId) {
    var host = document.getElementById('rec-offer-list');
    if (!host) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + subId + '/offers');
        var rows = res.ok ? await res.json() : [];
        var sym = getCurrencySymbol();
        host.innerHTML = rows.length ? rows.map(function (o) {
            var color = o.status === 'accepted' ? 'var(--success-color)'
                      : o.status === 'declined' ? 'var(--danger-color)' : 'var(--warning-color)';
            var actions = '';
            if (o.status === 'draft') actions = '<button class="btn btn-outline btn-sm" onclick="setOfferStatus(' + o.id + ',\'sent\')">Mark Sent</button>';
            else if (o.status === 'sent') actions =
                '<button class="btn btn-outline btn-sm" onclick="setOfferStatus(' + o.id + ',\'accepted\')" style="color:var(--success-color);border-color:var(--success-color);">Accepted</button> ' +
                '<button class="btn btn-outline btn-sm" onclick="setOfferStatus(' + o.id + ',\'declined\')" style="color:var(--danger-color);border-color:var(--danger-color);">Declined</button>';
            if (o.status !== 'withdrawn' && o.status !== 'accepted') {
                actions += ' <button class="btn btn-outline btn-sm" onclick="setOfferStatus(' + o.id + ',\'withdrawn\')">Withdraw</button>';
            }
            return '<div style="padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;">' +
                '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">' +
                    '<strong>' + esc(o.job_title || 'Offer') + '</strong>' + levelBadge(o.level) +
                    '<span style="margin-left:auto;text-transform:capitalize;color:' + color + ';font-weight:600;">' + esc(o.status) + '</span>' +
                '</div>' +
                '<div style="font-size:0.85rem;margin-top:4px;">' + sym +
                    Number(o.salary || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) +
                    (o.start_date ? ' &middot; starts ' + esc(o.start_date) : '') +
                    (o.expires_on ? ' &middot; expires ' + esc(o.expires_on) : '') + '</div>' +
                (o.notes ? '<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:4px;">' + esc(o.notes) + '</div>' : '') +
                (actions ? '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">' + actions + '</div>' : '') +
                '</div>';
        }).join('') : '<p style="color:var(--text-secondary);font-size:0.85rem;">No offer yet.</p>';
    } catch (e) { host.innerHTML = ''; }
}
window.renderCandidateOffers = renderCandidateOffers;

async function openOfferModal() {
    if (!recCurrentSubId) return;
    var modal = document.getElementById('offer-modal');
    if (!modal) return;
    await populateLevelRoleSelects('of-level', null);
    modal.style.display = 'flex';
}
window.openOfferModal = openOfferModal;

function closeOfferModal() {
    var m = document.getElementById('offer-modal');
    if (m) m.style.display = 'none';
}
window.closeOfferModal = closeOfferModal;

async function saveOffer() {
    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    var payload = {
        job_title: val('of-title'),
        level: val('of-level'),
        salary: parseFloat(val('of-salary')) || 0,
        start_date: val('of-start'),
        expires_on: val('of-expires'),
        notes: val('of-notes')
    };
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/offers', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Offer created', 'success');
        closeOfferModal();
        renderCandidateOffers(recCurrentSubId);
        renderCandidateHistory(recCurrentSubId);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.saveOffer = saveOffer;

async function setOfferStatus(offerId, status) {
    var body = { status: status };
    if (status === 'declined') {
        var reason = prompt('Reason for declining (optional):', '');
        if (reason === null) return;
        body.decline_reason = reason;
    }
    try {
        var res = await fetch('/api/recruitment/offers/' + offerId, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Offer ' + status, 'success');
        renderCandidateOffers(recCurrentSubId);
        renderCandidateHistory(recCurrentSubId);
        loadRecAnalytics();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.setOfferStatus = setOfferStatus;

// --- Candidate email -------------------------------------------------------
async function openCandidateEmail(template) {
    if (!recCurrentSubId) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId +
                              '/email-preview?template=' + encodeURIComponent(template));
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        document.getElementById('ce-to').value = data.to;
        document.getElementById('ce-subject').value = data.subject;
        document.getElementById('ce-body').value = data.body;
        document.getElementById('cand-email-modal').style.display = 'flex';
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.openCandidateEmail = openCandidateEmail;

function closeCandidateEmail() {
    var m = document.getElementById('cand-email-modal');
    if (m) m.style.display = 'none';
}
window.closeCandidateEmail = closeCandidateEmail;

async function sendCandidateEmail() {
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/email', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subject: document.getElementById('ce-subject').value,
                body: document.getElementById('ce-body').value
            })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast(data.message, 'success');
        closeCandidateEmail();
        renderCandidateHistory(recCurrentSubId);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.sendCandidateEmail = sendCandidateEmail;

// --- Reject / reopen -------------------------------------------------------
async function rejectCandidate() {
    if (!recCurrentSubId) return;
    var reason = prompt('Why are you rejecting this candidate?\n(Recorded against the application.)', '');
    if (reason === null) return;
    if (!reason.trim()) { showToast('A reason is required', 'error'); return; }
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/reject', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Candidate rejected', 'success');
        showRecSubmissionDetail(recCurrentSubId);
        loadRecAnalytics();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.rejectCandidate = rejectCandidate;

async function reopenCandidate() {
    if (!recCurrentSubId) return;
    try {
        var res = await fetch('/api/recruitment/submissions/' + recCurrentSubId + '/reopen', { method: 'POST' });
        if (!res.ok) throw new Error('Failed');
        showToast('Application reopened', 'success');
        showRecSubmissionDetail(recCurrentSubId);
    } catch (e) { showToast('Failed', 'error'); }
}
window.reopenCandidate = reopenCandidate;

// ==========================================================================
// HR DATA BUS
// Every HR module reads the same underlying records, so a change in one place
// leaves the others showing stale numbers. Instead of each handler remembering
// which sibling views to refresh, mutations announce what changed and the bus
// refreshes whatever is currently on screen plus the always-visible counters.
// ==========================================================================

// Which loaders each kind of change invalidates.
var HR_REFRESH_MAP = {
    employees:   ['employees-view', 'departments-view', 'orgchart-view', 'onboarding-hub-view', 'payroll-view'],
    departments: ['departments-view', 'employees-view', 'orgchart-view'],
    leave:       ['leave-view', 'employees-view'],
    attendance:  ['attendance-view', 'employees-view'],
    payroll:     ['payroll-view', 'employees-view'],
    goals:       ['goals-view', 'employees-view'],
    onboarding:  ['onboarding-hub-view', 'employees-view'],
    recruitment: ['recruitment-view', 'employees-view', 'onboarding-hub-view', 'orgchart-view']
};

var HR_VIEW_LOADERS = {
    'employees-view':      function () { fetchEmployees(currentEmpFilter); },
    'departments-view':    function () { fetchDepartments(); },
    'orgchart-view':       function () { loadOrgChart(); },
    'onboarding-hub-view': function () { loadOnboardingHub(); loadDocumentQueue(); loadExpiringDocuments(); loadOnboardingPipeline(); },
    'payroll-view':        function () { fetchPayslips(currentPsFilter); },
    'leave-view':          function () { loadLeaveView(); },
    'goals-view':          function () { loadGoalsView(); },
    'attendance-view':     function () { loadAttendanceStats(); loadAttendance(); },
    'recruitment-view':    function () { loadRecAnalytics(); }
};

function currentViewId() {
    var active = document.querySelector('.view-section.active');
    return active ? active.id : '';
}

/**
 * Announce that HR data changed.
 * @param {string} scope  key of HR_REFRESH_MAP
 * @param {object} [opts] {employeeId} to also refresh an open profile
 */
function hrDataChanged(scope, opts) {
    opts = opts || {};
    // Headline counters sit above every HR view, so they always refresh.
    if (typeof loadHRStats === 'function') loadHRStats();

    var affected = HR_REFRESH_MAP[scope] || [];
    var visible = currentViewId();
    affected.forEach(function (viewId) {
        // Only reload what the user can actually see; the rest reloads on
        // navigation via the showView hooks.
        if (viewId !== visible) return;
        var loader = HR_VIEW_LOADERS[viewId];
        if (typeof loader === 'function') {
            try { loader(); } catch (e) { console.error('refresh failed for ' + viewId, e); }
        }
    });

    // An open employee profile is a view onto all of this too.
    var profileOpen = visible === 'employee-detail-view';
    var targetId = opts.employeeId || currentEmployeeId;
    if (profileOpen && targetId && typeof viewEmployee === 'function') {
        viewEmployee(targetId);
    }
}
window.hrDataChanged = hrDataChanged;

// --- Cross-module navigation ----------------------------------------------
// A person's name should always be a way to reach their profile.

function openEmployee(empId) {
    if (!empId) return;
    showView('employee-detail-view');
    viewEmployee(empId);
}
window.openEmployee = openEmployee;

// Renders a name as a link when we know which employee it is.
function employeeLink(empId, name) {
    var label = esc(name || 'Unknown');
    if (!empId) return label;
    return '<a href="#" class="link" onclick="event.preventDefault();openEmployee(' + empId + ')">' + label + '</a>';
}
window.employeeLink = employeeLink;

// Jump to a list already filtered to one person, so "show me their leave"
// does not mean scrolling a global table.
var _hrFocusEmployee = null;

function focusEmployeeIn(viewId, empId, name) {
    _hrFocusEmployee = { id: empId, name: name || '' };
    showView(viewId);
    setTimeout(function () { applyEmployeeFocus(viewId); }, 350);
}
window.focusEmployeeIn = focusEmployeeIn;

function applyEmployeeFocus(viewId) {
    if (!_hrFocusEmployee) return;
    var name = _hrFocusEmployee.name;
    _hrFocusEmployee = null;
    if (!name) return;

    // Some views own a search box; the rest are filtered row by row, because
    // Leave, Goals and Attendance have no search field to drive.
    var searchIds = { 'payroll-view': 'payslip-search', 'employees-view': 'employee-search' };
    var input = document.getElementById(searchIds[viewId] || '');
    if (input) {
        input.value = name;
        input.dispatchEvent(new Event('keyup', { bubbles: true }));
        input.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
        filterRowsByName(viewId, name);
    }
    showFocusBanner(viewId, name);
}

// Hide rows and cards that do not mention this person. Marks what it hid so
// clearing puts everything back without a reload.
function filterRowsByName(viewId, name) {
    var view = document.getElementById(viewId);
    if (!view) return;
    var needle = name.toLowerCase();
    var rows = view.querySelectorAll('tbody tr, .leave-card, .goal-card');
    rows.forEach(function (row) {
        var match = (row.textContent || '').toLowerCase().indexOf(needle) >= 0;
        if (!match) {
            row.dataset.hrHidden = '1';
            row.style.display = 'none';
        }
    });
}

function showFocusBanner(viewId, name) {
    var view = document.getElementById(viewId);
    if (!view || !name) return;
    var existing = view.querySelector('.hr-focus-banner');
    if (existing) existing.remove();
    var banner = document.createElement('div');
    banner.className = 'hr-focus-banner';
    banner.style.cssText = 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 14px;' +
        'margin-bottom:16px;border-radius:8px;background:rgba(0,240,255,0.08);' +
        'border:1px solid rgba(0,240,255,0.3);font-size:0.85rem;';
    banner.innerHTML = 'Showing only <strong>' + esc(name) + '</strong>' +
        '<button type="button" class="btn btn-outline btn-sm" style="margin-left:auto;" ' +
        'onclick="clearEmployeeFocus(&quot;' + viewId + '&quot;)">Show everyone</button>';
    var header = view.querySelector('.invoices-header-area');
    if (header && header.nextSibling) view.insertBefore(banner, header.nextSibling);
    else view.insertBefore(banner, view.firstChild);
}

function clearEmployeeFocus(viewId) {
    var view = document.getElementById(viewId);
    if (!view) return;
    var banner = view.querySelector('.hr-focus-banner');
    if (banner) banner.remove();
    view.querySelectorAll('[data-hr-hidden]').forEach(function (row) {
        row.style.display = '';
        delete row.dataset.hrHidden;
    });
    ['payslip-search', 'employee-search'].forEach(function (id) {
        var input = document.getElementById(id);
        if (input && view.contains(input)) {
            input.value = '';
            input.dispatchEvent(new Event('keyup', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    });
}
window.clearEmployeeFocus = clearEmployeeFocus;

// --- Employee profile: leave and attendance -------------------------------
// Both come from the same /api/employees/{id} payload the rest of the profile
// uses, so the profile cannot disagree with the Leave or Attendance tabs.

function renderEmployeeLeavePanel(emp) {
    var host = document.getElementById('emp-leave-panel');
    if (!host) return;
    var bal = emp.leave_balance || {};
    var requests = emp.leave_requests || [];

    function bar(label, taken, total, color) {
        var pct = total ? Math.min(100, Math.round((taken / total) * 100)) : 0;
        return '<div style="margin-bottom:12px;">' +
            '<div style="display:flex;justify-content:space-between;font-size:0.82rem;margin-bottom:4px;">' +
                '<span style="color:var(--text-secondary);">' + label + '</span>' +
                '<strong>' + taken + ' / ' + total + ' days</strong></div>' +
            '<div style="height:6px;background:rgba(255,255,255,0.1);border-radius:3px;overflow:hidden;">' +
                '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:3px;"></div></div></div>';
    }

    var html = '';
    if (emp.on_leave_today) {
        html += '<div style="padding:8px 12px;border-radius:8px;background:rgba(252,211,77,0.12);' +
                'border:1px solid rgba(252,211,77,0.35);color:var(--warning-color);font-size:0.82rem;' +
                'font-weight:600;margin-bottom:12px;">On approved leave today</div>';
    }
    html += bar('Annual', bal.annual_taken || 0, bal.annual_total || 0, 'var(--primary-color)');
    html += bar('Sick', bal.sick_taken || 0, bal.sick_total || 0, 'var(--warning-color)');
    if (bal.annual_pending) {
        html += '<p style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:10px;">' +
                bal.annual_pending + ' day(s) awaiting approval.</p>';
    }

    if (requests.length) {
        html += '<div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;' +
                'color:var(--text-secondary);margin:14px 0 6px;">Recent requests</div>';
        html += requests.slice(0, 5).map(function (l) {
            var color = l.status === 'approved' ? 'var(--success-color)'
                      : l.status === 'rejected' ? 'var(--danger-color)' : 'var(--warning-color)';
            return '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:6px 0;' +
                   'border-bottom:1px solid var(--border-color);font-size:0.82rem;">' +
                   '<span style="text-transform:capitalize;">' + esc(l.leave_type) + '</span>' +
                   '<span style="color:var(--text-secondary);">' + esc(l.start_date) + ' to ' + esc(l.end_date) + '</span>' +
                   '<span style="margin-left:auto;color:' + color + ';text-transform:capitalize;">' + esc(l.status) + '</span>' +
                   '</div>';
        }).join('');
    } else {
        html += '<p style="color:var(--text-secondary);font-size:0.85rem;">No leave requested.</p>';
    }
    host.innerHTML = html;
}
window.renderEmployeeLeavePanel = renderEmployeeLeavePanel;

function renderEmployeeAttendancePanel(emp) {
    var host = document.getElementById('emp-attendance-panel');
    if (!host) return;
    var a = emp.attendance_summary || {};
    var tiles = [
        ['Days present', a.days_present || 0, ''],
        ['Hours', (a.hours_30d || 0) + 'h', ''],
        ['Overtime', (a.overtime_30d || 0) + 'h', 'var(--primary-color)'],
        ['Late', a.days_late || 0, (a.days_late ? 'var(--warning-color)' : '')]
    ];
    var html = '';
    if (a.clocked_in_today) {
        html += '<div style="padding:8px 12px;border-radius:8px;background:rgba(57,255,20,0.12);' +
                'border:1px solid rgba(57,255,20,0.35);color:var(--success-color);font-size:0.82rem;' +
                'font-weight:600;margin-bottom:12px;">Clocked in since ' + esc(a.today_clock_in || '') + '</div>';
    } else if (a.today_clock_in) {
        html += '<div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:12px;">' +
                'Today: ' + esc(a.today_clock_in) + ' to ' + esc(a.today_clock_out || '-') + '</div>';
    }
    html += '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;">' +
        tiles.map(function (t) {
            return '<div style="padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;">' +
                   '<div style="font-size:0.72rem;color:var(--text-secondary);">' + t[0] + '</div>' +
                   '<div style="font-size:1.1rem;font-weight:700;' + (t[2] ? 'color:' + t[2] + ';' : '') + '">' + t[1] + '</div></div>';
        }).join('') + '</div>';
    host.innerHTML = html;
}
window.renderEmployeeAttendancePanel = renderEmployeeAttendancePanel;

// Deep links: open the full tab already narrowed to this person.
function viewEmployeeLeave() {
    var name = (document.getElementById('emp-detail-name') || {}).textContent || '';
    focusEmployeeIn('leave-view', currentEmployeeId, name);
}
window.viewEmployeeLeave = viewEmployeeLeave;

function viewEmployeeAttendance() {
    var name = (document.getElementById('emp-detail-name') || {}).textContent || '';
    focusEmployeeIn('attendance-view', currentEmployeeId, name);
}
window.viewEmployeeAttendance = viewEmployeeAttendance;

function viewEmployeePayslips() {
    var name = (document.getElementById('emp-detail-name') || {}).textContent || '';
    focusEmployeeIn('payroll-view', currentEmployeeId, name);
}
window.viewEmployeePayslips = viewEmployeePayslips;

// ==========================================================================
// ONBOARDING DOCUMENTS
// HR defines what new starters must provide; employees upload it from their
// own portal; the submissions land in this queue for review.
// ==========================================================================

var _docRequirements = [];

// --- Review queue -----------------------------------------------------------

async function loadDocumentQueue() {
    var host = document.getElementById('doc-queue-list');
    if (!host) return;
    var status = (document.getElementById('doc-queue-filter') || {}).value || 'submitted';
    host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">Loading...</p>';
    try {
        var res = await fetch('/api/onboarding/document-queue?status=' + encodeURIComponent(status));
        var rows = res.ok ? await res.json() : [];
        if (!rows.length) {
            host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">' +
                (status === 'submitted' ? 'Nothing waiting for review.' : 'Nothing here.') + '</p>';
            return;
        }
        var colors = {
            pending: 'var(--text-secondary)', submitted: 'var(--primary-color)',
            approved: 'var(--success-color)', rejected: 'var(--danger-color)'
        };
        host.innerHTML = rows.map(function (r) {
            var actions = '';
            if (r.status === 'submitted' || r.status === 'approved' || r.status === 'rejected') {
                if (r.document_id) {
                    actions += '<button class="btn btn-outline btn-sm" onclick="downloadRequestFile(' + r.id + ')">Download</button> ';
                }
            }
            if (r.status === 'submitted') {
                actions += '<button class="btn btn-outline btn-sm" style="color:var(--success-color);border-color:var(--success-color);" onclick="reviewDocument(' + r.id + ',\'approve\')">Approve</button> ' +
                           '<button class="btn btn-outline btn-sm" style="color:var(--danger-color);border-color:var(--danger-color);" onclick="reviewDocument(' + r.id + ',\'reject\')">Reject</button>';
            }
            var meta = [];
            if (r.file_name) meta.push(esc(r.file_name));
            if (r.submitted_at) meta.push('sent ' + esc(r.submitted_at.slice(0, 16)));
            else if (r.due_date) meta.push((r.is_overdue ? 'overdue since ' : 'due ') + esc(r.due_date));
            if (r.review_note) meta.push('note: ' + esc(r.review_note));

            return '<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;padding:12px 0;' +
                   'border-bottom:1px solid var(--border-color);">' +
                '<div style="flex:1;min-width:190px;">' +
                    '<strong>' + employeeLink(r.employee_id, r.employee_name) + '</strong>' +
                    '<span style="color:var(--text-secondary);"> &middot; ' + esc(r.name) + '</span>' +
                    (r.is_mandatory ? '' : '<span style="font-size:0.72rem;color:var(--text-secondary);"> (optional)</span>') +
                    (meta.length ? '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:2px;">' +
                        meta.join(' &middot; ') + '</div>' : '') +
                '</div>' +
                '<span style="font-size:0.75rem;text-transform:capitalize;color:' + (colors[r.status] || '') +
                    ';font-weight:600;' + (r.is_overdue && r.status === 'pending' ? 'color:var(--danger-color);' : '') + '">' +
                    esc(r.status) + (r.is_overdue && r.status === 'pending' ? ' · overdue' : '') + '</span>' +
                (actions ? '<div style="display:flex;gap:6px;flex-wrap:wrap;">' + actions + '</div>' : '') +
            '</div>';
        }).join('');
    } catch (e) {
        host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">Could not load submissions.</p>';
    }
}
window.loadDocumentQueue = loadDocumentQueue;

async function downloadRequestFile(reqId) {
    try {
        var res = await fetch('/api/onboarding/document-requests/' + reqId + '/file');
        var doc = await res.json();
        if (!res.ok) throw new Error(doc.detail || 'Failed');
        var bytes = atob(doc.file_data);
        var arr = new Uint8Array(bytes.length);
        for (var i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        var url = URL.createObjectURL(new Blob([arr], { type: doc.file_type || 'application/octet-stream' }));
        var a = document.createElement('a');
        a.href = url; a.download = doc.file_name || 'document'; a.click();
        URL.revokeObjectURL(url);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.downloadRequestFile = downloadRequestFile;

async function reviewDocument(reqId, decision) {
    var note = '';
    if (decision === 'reject') {
        // The employee has to know what to fix, so a reason is required.
        note = prompt('Why is this being rejected?\n(The employee sees this.)', '');
        if (note === null) return;
        if (!note.trim()) { showToast('A reason is required', 'error'); return; }
    }
    try {
        var res = await fetch('/api/onboarding/document-requests/' + reqId + '/review', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision: decision, note: note })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Document ' + data.status, 'success');
        loadDocumentQueue();
        hrDataChanged('onboarding');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.reviewDocument = reviewDocument;

// --- Requirement settings ---------------------------------------------------

async function openRequirementsModal() {
    var modal = document.getElementById('requirements-modal');
    if (!modal) return;
    try {
        var depts = await (await fetch('/api/departments')).json();
        var sel = document.getElementById('req-department');
        sel.innerHTML = '<option value="">Select...</option>';
        depts.forEach(function (d) {
            sel.insertAdjacentHTML('beforeend', '<option value="' + d.id + '">' + esc(d.name) + '</option>');
        });
    } catch (e) { /* department scoping stays unavailable rather than blocking */ }
    await populateLevelRoleSelects('req-level', null);
    resetRequirementForm();
    await loadRequirements();
    modal.style.display = 'flex';
}
window.openRequirementsModal = openRequirementsModal;

function closeRequirementsModal() {
    var m = document.getElementById('requirements-modal');
    if (m) m.style.display = 'none';
}
window.closeRequirementsModal = closeRequirementsModal;

async function loadRequirements() {
    var host = document.getElementById('requirements-list');
    if (!host) return;
    try {
        var res = await fetch('/api/onboarding/requirements');
        _docRequirements = res.ok ? await res.json() : [];
    } catch (e) { _docRequirements = []; }

    if (!_docRequirements.length) {
        host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">Nothing required yet.</p>';
        return;
    }
    host.innerHTML = _docRequirements.map(function (r) {
        var scope = r.applies_to === 'department' ? (r.department_name || 'a department')
                  : r.applies_to === 'level' ? ('level ' + r.level) : 'everyone';
        return '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:10px 0;' +
               'border-bottom:1px solid var(--border-color);' + (r.is_active ? '' : 'opacity:0.5;') + '">' +
            '<div style="flex:1;min-width:170px;">' +
                '<strong>' + esc(r.name) + '</strong>' +
                (r.is_mandatory ? '<span style="color:var(--danger-color);"> *</span>'
                                : '<span style="font-size:0.72rem;color:var(--text-secondary);"> optional</span>') +
                '<div style="font-size:0.75rem;color:var(--text-secondary);">' +
                    esc(r.doc_type) + ' &middot; due ' + r.due_days + ' days after start &middot; ' + esc(scope) +
                    (r.requires_expiry ? ' &middot; expires (warn ' + r.expiry_reminder_days + 'd)' : '') +
                    (r.has_template ? ' &middot; template attached' : '') +
                    (r.is_active ? '' : ' &middot; inactive') + '</div>' +
            '</div>' +
            '<button class="btn btn-outline btn-sm" onclick="editRequirement(' + r.id + ')">Edit</button> ' +
            '<button class="btn btn-outline btn-sm" style="color:var(--danger-color);border-color:var(--danger-color);" ' +
                'onclick="deleteRequirement(' + r.id + ')">Remove</button>' +
        '</div>';
    }).join('');
}
window.loadRequirements = loadRequirements;

function onRequirementScopeChange() {
    var scope = (document.getElementById('req-applies') || {}).value;
    var dept = document.getElementById('req-dept-group');
    var lvl = document.getElementById('req-level-group');
    if (dept) dept.style.display = scope === 'department' ? 'flex' : 'none';
    if (lvl) lvl.style.display = scope === 'level' ? 'flex' : 'none';
}
window.onRequirementScopeChange = onRequirementScopeChange;

function resetRequirementForm() {
    ['req-id', 'req-name', 'req-description'].forEach(function (id) {
        var el = document.getElementById(id); if (el) el.value = '';
    });
    var days = document.getElementById('req-days'); if (days) days.value = 7;
    var type = document.getElementById('req-type'); if (type) type.value = 'identity';
    var applies = document.getElementById('req-applies'); if (applies) applies.value = 'all';
    var mand = document.getElementById('req-mandatory'); if (mand) mand.checked = true;
    var exp = document.getElementById('req-expiry'); if (exp) exp.checked = false;
    var rem = document.getElementById('req-reminder'); if (rem) rem.value = 30;
    setRequirementTemplateLabel('');
    var btn = document.getElementById('req-save-btn'); if (btn) btn.textContent = 'Add Document';
    onRequirementScopeChange();
    onRequirementExpiryChange();
}

function editRequirement(id) {
    var r = _docRequirements.filter(function (x) { return x.id === id; })[0];
    if (!r) return;
    function set(elId, v) { var el = document.getElementById(elId); if (el) el.value = v; }
    set('req-id', r.id);
    set('req-name', r.name);
    set('req-description', r.description);
    set('req-type', r.doc_type);
    set('req-days', r.due_days);
    set('req-applies', r.applies_to);
    set('req-department', r.department_id || '');
    set('req-level', r.level || '');
    document.getElementById('req-mandatory').checked = !!r.is_mandatory;
    document.getElementById('req-expiry').checked = !!r.requires_expiry;
    document.getElementById('req-reminder').value = r.expiry_reminder_days || 30;
    setRequirementTemplateLabel(r.template_file_name || '');
    document.getElementById('req-save-btn').textContent = 'Save Changes';
    onRequirementScopeChange();
    onRequirementExpiryChange();
}
window.editRequirement = editRequirement;

async function saveRequirement() {
    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    var id = val('req-id');
    var payload = {
        name: val('req-name').trim(),
        description: val('req-description'),
        doc_type: val('req-type'),
        due_days: parseInt(val('req-days')) || 0,
        applies_to: val('req-applies'),
        department_id: val('req-department') ? parseInt(val('req-department')) : null,
        level: val('req-level'),
        is_mandatory: document.getElementById('req-mandatory').checked,
        requires_expiry: document.getElementById('req-expiry').checked,
        expiry_reminder_days: parseInt(val('req-reminder')) || 30,
        is_active: true
    };
    if (!payload.name) { showToast('Give the document a name', 'error'); return; }
    try {
        var res = await fetch('/api/onboarding/requirements' + (id ? '/' + id : ''), {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast(id ? 'Document updated' : 'Document added', 'success');
        resetRequirementForm();
        loadRequirements();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.saveRequirement = saveRequirement;

async function deleteRequirement(id) {
    if (!confirm('Remove this document requirement?\nAnything already submitted is kept.')) return;
    try {
        var res = await fetch('/api/onboarding/requirements/' + id, { method: 'DELETE' });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast('Requirement removed', 'success');
        loadRequirements();
        loadDocumentQueue();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.deleteRequirement = deleteRequirement;

// --- Employee profile: their outstanding paperwork --------------------------

function renderEmployeeDocRequests(emp) {
    var host = document.getElementById('emp-doc-requests');
    if (!host) return;
    var rows = emp.document_requests || [];
    if (!rows.length) {
        host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No documents requested.</p>';
        return;
    }
    var colors = {
        pending: 'var(--text-secondary)', submitted: 'var(--primary-color)',
        approved: 'var(--success-color)', rejected: 'var(--danger-color)'
    };
    host.innerHTML = rows.map(function (r) {
        return '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:8px 0;' +
               'border-bottom:1px solid var(--border-color);font-size:0.85rem;">' +
            '<span style="flex:1;min-width:130px;">' + esc(r.name) +
                (r.is_mandatory ? '<span style="color:var(--danger-color);"> *</span>' : '') + '</span>' +
            (r.due_date ? '<span style="font-size:0.75rem;color:' +
                (r.is_overdue ? 'var(--danger-color)' : 'var(--text-secondary)') + ';">due ' + esc(r.due_date) + '</span>' : '') +
            (r.expires_on ? '<span style="font-size:0.75rem;color:' +
                (r.is_expired ? 'var(--danger-color)' : (r.expiring_soon ? 'var(--warning-color)' : 'var(--text-secondary)')) +
                ';">' + (r.is_expired ? 'expired ' : 'expires ') + esc(r.expires_on) + '</span>' : '') +
            '<span style="text-transform:capitalize;color:' + (colors[r.status] || '') + ';font-weight:600;">' +
                esc(r.status) + '</span>' +
            (r.document_id ? ' <button class="btn btn-outline btn-sm" onclick="downloadRequestFile(' + r.id + ')">Get</button>' : '') +
            (r.status === 'submitted'
                ? ' <button class="btn btn-outline btn-sm" style="color:var(--success-color);border-color:var(--success-color);" onclick="reviewDocument(' + r.id + ',\'approve\')">Approve</button>' +
                  ' <button class="btn btn-outline btn-sm" style="color:var(--danger-color);border-color:var(--danger-color);" onclick="reviewDocument(' + r.id + ',\'reject\')">Reject</button>'
                : '') +
        '</div>';
    }).join('');
}
window.renderEmployeeDocRequests = renderEmployeeDocRequests;

// Re-apply the current requirement rules to one person, for staff who predate
// a new rule or whose department or level changed.
async function syncEmployeeDocRequests() {
    if (!currentEmployeeId) return;
    try {
        var res = await fetch('/api/employees/' + currentEmployeeId + '/document-requests/sync', { method: 'POST' });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed');
        showToast(data.message, data.added ? 'success' : 'info');
        viewEmployee(currentEmployeeId);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.syncEmployeeDocRequests = syncEmployeeDocRequests;


// Any metered call can come back 402. Route those to the top-up prompt rather
// than showing a dead error the user cannot act on.
function reportApiError(res, data, fallback) {
    var detail = (data && data.detail) || fallback || 'Something went wrong';
    if (res && res.status === 402) { handleInsufficientCredit(detail); return; }
    showToast(detail, 'error');
}
window.reportApiError = reportApiError;

// ==========================================================================
// WALLET
// Prepaid credit for metered actions. Balance, spending history, what things
// cost, and top-up through whichever gateway the operator has configured.
// ==========================================================================

var _wallet = null;
var _walletProviders = null;

async function loadWallet() {
    try {
        var res = await fetch('/api/wallet');
        if (!res.ok) return;
        _wallet = await res.json();
    } catch (e) { return; }

    var sym = _wallet.symbol || '';
    var tiles = [
        ['Balance', sym + _wallet.balance.toFixed(2), _wallet.is_empty ? 'var(--danger-color)'
            : (_wallet.is_low ? 'var(--warning-color)' : 'var(--success-color)')],
        ['Spent all time', sym + _wallet.lifetime_spent.toFixed(2), ''],
        ['Topped up all time', sym + _wallet.lifetime_topped_up.toFixed(2), ''],
        ['Low balance at', sym + _wallet.low_balance.toFixed(2), '']
    ];
    var stats = document.getElementById('wallet-stats');
    if (stats) {
        stats.innerHTML = tiles.map(function (t) {
            return '<div class="stat-card" style="cursor:default;">' +
                '<span class="stat-label">' + t[0] + '</span>' +
                '<span class="stat-value"' + (t[2] ? ' style="color:' + t[2] + ';"' : '') + '>' + esc(t[1]) + '</span></div>';
        }).join('');
    }

    var banner = document.getElementById('wallet-low-banner');
    if (banner) {
        if (_wallet.is_empty || _wallet.is_low) {
            banner.style.display = 'block';
            banner.innerHTML = '<div style="padding:12px 16px;border-radius:8px;margin-bottom:24px;' +
                'background:rgba(252,211,77,0.12);border:1px solid rgba(252,211,77,0.35);' +
                'display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:0.87rem;">' +
                '<strong style="color:var(--warning-color);">' +
                (_wallet.is_empty ? 'Your wallet is empty.' : 'Your balance is running low.') + '</strong>' +
                '<span style="color:var(--text-secondary);">Sending, payroll and AI features need credit.</span>' +
                '<button class="btn btn-primary btn-sm" style="margin-left:auto;" onclick="openTopUpModal()">Top up</button></div>';
        } else {
            banner.style.display = 'none';
        }
    }

    var pricing = document.getElementById('wallet-pricing');
    if (pricing) {
        pricing.innerHTML = (_wallet.pricing || []).map(function (p) {
            var free = p.free_allowance
                ? '<span style="font-size:0.72rem;color:var(--success-color);"> ' +
                  Math.max(0, p.free_allowance - p.used_this_month) + ' free left this month</span>' : '';
            return '<div style="display:flex;gap:10px;align-items:center;padding:7px 0;' +
                   'border-bottom:1px solid var(--border-color);font-size:0.85rem;">' +
                '<span style="flex:1;">' + esc(p.label) + free + '</span>' +
                '<strong>' + esc(_wallet.symbol) + p.unit_price.toFixed(2) + '</strong></div>';
        }).join('') || '<p style="color:var(--text-secondary);font-size:0.85rem;">Nothing is metered yet.</p>';
    }

    loadWalletTransactions();
    loadTopUpHistory();
}
window.loadWallet = loadWallet;

async function loadWalletTransactions() {
    var body = document.getElementById('wallet-tx-body');
    if (!body) return;
    var dir = (document.getElementById('wallet-tx-filter') || {}).value || '';
    try {
        var res = await fetch('/api/wallet/transactions?limit=100' + (dir ? '&direction=' + dir : ''));
        var rows = res.ok ? await res.json() : [];
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;color:var(--text-secondary);">No transactions yet.</td></tr>';
            return;
        }
        var sym = (_wallet && _wallet.symbol) || '';
        body.innerHTML = rows.map(function (t) {
            var credit = t.direction === 'credit';
            return '<tr><td>' + esc((t.created_at || '').slice(0, 16)) + '</td>' +
                '<td>' + esc(t.description || t.action_key) +
                    (t.reference ? '<br><span style="font-size:0.75rem;color:var(--text-secondary);">' + esc(t.reference) + '</span>' : '') +
                    (t.quantity > 1 ? '<span style="font-size:0.75rem;color:var(--text-secondary);"> x' + t.quantity + '</span>' : '') + '</td>' +
                '<td class="text-right" style="color:' + (credit ? 'var(--success-color)' : 'var(--danger-color)') + ';">' +
                    (credit ? '+' : '-') + sym + t.amount.toFixed(2) + '</td>' +
                '<td class="text-right">' + sym + t.balance_after.toFixed(2) + '</td></tr>';
        }).join('');
    } catch (e) {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text-secondary);">Could not load transactions.</td></tr>';
    }
}
window.loadWalletTransactions = loadWalletTransactions;

async function loadTopUpHistory() {
    var host = document.getElementById('wallet-topups');
    if (!host) return;
    try {
        var res = await fetch('/api/wallet/topups?limit=10');
        var rows = res.ok ? await res.json() : [];
        if (!rows.length) {
            host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">No top-ups yet.</p>';
            return;
        }
        var colors = { paid: 'var(--success-color)', pending: 'var(--warning-color)',
                       failed: 'var(--danger-color)', cancelled: 'var(--text-secondary)' };
        host.innerHTML = rows.map(function (o) {
            return '<div style="display:flex;gap:10px;align-items:center;padding:7px 0;' +
                   'border-bottom:1px solid var(--border-color);font-size:0.85rem;">' +
                '<span style="flex:1;">' + esc((o.created_at || '').slice(0, 10)) +
                    ' <span style="color:var(--text-secondary);text-transform:capitalize;">' + esc(o.provider) + '</span></span>' +
                '<strong>' + esc(o.currency === 'GBP' ? '£' : '') + o.amount.toFixed(2) + '</strong>' +
                '<span style="color:' + (colors[o.status] || '') + ';text-transform:capitalize;font-size:0.78rem;">' + esc(o.status) + '</span>' +
                (o.checkout_url ? ' <a class="btn btn-outline btn-sm" href="' + esc(o.checkout_url) + '" target="_blank" rel="noopener">Resume</a>' : '') +
            '</div>';
        }).join('');
    } catch (e) { host.innerHTML = ''; }
}

// --- Top up -----------------------------------------------------------------

async function openTopUpModal() {
    var modal = document.getElementById('topup-modal');
    if (!modal) return;
    try {
        var res = await fetch('/api/wallet/providers');
        _walletProviders = await res.json();
    } catch (e) { return; }

    var presets = document.getElementById('topup-presets');
    if (presets) {
        presets.innerHTML = (_walletProviders.suggested || []).map(function (a) {
            return '<button type="button" class="btn btn-outline btn-sm" onclick="document.getElementById(\'topup-amount\').value=' + a + '">' +
                   esc(_walletProviders.symbol) + a + '</button>';
        }).join('');
    }

    var host = document.getElementById('topup-providers');
    if (host) {
        host.innerHTML = (_walletProviders.providers || []).map(function (p, i) {
            // A provider without keys is shown but disabled, so it is obvious
            // why it cannot be used rather than failing on click.
            return '<label style="display:flex;align-items:center;gap:10px;padding:10px 12px;' +
                   'border:1px solid var(--border-color);border-radius:8px;' +
                   (p.enabled ? 'cursor:pointer;' : 'opacity:0.5;cursor:not-allowed;') + '">' +
                '<input type="radio" name="topup-provider" value="' + esc(p.key) + '"' +
                    (p.enabled ? '' : ' disabled') + (p.enabled && i === 0 ? ' checked' : '') + '>' +
                '<span style="flex:1;">' + esc(p.label) + '</span>' +
                (p.enabled ? '' : '<span style="font-size:0.72rem;color:var(--text-secondary);">not configured</span>') +
            '</label>';
        }).join('');
    }

    var note = document.getElementById('topup-note');
    var go = document.getElementById('topup-go');
    if (!_walletProviders.any_enabled) {
        if (note) note.textContent = 'No payment provider is configured on this server yet. ' +
            'Add the gateway keys, or ask an administrator to credit your wallet manually.';
        if (go) { go.disabled = true; go.style.opacity = '0.5'; }
    } else {
        if (note) note.textContent = 'Minimum ' + _walletProviders.symbol + _walletProviders.min_amount +
            '. Credit is added once the payment clears.';
        if (go) { go.disabled = false; go.style.opacity = '1'; }
    }
    modal.style.display = 'flex';
}
window.openTopUpModal = openTopUpModal;

function closeTopUpModal() {
    var m = document.getElementById('topup-modal');
    if (m) m.style.display = 'none';
}
window.closeTopUpModal = closeTopUpModal;

async function startTopUp() {
    var amount = parseFloat((document.getElementById('topup-amount') || {}).value);
    if (!amount || amount <= 0) { showToast('Enter an amount', 'error'); return; }
    var picked = document.querySelector('input[name="topup-provider"]:checked');
    if (!picked) { showToast('Choose how to pay', 'error'); return; }

    try {
        var res = await fetch('/api/wallet/topup', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: amount, provider: picked.value })
        });
        var data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Could not start the payment');

        if (data.checkout_url || data.approve_url) {
            // Stripe and PayPal take the user to their own hosted page.
            window.location.href = data.checkout_url || data.approve_url;
            return;
        }
        if (data.provider === 'razorpay') {
            openRazorpayCheckout(data);
            return;
        }
        showToast('Payment started', 'info');
    } catch (e) { showToast(e.message, 'error'); }
}
window.startTopUp = startTopUp;

function openRazorpayCheckout(data) {
    // Razorpay renders in a modal from their own script; without it there is
    // nothing to show, so say so rather than failing silently.
    if (typeof window.Razorpay !== 'function') {
        showToast('Razorpay checkout script is not loaded on this page', 'error');
        return;
    }
    var rzp = new window.Razorpay({
        key: data.key_id,
        amount: data.amount_minor,
        currency: data.currency,
        name: data.name || 'Wallet top-up',
        order_id: data.razorpay_order_id,
        prefill: { email: data.prefill_email || '' },
        handler: function () {
            // Credit comes from the verified webhook, never from this callback.
            showToast('Payment received. Your balance will update shortly.', 'success');
            setTimeout(loadWallet, 2500);
        },
        modal: { ondismiss: function () { showToast('Payment cancelled', 'info'); } }
    });
    rzp.open();
}

// PayPal returns the buyer here; the capture call is what proves payment.
async function finishPayPalReturn() {
    var params = new URLSearchParams(window.location.search);
    if (params.get('topup') !== 'success') return;
    try {
        var orders = await (await fetch('/api/wallet/topups?limit=5')).json();
        var pending = orders.filter(function (o) { return o.provider === 'paypal' && o.status === 'pending'; })[0];
        if (!pending) return;
        var res = await fetch('/api/wallet/topup/' + pending.id + '/capture-paypal', { method: 'POST' });
        var data = await res.json();
        if (res.ok && data.credited) showToast('Wallet topped up', 'success');
    } catch (e) { /* the webhook or a later retry will settle it */ }
}

function handleTopUpReturn() {
    var params = new URLSearchParams(window.location.search);
    var state = params.get('topup');
    if (!state) return;
    if (state === 'success') {
        showToast('Payment complete. Updating your balance...', 'success');
        finishPayPalReturn().then(function () { loadWallet(); });
    } else if (state === 'cancelled') {
        showToast('Payment cancelled', 'info');
    }
    // Clear the marker so a refresh does not repeat this.
    window.history.replaceState({}, '', window.location.pathname);
}
window.handleTopUpReturn = handleTopUpReturn;

// Turn a 402 anywhere in the app into an actionable prompt.
function handleInsufficientCredit(detail) {
    showToast(detail || 'Not enough wallet credit', 'error');
    setTimeout(openTopUpModal, 600);
}
window.handleInsufficientCredit = handleInsufficientCredit;

// ==========================================================================
// AI ASSISTANT
// Answers from the tenant's own data. The previous version was an inline
// script that never ran: an unescaped quote in font-family:'Rajdhani' broke
// the whole block, so toggleAIChat was never defined and the orb did nothing.
// It also only ever replied "simulation mode".
// ==========================================================================

var _aiChatReady = false;

function toggleAIChat() {
    var w = document.getElementById('ai-chat-window');
    if (!w) return;
    var opening = w.style.display !== 'flex';
    w.style.display = opening ? 'flex' : 'none';
    if (opening) {
        if (!_aiChatReady) { initAIChat(); _aiChatReady = true; }
        var input = document.getElementById('ai-chat-input');
        if (input) input.focus();
    }
}
window.toggleAIChat = toggleAIChat;

function aiChatBubble(text, who) {
    var msgs = document.getElementById('ai-chat-messages');
    if (!msgs) return null;
    var el = document.createElement('div');
    if (who === 'user') {
        el.style.cssText = 'align-self:flex-end;background:rgba(255,255,255,0.1);padding:8px 12px;' +
            'border-radius:4px;border-right:2px solid var(--text-secondary);max-width:85%;overflow-wrap:anywhere;';
    } else {
        el.style.cssText = 'align-self:flex-start;background:rgba(0,240,255,0.1);padding:8px 12px;' +
            'border-radius:4px;border-left:2px solid var(--primary-color);max-width:90%;' +
            'white-space:pre-wrap;overflow-wrap:anywhere;';
    }
    el.textContent = text;          // textContent, so a reply can never inject markup
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
}

async function initAIChat() {
    aiChatBubble('Ask me about your invoices, people or hiring. I answer from your own data.', 'ai');
    try {
        var res = await fetch('/api/ai/suggestions');
        if (!res.ok) return;
        var data = await res.json();
        var host = document.getElementById('ai-chat-suggestions');
        if (!host) return;
        host.innerHTML = '';
        (data.suggestions || []).forEach(function (q) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn btn-outline btn-sm';
            b.style.cssText = 'font-size:0.72rem;padding:4px 9px;';
            b.textContent = q;
            b.onclick = function () {
                document.getElementById('ai-chat-input').value = q;
                sendAIChat();
            };
            host.appendChild(b);
        });
    } catch (e) { /* suggestions are optional */ }
}

async function sendAIChat() {
    var input = document.getElementById('ai-chat-input');
    if (!input) return;
    var question = input.value.trim();
    if (!question) return;
    input.value = '';

    var suggestions = document.getElementById('ai-chat-suggestions');
    if (suggestions) suggestions.innerHTML = '';

    aiChatBubble(question, 'user');
    var thinking = aiChatBubble('Thinking...', 'ai');

    try {
        var res = await fetch('/api/ai/assistant', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question })
        });
        var data = await res.json();
        if (thinking) thinking.remove();

        if (res.status === 402) {
            aiChatBubble(data.detail || 'Not enough wallet credit for the assistant.', 'ai');
            if (typeof handleInsufficientCredit === 'function') handleInsufficientCredit(data.detail);
            return;
        }
        if (!res.ok) { aiChatBubble(data.detail || 'Sorry, that did not work.', 'ai'); return; }
        aiChatBubble(data.answer, 'ai');
    } catch (e) {
        if (thinking) thinking.remove();
        aiChatBubble('Could not reach the assistant. Check your connection.', 'ai');
    }
}
window.sendAIChat = sendAIChat;

// --- AI helpers attached to specific screens -------------------------------

// Dashboard: a short read on where the business stands.
async function loadAIInsights() {
    var host = document.getElementById('ai-insights-panel');
    if (!host) return;
    host.innerHTML = '<span style="color:var(--text-secondary);font-size:0.85rem;">Reading your numbers...</span>';
    try {
        var res = await fetch('/api/ai/insights');
        var d = await res.json();
        if (!res.ok || !d.available) {
            host.closest('.glass-widget, .widget').style.display = 'none';
            return;
        }
        var colors = { high: 'var(--danger-color)', medium: 'var(--warning-color)', low: 'var(--text-secondary)' };
        host.innerHTML = '<p style="font-size:0.92rem;margin-bottom:12px;">' + esc(d.headline) + '</p>' +
            (d.actions || []).map(function (a) {
                return '<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;' +
                       'border-top:1px solid var(--border-color);font-size:0.85rem;">' +
                    '<span style="color:' + (colors[a.priority] || '') + ';font-size:0.7rem;font-weight:700;' +
                    'text-transform:uppercase;min-width:52px;">' + esc(a.priority || '') + '</span>' +
                    '<span>' + esc(a.text) + '</span></div>';
            }).join('');
    } catch (e) {
        var w = host.closest('.glass-widget, .widget');
        if (w) w.style.display = 'none';
    }
}
window.loadAIInsights = loadAIInsights;

// Recruitment: draft a job advert from the requisition fields.
async function aiWriteJobDescription() {
    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    var title = val('job-title');
    if (!title) { showToast('Enter a job title first', 'error'); return; }
    showToast('Drafting the advert...', 'info');
    try {
        var res = await fetch('/api/ai/job-description', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                department: (document.getElementById('job-department') || {}).selectedOptions
                    ? document.getElementById('job-department').selectedOptions[0].textContent : '',
                level: val('job-level'), location: val('job-location'),
                work_mode: val('job-work-mode'), employment_type: val('job-employment-type')
            })
        });
        var d = await res.json();
        if (!res.ok) { reportApiError(res, d, 'Could not draft the advert'); return; }
        if (!d.available) { showToast('AI is not configured on this server', 'error'); return; }
        var desc = document.getElementById('job-description');
        var reqs = document.getElementById('job-requirements');
        if (desc) desc.value = d.description || '';
        if (reqs) reqs.value = (d.requirements || []).map(function (r) { return '- ' + r; }).join('\n');
        showToast('Draft written - edit before publishing', 'success');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.aiWriteJobDescription = aiWriteJobDescription;

// Recruitment: interview questions for the candidate on screen.
async function aiInterviewQuestions() {
    if (!recCurrentSubId) { showToast('Open a candidate first', 'error'); return; }
    var form = recFormsLookup[recFormsSubId];
    showToast('Preparing questions...', 'info');
    try {
        var res = await fetch('/api/ai/interview-questions', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_title: form ? form.title : 'the role',
                submission_id: recCurrentSubId
            })
        });
        var d = await res.json();
        if (!res.ok) { reportApiError(res, d, 'Could not prepare questions'); return; }
        if (!d.available) { showToast('AI is not configured on this server', 'error'); return; }
        var host = document.getElementById('ai-screen-result');
        if (!host) return;
        host.innerHTML = '<div style="padding:16px;">' +
            '<strong style="font-size:0.9rem;">Suggested interview questions</strong>' +
            (d.questions || []).map(function (q) {
                return '<div style="padding:10px 0;border-top:1px solid var(--border-color);">' +
                    '<div style="font-size:0.87rem;">' + esc(q.question) + '</div>' +
                    '<div style="font-size:0.74rem;color:var(--text-secondary);margin-top:2px;">' +
                    esc(q.area || '') + (q.looking_for ? ' - ' + esc(q.looking_for) : '') + '</div></div>';
            }).join('') + '</div>';
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.aiInterviewQuestions = aiInterviewQuestions;

// Invoice builder: tidy a rough note into a line description.
async function aiDescribeLineItem(button) {
    var row = button.closest('.line-item-row');
    if (!row) return;
    var field = row.querySelector('.item-desc');
    var name = row.querySelector('.item-name');
    var rough = (field && field.value.trim()) || (name && name.value.trim()) || '';
    if (!rough) { showToast('Type a few words first', 'error'); return; }
    try {
        var res = await fetch('/api/ai/describe-item', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: rough })
        });
        var d = await res.json();
        if (!res.ok) { reportApiError(res, d, 'Could not rewrite that'); return; }
        if (!d.available) { showToast('AI is not configured on this server', 'error'); return; }
        if (field) {
            field.value = d.description;
            field.style.height = 'auto';
            field.style.height = field.scrollHeight + 'px';
        }
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.aiDescribeLineItem = aiDescribeLineItem;

// --- Document expiry and templates -----------------------------------------
// HR decides which documents carry an expiry date and can attach a blank form
// for the employee to fill in. The employee supplies the actual date.

function onRequirementExpiryChange() {
    var on = (document.getElementById('req-expiry') || {}).checked;
    var group = document.getElementById('req-reminder-group');
    if (group) group.style.display = on ? 'flex' : 'none';
}
window.onRequirementExpiryChange = onRequirementExpiryChange;

function pickRequirementTemplate() {
    if (!document.getElementById('req-id').value) {
        showToast('Save the document first, then attach a template', 'info');
        return;
    }
    document.getElementById('req-template-input').click();
}
window.pickRequirementTemplate = pickRequirementTemplate;

async function uploadRequirementTemplate(input) {
    var file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    var id = document.getElementById('req-id').value;
    if (!id) return;
    if (file.size > 5 * 1024 * 1024) { showToast('Template must be under 5MB', 'error'); return; }

    var reader = new FileReader();
    reader.onload = async function (e) {
        try {
            var res = await fetch('/api/onboarding/requirements/' + id + '/template', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_name: file.name, file_type: file.type,
                    file_data: e.target.result.split(',')[1]
                })
            });
            var d = await res.json();
            if (!res.ok) throw new Error(d.detail || 'Failed');
            showToast(d.message, 'success');
            setRequirementTemplateLabel(d.template_file_name);
            loadRequirements();
        } catch (err) { showToast(err.message, 'error'); }
    };
    reader.readAsDataURL(file);
}
window.uploadRequirementTemplate = uploadRequirementTemplate;

async function removeRequirementTemplate() {
    var id = document.getElementById('req-id').value;
    if (!id) return;
    try {
        var res = await fetch('/api/onboarding/requirements/' + id + '/template', { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed');
        setRequirementTemplateLabel('');
        showToast('Template removed', 'success');
        loadRequirements();
    } catch (e) { showToast('Failed to remove template', 'error'); }
}
window.removeRequirementTemplate = removeRequirementTemplate;

function setRequirementTemplateLabel(name) {
    var label = document.getElementById('req-template-name');
    var remove = document.getElementById('req-template-remove');
    if (label) label.textContent = name || 'none attached';
    if (remove) remove.style.display = name ? 'inline-flex' : 'none';
}

async function downloadRequirementTemplate(reqId) {
    try {
        var res = await fetch('/api/onboarding/requirements/' + reqId + '/template');
        var d = await res.json();
        if (!res.ok) throw new Error(d.detail || 'No template');
        var bytes = atob(d.file_data);
        var arr = new Uint8Array(bytes.length);
        for (var i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        var url = URL.createObjectURL(new Blob([arr], { type: d.file_type || 'application/octet-stream' }));
        var a = document.createElement('a');
        a.href = url; a.download = d.file_name || 'template'; a.click();
        URL.revokeObjectURL(url);
    } catch (e) { showToast(e.message, 'error'); }
}
window.downloadRequirementTemplate = downloadRequirementTemplate;

// Right-to-work and DBS checks lapse quietly; this is the screen that catches it.
async function loadExpiringDocuments() {
    var host = document.getElementById('expiring-docs-list');
    if (!host) return;
    try {
        var res = await fetch('/api/onboarding/expiring-documents?days=60');
        var d = res.ok ? await res.json() : { expired: [], expiring: [] };
        var rows = (d.expired || []).concat(d.expiring || []);
        if (!rows.length) {
            host.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem;">Nothing expiring in the next ' +
                (d.window_days || 60) + ' days.</p>';
            return;
        }
        host.innerHTML = rows.map(function (r) {
            var expired = r.is_expired;
            var when = expired
                ? 'expired ' + esc(r.expires_on)
                : 'expires ' + esc(r.expires_on) + ' (' + r.days_until_expiry + ' days)';
            return '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 0;' +
                   'border-bottom:1px solid var(--border-color);font-size:0.85rem;">' +
                '<span style="flex:1;min-width:150px;"><strong>' + employeeLink(r.employee_id, r.employee_name) +
                    '</strong> <span style="color:var(--text-secondary);">' + esc(r.name) + '</span></span>' +
                '<span style="color:' + (expired ? 'var(--danger-color)' : 'var(--warning-color)') +
                    ';font-weight:600;">' + when + '</span>' +
                (r.document_id ? ' <button class="btn btn-outline btn-sm" onclick="downloadRequestFile(' + r.id + ')">Get</button>' : '') +
            '</div>';
        }).join('');
    } catch (e) { host.innerHTML = ''; }
}
window.loadExpiringDocuments = loadExpiringDocuments;

// ==================== QUOTES ====================
// A quote is an invoice that has not been agreed yet. It reuses the line-item
// editor and the PDF generator; only the wording and the lifecycle differ.

var allQuotes = [];
var currentQuoteFilter = 'all';
var currentQuote = null;

function quoteStatusClass(status) {
    var s = (status || '').toLowerCase();
    if (s === 'accepted') return 'status-active';
    if (s === 'invoiced') return 'status-paid';
    if (s === 'declined' || s === 'expired') return 'status-terminated';
    if (s === 'sent') return 'status-onboarding';
    return 'status-draft';
}

async function fetchQuotes() {
    try {
        var res = await fetch('/api/quotes', { credentials: 'same-origin' });
        if (!res.ok) return;
        allQuotes = await res.json();
        renderQuotes();
    } catch (e) { console.error('fetchQuotes error:', e); }
}
window.fetchQuotes = fetchQuotes;

function filterQuotes(filter, btn) {
    currentQuoteFilter = filter;
    document.querySelectorAll('#quote-tabs .tab').forEach(function (t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    renderQuotes();
}
window.filterQuotes = filterQuotes;

function searchQuotes() { renderQuotes(); }
window.searchQuotes = searchQuotes;

function renderQuotes() {
    var tbody = document.getElementById('quotes-table-body');
    if (!tbody) return;

    var term = (document.getElementById('quote-search') || {}).value || '';
    term = term.trim().toLowerCase();

    var rows = allQuotes.filter(function (q) {
        var matchesFilter = currentQuoteFilter === 'all'
            || (q.status || '').toLowerCase() === currentQuoteFilter;
        if (!matchesFilter) return false;
        if (!term) return true;
        return [q.number, q.to, q.ref, q.title].some(function (v) {
            return (v || '').toLowerCase().indexOf(term) !== -1;
        });
    });

    var count = document.getElementById('quote-count');
    if (count) count.textContent = rows.length + (rows.length === 1 ? ' item' : ' items');

    if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">No quotes found.</td></tr>';
        return;
    }

    tbody.innerHTML = rows.map(function (q) {
        return '<tr style="cursor:pointer;" onclick="viewQuote(\'' + encodeURIComponent(q.number) + '\')">' +
            '<td><strong>' + esc(q.number) + '</strong></td>' +
            '<td>' + esc(q.ref || '-') + '</td>' +
            '<td>' + esc(q.to || '-') + '</td>' +
            '<td>' + esc(q.title || '-') + '</td>' +
            '<td>' + esc(q.date || '-') + '</td>' +
            '<td>' + esc(q.expiry_date || '-') + '</td>' +
            '<td class="text-right"><strong>' + formatCurrency(q.total, q.currency) + '</strong></td>' +
            '<td><span class="status-pill ' + quoteStatusClass(q.status) + '">' + esc(q.status) + '</span></td>' +
            '</tr>';
    }).join('');
}
window.renderQuotes = renderQuotes;

// --- Creating -----------------------------------------------------------

async function prepareNewQuote() {
    var form = document.getElementById('quote-form');
    if (form) form.reset();
    var body = document.getElementById('quote-line-items-body');
    if (body) { body.innerHTML = ''; addLineItemRow('quote'); }

    var today = localDate(new Date());
    var expiry = localDate(new Date(Date.now() + 30 * 86400000));
    var issueEl = document.getElementById('quote-issue-date');
    var expiryEl = document.getElementById('quote-expiry-date');
    if (issueEl) issueEl.value = today;
    if (expiryEl) expiryEl.value = expiry;

    try {
        var res = await fetch('/api/next-quote-number', { credentials: 'same-origin' });
        if (res.ok) {
            var data = await res.json();
            var numEl = document.getElementById('quote-number');
            if (numEl) numEl.placeholder = data.next_number || 'QU-0001';
        }
    } catch (e) { /* the server assigns one anyway */ }

    calculateTotals('quote');
    showView('create-quote-view');
    // Same pickers as the invoice form, rather than a bare text box.
    if (typeof setupCurrencyPicker === 'function' &&
        document.getElementById('quote-currency-display') && !_curPickers['quoteCurrency']) {
        setupCurrencyPicker('quoteCurrency', 'quote-currency-display', 'quote-currency',
                            'quote-currency-list', 'quote-currency-search', 'quote-currency-items');
    }
    if (typeof setCurrencyPickerDisplay === 'function' && _curPickers['quoteCurrency']) {
        setCurrencyPickerDisplay('quoteCurrency', _appCurrency);
    }
    if (typeof setupContactAutocomplete === 'function') {
        setupContactAutocomplete('quote-contact', 'quote-contact-dropdown');
    }
}
window.prepareNewQuote = prepareNewQuote;

function collectQuotePayload(status) {
    var contact = (document.getElementById('quote-contact') || {}).value || '';
    if (!contact.trim()) { showToast('Customer name is required', 'error'); return null; }

    var line_items = [];
    scopedLineRows('quote').forEach(function (row) {
        var name = row.querySelector('.item-name') ? row.querySelector('.item-name').value : '';
        var desc = row.querySelector('.item-desc') ? row.querySelector('.item-desc').value : '';
        var qty = parseFloat(row.querySelector('.item-qty') ? row.querySelector('.item-qty').value : 0) || 0;
        var price = parseFloat(row.querySelector('.item-price') ? row.querySelector('.item-price').value : 0) || 0;
        var disc = parseFloat(row.querySelector('.item-disc') ? row.querySelector('.item-disc').value : 0) || 0;
        var account = row.querySelector('.item-account') ? row.querySelector('.item-account').value : '200 - Sales';
        var tax_rate = row.querySelector('.item-tax-rate') ? row.querySelector('.item-tax-rate').value : 'No Tax';
        if (name || desc || qty > 0 || price > 0) {
            line_items.push({ name: name, description: desc, qty: qty, price: price, disc: disc, account: account, tax_rate: tax_rate });
        }
    });
    if (line_items.length === 0) { showToast('Add at least one line item', 'error'); return null; }

    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    return {
        contact: contact,
        email: val('quote-email'),
        phone_number: val('quote-phone'),
        issue_date: val('quote-issue-date'),
        expiry_date: val('quote-expiry-date'),
        quote_number: val('quote-number'),
        reference: val('quote-ref'),
        title: val('quote-title'),
        summary: val('quote-summary'),
        terms: val('quote-terms'),
        line_items: line_items,
        tax_type: val('quote-tax-type') || 'exclusive',
        status: status,
        currency: val('quote-currency') || (_appCurrency || 'GBP'),
    };
}

async function submitQuote(status) {
    var payload = collectQuotePayload(status || 'Draft');
    if (!payload) return;
    try {
        var res = await fetch('/api/quotes', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify(payload),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not save the quote'); return; }

        await fetchQuotes();
        if (status === 'Sent' && payload.email) {
            showToast('Quote created. Sending...', 'info');
            await viewQuote(data.number);
            await sendQuoteEmail();
        } else if (status === 'Sent') {
            showToast('Quote created. Add an email address to send it.', 'warning');
            showView('quotes-view');
        } else {
            showToast('Quote saved as draft', 'success');
            showView('quotes-view');
        }
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.submitQuote = submitQuote;

// --- Viewing ------------------------------------------------------------

async function viewQuote(number) {
    number = decodeURIComponent(number);
    try {
        var res = await fetch('/api/quotes/' + encodeURIComponent(number), { credentials: 'same-origin' });
        if (!res.ok) { showToast('Quote not found', 'error'); return; }
        var q = await res.json();
        currentQuote = q;
        _viewCurrency = q.currency || _appCurrency;

        function put(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }
        put('view-quote-title', 'Quote ' + q.number);
        put('view-quote-number-val', q.number);
        put('view-quote-contact', q.to || '-');
        put('view-quote-email-display', q.email || '');
        put('view-quote-phone-display', q.phone_number || '');
        put('view-quote-issue-date', q.date || '-');
        // The generator reads the expiry from the slot an invoice uses for its
        // due date; see PDF_DOC_TYPES.
        put('view-quote-due-date', q.expiry_date || '-');
        put('view-quote-ref', q.ref || '-');
        put('view-quote-subject', q.title || '');
        put('view-quote-summary-text', q.summary || '');
        put('view-quote-terms-text', q.terms || '');
        put('view-quote-company-name', (q.company && q.company.name) || '');
        put('view-quote-company-address', (q.company && q.company.address) || '');
        put('view-quote-company-email', (q.company && q.company.email) || '');
        put('view-quote-company-phone', (q.company && q.company.phone_number) || '');
        put('view-quote-company-abn', (q.company && q.company.abn) || '');
        put('view-quote-summary-subtotal', Number(q.subtotal || 0).toFixed(2));
        put('view-quote-summary-vat', Number(q.tax_total || 0).toFixed(2));
        put('view-quote-summary-total', Number(q.total || 0).toFixed(2));
        put('view-quote-due-currency', currencySymbolFor(q.currency));

        var statusEl = document.getElementById('view-quote-status');
        if (statusEl) {
            statusEl.textContent = q.status;
            statusEl.className = 'status-pill ' + quoteStatusClass(q.status);
        }

        var linked = document.getElementById('view-quote-invoice-link');
        if (linked) {
            if (q.invoice_number) {
                linked.style.display = 'block';
                linked.innerHTML = 'Invoiced as <a href="#" onclick="event.preventDefault();showView(\'invoices-view\');viewInvoice(\'' +
                    encodeURIComponent(q.invoice_number) + '\')"><strong>' + esc(q.invoice_number) + '</strong></a>';
            } else {
                linked.style.display = 'none';
            }
        }

        var tbody = document.getElementById('view-quote-line-items-body');
        if (tbody) {
            tbody.innerHTML = (q.line_items || []).map(function (li) {
                return '<tr>' +
                    '<td style="padding:12px 16px;word-wrap:break-word;max-width:200px;vertical-align:top;">' + esc(li.name || '') + '</td>' +
                    '<td style="padding:12px 16px;word-wrap:break-word;max-width:280px;vertical-align:top;">' + esc(li.description || '') + '</td>' +
                    '<td style="padding:12px 16px;text-align:right;vertical-align:top;">' + esc(li.qty) + '</td>' +
                    '<td style="padding:12px 16px;text-align:right;vertical-align:top;">' + Number(li.price || 0).toFixed(2) + '</td>' +
                    '<td style="padding:12px 16px;text-align:right;vertical-align:top;">' + (li.disc || 0) + '%</td>' +
                    '<td style="padding:12px 16px;vertical-align:top;">' + esc(li.tax_rate || 'No Tax') + '</td>' +
                    '<td style="padding:12px 16px;text-align:right;font-weight:600;vertical-align:top;">' + Number(li.amount || 0).toFixed(2) + '</td>' +
                    '</tr>';
            }).join('');
        }

        // What you can still do depends on where the quote has got to.
        var canConvert = q.status !== 'Invoiced' && q.status !== 'Declined';
        var convertBtn = document.getElementById('quote-convert-btn');
        if (convertBtn) convertBtn.style.display = canConvert ? '' : 'none';
        var decideWrap = document.getElementById('quote-decide-actions');
        if (decideWrap) decideWrap.style.display = (q.status === 'Invoiced') ? 'none' : '';

        showView('view-quote-view');
    } catch (e) { showToast('Failed to load quote: ' + e.message, 'error'); }
}
window.viewQuote = viewQuote;

function currencySymbolFor(code) {
    var map = { GBP: '£', USD: '$', EUR: '€', INR: '₹', AUD: '$', CAD: '$', NZD: '$' };
    return map[(code || '').toUpperCase()] || '';
}

// --- Actions ------------------------------------------------------------

function downloadQuotePDF() {
    if (!currentQuote) { showToast('No quote loaded', 'error'); return; }
    try {
        var doc = generateQuotePDF();
        doc.save(currentQuote.number + '.pdf');
    } catch (e) { showToast('PDF generation failed: ' + e.message, 'error'); }
}
window.downloadQuotePDF = downloadQuotePDF;

async function sendQuoteEmail() {
    if (!currentQuote) { showToast('No quote loaded', 'error'); return; }
    if (!currentQuote.email) { showToast('This quote has no email address', 'error'); return; }

    var pdfB64 = '';
    try {
        var doc = generateQuotePDF();
        pdfB64 = (doc.output('datauristring').split('base64,')[1]) || '';
    } catch (e) {
        showToast('PDF generation failed: ' + e.message, 'error');
        return;
    }

    try {
        showToast('Sending quote...', 'info');
        var res = await fetch('/api/quotes/' + encodeURIComponent(currentQuote.number) + '/send', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                logo_data: localStorage.getItem('company_logo') || '',
                pdf_data: pdfB64,
            }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (res.ok) {
            showToast('Quote sent with the PDF attached', 'success');
            await fetchQuotes();
            await viewQuote(currentQuote.number);
        } else {
            reportApiError(res, data, 'Could not send the quote');
        }
    } catch (e) { showToast('Failed to send: ' + e.message, 'error'); }
}
window.sendQuoteEmail = sendQuoteEmail;

async function setQuoteStatus(status) {
    if (!currentQuote) return;
    try {
        var res = await fetch('/api/quotes/' + encodeURIComponent(currentQuote.number) + '/status', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify({ status: status }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not update the quote'); return; }
        showToast('Quote marked ' + status.toLowerCase(), 'success');
        await fetchQuotes();
        await viewQuote(currentQuote.number);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.setQuoteStatus = setQuoteStatus;

async function convertQuoteToInvoice() {
    if (!currentQuote) return;
    if (!confirm('Create an invoice from quote ' + currentQuote.number + '?')) return;
    try {
        var res = await fetch('/api/quotes/' + encodeURIComponent(currentQuote.number) + '/convert', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify({}),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not convert the quote'); return; }
        showToast('Invoice ' + data.invoice_number + ' created', 'success');
        await fetchQuotes();
        if (typeof fetchInvoices === 'function') await fetchInvoices();
        await viewInvoice(data.invoice_number);
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.convertQuoteToInvoice = convertQuoteToInvoice;

async function deleteQuote() {
    if (!currentQuote) return;
    if (!confirm('Delete quote ' + currentQuote.number + '? This cannot be undone.')) return;
    try {
        var res = await fetch('/api/quotes/' + encodeURIComponent(currentQuote.number), {
            method: 'DELETE', credentials: 'same-origin',
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not delete the quote'); return; }
        showToast('Quote deleted', 'success');
        currentQuote = null;
        await fetchQuotes();
        showView('quotes-view');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.deleteQuote = deleteQuote;

// ==================== TAX RATES ====================
// The tenant's own list of tax options. Line items store the rendered label,
// so this list only ever affects what you can pick next - never what has
// already been issued.

var _taxRates = [];

function taxRateLabel(name, percent) {
    name = (name || '').trim();
    var pct = Number(percent) || 0;
    if (!name) return pct + '%';
    // Mirrors tax_rate_label() on the server.
    if (pct === 0 && ['no tax', 'none', 'exempt'].indexOf(name.toLowerCase()) !== -1) return name;
    return pct + '% ' + name;
}

async function loadTaxRates() {
    try {
        var res = await fetch('/api/tax-rates', { credentials: 'same-origin' });
        if (!res.ok) return _taxRates;
        _taxRates = await res.json();
    } catch (e) { /* fall back to whatever we already had */ }
    renderTaxRateRows();
    refreshTaxRateSelects();
    return _taxRates;
}
window.loadTaxRates = loadTaxRates;

// The <option> list every line-item row uses. `selected` keeps a row's current
// choice even if it is a label no longer in the list, which is what an older
// document carries.
function taxOptionsHtml(selected) {
    var list = _taxRates.length ? _taxRates : [
        { label: '20% VAT', is_default: true }, { label: '5% VAT' },
        { label: '0% Zero Rated' }, { label: 'No Tax' }
    ];
    var labels = list.map(function (t) { return t.label; });
    if (selected && labels.indexOf(selected) === -1) labels.unshift(selected);

    var preferred = selected;
    if (!preferred) {
        var def = list.filter(function (t) { return t.is_default; })[0];
        preferred = def ? def.label : labels[0];
    }
    return labels.map(function (l) {
        return '<option' + (l === preferred ? ' selected' : '') + '>' + esc(l) + '</option>';
    }).join('');
}
window.taxOptionsHtml = taxOptionsHtml;

// Existing rows follow the list when it changes, unless the row is carrying a
// label the list no longer has.
function refreshTaxRateSelects() {
    var available = _taxRates.map(function (t) { return t.label; });
    document.querySelectorAll('select.item-tax-rate').forEach(function (sel) {
        // A rate the tenant has just deleted must not stay selected on a line
        // they are still writing - that would invoice at a rate they removed.
        // Rows fall back to the new default instead.
        var current = available.indexOf(sel.value) === -1 ? '' : sel.value;
        sel.innerHTML = taxOptionsHtml(current);
        if (current) sel.value = current;
    });
    renderBillTaxRates();
    if (typeof calculateTotals === 'function') {
        Object.keys(DOC_FORM_SCOPES).forEach(function (scope) { calculateTotals(scope); });
    }
}

function renderTaxRateRows() {
    var tbody = document.getElementById('tax-rates-body');
    if (!tbody) return;
    if (!_taxRates.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-secondary);">No tax rates yet.</td></tr>';
        return;
    }
    tbody.innerHTML = _taxRates.map(function (t, i) {
        return '<tr class="tax-rate-row">' +
            '<td><input type="text" class="form-control tax-rate-name" value="' + esc(t.name) + '" maxlength="60" oninput="updateTaxRatePreview(this)"></td>' +
            '<td><input type="number" class="form-control tax-rate-percent" value="' + esc(t.percent) + '" min="0" max="100" step="0.01" oninput="updateTaxRatePreview(this)"></td>' +
            '<td class="tax-rate-preview" style="color:var(--text-secondary);">' + esc(t.label) + '</td>' +
            '<td style="text-align:center;"><input type="radio" name="tax-rate-default" class="tax-rate-default"' + (t.is_default ? ' checked' : '') + '></td>' +
            '<td style="text-align:center;"><button type="button" class="btn-icon" onclick="removeTaxRateRow(this)" style="color:var(--danger-color);background:none;border:none;cursor:pointer;">&#10005;</button></td>' +
            '</tr>';
    }).join('');
}

function updateTaxRatePreview(el) {
    var row = el.closest('.tax-rate-row');
    if (!row) return;
    var name = row.querySelector('.tax-rate-name').value;
    var pct = row.querySelector('.tax-rate-percent').value;
    var cell = row.querySelector('.tax-rate-preview');
    if (cell) cell.textContent = taxRateLabel(name, pct);
}
window.updateTaxRatePreview = updateTaxRatePreview;

function addTaxRateRow() {
    var tbody = document.getElementById('tax-rates-body');
    if (!tbody) return;
    if (!document.querySelectorAll('.tax-rate-row').length) tbody.innerHTML = '';
    tbody.insertAdjacentHTML('beforeend',
        '<tr class="tax-rate-row">' +
        '<td><input type="text" class="form-control tax-rate-name" placeholder="e.g. GST" maxlength="60" oninput="updateTaxRatePreview(this)"></td>' +
        '<td><input type="number" class="form-control tax-rate-percent" value="0" min="0" max="100" step="0.01" oninput="updateTaxRatePreview(this)"></td>' +
        '<td class="tax-rate-preview" style="color:var(--text-secondary);">-</td>' +
        '<td style="text-align:center;"><input type="radio" name="tax-rate-default" class="tax-rate-default"></td>' +
        '<td style="text-align:center;"><button type="button" class="btn-icon" onclick="removeTaxRateRow(this)" style="color:var(--danger-color);background:none;border:none;cursor:pointer;">&#10005;</button></td>' +
        '</tr>');
}
window.addTaxRateRow = addTaxRateRow;

function removeTaxRateRow(btn) {
    if (document.querySelectorAll('.tax-rate-row').length <= 1) {
        showToast('Keep at least one tax rate', 'error');
        return;
    }
    var row = btn.closest('.tax-rate-row');
    if (row) row.remove();
}
window.removeTaxRateRow = removeTaxRateRow;

async function saveTaxRates() {
    var rows = [];
    var bad = null;
    document.querySelectorAll('.tax-rate-row').forEach(function (row) {
        var name = (row.querySelector('.tax-rate-name').value || '').trim();
        var pctRaw = row.querySelector('.tax-rate-percent').value;
        var pct = parseFloat(pctRaw);
        if (!name && !pctRaw) return;             // a blank row the user abandoned
        if (!name) { bad = bad || 'Every tax rate needs a name'; return; }
        if (isNaN(pct) || pct < 0 || pct > 100) {
            bad = bad || ('"' + name + '" must be between 0 and 100 percent');
            return;
        }
        rows.push({ name: name, percent: pct, is_default: row.querySelector('.tax-rate-default').checked });
    });

    if (bad) { showToast(bad, 'error'); return; }
    if (!rows.length) { showToast('Keep at least one tax rate', 'error'); return; }

    try {
        var res = await fetch('/api/tax-rates', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify({ tax_rates: rows }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not save the tax rates'); return; }
        _taxRates = data;
        renderTaxRateRows();
        refreshTaxRateSelects();
        showToast('Tax rates saved', 'success');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.saveTaxRates = saveTaxRates;

// ==================== ONBOARDING PIPELINE ====================
// One board for the whole journey from hire to working employee. Stages are
// worked out from the person's actual records, so nothing has to be dragged
// to keep it honest - you move someone on by approving their documents or
// ticking their checklist, and the card follows.

async function loadOnboardingPipeline() {
    var host = document.getElementById('onb-pipeline-board');
    if (!host) return;
    try {
        var res = await fetch('/api/onboarding/pipeline', { credentials: 'same-origin' });
        if (!res.ok) return;
        var data = await res.json();
        renderOnboardingPipeline(data);
    } catch (e) { console.error('Onboarding pipeline load failed:', e); }
}
window.loadOnboardingPipeline = loadOnboardingPipeline;

function renderOnboardingPipeline(data) {
    var host = document.getElementById('onb-pipeline-board');
    if (!host) return;

    var summary = document.getElementById('onb-pipeline-summary');
    if (summary) {
        summary.textContent = data.total === 0
            ? 'Nobody is onboarding right now'
            : data.total + ' onboarding' + (data.blocked ? ' · ' + data.blocked + ' blocked' : '');
    }

    host.innerHTML = (data.stages || []).map(function (stage) {
        var cards = (stage.cards || []).map(onboardingCardHtml).join('') ||
            '<div class="onb-empty">Nobody here</div>';
        return '<div class="onb-col">' +
            '<div class="onb-col-head"><strong>' + esc(stage.label) + '</strong>' +
                '<span class="onb-col-count">' + stage.count + '</span></div>' +
            '<div class="onb-col-hint">' + esc(stage.hint) + '</div>' +
            cards +
        '</div>';
    }).join('');
}

function onboardingCardHtml(c) {
    var pct = c.items_total ? Math.round((c.items_done / c.items_total) * 100) : 0;

    // Say what is actually holding this person up, not just that they are stuck.
    var blockers = [];
    if (c.docs_overdue && c.docs_overdue.length) blockers.push('overdue: ' + c.docs_overdue.join(', '));
    if (c.items_overdue) blockers.push(c.items_overdue + ' overdue task' + (c.items_overdue === 1 ? '' : 's'));
    var waiting = '';
    if (c.awaiting_employee && c.awaiting_employee.length) waiting = 'Needs: ' + c.awaiting_employee.join(', ');
    else if (c.awaiting_hr && c.awaiting_hr.length) waiting = 'To review: ' + c.awaiting_hr.join(', ');

    var actions = '<button class="btn btn-outline btn-sm" onclick="openEmployee(' + c.employee_id + ')">Open</button>';
    if (c.awaiting_employee && c.awaiting_employee.length) {
        actions += '<button class="btn btn-outline btn-sm" onclick="nudgeStarter(' + c.employee_id + ')">Remind</button>';
    }
    if (c.awaiting_hr && c.awaiting_hr.length) {
        actions += '<button class="btn btn-outline btn-sm" onclick="showView(\'onboarding-hub-view\');loadDocumentQueue()">Review</button>';
    }
    if (c.stage === 'ready') {
        actions += '<button class="btn btn-primary btn-sm" onclick="finishOnboarding(' + c.employee_id + ')">Complete</button>';
    }

    return '<div class="onb-card' + (c.is_blocked ? ' is-blocked' : '') + '">' +
        '<div class="onb-card-name">' + esc(c.name) + '</div>' +
        '<div class="onb-card-sub">' + esc(c.job_title || '—') +
            (c.department ? ' · ' + esc(c.department) : '') + '</div>' +
        (c.hired_from
            ? '<div class="onb-card-sub">Hired from application by ' + esc(c.hired_from.candidate_name) + '</div>'
            : '') +
        (waiting ? '<div class="onb-card-meta">' + esc(waiting) + '</div>' : '') +
        (blockers.length
            ? '<div class="onb-card-meta" style="color:var(--danger-color);">' + esc(blockers.join(' · ')) + '</div>'
            : '') +
        '<div class="onb-bar"><span style="width:' + pct + '%"></span></div>' +
        '<div class="onb-card-meta">' + c.items_done + '/' + c.items_total + ' tasks · ' +
            c.docs_approved + '/' + c.docs_total + ' documents' +
            (c.days_since_start !== null && c.days_since_start !== undefined
                ? ' · day ' + c.days_since_start : '') + '</div>' +
        '<div class="onb-card-actions">' + actions + '</div>' +
    '</div>';
}

async function nudgeStarter(empId) {
    try {
        var res = await fetch('/api/employees/' + empId + '/nudge', {
            method: 'POST', credentials: 'same-origin',
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not send the reminder'); return; }
        showToast('Reminder sent: ' + (data.items || []).join(', '), 'success');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.nudgeStarter = nudgeStarter;

async function finishOnboarding(empId) {
    if (!confirm('Mark onboarding complete? They become an active employee.')) return;
    try {
        var res = await fetch('/api/employees/' + empId + '/complete-onboarding', {
            method: 'POST', credentials: 'same-origin',
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not complete onboarding'); return; }
        showToast('Onboarding complete', 'success');
        hrDataChanged('onboarding', { employeeId: empId });
        loadOnboardingPipeline();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.finishOnboarding = finishOnboarding;

// ==================== SALES PIPELINE ====================
// The money flow in one place. Like the onboarding board, stages come from the
// documents themselves, so nothing is dragged: send a quote, accept it,
// convert it, take the payment, and the card moves because the document did.

// Whether the AI is set up at all, asked once. Buttons that cannot possibly
// work should say so rather than failing when pressed.
var _aiStatus = null;

async function loadAiStatus() {
    try {
        var res = await fetch('/api/ai/status', { credentials: 'same-origin' });
        if (res.ok) _aiStatus = await res.json();
    } catch (e) { /* leave unknown; features still try and report properly */ }
    applyAiStatus();
    return _aiStatus;
}
window.loadAiStatus = loadAiStatus;

function applyAiStatus() {
    if (!_aiStatus || _aiStatus.configured) return;
    document.querySelectorAll('[data-ai]').forEach(function (el) {
        el.disabled = true;
        el.title = _aiStatus.message || 'AI is not set up yet.';
    });
}

// One message for every AI failure, so "not configured" does not read the same
// as "the service is busy".
function aiUnavailableText() {
    if (_aiStatus && !_aiStatus.configured) return _aiStatus.message || 'AI is not set up yet.';
    return 'The AI is unavailable right now. Try again in a moment.';
}
window.aiUnavailableText = aiUnavailableText;

async function loadSalesPipeline() {
    var host = document.getElementById('sales-pipeline-board');
    if (!host) return;
    try {
        var res = await fetch('/api/sales/pipeline', { credentials: 'same-origin' });
        if (!res.ok) return;
        renderSalesPipeline(await res.json());
    } catch (e) { console.error('Sales pipeline load failed:', e); }
}
window.loadSalesPipeline = loadSalesPipeline;

// Money in more than one currency cannot be added up without a rate, and this
// app has no rates. So each currency is shown on its own line rather than
// summed into a number that means nothing.
function moneyLines(totals, emptyText) {
    if (!totals || !totals.length) return esc(emptyText || '0');
    return totals.map(function (t) {
        return '<div>' + esc(formatCurrency(t.value, t.currency)) + '</div>';
    }).join('');
}

function renderSalesPipeline(data) {
    var host = document.getElementById('sales-pipeline-board');
    if (!host) return;

    var summary = document.getElementById('sales-pipeline-summary');
    if (summary) {
        var zero = formatCurrency(0, data.base_currency);
        summary.innerHTML =
            statTile('In the pipeline', moneyLines(data.pipeline && data.pipeline.totals, zero),
                     'quotes not yet invoiced') +
            statTile('Outstanding', moneyLines(data.outstanding, zero), 'invoiced, not paid') +
            statTile('Overdue', String(data.overdue_count || 0),
                     (data.overdue_count === 1 ? 'invoice' : 'invoices') + ' past due') +
            statTile('Lost', moneyLines(data.lost && data.lost.totals, zero),
                     'declined or expired');
    }

    host.innerHTML = (data.stages || []).map(function (stage) {
        var cards = (stage.cards || []).map(salesCardHtml).join('') ||
            '<div class="onb-empty">Nothing here</div>';
        var hidden = (stage.count || 0) - (stage.shown || 0);
        return '<div class="onb-col">' +
            '<div class="onb-col-head"><strong>' + esc(stage.label) + '</strong>' +
                '<span class="onb-col-count">' + stage.count + '</span></div>' +
            '<div class="onb-col-hint">' + moneyLines(stage.totals, formatCurrency(0, data.base_currency)) + '</div>' +
            '<div class="onb-col-body">' + cards +
                (hidden > 0
                    ? '<div class="onb-empty">and ' + hidden + ' more</div>'
                    : '') +
            '</div>' +
        '</div>';
    }).join('');
}

// `value` is already-escaped markup, because a tile may show one line per
// currency. Everything that goes into it is escaped at the point it is built.
function statTile(label, valueHtml, hint) {
    return '<div class="stat-card is-centered" style="cursor:default;">' +
        '<div style="font-size:0.8rem;color:var(--text-secondary);">' + esc(label) + '</div>' +
        '<div class="stat-money">' + valueHtml + '</div>' +
        '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:2px;">' + esc(hint) + '</div>' +
    '</div>';
}

function salesCardHtml(c) {
    var open = c.kind === 'quote'
        ? 'viewQuote(\'' + encodeURIComponent(c.number) + '\')'
        : 'viewInvoice(\'' + encodeURIComponent(c.number) + '\')';
    var line = c.kind === 'invoice' && c.is_overdue
        ? '<div class="onb-card-meta" style="color:var(--danger-color);">' +
          c.days_overdue + ' day(s) overdue</div>'
        : '<div class="onb-card-meta">' + esc(c.due_or_expiry || '') + '</div>';

    return '<div class="onb-card' + (c.is_overdue ? ' is-blocked' : '') + '" ' +
        'style="cursor:pointer;" onclick="' + open + '">' +
        '<div class="onb-card-name">' + esc(c.to || '-') + '</div>' +
        '<div class="onb-card-sub">' + esc(c.number) +
            (c.title ? ' · ' + esc(c.title) : '') + '</div>' +
        '<div style="font-weight:700;margin-top:6px;">' +
            formatCurrency(c.total, c.currency) + '</div>' +
        line +
    '</div>';
}

// ==================== RECURRING INVOICES ====================

var allRecurring = [];

async function loadRecurring() {
    var tbody = document.getElementById('recurring-table-body');
    if (!tbody) return;
    try {
        var res = await fetch('/api/recurring-invoices', { credentials: 'same-origin' });
        if (!res.ok) return;
        allRecurring = await res.json();
        renderRecurring();
    } catch (e) { console.error('Recurring load failed:', e); }
}
window.loadRecurring = loadRecurring;

function renderRecurring() {
    var tbody = document.getElementById('recurring-table-body');
    if (!tbody) return;
    var count = document.getElementById('recurring-count');
    if (count) count.textContent = allRecurring.length +
        (allRecurring.length === 1 ? ' item' : ' items');

    if (!allRecurring.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
            'No recurring invoices yet. Set one up and it raises itself.</td></tr>';
        return;
    }
    tbody.innerHTML = allRecurring.map(function (r) {
        return '<tr>' +
            '<td><strong>' + esc(r.name || '-') + '</strong></td>' +
            '<td>' + esc(r.to || '-') + '</td>' +
            '<td>' + esc(r.frequency) + '</td>' +
            '<td>' + esc(r.next_run || '-') + '</td>' +
            '<td class="text-right"><strong>' + formatCurrency(r.total, r.currency) + '</strong></td>' +
            '<td class="text-right">' + (r.invoices_created || 0) + '</td>' +
            '<td><span class="status-pill ' + (r.is_active ? 'status-active' : 'status-terminated') + '">' +
                (r.is_active ? 'Active' : 'Stopped') + '</span></td>' +
            '<td class="text-right">' +
                '<button class="btn btn-outline btn-sm" onclick="stopRecurring(' + r.id + ')">Stop</button>' +
            '</td></tr>';
    }).join('');
}

// Reuses the invoice editor: fill it in, then say how often instead of saving once.
async function prepareNewRecurring() {
    showView('create-invoice-view');
    await new Promise(function (r) { setTimeout(r, 200); });
    showToast('Fill in the invoice, then use "Make recurring"', 'info');
}
window.prepareNewRecurring = prepareNewRecurring;

async function makeInvoiceRecurring() {
    var contact = (document.getElementById('inv-contact') || {}).value || '';
    if (!contact.trim()) { showToast('Customer name is required', 'error'); return; }

    var line_items = [];
    scopedLineRows('invoice').forEach(function (row) {
        var name = row.querySelector('.item-name') ? row.querySelector('.item-name').value : '';
        var desc = row.querySelector('.item-desc') ? row.querySelector('.item-desc').value : '';
        var qty = parseFloat(row.querySelector('.item-qty') ? row.querySelector('.item-qty').value : 0) || 0;
        var price = parseFloat(row.querySelector('.item-price') ? row.querySelector('.item-price').value : 0) || 0;
        var disc = parseFloat(row.querySelector('.item-disc') ? row.querySelector('.item-disc').value : 0) || 0;
        var account = row.querySelector('.item-account') ? row.querySelector('.item-account').value : '200 - Sales';
        var tax_rate = row.querySelector('.item-tax-rate') ? row.querySelector('.item-tax-rate').value : 'No Tax';
        if (name || desc || qty > 0 || price > 0) {
            line_items.push({ name: name, description: desc, qty: qty, price: price,
                              disc: disc, account: account, tax_rate: tax_rate });
        }
    });
    if (!line_items.length) { showToast('Add at least one line item', 'error'); return; }

    var frequency = prompt('How often? weekly, monthly, quarterly or yearly', 'monthly');
    if (!frequency) return;
    var firstIssue = prompt('First issue date (YYYY-MM-DD)',
        (document.getElementById('inv-issue-date') || {}).value ||
        localDate(new Date()));
    if (!firstIssue) return;

    function val(id) { var el = document.getElementById(id); return el ? el.value : ''; }
    try {
        var res = await fetch('/api/recurring-invoices', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                name: contact + ' · ' + frequency,
                contact: contact,
                email: val('inv-email'),
                phone_number: val('inv-phone'),
                reference: val('inv-ref'),
                line_items: line_items,
                tax_type: val('tax-type') || 'exclusive',
                currency: val('inv-currency') || (_appCurrency || 'GBP'),
                bank_details: val('inv-bank-account'),
                frequency: (frequency || 'monthly').trim().toLowerCase(),
                next_run: firstIssue.trim(),
                payment_terms_days: 14,
            }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not set that up'); return; }
        showToast('Recurring invoice set up. Next issue ' + data.next_run, 'success');
        await loadRecurring();
        showView('recurring-view');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.makeInvoiceRecurring = makeInvoiceRecurring;

async function stopRecurring(id) {
    if (!confirm('Stop this recurring invoice? Invoices already raised are kept.')) return;
    try {
        var res = await fetch('/api/recurring-invoices/' + id, {
            method: 'DELETE', credentials: 'same-origin',
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not stop it'); return; }
        showToast('Stopped', 'success');
        await loadRecurring();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.stopRecurring = stopRecurring;

// ==================== TEAM ====================
// A company used to be one shared login. These are the people who have their
// own, and what each of them is allowed to do.

var _team = { members: [], your_role: 'owner' };

async function loadTeam() {
    var tbody = document.getElementById('team-table-body');
    if (!tbody) return;
    try {
        var res = await fetch('/api/team', { credentials: 'same-origin' });
        if (!res.ok) return;
        _team = await res.json();
        renderTeam();
        applyRoleToUi();
    } catch (e) { console.error('Team load failed:', e); }
}
window.loadTeam = loadTeam;

function renderTeam() {
    var tbody = document.getElementById('team-table-body');
    if (!tbody) return;
    var isOwner = _team.your_role === 'owner';

    var inviteBtn = document.getElementById('team-invite-btn');
    if (inviteBtn) inviteBtn.style.display = isOwner ? '' : 'none';

    tbody.innerHTML = (_team.members || []).map(function (m) {
        var status = m.is_account_owner ? 'Account owner'
                   : (!m.is_active ? 'Disabled'
                   : (m.accepted ? 'Active' : 'Invited'));
        var statusClass = (!m.is_active && !m.is_account_owner) ? 'status-terminated'
                        : (m.accepted ? 'status-active' : 'status-onboarding');

        // Only the owner may change roles, and the owner's own row is fixed:
        // there is exactly one account owner.
        var roleCell = (isOwner && !m.is_account_owner)
            ? '<select class="form-control" style="min-width:100px;" onchange="setTeamRole(' + m.id + ', this.value)">' +
                  '<option value="admin"' + (m.role === 'admin' ? ' selected' : '') + '>Admin</option>' +
                  '<option value="viewer"' + (m.role === 'viewer' ? ' selected' : '') + '>Viewer</option>' +
              '</select>'
            : '<span class="status-pill status-draft">' + esc(m.role) + '</span>';

        var actions = (isOwner && !m.is_account_owner)
            ? '<button class="btn btn-outline btn-sm" onclick="toggleTeamMember(' + m.id + ',' + (!m.is_active) + ')">' +
                  (m.is_active ? 'Disable' : 'Enable') + '</button>' +
              '<button class="btn btn-outline btn-sm" style="color:var(--danger-color);border-color:var(--danger-color);margin-left:6px;" ' +
                  'onclick="removeTeamMember(' + m.id + ')">Remove</button>'
            : '';

        return '<tr>' +
            '<td><strong>' + esc(m.name || m.email) + '</strong>' +
                (m.name ? '<div style="font-size:0.8rem;color:var(--text-secondary);">' + esc(m.email) + '</div>' : '') +
            '</td>' +
            '<td>' + roleCell + '</td>' +
            '<td><span class="status-pill ' + statusClass + '">' + esc(status) + '</span></td>' +
            '<td>' + esc(m.last_login || 'Never') + '</td>' +
            '<td class="text-right">' + actions + '</td>' +
        '</tr>';
    }).join('');
}

// A read-only member should not be shown buttons that will only refuse them.
function applyRoleToUi() {
    if (_team.your_role !== 'viewer') return;
    var banner = document.getElementById('readonly-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'readonly-banner';
        banner.style.cssText = 'background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.35);' +
            'color:#f59e0b;padding:8px 14px;font-size:0.85rem;text-align:center;';
        banner.textContent = 'You have read-only access. You can look at everything but not change it.';
        document.body.insertBefore(banner, document.body.firstChild);
    }
}

async function inviteTeamMember() {
    var email = prompt('Their work email address');
    if (!email) return;
    var role = prompt('Role: admin or viewer', 'admin');
    if (!role) return;
    var name = prompt('Their name (optional)') || '';
    try {
        var res = await fetch('/api/team/invite', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ email: email.trim(), role: role.trim().toLowerCase(), name: name.trim() }),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not send that invite'); return; }
        showToast('Invited ' + data.email + '. They will get a link to set a password.', 'success');
        loadTeam();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.inviteTeamMember = inviteTeamMember;

async function setTeamRole(id, role) {
    await updateTeamMember(id, { role: role }, 'Role updated');
}
window.setTeamRole = setTeamRole;

async function toggleTeamMember(id, makeActive) {
    await updateTeamMember(id, { is_active: makeActive },
                           makeActive ? 'Access restored' : 'Access suspended');
}
window.toggleTeamMember = toggleTeamMember;

async function updateTeamMember(id, body, okMessage) {
    try {
        var res = await fetch('/api/team/' + id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify(body),
        });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not update them'); return; }
        showToast(okMessage, 'success');
        loadTeam();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}

async function removeTeamMember(id) {
    if (!confirm('Remove them from the team? They will not be able to sign in.')) return;
    try {
        var res = await fetch('/api/team/' + id, { method: 'DELETE', credentials: 'same-origin' });
        var data = await res.json().catch(function () { return {}; });
        if (!res.ok) { reportApiError(res, data, 'Could not remove them'); return; }
        showToast('Removed from the team', 'success');
        loadTeam();
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.removeTeamMember = removeTeamMember;

// ==================== CUSTOMER DETAIL ====================
// Contacts were a flat list. This is everything about one of them: what they
// were quoted, what they were billed, what they paid and what they still owe.

async function openCustomer(contactId) {
    try {
        var res = await fetch('/api/contacts/' + contactId + '/detail', { credentials: 'same-origin' });
        if (!res.ok) { showToast('Customer not found', 'error'); return; }
        renderCustomer(await res.json());
        showView('customer-view');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}
window.openCustomer = openCustomer;

function renderCustomer(d) {
    var c = d.contact || {}, s = d.summary || {};
    document.getElementById('cust-name').textContent = c.name || 'Customer';

    var sub = [c.email, c.phone_number].filter(Boolean).join(' · ');
    document.getElementById('cust-summary').innerHTML =
        statTile('Outstanding', moneyLines(s.outstanding, formatCurrency(0)), sub || 'owed now') +
        statTile('Billed all time', moneyLines(s.billed, formatCurrency(0)),
                 s.invoice_count + (s.invoice_count === 1 ? ' invoice' : ' invoices')) +
        statTile('Paid', moneyLines(s.paid, formatCurrency(0)), 'received') +
        statTile('Overdue', String(s.overdue_count || 0),
                 (s.overdue_count === 1 ? 'invoice' : 'invoices') + ' past due');

    var inv = document.getElementById('cust-invoices');
    inv.innerHTML = (d.invoices || []).length ? d.invoices.map(function (i) {
        return '<tr style="cursor:pointer;" onclick="viewInvoice(\'' + encodeURIComponent(i.number) + '\')">' +
            '<td><strong>' + esc(i.number) + '</strong></td>' +
            '<td>' + esc(i.date || '-') + '</td>' +
            '<td' + (i.is_overdue ? ' style="color:var(--danger-color);"' : '') + '>' +
                esc(i.due_date || '-') + (i.is_overdue ? ' (' + i.days_overdue + 'd late)' : '') + '</td>' +
            '<td class="text-right">' + formatCurrency(i.paid, i.currency) + '</td>' +
            '<td class="text-right"><strong>' + formatCurrency(i.due, i.currency) + '</strong></td>' +
            '<td><span class="status-pill ' + (i.status === 'Paid' ? 'status-active' : 'status-onboarding') + '">' +
                esc(i.status) + '</span></td></tr>';
    }).join('') : '<tr><td colspan="6" style="text-align:center;padding:28px;color:var(--text-secondary);">Nothing billed yet.</td></tr>';

    var qt = document.getElementById('cust-quotes');
    qt.innerHTML = (d.quotes || []).length ? d.quotes.map(function (q) {
        return '<tr style="cursor:pointer;" onclick="viewQuote(\'' + encodeURIComponent(q.number) + '\')">' +
            '<td><strong>' + esc(q.number) + '</strong></td>' +
            '<td>' + esc(q.title || '-') + '</td>' +
            '<td>' + esc(q.date || '-') + '</td>' +
            '<td>' + esc(q.expiry_date || '-') + '</td>' +
            '<td class="text-right"><strong>' + formatCurrency(q.total, q.currency) + '</strong></td>' +
            '<td><span class="status-pill ' + quoteStatusClass(q.status) + '">' + esc(q.status) + '</span></td></tr>';
    }).join('') : '<tr><td colspan="6" style="text-align:center;padding:28px;color:var(--text-secondary);">No quotes yet.</td></tr>';

    var pay = document.getElementById('cust-payments');
    pay.innerHTML = (d.payments || []).length ? d.payments.map(function (p) {
        return '<tr>' +
            '<td>' + esc(p.invoice_number) + '</td>' +
            '<td>' + esc(p.paid_on || '-') + '</td>' +
            '<td>' + esc((p.method || '').replace('_', ' ')) + '</td>' +
            '<td>' + esc(p.reference || '-') + '</td>' +
            '<td class="text-right"><strong>' + formatCurrency(p.amount) + '</strong></td></tr>';
    }).join('') : '<tr><td colspan="5" style="text-align:center;padding:28px;color:var(--text-secondary);">Nothing received yet.</td></tr>';
}
