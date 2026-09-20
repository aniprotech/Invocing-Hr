# Hosts: one app, three front doors

The Invoicing app, the HR app and the employee portal are one deployment.
Naming three hosts gives each its own address:

| Host | What it is | Its root opens |
|---|---|---|
| `www.aniprotech.com` | the site: front page, pricing, policies, superadmin | the front page |
| `invoice.aniprotech.com` | the Invoicing app | its sign-in, or the app if you are in |
| `hr.aniprotech.com` | the HR app | its sign-in, or the HR dashboard if you are in |
| `employee.aniprotech.com` | the staff portal | the staff sign-in, or the dashboard if you are in |

Nothing is duplicated and nothing moves: same code, same database, same
API on every host. The first label of the host decides which face is shown.
On a product host the app shows that product alone, whatever the plan
holds; a link to the other product goes to the other host, hash and all; a
business page opened on the wrong host is sent to the right one. A business
with both products signs in once and switches from the account menu.

## Switching it on

Until `PRODUCT_HOSTS` is set, everything stays on one address exactly as
before. Do these in order; nothing changes for visitors until step 4.

1. **DNS.** Add three CNAME records at your DNS provider, each pointing at
   the Railway service's domain (the `xxx.up.railway.app` one, or whatever
   Railway shows under *Custom Domain*):
   `invoice`, `hr`, `employee`.

2. **Railway.** Service → *Settings* → *Networking* → *Custom Domain*, add
   `invoice.aniprotech.com`, `hr.aniprotech.com` and `employee.aniprotech.com`.
   Railway issues the certificates; wait until each shows a green tick.

3. **Google sign-in.** Google Cloud console → *APIs & Services* →
   *Credentials* → the OAuth client → *Authorised redirect URIs*, add:
   - `https://invoice.aniprotech.com/api/auth/callback`
   - `https://hr.aniprotech.com/api/auth/callback`
   - `https://employee.aniprotech.com/api/auth/callback`

   Keep the `www` one. Google refuses a sign-in that starts on a host whose
   callback it has not been told about.

4. **Variables** on the app service (the one built from the Dockerfile):

   ```
   PRODUCT_HOSTS=invoicing=invoice.aniprotech.com,hr=hr.aniprotech.com,employee=employee.aniprotech.com
   COOKIE_DOMAIN=.aniprotech.com
   APP_BASE_URL=https://www.aniprotech.com
   ```

   `COOKIE_DOMAIN` puts the session on the parent domain so one sign-in
   counts on every host. Without it, each host asks you to sign in
   separately, and *Switch to HR* lands on the HR sign-in rather than the
   HR dashboard. Setting it signs everyone out once, because the old cookie
   was the host's own.

   Note that a cookie on `.aniprotech.com` is also sent to any other
   subdomain of aniprotech.com - Caremonitor included. It is signed, so
   nothing can read or forge it, but it does travel.

5. **Check.** `https://hr.aniprotech.com/` should land on *Sign in to HR*;
   `https://www.aniprotech.com/app.html` should bounce to
   `invoice.aniprotech.com`; `https://www.aniprotech.com/api/platform/landing`
   should list the three hosts under `products`.

## Trying it locally

Browsers resolve `*.localhost` to your own machine, so with the backend on
port 8000:

```
PRODUCT_HOSTS=invoicing=invoice.localhost:8000,hr=hr.localhost:8000,employee=employee.localhost:8000
```

then open `http://hr.localhost:8000/`. Leave `COOKIE_DOMAIN` unset locally;
browsers do not accept a domain cookie on localhost.

## What lives where

- `backend/main.py`, *ONE APP, THREE FRONT DOORS*: `product_for_host`,
  `page_url` (which host a link is built on), the `front_door` middleware,
  the per-host manifest.
- `frontend/app.js`, *One app, three front doors*: the face, the switch,
  and `applyRoute` sending the other product's hashes to the other host.
- `frontend/login.html` says which product it is; `frontend/index.html`
  sends each sign-in link to its door once `/api/platform/landing` names them.
- Tests: `backend/tests/test_front_doors.py`, `frontend/tests/front-doors.js`.
