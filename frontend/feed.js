/**
 * The company feed.
 *
 * One implementation, mounted on two pages. The staff portal and the HR app
 * show the same posts and differ only in what the viewer may do to them - and
 * the server says which, per post, so this file never has to know the rules.
 *
 * Styled with its own small set of rules rather than either page's, because
 * the portal is light and the HR app is dark and this has to read on both.
 * Everything leans on currentColor and translucent overlays for that reason.
 *
 *   Feed.mount(document.getElementById('feed'))
 */
(function () {
    'use strict';

    var PAGE = {};          // per-mount state, keyed by the element's id
    var IMAGE_MAX_BYTES = 2 * 1024 * 1024;
    var IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];

    function esc(s) {
        if (s === null || s === undefined) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function when(iso) {
        // "2026-09-12 14:03:00" -> "12 Sep, 14:03". Left alone if it does not
        // parse, which is better than "Invalid Date" under somebody's photo.
        if (!iso) return '';
        var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(iso);
        if (!m) return iso;
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return parseInt(m[3], 10) + ' ' + months[parseInt(m[2], 10) - 1] +
            ', ' + m[4] + ':' + m[5];
    }

    var CSS = [
        '.fd{font-size:14px;line-height:1.45;max-width:640px}',
        '.fd *{box-sizing:border-box}',
        '.fd-box{border:1px solid rgba(128,128,128,.28);border-radius:14px;padding:14px 16px;margin-bottom:14px;background:rgba(128,128,128,.04)}',
        '.fd-compose textarea{width:100%;min-height:70px;resize:vertical;border:1px solid rgba(128,128,128,.3);border-radius:10px;padding:10px 12px;font:inherit;color:inherit;background:rgba(128,128,128,.06)}',
        '.fd-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px}',
        '.fd-btn{font:inherit;font-size:13px;padding:6px 12px;border-radius:999px;border:1px solid rgba(128,128,128,.35);background:transparent;color:inherit;cursor:pointer}',
        '.fd-btn.on{background:rgba(56,189,248,.18);border-color:rgba(56,189,248,.6)}',
        '.fd-btn[disabled]{opacity:.5;cursor:default}',
        '.fd-primary{background:#0ea5e9;border-color:#0ea5e9;color:#fff;font-weight:600}',
        '.fd-quiet{border:0;opacity:.7;padding:4px 8px}',
        '.fd-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}',
        '.fd-who{font-weight:600}',
        '.fd-when{opacity:.6;font-size:12px}',
        '.fd-pin{font-size:11px;padding:1px 8px;border-radius:999px;background:rgba(251,191,36,.2);border:1px solid rgba(251,191,36,.5)}',
        '.fd-body{margin:8px 0 0;white-space:pre-wrap;word-wrap:break-word}',
        '.fd-img{display:block;max-width:100%;max-height:520px;border-radius:10px;margin-top:10px;object-fit:contain}',
        '.fd-preview{position:relative;display:inline-block;margin-top:8px}',
        '.fd-preview img{max-height:160px;border-radius:8px;display:block}',
        '.fd-preview button{position:absolute;top:4px;right:4px}',
        '.fd-comments{margin-top:10px;border-top:1px solid rgba(128,128,128,.2);padding-top:10px}',
        '.fd-comment{padding:6px 0;font-size:13px}',
        '.fd-comment .fd-who{font-size:13px}',
        '.fd-comments input{width:100%;font:inherit;font-size:13px;padding:7px 10px;border-radius:8px;border:1px solid rgba(128,128,128,.3);background:rgba(128,128,128,.06);color:inherit}',
        '.fd-empty{opacity:.65;text-align:center;padding:30px 0}',
        '.fd-err{color:#f43f5e;font-size:13px;margin-top:6px}',
        '.fd-note{opacity:.7;font-size:12px}',
    ].join('');

    function ensureStyle(doc) {
        if (doc.getElementById('fd-style')) return;
        var st = doc.createElement('style');
        st.id = 'fd-style';
        st.textContent = CSS;
        doc.head.appendChild(st);
    }

    function api(method, url, body) {
        var init = { method: method, headers: {} };
        if (body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
        }
        return fetch(url, init).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (data) {
                if (!res.ok) {
                    var e = new Error(data.detail || 'That did not go through.');
                    e.status = res.status;
                    throw e;
                }
                return data;
            });
        });
    }

    // ---- rendering ---------------------------------------------------------------

    function composer(state) {
        if (!state.canPost) {
            return '<div class="fd-box fd-note">Only HR can post here at the moment.</div>';
        }
        return '<div class="fd-box fd-compose">' +
            '<textarea id="' + state.id + '-text" placeholder="Share something with everyone" maxlength="2000"></textarea>' +
            '<div id="' + state.id + '-preview"></div>' +
            '<div class="fd-row">' +
                '<input type="file" id="' + state.id + '-file" accept="image/png,image/jpeg,image/gif,image/webp" style="display:none">' +
                '<button class="fd-btn" type="button" data-act="pick">Add a picture</button>' +
                (state.isHr ? '<label class="fd-note" style="display:flex;align-items:center;gap:6px;">' +
                    '<input type="checkbox" id="' + state.id + '-pin"> Pin to the top</label>' : '') +
                '<span style="flex:1"></span>' +
                '<button class="fd-btn fd-primary" type="button" data-act="post">Post</button>' +
            '</div>' +
            '<div class="fd-err" id="' + state.id + '-err" hidden></div>' +
        '</div>';
    }

    function postHtml(state, p) {
        return '<div class="fd-box fd-post" data-id="' + p.id + '">' +
            '<div class="fd-head">' +
                '<span class="fd-who">' + esc(p.author || (p.from_company ? 'The company' : 'Someone')) + '</span>' +
                '<span class="fd-when">' + esc(when(p.created_at)) + '</span>' +
                (p.pinned ? '<span class="fd-pin">Pinned</span>' : '') +
                '<span style="flex:1"></span>' +
                (p.can_pin ? '<button class="fd-btn fd-quiet" data-act="pin">' + (p.pinned ? 'Unpin' : 'Pin') + '</button>' : '') +
                (p.can_delete ? '<button class="fd-btn fd-quiet" data-act="delete">Delete</button>' : '') +
            '</div>' +
            (p.body ? '<p class="fd-body">' + esc(p.body) + '</p>' : '') +
            // The picture is fetched on its own rather than carried in the
            // list, so a page of photos is a page of small requests the
            // browser can cache, not one enormous one.
            (p.has_image ? '<img class="fd-img" src="/api/feed/' + p.id + '/image" alt="" loading="lazy">' : '') +
            '<div class="fd-row">' +
                '<button class="fd-btn' + (p.liked_by_me ? ' on' : '') + '" data-act="like">' +
                    (p.liked_by_me ? '♥' : '♡') + ' <span class="fd-likes">' + (p.likes || 0) + '</span></button>' +
                '<button class="fd-btn" data-act="comments">\u{1F4AC} <span class="fd-ccount">' + (p.comments || 0) + '</span></button>' +
            '</div>' +
            '<div class="fd-comments" hidden></div>' +
        '</div>';
    }

    function commentHtml(c) {
        return '<div class="fd-comment" data-cid="' + c.id + '">' +
            '<span class="fd-who">' + esc(c.author || 'Someone') + '</span> ' +
            '<span class="fd-when">' + esc(when(c.created_at)) + '</span>' +
            (c.can_delete ? ' <button class="fd-btn fd-quiet" data-act="delete-comment" style="font-size:11px">Delete</button>' : '') +
            '<div>' + esc(c.body) + '</div>' +
        '</div>';
    }

    function render(state) {
        var host = state.el;
        var posts = state.posts.map(function (p) { return postHtml(state, p); }).join('');
        host.innerHTML = '<div class="fd">' +
            composer(state) +
            (state.posts.length ? posts : '<div class="fd-empty">Nothing here yet.</div>') +
            (state.nextBefore ? '<div style="text-align:center"><button class="fd-btn" data-act="more">Show older posts</button></div>' : '') +
        '</div>';
    }

    // ---- actions ------------------------------------------------------------------

    function load(state, before) {
        var url = '/api/feed' + (before ? '?before=' + before : '');
        return api('GET', url).then(function (data) {
            if (before) state.posts = state.posts.concat(data.posts || []);
            else state.posts = data.posts || [];
            state.nextBefore = data.next_before || 0;
            state.canPost = !!data.can_post;
            state.isHr = !!data.is_hr;
            render(state);
        }).catch(function (e) {
            state.el.innerHTML = '<div class="fd"><div class="fd-empty">Could not load the feed. ' + esc(e.message) + '</div></div>';
        });
    }

    function showErr(state, msg) {
        var box = state.el.querySelector('#' + state.id + '-err');
        if (!box) { if (msg) alert(msg); return; }
        box.textContent = msg || '';
        box.hidden = !msg;
    }

    function pickImage(state) {
        var input = state.el.querySelector('#' + state.id + '-file');
        if (input) input.click();
    }

    function imageChosen(state, file) {
        showErr(state, '');
        if (!file) return;
        // Checked here so the person hears about it now, and checked again on
        // the server so it is actually enforced.
        if (IMAGE_TYPES.indexOf(file.type) === -1) {
            showErr(state, 'That is not a picture the feed can show - use PNG, JPEG, GIF or WebP.');
            return;
        }
        if (file.size > IMAGE_MAX_BYTES) {
            showErr(state, 'That picture is too large - keep it under 2MB.');
            return;
        }
        var reader = new FileReader();
        reader.onload = function () {
            state.pendingImage = String(reader.result || '');
            var pv = state.el.querySelector('#' + state.id + '-preview');
            if (pv) {
                pv.innerHTML = '<div class="fd-preview"><img src="' + state.pendingImage + '" alt="">' +
                    '<button class="fd-btn fd-quiet" data-act="unpick" type="button">×</button></div>';
            }
        };
        reader.readAsDataURL(file);
    }

    function unpickImage(state) {
        state.pendingImage = '';
        var pv = state.el.querySelector('#' + state.id + '-preview');
        if (pv) pv.innerHTML = '';
        var input = state.el.querySelector('#' + state.id + '-file');
        if (input) input.value = '';
    }

    function submit(state) {
        var ta = state.el.querySelector('#' + state.id + '-text');
        var text = ta ? ta.value.trim() : '';
        if (!text && !state.pendingImage) {
            showErr(state, 'Say something, or add a picture.');
            return Promise.resolve();
        }
        var pin = state.el.querySelector('#' + state.id + '-pin');
        var btn = state.el.querySelector('[data-act="post"]');
        if (btn) btn.disabled = true;
        return api('POST', '/api/feed', {
            body: text, image_data: state.pendingImage || '',
            pinned: !!(pin && pin.checked),
        }).then(function () {
            state.pendingImage = '';
            return load(state, 0);
        }).catch(function (e) {
            showErr(state, e.message);
            if (btn) btn.disabled = false;
        });
    }

    function like(state, postEl) {
        var id = postEl.getAttribute('data-id');
        return api('POST', '/api/feed/' + id + '/like').then(function (r) {
            var btn = postEl.querySelector('[data-act="like"]');
            btn.className = 'fd-btn' + (r.liked_by_me ? ' on' : '');
            btn.innerHTML = (r.liked_by_me ? '♥' : '♡') +
                ' <span class="fd-likes">' + r.likes + '</span>';
            var p = state.posts.filter(function (x) { return String(x.id) === id; })[0];
            if (p) { p.likes = r.likes; p.liked_by_me = r.liked_by_me; }
        }).catch(function (e) { alert(e.message); });
    }

    function toggleComments(state, postEl) {
        var box = postEl.querySelector('.fd-comments');
        if (!box.hidden) { box.hidden = true; return Promise.resolve(); }
        var id = postEl.getAttribute('data-id');
        return api('GET', '/api/feed/' + id + '/comments').then(function (rows) {
            box.innerHTML = rows.map(commentHtml).join('') +
                '<div class="fd-row"><input placeholder="Write a comment" maxlength="1000" data-role="comment-text">' +
                '<button class="fd-btn" data-act="comment">Send</button></div>';
            box.hidden = false;
        }).catch(function (e) { alert(e.message); });
    }

    function comment(state, postEl) {
        var id = postEl.getAttribute('data-id');
        var input = postEl.querySelector('[data-role="comment-text"]');
        var text = input ? input.value.trim() : '';
        if (!text) return Promise.resolve();
        return api('POST', '/api/feed/' + id + '/comments', { body: text }).then(function (c) {
            var box = postEl.querySelector('.fd-comments');
            var row = box.querySelector('.fd-row');
            row.insertAdjacentHTML('beforebegin', commentHtml(c));
            input.value = '';
            var count = postEl.querySelector('.fd-ccount');
            if (count) count.textContent = String((parseInt(count.textContent, 10) || 0) + 1);
        }).catch(function (e) { alert(e.message); });
    }

    function deleteComment(state, postEl, commentEl) {
        var id = postEl.getAttribute('data-id');
        var cid = commentEl.getAttribute('data-cid');
        return api('DELETE', '/api/feed/' + id + '/comments/' + cid).then(function () {
            commentEl.remove();
            var count = postEl.querySelector('.fd-ccount');
            if (count) count.textContent = String(Math.max(0, (parseInt(count.textContent, 10) || 1) - 1));
        }).catch(function (e) { alert(e.message); });
    }

    function remove(state, postEl) {
        if (!confirm('Delete this post? Its likes and comments go with it.')) return Promise.resolve();
        var id = postEl.getAttribute('data-id');
        return api('DELETE', '/api/feed/' + id).then(function () {
            state.posts = state.posts.filter(function (x) { return String(x.id) !== id; });
            render(state);
        }).catch(function (e) { alert(e.message); });
    }

    function pin(state, postEl) {
        var id = postEl.getAttribute('data-id');
        // Reloaded rather than patched, because pinning moves the post to the
        // top and the order is the server's to decide.
        return api('POST', '/api/feed/' + id + '/pin').then(function () {
            return load(state, 0);
        }).catch(function (e) { alert(e.message); });
    }

    // ---- wiring ---------------------------------------------------------------------

    function onClick(state, ev) {
        var t = ev.target.closest ? ev.target.closest('[data-act]') : null;
        if (!t || !state.el.contains(t)) return;
        var act = t.getAttribute('data-act');
        var postEl = t.closest('.fd-post');
        ev.preventDefault();
        if (act === 'pick') return pickImage(state);
        if (act === 'unpick') return unpickImage(state);
        if (act === 'post') return submit(state);
        if (act === 'more') return load(state, state.nextBefore);
        if (!postEl) return;
        if (act === 'like') return like(state, postEl);
        if (act === 'comments') return toggleComments(state, postEl);
        if (act === 'comment') return comment(state, postEl);
        if (act === 'delete') return remove(state, postEl);
        if (act === 'pin') return pin(state, postEl);
        if (act === 'delete-comment') return deleteComment(state, postEl, t.closest('.fd-comment'));
    }

    function mount(el) {
        if (!el) return null;
        var doc = el.ownerDocument;
        ensureStyle(doc);
        var id = el.id || ('fd-' + Math.random().toString(36).slice(2, 8));
        el.id = id;
        var state = PAGE[id] = {
            id: id, el: el, posts: [], nextBefore: 0,
            canPost: false, isHr: false, pendingImage: '',
        };
        el.addEventListener('click', function (ev) { onClick(state, ev); });
        el.addEventListener('change', function (ev) {
            if (ev.target && ev.target.id === id + '-file') {
                imageChosen(state, ev.target.files && ev.target.files[0]);
            }
        });
        el.addEventListener('keydown', function (ev) {
            // Enter sends a comment; the composer keeps Enter for new lines.
            if (ev.key === 'Enter' && ev.target && ev.target.getAttribute('data-role') === 'comment-text') {
                ev.preventDefault();
                comment(state, ev.target.closest('.fd-post'));
            }
        });
        el.innerHTML = '<div class="fd"><div class="fd-empty">Loading…</div></div>';
        state.ready = load(state, 0);
        return state;
    }

    window.Feed = {
        mount: mount,
        reload: function (el) { var s = PAGE[el.id]; return s ? load(s, 0) : Promise.resolve(); },
        _state: function (el) { return PAGE[el.id]; },
    };
})();
