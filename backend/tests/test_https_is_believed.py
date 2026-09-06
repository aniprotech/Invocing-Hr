"""What the application believes about the connection it is answering.

TLS is terminated at the platform's edge and the request reaches this
container over plain HTTP. uvicorn will read the proxy's headers and correct
for that, but only from a proxy on 127.0.0.1, and the platform's is not - so
every request looked like plain http from an address belonging to the proxy.

Three separate things were quietly wrong, and none of them looked like a bug
from outside:

  - Strict-Transport-Security is only set on an https request, so it was
    never sent. Checked against the live site before this was written: the
    other four security headers were there and that one was not.
  - Absolute links built from the request came out http://. Somebody had
    already noticed for the OAuth callback and patched the string back to
    https in three places; the invoice link a customer opens, the password
    reset, the tracking pixel and the payment provider's return address were
    all still http.
  - Every caller shared one address, which is also the rate limiter's key.
    Five sign-ups per five minutes stopped being five per person and became
    five for the whole platform.
"""
import pytest

import main
import models


def sign_in_attempts(email):
    with main.SessionLocal() as db:
        return [row.ip_address for row in db.query(models.DBClientLoginLog).filter(
            models.DBClientLoginLog.email == email).all()]


def a_failed_sign_in(client, email, forwarded_for=None):
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    return client.post("/api/client/login",
                       json={"email": email, "password": "not-the-password"},
                       headers=headers)


# --- the scheme -----------------------------------------------------------------

def test_the_app_knows_it_is_on_https_behind_the_proxy(client):
    """The header the proxy sends is the only evidence there is."""
    res = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert res.headers.get("strict-transport-security") == \
        "max-age=31536000; includeSubDomains", dict(res.headers)


def test_a_genuinely_plain_request_is_not_told_to_use_https(client):
    """Sending HSTS over http would pin a local or internal deployment to a
    scheme it may not have."""
    assert "strict-transport-security" not in {k.lower() for k in client.get("/api/health").headers}


def test_a_forwarded_http_is_believed_too(client):
    """The header is read, not assumed. A proxy that really did receive plain
    http must not produce an https answer."""
    res = client.get("/api/health", headers={"X-Forwarded-Proto": "http"})
    assert "strict-transport-security" not in {k.lower() for k in res.headers}


def test_a_chain_of_proxies_is_read_from_the_first_hop(client):
    """The scheme the browser used is the leftmost entry - later hops describe
    connections inside the platform, not the one that matters."""
    res = client.get("/api/health", headers={"X-Forwarded-Proto": "https, http"})
    assert res.headers.get("strict-transport-security"), dict(res.headers)


def test_nonsense_in_the_header_leaves_the_scheme_alone(client):
    res = client.get("/api/health", headers={"X-Forwarded-Proto": "gopher"})
    assert res.status_code == 200
    assert "strict-transport-security" not in {k.lower() for k in res.headers}


# --- who the caller is -----------------------------------------------------------

def test_the_sign_in_log_records_the_caller_not_the_proxy(client):
    """An account holder is shown this list to spot somebody else's access.
    One address for every sign-in on the platform tells them nothing."""
    a_failed_sign_in(client, "watcher@example.com", "203.0.113.7")
    assert "203.0.113.7" in sign_in_attempts("watcher@example.com"), \
        sign_in_attempts("watcher@example.com")


def test_two_people_do_not_share_one_rate_limit(client):
    """The reason this matters most. Every limit in the app is keyed on the
    caller's address, so while everybody looked like the proxy, ten failed
    sign-ins anywhere on the platform locked out everybody else."""
    for _ in range(11):
        a_failed_sign_in(client, "first@example.com", "198.51.100.1")

    assert a_failed_sign_in(client, "first@example.com", "198.51.100.1").status_code == 429, \
        "the limit did not apply to the person who spent it"

    somebody_else = a_failed_sign_in(client, "second@example.com", "198.51.100.2")
    assert somebody_else.status_code == 401, \
        f"a stranger was locked out by somebody else's attempts ({somebody_else.status_code})"


def test_a_caller_cannot_get_a_fresh_allowance_by_forging_the_chain(client):
    """Each hop appends what it saw, so the rightmost entry is the one our own
    proxy observed. Reading from the left instead would let anyone reset their
    own limit by sending an X-Forwarded-For of their choosing."""
    for _ in range(11):
        a_failed_sign_in(client, "persistent@example.com", "192.0.2.50")

    forged = a_failed_sign_in(client, "persistent@example.com",
                              "10.9.9.9, 192.0.2.50")
    assert forged.status_code == 429, \
        "prepending an address of their own bought them a new allowance"


def test_no_header_leaves_the_connection_speaking_for_itself(client):
    """Nothing to correct for when the app is reached directly."""
    a_failed_sign_in(client, "direct@example.com")
    assert sign_in_attempts("direct@example.com") == ["testclient"], \
        sign_in_attempts("direct@example.com")


# --- the middleware itself ----------------------------------------------------------

@pytest.mark.parametrize("kind,proto,expected", [
    ("http", "https", "https"),
    ("http", "http", "http"),
    ("websocket", "https", "wss"),
    ("websocket", "http", "ws"),
])
def test_a_websocket_gets_a_websocket_scheme(kind, proto, expected):
    """A proxy reports https for a websocket too, but a websocket scope spells
    its scheme ws/wss. Writing "https" there is a scope no ASGI server would
    have produced."""
    seen = {}

    async def record(scope, receive, send):
        seen.update(scope)

    scope = {"type": kind, "scheme": "ws" if kind == "websocket" else "http",
             "client": ("127.0.0.1", 5000),
             "headers": [(b"x-forwarded-proto", proto.encode())]}

    import asyncio
    asyncio.run(main.TrustTheProxy(record)(scope, None, None))
    assert seen["scheme"] == expected


@pytest.mark.skipif(not main.TRUST_PROXY_HEADERS,
                    reason="this environment is reached directly and opted out")
def test_the_correction_runs_before_anything_that_reads_the_scheme():
    """Outermost, or it is pointless. The session cookie's Secure flag, the
    security headers and every route all read the scheme, and whichever of
    them runs first would read the uncorrected one."""
    stack = [m.cls.__name__ for m in main.app.user_middleware]
    assert stack[0] == "TrustTheProxy", stack
