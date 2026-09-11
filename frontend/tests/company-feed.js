/**
 * The company feed, as rendered.
 *
 * One file, mounted on two pages. What the viewer may do to each post comes
 * from the server per post, so this never has to know the rules - and the
 * checks here are that it obeys what it is told rather than that it knows
 * anything.
 *
 * The one thing it has to know on its own is that every string in a post was
 * typed by somebody else. A feed is the one place in the product where staff
 * write text that other staff's browsers then render, so the escaping is not
 * a detail.
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

const POSTS = [
    { id: 12, author: 'Sam Staff', author_employee_id: 2, from_company: false,
      body: 'Great day at the summer party!', has_image: true, pinned: false,
      created_at: '2026-09-11 15:20:00', likes: 3, liked_by_me: false, comments: 2,
      can_delete: true, can_pin: false },
    { id: 11, author: 'Acme Ltd', author_employee_id: null, from_company: true,
      body: 'Office closed Monday', has_image: false, pinned: true,
      created_at: '2026-09-10 09:00:00', likes: 0, liked_by_me: false, comments: 0,
      can_delete: false, can_pin: false },
    { id: 10, author: 'Lee <b>Evil</b>', author_employee_id: 3, from_company: false,
      body: '<img src=x onerror=alert(1)> <script>alert(2)</script>', has_image: false,
      pinned: false, created_at: '2026-09-09 12:00:00', likes: 1, liked_by_me: true,
      comments: 0, can_delete: false, can_pin: false },
];

function boot(opts) {
    opts = opts || {};
    const dom = new JSDOM('<div id="feed"></div>', {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/employee-dashboard.html',
    });
    const w = dom.window;
    const sent = [];
    const alerts = [];
    w.console.error = () => { };
    w.alert = m => alerts.push(String(m));
    w.confirm = () => opts.confirm !== false;
    w.fetch = (url, init) => {
        const p = String(url).split('?')[0];
        const q = String(url).split('?')[1] || '';
        const method = (init && init.method) || 'GET';
        sent.push({ url: p, q, method, body: init && init.body });
        const give = (b, status) => Promise.resolve({
            ok: !status || status < 400, status: status || 200,
            json: () => Promise.resolve(b) });
        if (p === '/api/feed' && method === 'GET') {
            if (q.indexOf('before=') !== -1) {
                return give({ posts: [{ id: 3, author: 'Old', body: 'Older post', has_image: false,
                    created_at: '2026-01-01 10:00:00', likes: 0, liked_by_me: false,
                    comments: 0, can_delete: false, can_pin: false }],
                    next_before: 0, can_post: true, is_hr: false });
            }
            return give({ posts: opts.posts || POSTS, next_before: opts.more ? 10 : 0,
                          can_post: opts.canPost !== false, is_hr: !!opts.isHr });
        }
        if (p === '/api/feed' && method === 'POST') {
            if (opts.postFails) return give({ detail: 'Only HR can post here at the moment' }, 403);
            return give({ id: 99 });
        }
        if (/\/like$/.test(p)) return give({ id: 12, liked_by_me: true, likes: 4 });
        if (/\/comments$/.test(p) && method === 'GET') {
            return give([{ id: 1, author: 'Ada', body: 'Lovely <b>x</b>', created_at: '2026-09-11 16:00:00', can_delete: false }]);
        }
        if (/\/comments$/.test(p) && method === 'POST') {
            return give({ id: 2, author: 'Me', body: JSON.parse(init.body).body, created_at: '2026-09-12 10:00:00', can_delete: true });
        }
        if (/\/pin$/.test(p)) return give({ id: 11, pinned: false });
        if (method === 'DELETE') return give({ deleted: 12 });
        return give({});
    };
    w.eval(fs.readFileSync(path.join(ROOT, 'feed.js'), 'utf8'));
    return { w, doc: w.document, sent, alerts };
}

const bodyOf = e => { try { return JSON.parse(e.body); } catch (x) { return {}; } };

(async () => {
    // --- it loads and draws --------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        const state = w.Feed.mount(doc.getElementById('feed'));
        await state.ready;
        await wait(20);

        check('mounting asks for the feed', sent.some(s => s.url === '/api/feed' && s.method === 'GET'));
        const posts = [...doc.querySelectorAll('.fd-post')];
        check('every post is drawn', posts.length === 3, posts.length);
        check('in the order the server gave', posts.map(p => p.getAttribute('data-id')).join(',') === '12,11,10');
        check('a post says who wrote it', /Sam Staff/.test(posts[0].textContent));
        check('  and when, readably', /11 Sep, 15:20/.test(posts[0].textContent), posts[0].textContent);
        check('a pinned post is marked', !!posts[1].querySelector('.fd-pin'));
        check('  and an unpinned one is not', !posts[0].querySelector('.fd-pin'));
        check('the like count is shown', posts[0].querySelector('.fd-likes').textContent === '3');
        check('  and whether I liked it', posts[2].querySelector('[data-act="like"]').classList.contains('on')
            && !posts[0].querySelector('[data-act="like"]').classList.contains('on'));
        check('the comment count is shown', posts[0].querySelector('.fd-ccount').textContent === '2');
    }

    // --- the picture is a request of its own ----------------------------------------
    {
        const { w, doc } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const img = doc.querySelector('.fd-post[data-id="12"] img.fd-img');
        check('a post with a picture asks for it by id', !!img && img.getAttribute('src') === '/api/feed/12/image',
            img && img.getAttribute('src'));
        check('  lazily', !!img && img.getAttribute('loading') === 'lazy');
        check('a post without one has no img', !doc.querySelector('.fd-post[data-id="11"] img'));
    }

    // --- other people's text is text --------------------------------------------------
    {
        const { w, doc } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const evil = doc.querySelector('.fd-post[data-id="10"]');
        check('a script in a post body does not become a script',
            !evil.querySelector('script') && !evil.querySelector('img[src="x"]'));
        check('  it is shown as the text it was',
            /<script>alert\(2\)<\/script>/.test(evil.querySelector('.fd-body').textContent));
        check('a tag in an author name does not become a tag',
            !evil.querySelector('.fd-who b') && /<b>Evil<\/b>/.test(evil.querySelector('.fd-who').textContent));
    }

    // --- what the viewer may do is what the server said -----------------------------------
    {
        const { w, doc } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        check('Delete appears only where allowed',
            !!doc.querySelector('.fd-post[data-id="12"] [data-act="delete"]') &&
            !doc.querySelector('.fd-post[data-id="11"] [data-act="delete"]'));
        check('Pin appears nowhere for staff', !doc.querySelector('[data-act="pin"]'));
    }
    {
        const { w, doc } = boot({ isHr: true, posts: POSTS.map(p => Object.assign({}, p, { can_pin: true, can_delete: true })) });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        check('and everywhere for HR', doc.querySelectorAll('[data-act="pin"]').length === 3);
        check('  reading Unpin on a pinned post',
            doc.querySelector('.fd-post[data-id="11"] [data-act="pin"]').textContent === 'Unpin');
        check('HR gets the pin-to-top box in the composer', !!doc.getElementById('feed-pin'));
    }

    // --- posting -----------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.getElementById('feed-text').value = 'Hello everyone';
        doc.querySelector('[data-act="post"]').click();
        await wait(30);
        const call = sent.find(s => s.url === '/api/feed' && s.method === 'POST');
        check('posting sends the text', !!call && bodyOf(call).body === 'Hello everyone', call && call.body);
        check('  with no picture when none was chosen', !!call && bodyOf(call).image_data === '');
        check('  and reloads the feed', sent.filter(s => s.url === '/api/feed' && s.method === 'GET').length === 2);
    }
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.querySelector('[data-act="post"]').click();
        await wait(20);
        check('an empty post is stopped on the page', !sent.some(s => s.method === 'POST'));
        check('  and told why', /Say something/.test(doc.getElementById('feed-err').textContent));
    }
    {
        const { w, doc } = boot({ canPost: false });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        check('when staff may not post there is no composer', !doc.getElementById('feed-text'));
        check('  and it says so', /Only HR can post/.test(doc.getElementById('feed').textContent));
    }
    {
        const { w, doc } = boot({ postFails: true });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.getElementById('feed-text').value = 'Try';
        doc.querySelector('[data-act="post"]').click();
        await wait(30);
        check('a refused post shows the reason the server gave',
            /Only HR can post/.test(doc.getElementById('feed-err').textContent),
            doc.getElementById('feed-err').textContent);
    }

    // --- the picture picker checks before the server does ---------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const input = doc.getElementById('feed-file');
        const svg = new w.File(['<svg/>'], 'x.svg', { type: 'image/svg+xml' });
        Object.defineProperty(input, 'files', { value: [svg], configurable: true });
        input.dispatchEvent(new w.Event('change', { bubbles: true }));
        await wait(20);
        check('an SVG is refused on the page', /PNG, JPEG, GIF or WebP/.test(doc.getElementById('feed-err').textContent),
            doc.getElementById('feed-err').textContent);
        check('  and nothing is queued', !w.Feed._state(doc.getElementById('feed')).pendingImage);
    }
    {
        const { w, doc } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const input = doc.getElementById('feed-file');
        const big = new w.File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' });
        Object.defineProperty(input, 'files', { value: [big], configurable: true });
        input.dispatchEvent(new w.Event('change', { bubbles: true }));
        await wait(20);
        check('a picture over 2MB is refused on the page', /too large/.test(doc.getElementById('feed-err').textContent));
    }
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const input = doc.getElementById('feed-file');
        const png = new w.File([new Uint8Array([137, 80, 78, 71])], 'ok.png', { type: 'image/png' });
        Object.defineProperty(input, 'files', { value: [png], configurable: true });
        input.dispatchEvent(new w.Event('change', { bubbles: true }));
        await wait(60);
        const st = w.Feed._state(doc.getElementById('feed'));
        check('a PNG is read into a data URL', /^data:image\/png;base64,/.test(st.pendingImage), st.pendingImage.slice(0, 40));
        check('  and previewed', !!doc.querySelector('.fd-preview img'));
        doc.querySelector('[data-act="post"]').click();
        await wait(30);
        const call = sent.find(s => s.url === '/api/feed' && s.method === 'POST');
        check('  and sent with the post', !!call && /^data:image\/png;base64,/.test(bodyOf(call).image_data));
    }

    // --- likes ---------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.querySelector('.fd-post[data-id="12"] [data-act="like"]').click();
        await wait(30);
        check('liking posts to the like endpoint', sent.some(s => s.url === '/api/feed/12/like' && s.method === 'POST'));
        const btn = doc.querySelector('.fd-post[data-id="12"] [data-act="like"]');
        check('  and shows the count the server returned', btn.querySelector('.fd-likes').textContent === '4');
        check('  and that I now like it', btn.classList.contains('on'));
    }

    // --- comments ---------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        const post = doc.querySelector('.fd-post[data-id="12"]');
        check('comments start closed', post.querySelector('.fd-comments').hidden === true);
        post.querySelector('[data-act="comments"]').click();
        await wait(30);
        check('opening them fetches them', sent.some(s => s.url === '/api/feed/12/comments' && s.method === 'GET'));
        check('  and shows them', /Ada/.test(post.querySelector('.fd-comments').textContent));
        check('  escaped', !post.querySelector('.fd-comment b'));

        post.querySelector('[data-role="comment-text"]').value = 'Me too';
        post.querySelector('[data-act="comment"]').click();
        await wait(30);
        const call = sent.find(s => s.url === '/api/feed/12/comments' && s.method === 'POST');
        check('sending one posts it', !!call && bodyOf(call).body === 'Me too');
        check('  and it appears without a reload', post.querySelectorAll('.fd-comment').length === 2);
        check('  and the count goes up', post.querySelector('.fd-ccount').textContent === '3');
    }

    // --- deleting -----------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot();
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.querySelector('.fd-post[data-id="12"] [data-act="delete"]').click();
        await wait(30);
        check('deleting sends a DELETE', sent.some(s => s.url === '/api/feed/12' && s.method === 'DELETE'));
        check('  and the post is gone from the page', !doc.querySelector('.fd-post[data-id="12"]'));
    }
    {
        const { w, doc, sent } = boot({ confirm: false });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        doc.querySelector('.fd-post[data-id="12"] [data-act="delete"]').click();
        await wait(30);
        check('but not without asking', !sent.some(s => s.method === 'DELETE'));
    }

    // --- more --------------------------------------------------------------------------------------------------
    {
        const { w, doc, sent } = boot({ more: true });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        check('when there is more, it says so', !!doc.querySelector('[data-act="more"]'));
        doc.querySelector('[data-act="more"]').click();
        await wait(30);
        check('  and asks for it by id, not page number',
            sent.some(s => s.url === '/api/feed' && /before=10/.test(s.q)));
        check('  appending rather than replacing', doc.querySelectorAll('.fd-post').length === 4);
        check('  and stops offering more when there is none', !doc.querySelector('[data-act="more"]'));
    }
    {
        const { w, doc } = boot({ posts: [] });
        await w.Feed.mount(doc.getElementById('feed')).ready;
        await wait(20);
        check('an empty feed says so rather than showing nothing', /Nothing here yet/.test(doc.getElementById('feed').textContent));
    }

    // --- both pages actually load it ------------------------------------------------------------------------------
    {
        const portal = fs.readFileSync(path.join(ROOT, 'employee-dashboard.html'), 'utf8');
        const hr = fs.readFileSync(path.join(ROOT, 'app.html'), 'utf8');
        const sw = fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8');
        check('the staff portal loads feed.js', /feed\.js\?v=\d+/.test(portal));
        check('  and has a Feed tab', /data-tab="feed"/.test(portal) && /id="tab-feed"/.test(portal));
        check('the HR app loads feed.js', /feed\.js\?v=\d+/.test(hr));
        check('  and has a Feed view', /id="feed-view"/.test(hr) && /id="nav-feed"/.test(hr));
        check('the service worker precaches it', /\/feed\.js\?v=\d+/.test(sw));
        const vs = new Set([...(portal + hr + sw).matchAll(/feed\.js\?v=(\d+)/g)].map(m => m[1]));
        check('  all at the same version', vs.size === 1, [...vs].join(','));
    }

    console.log(failures === 0
        ? '\nAll company-feed checks passed.'
        : `\n${failures} company-feed check(s) failed.`);
    process.exit(failures === 0 ? 0 : 1);
})();
