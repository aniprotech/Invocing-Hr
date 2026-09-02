"""A business sending from its own mail account.

Everything left through the operator's account, so a customer received an
invoice from us rather than from the business that raised it, replies came
back to the wrong place, and deliverability rode on one domain's reputation
for everybody.

The thing that is new and dangerous here is that a tenant now types the host,
so this server connects wherever they say. Left open that is a way to make the
machine talk to things only it can reach - a database on the private network,
a metadata service, itself. So the checks on where it will connect are the
tests worth having, alongside the usual one: a password that goes in never
comes back out.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _dns(monkeypatch):
    """Resolution without the network.

    A test that needs DNS fails on a train. Literal addresses resolve to
    themselves so the private-range checks are exercised for real; a name
    marked invalid fails to resolve; anything else is a public host.
    """
    import ipaddress
    import socket

    def fake_getaddrinfo(host, *a, **kw):
        if "invalid" in host or "no-such" in host:
            raise socket.gaierror(f"cannot resolve {host}")
        if host in ("localhost", "localhost.localdomain"):
            address = "127.0.0.1"              # as real resolution would
        else:
            try:
                ipaddress.ip_address(host)
                address = host
            except ValueError:
                address = "93.184.216.34"      # a public address
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    yield


def save(tenant, **body):
    return tenant.put("/api/email-settings", json=body)


def read(tenant):
    res = tenant.get("/api/email-settings")
    assert res.status_code == 200, res.text
    return res.json()


# --- what a business starts with ---------------------------------------------------
def test_a_business_starts_out_following_the_platform(tenant):
    """Nobody is made to configure anything to keep working."""
    got = read(tenant)
    assert got["transport"] == ""
    assert got["has_password"] is False


def test_the_company_name_is_offered_as_the_sender_name(tenant):
    assert read(tenant)["from_name"], read(tenant)


# --- where it will and will not connect ---------------------------------------------
def test_its_own_machine_is_refused(tenant):
    """Otherwise this is a way to reach whatever is listening on localhost."""
    res = save(tenant, transport="smtp", smtp_host="localhost", smtp_port=587,
               from_email="billing@acme.test")
    assert res.status_code == 400, res.text
    assert "public mail server" in res.json()["detail"]


def test_a_private_address_is_refused(tenant):
    """A database or a metadata service on the private network is exactly what
    this must not be pointed at."""
    for host in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254"):
        res = save(tenant, transport="smtp", smtp_host=host, smtp_port=587,
                   from_email="billing@acme.test")
        assert res.status_code == 400, (host, res.text)


def test_a_port_that_is_not_a_mail_port_is_refused(tenant):
    """Mail lives on four ports. Anything else is reaching for something that
    is not mail."""
    for port in (22, 3306, 6379, 8000, 11211):
        res = save(tenant, transport="smtp", smtp_host="smtp.example.com",
                   smtp_port=port, from_email="billing@acme.test")
        assert res.status_code == 400, (port, res.text)
        assert "mail ports" in res.json()["detail"]


def test_the_usual_mail_ports_are_allowed(tenant):
    for port in (25, 465, 587, 2525):
        res = save(tenant, transport="smtp", smtp_host="smtp.example.com",
                   smtp_port=port, from_email="billing@acme.test")
        assert res.status_code == 200, (port, res.text)


def test_a_host_that_does_not_exist_is_refused(tenant):
    res = save(tenant, transport="smtp",
               smtp_host="no-such-host-really-not-here.invalid",
               smtp_port=587, from_email="billing@acme.test")
    assert res.status_code == 400
    assert "Could not find" in res.json()["detail"]


def test_the_check_is_only_for_smtp(tenant):
    """Choosing Gmail should not be blocked by a host nobody is going to use."""
    assert save(tenant, transport="gmail").status_code == 200


# --- the password ---------------------------------------------------------------------
def test_the_password_never_comes_back_out(tenant):
    """This endpoint is read by a browser."""
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_user="billing", smtp_password="hunter2",
         from_email="billing@acme.test")
    got = read(tenant)
    assert got["has_password"] is True
    assert "hunter2" not in str(got), got
    assert got["smtp_password"] != "hunter2"


def test_saving_something_else_does_not_wipe_the_password(tenant):
    """The field comes back empty because it is masked, so an empty field has
    to mean "leave it alone" or every other edit clears it."""
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_password="hunter2", from_email="billing@acme.test")
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_user="someone-else", from_email="billing@acme.test")
    assert read(tenant)["has_password"] is True


def test_a_password_can_be_removed_on_purpose(tenant):
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_password="hunter2", from_email="billing@acme.test")
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         clear_password=True, from_email="billing@acme.test")
    assert read(tenant)["has_password"] is False


# --- who the mail comes from -----------------------------------------------------------
def test_smtp_needs_an_address_to_come_from(tenant):
    """Sending through their server under our address is the one combination
    that gets mail rejected outright."""
    res = save(tenant, transport="smtp", smtp_host="smtp.example.com",
               smtp_port=587)
    assert res.status_code == 400
    assert "come from" in res.json()["detail"]


def test_a_nonsense_sender_address_is_refused(tenant):
    res = save(tenant, transport="smtp", smtp_host="smtp.example.com",
               smtp_port=587, from_email="not-an-address")
    assert res.status_code == 400


# --- other people's settings -------------------------------------------------------------
def test_one_business_cannot_read_another_s(tenant, client):
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_user="theirs", from_email="billing@acme.test")

    import uuid
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})

    got = client.get("/api/email-settings").json()
    assert got["smtp_user"] == "", got
    assert got["has_password"] is False


def test_it_needs_a_session(client):
    assert client.get("/api/email-settings").status_code in (401, 403)
    assert client.put("/api/email-settings", json={}).status_code in (401, 403)


# --- what actually happens when it sends ----------------------------------------------------
class FakeSMTP:
    last = None

    def __init__(self, host, port, timeout=None):
        FakeSMTP.last = {"host": host, "port": port, "message": None,
                         "login": None, "envelope": None}

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        FakeSMTP.last["login"] = (user, password)

    def sendmail(self, sender, recipients, message):
        FakeSMTP.last["sender"] = sender
        FakeSMTP.last["envelope"] = list(recipients)
        FakeSMTP.last["message"] = message

    def quit(self):
        pass


@pytest.fixture
def fake_server(monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    FakeSMTP.last = None
    yield FakeSMTP


def client_id_of(tenant):
    return tenant.get("/api/client/me").json()["id"]


def test_a_business_sends_through_its_own_server(tenant, fake_server):
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=2525,
         smtp_user="billing", smtp_password="hunter2",
         from_email="billing@acme.test", from_name="Acme Ltd")

    ok, message = main.send_email_background(
        "customer@example.test", "Invoice", "Body",
        "hello@keyroutes.co", client_id=client_id_of(tenant))

    assert ok, message
    assert fake_server.last["host"] == "smtp.example.com"
    assert fake_server.last["port"] == 2525
    assert fake_server.last["login"] == ("billing", "hunter2")


def test_and_the_invoice_comes_from_them_not_from_us(tenant, fake_server):
    """The whole point. A customer receiving an invoice from the operator's
    address replies to the wrong company."""
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_password="hunter2", from_email="billing@acme.test",
         from_name="Acme Ltd")

    main.send_email_background("customer@example.test", "Invoice", "Body",
                               "hello@keyroutes.co",
                               client_id=client_id_of(tenant))

    assert "billing@acme.test" in fake_server.last["message"]
    assert "Acme Ltd" in fake_server.last["message"]
    assert "hello@keyroutes.co" not in fake_server.last["message"]


def test_a_business_that_has_set_nothing_up_still_sends(tenant, fake_server,
                                                        monkeypatch):
    """Adding this must not stop anybody who never touches the screen."""
    monkeypatch.setenv("SMTP_HOST", "platform.example.test")
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = "smtp"
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None,
                                     value="smtp"))
        db.commit()
    try:
        ok, message = main.send_email_background(
            "customer@example.test", "Invoice", "Body", "hello@keyroutes.co",
            client_id=client_id_of(tenant))
        assert ok, message
        assert fake_server.last["host"] == "platform.example.test"
    finally:
        with main.SessionLocal() as db:
            row = db.query(models.DBSettings).filter(
                models.DBSettings.key == "email.transport",
                models.DBSettings.client_id == None,    # noqa: E711
            ).first()
            if row:
                row.value = was or "gmail"
                db.commit()


def test_a_business_whose_host_stopped_resolving_is_refused_at_send(tenant,
                                                                    fake_server):
    """Saved once and checked again here, because DNS can change afterwards -
    a host that was public when it was saved can point at the private network
    tomorrow."""
    save(tenant, transport="smtp", smtp_host="smtp.example.com", smtp_port=587,
         smtp_password="hunter2", from_email="billing@acme.test")

    with main.SessionLocal() as db:
        row = db.query(models.DBClientEmailSettings).filter(
            models.DBClientEmailSettings.client_id == client_id_of(tenant)).first()
        row.smtp_host = "127.0.0.1"
        db.commit()

    ok, why = main.send_email_background(
        "customer@example.test", "Invoice", "Body", "hello@keyroutes.co",
        client_id=client_id_of(tenant))
    assert ok is False
    assert "public mail server" in why
    assert fake_server.last is None, "it connected anyway"
