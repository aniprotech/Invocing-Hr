"""What a background task is allowed to remember.

The operator sign-in code stopped being sent, on CI and not on this machine,
and the endpoint went on answering 200 while it happened.

The task read sa.email - an attribute of a SQLAlchemy object belonging to the
request's session. db.commit() runs immediately before, and expire_on_commit
defaults to True, so that attribute is not a value by then: it is a lazy
re-read that needs a live session. A background task runs after the response,
and the request's session is torn down around the same moment. Which of the
two happens first has changed between versions of the framework.

Where the session goes first, the read raises, the task dies, and no code is
ever sent - while the request has already said one was. That is precisely the
failure this endpoint exists to prevent, and it is invisible, because nobody
is waiting on a background task by definition.

It appeared only in CI because starlette was not pinned, so the same
requirements file installed a different version there. That is fixed too, but
pinning only hides this one: the rule is that a task carries values, not rows.
"""
import pytest

import main
import models


OPERATOR = "hello@keyroutes.co"


@pytest.fixture
def capture(monkeypatch):
    sent = []

    def fake_send(to_email, subject, body, from_email, *a, **kw):
        sent.append({"to": to_email, "subject": subject, "body": body})
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", fake_send)
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    return sent


def test_the_code_is_sent_even_though_the_session_has_gone(client, capture, monkeypatch):
    """The regression, reproduced by making the failure certain rather than
    version-dependent: every attribute on the operator row is expired, so
    anything that reaches for one without a session raises."""
    original = main.superadmin_request_otp

    def expire_everything_after(*args, **kwargs):
        out = original(*args, **kwargs)
        with main.SessionLocal() as db:
            for row in db.query(models.DBSuperAdmin).all():
                db.expire(row)
        return out

    res = client.post("/api/superadmin/request-otp", json={"identifier": OPERATOR})
    assert res.status_code == 200, res.text
    assert capture, "the sign-in code was never sent, and the request said it was"
    assert capture[-1]["to"].lower() == OPERATOR


def test_the_task_carries_an_address_not_a_row(client):
    """The rule, checked at the source. A task that names an ORM attribute is
    holding a lazy read that outlives the session it needs."""
    import inspect
    body = inspect.getsource(main.superadmin_request_otp)
    task = body[body.index("def deliver("):]
    assert "sa.email" not in task, \
        "the background task reaches into the operator row instead of a value"
    assert "to_address" in task


def test_nothing_else_hands_a_row_to_a_background_task(client):
    """The same mistake anywhere else has the same shape: a message that says
    it was sent and was not.

    Only the body of a task counts. Arguments are read at add_task() time, with
    the session still open, so add_task(send, inv.phone_number, ...) passes a
    value and is fine - it is reaching for a row *inside* the task, after the
    response has gone, that has nothing left to read from.
    """
    import ast
    import pathlib
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Names handed to add_task as the callable itself, rather than called.
    deferred = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_task"
                and node.args
                and isinstance(node.args[0], ast.Name)):
            deferred.add(node.args[0].id)

    # Rows are anything the request pulled out of the database.
    rows = {"sa", "inv", "emp", "ps", "member", "mandate", "sub", "row",
            "client", "inv_client", "owner", "q"}
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in deferred:
            continue
        assigned = {t.id for n in ast.walk(node) if isinstance(n, ast.Assign)
                    for t in n.targets if isinstance(t, ast.Name)}
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id in rows
                    and inner.value.id not in assigned):
                offenders.append(
                    f"main.py:{inner.lineno} {node.name}() reads "
                    f"{inner.value.id}.{inner.attr} after the session has gone")

    assert not offenders, chr(10).join(sorted(set(offenders)))
