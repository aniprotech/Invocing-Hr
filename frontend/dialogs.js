/**
 * alert(), confirm() and prompt(), replaced.
 *
 * The native ones freeze the tab, cannot be styled, and on a phone put the
 * page's origin above the message - so the last thing somebody reads before
 * deleting an invoice is a URL. They are also the only part of the product
 * that looks like nothing else in it.
 *
 * Loaded by every page that needs to ask a question, because only one of them
 * loads app.js. The styles travel with it for the same reason: two of those
 * pages are Tailwind and load neither stylesheet.
 *
 * These return promises, so a caller awaits the answer where it used to read
 * it off the return value.
 */
(function () {
    if (window.uiConfirm) return;   // already loaded

    var STYLE_ID = 'ui-dialog-styles';
    if (!document.getElementById(STYLE_ID)) {
        var tag = document.createElement('style');
        tag.id = STYLE_ID;
        tag.textContent = `/* --- Dialogs -------------------------------------------------------------
   Replacing alert(), confirm() and prompt(). The native ones freeze the tab,
   cannot be styled, and put the page's origin above the message on a phone -
   so the last thing somebody reads before deleting an invoice is a URL. */

.ui-dialog-scrim {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.62);
    backdrop-filter: blur(3px);
    display: flex;
    align-items: center;
    justify-content: center;
    /* Above every other layer, because it is answering a question that blocks
       whatever is underneath. */
    z-index: var(--layer-modal, 9000);
    padding: 20px;
    opacity: 0;
    transition: opacity 0.16s ease;
}
.ui-dialog-scrim.is-open { opacity: 1; }

.ui-dialog {
    background: var(--bg-card, #0f172a);
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
    border-radius: 16px;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
    transform: translateY(8px) scale(0.98);
    transition: transform 0.16s ease;
    overflow: hidden;
    /* Never taller than the screen. A long form - Add certification, with
       seven fields - was centred and cut off at both ends on a laptop, its
       title above the top and Save below the bottom, with nothing to scroll.
       Now the questions scroll inside it and the buttons stay in sight. */
    max-height: calc(100vh - 40px);
    max-height: calc(100dvh - 40px);
    display: flex;
    flex-direction: column;
}
.ui-dialog-scrim.is-open .ui-dialog { transform: none; }

.ui-dialog-body { padding: 24px 24px 8px; display: flex; gap: 14px; overflow-y: auto; min-height: 0; flex: 1 1 auto; }

.ui-dialog-icon {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.05rem;
    line-height: 1;
}
.ui-dialog-icon.is-ask    { background: rgba(14, 165, 233, 0.12);  color: var(--primary, #0ea5e9); }
.ui-dialog-icon.is-warn   { background: rgba(251, 191, 36, 0.14); color: var(--warning-color, #fbbf24); }
.ui-dialog-icon.is-danger { background: rgba(225, 29, 72, 0.12);   color: var(--danger-color, #e11d48); }

.ui-dialog-title {
    font-size: 1rem;
    font-weight: 650;
    color: var(--text-primary, #f8fafc);
    margin: 2px 0 4px;
}
.ui-dialog-message {
    font-size: 0.875rem;
    line-height: 1.5;
    color: var(--text-secondary, #94a3b8);
    /* A message built from a record's own name can be long and can contain
       newlines; neither should break the box. */
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

.ui-dialog-input {
    width: 100%;
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.12));
    background: var(--bg-input, rgba(255, 255, 255, 0.04));
    color: var(--text-primary, #f8fafc);
    font-size: 0.875rem;
    font-family: inherit;
}
.ui-dialog-input:focus {
    outline: none;
    border-color: var(--primary, #0ea5e9);
}

.ui-dialog-actions {
    flex: 0 0 auto;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 16px 24px 20px;
    flex-wrap: wrap;
}
.ui-dialog-btn {
    padding: 9px 18px;
    border-radius: 9px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
    font-family: inherit;
    min-height: 40px;
}
.ui-dialog-btn.is-cancel {
    background: transparent;
    border-color: var(--border-color, rgba(255, 255, 255, 0.14));
    color: var(--text-secondary, #94a3b8);
}
.ui-dialog-btn.is-cancel:hover { color: var(--text-primary, #f8fafc); }
.ui-dialog-btn.is-go {
    background: var(--primary, #0ea5e9);
    color: #ffffff;
}
/* Destructive actions are not the same colour as ordinary ones, so the button
   that cannot be undone never looks like the one that can. */
.ui-dialog-btn.is-go.is-danger {
    background: var(--danger-color, #e11d48);
    color: #fff;
}
.ui-dialog-btn:disabled { opacity: 0.6; cursor: default; }

@media (max-width: 520px) {
    .ui-dialog-actions { flex-direction: column-reverse; }
    .ui-dialog-btn { width: 100%; }
}

/* On a light page. The variables above fall back to a dark palette, which
   is right for the HR app and wrong for the staff portal - a dark card on a
   white page reads as something having broken. Decided from the page's own
   background when the dialog opens, not from which page it is. */
.ui-dialog-scrim.is-light .ui-dialog {
    background: #ffffff;
    border-color: rgba(15, 23, 42, 0.08);
    box-shadow: 0 24px 60px rgba(15, 23, 42, 0.18);
}
.ui-dialog-scrim.is-light .ui-dialog-title { color: #0f172a; }
.ui-dialog-scrim.is-light .ui-dialog-message { color: #475569; }
.ui-dialog-scrim.is-light .ui-dialog-input,
.ui-dialog-scrim.is-light .ui-dialog-field select,
.ui-dialog-scrim.is-light .ui-dialog-field textarea {
    background: #f8fafc; color: #0f172a; border-color: rgba(15, 23, 42, 0.14);
}
.ui-dialog-scrim.is-light .ui-dialog-btn.is-cancel { color: #475569; border-color: rgba(15, 23, 42, 0.14); }
.ui-dialog-scrim.is-light .ui-dialog-btn.is-cancel:hover { color: #0f172a; }
.ui-dialog-scrim.is-light .ui-dialog-field label { color: #64748b; }

/* Several things asked at once, each with a name. A form, not a chain of
   prompts where the third question has forgotten the first answer. */
.ui-dialog-field { margin-top: 12px; }
.ui-dialog-field label {
    display: block; font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.4px; color: var(--text-secondary, #94a3b8); margin-bottom: 5px;
}
.ui-dialog-field select, .ui-dialog-field textarea, .ui-dialog-field .ui-dialog-input {
    width: 100%; box-sizing: border-box; font: inherit; font-size: 0.92rem;
    padding: 9px 11px; border-radius: 10px;
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.14));
    background: var(--bg-input, rgba(255, 255, 255, 0.04));
    color: var(--text-primary, #f8fafc); margin: 0;
}
.ui-dialog-field textarea { min-height: 72px; resize: vertical; }
.ui-dialog-field select:focus, .ui-dialog-field textarea:focus, .ui-dialog-field .ui-dialog-input:focus {
    outline: none; border-color: var(--primary, #0ea5e9);
}
.ui-dialog-field .ui-dialog-hint { font-size: 0.76rem; color: var(--text-secondary, #94a3b8); margin-top: 4px; }
.ui-dialog-error { color: var(--danger-color, #e11d48); font-size: 0.82rem; margin-top: 10px; display: none; }
.ui-dialog-error.is-shown { display: block; }

/* Something happened and nothing needs deciding. Said at the bottom and
   gone in a few seconds, rather than a box that has to be dismissed. */
.ui-toast-host {
    position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%);
    display: flex; flex-direction: column; gap: 8px; align-items: center;
    z-index: var(--layer-toast, 9500); pointer-events: none; width: min(92vw, 440px);
}
.ui-toast {
    pointer-events: auto; width: 100%; box-sizing: border-box;
    padding: 11px 16px; border-radius: 12px; font-size: 0.88rem; line-height: 1.4;
    background: #0f172a; color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
    display: flex; gap: 10px; align-items: flex-start;
    opacity: 0; transform: translateY(8px); transition: opacity 0.16s ease, transform 0.16s ease;
}
.ui-toast.is-open { opacity: 1; transform: none; }
.ui-toast::before { content: ''; flex: none; width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; background: #38bdf8; }
.ui-toast.is-success::before { background: #34d399; }
.ui-toast.is-error::before { background: #f43f5e; }
.ui-toast.is-light { background: #ffffff; color: #0f172a; border-color: rgba(15, 23, 42, 0.1); box-shadow: 0 12px 32px rgba(15, 23, 42, 0.16); }
`;
        // Normally the head; documentElement covers a script that runs before
        // one exists, which is a crash rather than a missing stylesheet.
        (document.head || document.documentElement).appendChild(tag);
    }

    // Every page has its own escaper, or none. This one belongs to the dialog.
    function esc(v) {
        if (v === null || v === undefined) return '';
        return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // --- Dialogs ---------------------------------------------------------------
    // Replacing the browser's alert(), confirm() and prompt().
    //
    // The native ones freeze the tab, cannot be styled, and on a phone put the
    // page's origin above the message - so the last thing somebody reads before
    // deleting an invoice is a URL. They are also the only part of the product
    // that looks like nothing else in it.
    //
    // These return promises, so a caller awaits the answer where it used to read
    // it off the return value.

    function _uiDialogClose(scrim, resolve, value) {
        scrim.classList.remove('is-open');
        // Let the fade finish before the node goes, or it vanishes mid-animation.
        setTimeout(function () {
            if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        }, 160);
        document.removeEventListener('keydown', scrim._onKey, true);
        if (scrim._lastFocus && scrim._lastFocus.focus) {
            // Back to whatever opened it, so the keyboard does not start again
            // from the top of the page.
            try { scrim._lastFocus.focus(); } catch (e) { }
        }
        resolve(value);
    }

    // Whether the page behind is light. Read from the body's own background
    // rather than guessed from which page this is, so a page that changes its
    // theme - or a new page nobody thought to list - gets the right palette.
    function _pageIsLight() {
        try {
            var bg = getComputedStyle(document.body).backgroundColor || '';
            var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(bg);
            if (!m) return false;
            if (m[4] !== undefined && parseFloat(m[4]) === 0) {
                // Transparent body: look at the root instead.
                bg = getComputedStyle(document.documentElement).backgroundColor || '';
                m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(bg);
                if (!m) return false;
            }
            var lum = (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
            return lum > 0.6;
        } catch (e) { return false; }
    }

    function _fieldHtml(f, i) {
        var id = 'ui-dialog-f' + i;
        var attrs = ' id="' + id + '" name="' + esc(f.name) + '"' +
            (f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : '') +
            (f.required ? ' data-required="1"' : '');
        var control;
        if (f.type === 'select') {
            control = '<select' + attrs + '>' +
                (f.placeholder ? '<option value="">' + esc(f.placeholder) + '</option>' : '') +
                (f.options || []).map(function (o) {
                    var v = (o && typeof o === 'object') ? o.value : o;
                    var l = (o && typeof o === 'object') ? o.label : o;
                    return '<option value="' + esc(v) + '"' +
                        (String(f.value) === String(v) ? ' selected' : '') + '>' + esc(l) + '</option>';
                }).join('') + '</select>';
        } else if (f.type === 'textarea') {
            control = '<textarea' + attrs + '>' + esc(f.value == null ? '' : f.value) + '</textarea>';
        } else {
            control = '<input class="ui-dialog-input" type="' + esc(f.type || 'text') + '"' + attrs +
                (f.min != null ? ' min="' + esc(f.min) + '"' : '') +
                (f.step != null ? ' step="' + esc(f.step) + '"' : '') +
                ' value="' + esc(f.value == null ? '' : f.value) + '">';
        }
        return '<div class="ui-dialog-field">' +
            (f.label ? '<label for="' + id + '">' + esc(f.label) + '</label>' : '') +
            control +
            (f.hint ? '<div class="ui-dialog-hint">' + esc(f.hint) + '</div>' : '') +
        '</div>';
    }

    function _uiDialog(opts) {
        return new Promise(function (resolve) {
            var scrim = document.createElement('div');
            scrim.className = 'ui-dialog-scrim' + (_pageIsLight() ? ' is-light' : '');
            scrim._lastFocus = document.activeElement;

            // A prompt is a form with one unlabelled field. A chooser is a form
            // with one select. Everything with fields goes through one path.
            var fields = opts.fields || null;
            if (opts.kind === 'prompt') {
                fields = [{ name: 'value', type: 'text', value: opts.value }];
            } else if (opts.kind === 'choose') {
                fields = [{ name: 'value', type: 'select', options: opts.options,
                            value: opts.value, placeholder: opts.placeholder, required: true }];
            }
            var wantsInput = !!fields;
            var danger = !!opts.danger;
            var tone = danger ? 'is-danger' : (opts.kind === 'alert' ? 'is-warn' : 'is-ask');
            var glyph = danger ? '!' : (opts.kind === 'alert' ? 'i' : '?');

            scrim.innerHTML =
                '<div class="ui-dialog" role="' + (opts.kind === 'alert' ? 'alertdialog' : 'dialog') + '" ' +
                     'aria-modal="true" aria-labelledby="ui-dialog-title">' +
                    '<div class="ui-dialog-body">' +
                        '<div class="ui-dialog-icon ' + tone + '" aria-hidden="true">' + glyph + '</div>' +
                        '<div style="flex:1;min-width:0;">' +
                            '<div class="ui-dialog-title" id="ui-dialog-title">' +
                                esc(opts.title || (opts.kind === 'alert' ? 'Just so you know' : 'Are you sure?')) +
                            '</div>' +
                            (opts.message ? '<div class="ui-dialog-message">' + esc(opts.message) + '</div>' : '') +
                            (wantsInput ? fields.map(_fieldHtml).join('') : '') +
                            '<div class="ui-dialog-error" id="ui-dialog-error"></div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="ui-dialog-actions">' +
                        (opts.kind === 'alert' ? ''
                            : '<button type="button" class="ui-dialog-btn is-cancel">' +
                              esc(opts.cancelText || 'Cancel') + '</button>') +
                        '<button type="button" class="ui-dialog-btn is-go' + (danger ? ' is-danger' : '') + '">' +
                            esc(opts.confirmText || (opts.kind === 'alert' ? 'OK' : 'Confirm')) +
                        '</button>' +
                    '</div>' +
                '</div>';

            document.body.appendChild(scrim);
            // A frame before the class goes on, or the transition has nothing to
            // animate from.
            requestAnimationFrame(function () { scrim.classList.add('is-open'); });

            var controls = wantsInput
                ? fields.map(function (f, i) { return scrim.querySelector('#ui-dialog-f' + i); })
                : [];
            var input = controls[0] || null;
            var errBox = scrim.querySelector('#ui-dialog-error');

            function read() {
                var out = {};
                fields.forEach(function (f, i) { out[f.name] = controls[i] ? controls[i].value : ''; });
                return out;
            }

            var cancelled = opts.kind === 'alert' ? true : (wantsInput ? null : false);
            function settle(ok) {
                if (!ok) return _uiDialogClose(scrim, resolve, cancelled);
                if (!wantsInput) return _uiDialogClose(scrim, resolve, true);
                // A required field left empty is said in the dialog, not by a
                // second dialog on top of the first.
                var missing = fields.filter(function (f, i) {
                    return f.required && !String(controls[i] ? controls[i].value : '').trim();
                });
                if (missing.length) {
                    errBox.textContent = (missing[0].label || 'That') + ' is needed.';
                    errBox.classList.add('is-shown');
                    var idx = fields.indexOf(missing[0]);
                    if (controls[idx]) controls[idx].focus();
                    return;
                }
                if (opts.kind === 'form') return _uiDialogClose(scrim, resolve, read());
                _uiDialogClose(scrim, resolve, read().value);
            }

            var goBtn = scrim.querySelector('.ui-dialog-btn.is-go');
            var cancelBtn = scrim.querySelector('.ui-dialog-btn.is-cancel');
            goBtn.addEventListener('click', function () { settle(true); });
            if (cancelBtn) cancelBtn.addEventListener('click', function () { settle(false); });

            // Clicking the scrim is a cancel; clicking the dialog is not.
            scrim.addEventListener('click', function (e) {
                if (e.target === scrim) settle(false);
            });

            scrim._onKey = function (e) {
                if (e.key === 'Escape') { e.stopPropagation(); settle(false); return; }
                // Enter sends a one-line answer; in a textarea it is a new line.
                if (e.key === 'Enter' && (opts.kind === 'alert' ||
                        (wantsInput && !(e.target && e.target.tagName === 'TEXTAREA')))) {
                    e.preventDefault(); settle(true); return;
                }
                if (e.key !== 'Tab') return;
                // Keep the keyboard inside the dialog: it is answering a question
                // that blocks the page behind it.
                var focusable = scrim.querySelectorAll('button, input, select, textarea');
                if (!focusable.length) return;
                var first = focusable[0], last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault(); last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault(); first.focus();
                }
            };
            document.addEventListener('keydown', scrim._onKey, true);

            (input || goBtn).focus();
            if (input && input.select && input.tagName === 'INPUT') input.select();
        });
    }

    // Something happened and there is nothing to decide.
    function uiAlert(message, opts) {
        opts = opts || {};
        return _uiDialog({ kind: 'alert', message: message, title: opts.title,
                           confirmText: opts.confirmText, danger: opts.danger });
    }
    window.uiAlert = uiAlert;

    // Yes or no. Resolves false on Escape, on the scrim, and on Cancel, so a
    // caller that only acts on true is safe by default.
    function uiConfirm(message, opts) {
        opts = opts || {};
        return _uiDialog({ kind: 'confirm', message: message, title: opts.title,
                           confirmText: opts.confirmText, cancelText: opts.cancelText,
                           danger: opts.danger });
    }
    window.uiConfirm = uiConfirm;

    // A line of text, or null if they backed out - the same shape prompt() had, so
    // call sites keep their `|| ''` and their null checks.
    function uiPrompt(message, value, opts) {
        opts = opts || {};
        return _uiDialog({ kind: 'prompt', message: message, value: value,
                           title: opts.title, confirmText: opts.confirmText || 'Save',
                           cancelText: opts.cancelText });
    }
    window.uiPrompt = uiPrompt;

    // One thing from a list. Replaces the prompt that showed a numbered list
    // and asked for the number - a text box being used as a picker.
    //   options: ['good', 'fair'] or [{ value: 7, label: 'Dana Boss' }]
    // Resolves to the chosen value, or null if they backed out.
    function uiChoose(message, options, opts) {
        opts = opts || {};
        return _uiDialog({ kind: 'choose', message: message, options: options,
                           value: opts.value, placeholder: opts.placeholder,
                           title: opts.title, confirmText: opts.confirmText || 'Choose',
                           cancelText: opts.cancelText });
    }
    window.uiChoose = uiChoose;

    // Several things at once, each labelled. Replaces a chain of prompts
    // where the third question had forgotten the first answer and nothing
    // could be corrected without starting again.
    //   fields: [{ name, label, type: 'text'|'date'|'number'|'select'|'textarea',
    //              value, placeholder, options, required, hint }]
    // Resolves to { name: value, ... }, or null if they backed out.
    function uiForm(fields, opts) {
        opts = opts || {};
        return _uiDialog({ kind: 'form', fields: fields, message: opts.message,
                           title: opts.title, confirmText: opts.confirmText || 'Save',
                           cancelText: opts.cancelText, danger: opts.danger });
    }
    window.uiForm = uiForm;

    // Something happened and nothing needs deciding. A line at the bottom
    // that goes away on its own, for pages that have no toast of their own.
    // Pages with one already (the HR app's showToast) keep theirs.
    function uiToast(message, kind, ms) {
        var host = document.getElementById('ui-toast-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'ui-toast-host';
            host.className = 'ui-toast-host';
            host.setAttribute('aria-live', 'polite');
            (document.body || document.documentElement).appendChild(host);
        }
        var el = document.createElement('div');
        el.className = 'ui-toast is-' + (kind || 'info') + (_pageIsLight() ? ' is-light' : '');
        el.textContent = String(message == null ? '' : message);
        host.appendChild(el);
        requestAnimationFrame(function () { el.classList.add('is-open'); });
        var life = ms || (kind === 'error' ? 5000 : 3000);
        setTimeout(function () {
            el.classList.remove('is-open');
            setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 200);
        }, life);
        return el;
    }
    window.uiToast = uiToast;

    window.uiAlert = uiAlert;
    window.uiConfirm = uiConfirm;
    window.uiPrompt = uiPrompt;
})();
