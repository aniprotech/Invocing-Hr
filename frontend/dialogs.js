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
}
.ui-dialog-scrim.is-open .ui-dialog { transform: none; }

.ui-dialog-body { padding: 24px 24px 8px; display: flex; gap: 14px; }

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

    function _uiDialog(opts) {
        return new Promise(function (resolve) {
            var scrim = document.createElement('div');
            scrim.className = 'ui-dialog-scrim';
            scrim._lastFocus = document.activeElement;

            var wantsInput = opts.kind === 'prompt';
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
                            '<div class="ui-dialog-message">' + esc(opts.message || '') + '</div>' +
                            (wantsInput
                                ? '<input class="ui-dialog-input" id="ui-dialog-input" type="text">'
                                : '') +
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

            var input = scrim.querySelector('#ui-dialog-input');
            if (input) input.value = opts.value == null ? '' : String(opts.value);

            var cancelled = opts.kind === 'alert' ? true : (wantsInput ? null : false);
            function settle(ok) {
                if (!ok) return _uiDialogClose(scrim, resolve, cancelled);
                if (wantsInput) return _uiDialogClose(scrim, resolve, input.value);
                _uiDialogClose(scrim, resolve, true);
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
                if (e.key === 'Enter' && (wantsInput || opts.kind === 'alert')) {
                    e.preventDefault(); settle(true); return;
                }
                if (e.key !== 'Tab') return;
                // Keep the keyboard inside the dialog: it is answering a question
                // that blocks the page behind it.
                var focusable = scrim.querySelectorAll('button, input');
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
            if (input) input.select();
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

    window.uiAlert = uiAlert;
    window.uiConfirm = uiConfirm;
    window.uiPrompt = uiPrompt;
})();
