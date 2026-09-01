"""Adding to and deleting from the front page.

The section headings were already editable while the entries beneath them
were written into the HTML, so an operator could rename the FAQ and not add a
question to it.

Two rules matter here. Only the operator may write to a page every visitor
reads. And an empty section means "leave what ships with the page alone" -
if deleting the last row blanked the section instead, one delete would empty
the front page and nothing would say why.
"""
import pytest
from fastapi.testclient import TestClient

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _clear_items():
    with main.SessionLocal() as db:
        db.query(models.DBLandingItem).delete()
        db.commit()
    yield
    with main.SessionLocal() as db:
        db.query(models.DBLandingItem).delete()
        db.commit()


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def stranger():
    """A genuinely separate session - the superadmin fixture hands back the
    same client it logged in, so reusing it would prove nothing."""
    with TestClient(main.app) as c:
        yield c


def add(superadmin, **body):
    body.setdefault("kind", "faq")
    body.setdefault("title", "What is it?")
    res = superadmin.post("/api/superadmin/landing-items", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# --- who may write to the front page ------------------------------------------
def test_a_stranger_cannot_add_to_the_front_page(stranger):
    res = stranger.post("/api/superadmin/landing-items",
                      json={"kind": "faq", "title": "Hacked"})
    assert res.status_code in (401, 403), res.text


def test_a_tenant_cannot_add_to_the_front_page(tenant):
    """A signed-in business is still not the operator."""
    res = tenant.post("/api/superadmin/landing-items",
                      json={"kind": "faq", "title": "Ours now"})
    assert res.status_code in (401, 403), res.text


def test_a_stranger_cannot_delete_from_the_front_page(superadmin, stranger):
    row = add(superadmin)
    assert stranger.delete(
        f"/api/superadmin/landing-items/{row['id']}").status_code in (401, 403)


# --- adding, editing, deleting -------------------------------------------------
def test_an_item_can_be_added_and_is_published(superadmin, client):
    add(superadmin, kind="faq", title="Do you do payroll?", body="Yes.")
    got = client.get("/api/platform/landing").json()
    titles = [i["title"] for i in got["items"]["faq"]]
    assert "Do you do payroll?" in titles, got["items"]


def test_an_item_can_be_deleted(superadmin, client):
    row = add(superadmin, kind="faq", title="Temporary")
    assert superadmin.delete(
        f"/api/superadmin/landing-items/{row['id']}").status_code == 200
    got = client.get("/api/platform/landing").json()
    assert [i["title"] for i in got["items"]["faq"]] == []


def test_an_item_can_be_edited(superadmin):
    row = add(superadmin, title="Frist draft")
    res = superadmin.put(f"/api/superadmin/landing-items/{row['id']}",
                         json={"title": "First draft"})
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "First draft"


def test_hiding_one_takes_it_off_the_page_without_losing_it(superadmin, client):
    """Pulling something from the site is not the same as throwing it away."""
    row = add(superadmin, kind="faq", title="Seasonal")
    superadmin.put(f"/api/superadmin/landing-items/{row['id']}",
                   json={"is_active": False})

    public = client.get("/api/platform/landing").json()
    assert [i["title"] for i in public["items"]["faq"]] == []

    mine = superadmin.get("/api/superadmin/landing-items").json()
    assert [i["title"] for i in mine["items"]["faq"]] == ["Seasonal"]


def test_the_three_sections_stay_separate(superadmin, client):
    add(superadmin, kind="module", title="Payroll")
    add(superadmin, kind="industry", title="Retail")
    add(superadmin, kind="faq", title="How much?")
    items = client.get("/api/platform/landing").json()["items"]
    assert [i["title"] for i in items["module"]] == ["Payroll"]
    assert [i["title"] for i in items["industry"]] == ["Retail"]
    assert [i["title"] for i in items["faq"]] == ["How much?"]


def test_new_items_go_to_the_end(superadmin, client):
    """Adding one must not reshuffle what an operator already arranged."""
    add(superadmin, kind="module", title="First")
    add(superadmin, kind="module", title="Second")
    add(superadmin, kind="module", title="Third")
    titles = [i["title"] for i in
              client.get("/api/platform/landing").json()["items"]["module"]]
    assert titles == ["First", "Second", "Third"], titles


def test_the_order_can_be_changed(superadmin, client):
    a = add(superadmin, kind="module", title="A")
    b = add(superadmin, kind="module", title="B")
    superadmin.put(f"/api/superadmin/landing-items/{b['id']}", json={"sort_order": 0})
    titles = [i["title"] for i in
              client.get("/api/platform/landing").json()["items"]["module"]]
    assert titles == ["B", "A"], titles


# --- refusals ------------------------------------------------------------------
def test_an_item_needs_a_title(superadmin):
    res = superadmin.post("/api/superadmin/landing-items",
                          json={"kind": "faq", "title": "   "})
    assert res.status_code == 400


def test_a_title_cannot_be_emptied_by_editing(superadmin):
    row = add(superadmin, title="Real")
    assert superadmin.put(f"/api/superadmin/landing-items/{row['id']}",
                          json={"title": " "}).status_code == 400


def test_an_unknown_section_is_refused(superadmin):
    res = superadmin.post("/api/superadmin/landing-items",
                          json={"kind": "pricing", "title": "Cheap"})
    assert res.status_code == 400


def test_deleting_something_that_is_not_there_is_a_404(superadmin):
    assert superadmin.delete("/api/superadmin/landing-items/99999").status_code == 404


# --- the empty case ------------------------------------------------------------
def test_nothing_added_means_empty_lists_not_missing_keys(client):
    """The page checks for entries; a missing key would read as an error
    rather than as "use what you ship with"."""
    items = client.get("/api/platform/landing").json()["items"]
    assert items == {"module": [], "industry": [], "faq": [], "policy": []}, items


# --- the copy hooks and the settings behind them --------------------------------
def test_every_editable_spot_on_the_page_has_a_setting_behind_it():
    """A data-cms hook with no setting is a box on the page that silently
    never changes, and nothing says so - the operator edits and nothing moves."""
    import pathlib
    import re

    page = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    hooks = set(re.findall(r'data-cms="([A-Za-z0-9_]+)"', page.read_text(encoding="utf-8")))
    assert hooks, "no editable copy found at all"

    known = {s.key.split(".", 1)[1] for s in main.PLATFORM_SETTINGS if s.group == "Landing"}
    assert not (hooks - known), sorted(hooks - known)


def test_no_heading_on_the_front_page_is_still_hardcoded():
    """The point of the change: every section could be renamed without a deploy."""
    import pathlib
    import re

    page = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    headings = re.findall(r"<h2[^>]*>", page.read_text(encoding="utf-8"))
    assert headings, "no headings found"
    assert [h for h in headings if "data-cms" in h] == headings, \
        [h for h in headings if "data-cms" not in h]


# --- policies -------------------------------------------------------------------
def test_a_policy_is_published_and_readable_without_an_account(superadmin, stranger):
    """A privacy notice nobody can read without signing up is not a privacy
    notice."""
    row = add(superadmin, kind="policy", title="Privacy Policy",
              body="We keep your data.\n\nWe do not sell it.")
    got = stranger.get(f"/api/platform/policies/{row['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["title"] == "Privacy Policy"
    assert "do not sell" in got.json()["body"]


def test_a_hidden_policy_is_not_readable(superadmin, stranger):
    """Unpublishing has to actually unpublish - the link goes, and so must
    the page behind it."""
    row = add(superadmin, kind="policy", title="Draft Terms", body="Not ready.")
    superadmin.put(f"/api/superadmin/landing-items/{row['id']}",
                   json={"is_active": False})
    assert stranger.get(f"/api/platform/policies/{row['id']}").status_code == 404


def test_a_card_cannot_be_read_as_a_policy(superadmin, stranger):
    """The endpoint is for policies; serving an FAQ card through it would put
    marketing copy on a page headed like a legal notice."""
    row = add(superadmin, kind="faq", title="How much?", body="It depends.")
    assert stranger.get(f"/api/platform/policies/{row['id']}").status_code == 404


def test_the_front_page_gets_the_titles_but_not_the_text(superadmin, client):
    """Pages of legal text on every visit to the home page is pages nobody
    asked for. The footer only needs enough to draw a link."""
    add(superadmin, kind="policy", title="Privacy Policy", body="Long " * 500)
    listed = client.get("/api/platform/landing").json()["items"]["policy"]
    assert len(listed) == 1
    assert listed[0]["title"] == "Privacy Policy"
    assert "body" not in listed[0], listed[0]


def test_a_policy_may_be_long(superadmin, stranger):
    """Capped like an FAQ answer, a privacy notice would be cut off mid
    sentence and nothing would say so."""
    long_text = "Clause. " * 2000            # ~16k characters
    row = add(superadmin, kind="policy", title="Terms", body=long_text)
    got = stranger.get(f"/api/platform/policies/{row['id']}").json()
    assert len(got["body"]) > 10000, len(got["body"])


def test_a_card_is_still_kept_short(superadmin):
    """The long limit is for policies only - an FAQ answer running to pages
    would break the layout it sits in."""
    row = add(superadmin, kind="faq", title="Q", body="x" * 5000)
    stored = [i for i in
              superadmin.get("/api/superadmin/landing-items").json()["items"]["faq"]
              if i["id"] == row["id"]][0]
    assert len(stored["body"]) == 2000, len(stored["body"])
