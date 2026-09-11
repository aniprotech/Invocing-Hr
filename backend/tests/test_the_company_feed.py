"""A place for the company to be a company.

Announcements went out as notifications - one copy per person, gone once
dismissed, and only ever from HR to staff. There was nowhere to put a photo of
the team at the summer party, no way for anybody but HR to say anything, and
nothing anybody could react to.

One feed, served once, for whoever is looking. HR and staff see the same
posts; what differs is what each may do to them, and that is a flag checked
on the way in rather than a second copy of every endpoint.

The tests that carry the most weight are not the happy path. An image
somebody uploads is served straight back into everybody else's browser, so
what is accepted, and how it comes back out, is the part that has to be
right.
"""
import base64
import uuid

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"

# The smallest valid PNG there is: 1x1, transparent.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
SVG_DATA_URL = "data:image/svg+xml;base64," + base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>').decode()


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    """Switch the session to this employee. The client session is cleared
    first, so the viewer is unambiguously staff."""
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def post(client, body="Hello", **extra):
    payload = {"body": body}
    payload.update(extra)
    res = client.post("/api/feed", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def feed(client, **params):
    res = client.get("/api/feed", params=params)
    assert res.status_code == 200, res.text
    return res.json()


# --- one feed, seen by everybody --------------------------------------------------

def test_hr_and_staff_see_the_same_feed(tenant, account):
    staff = person(tenant, first_name="Sam", last_name="Staff")
    post(tenant, "From the company")
    as_staff(tenant, staff)
    post(tenant, "From Sam")

    mine = [p["body"] for p in feed(tenant)["posts"]]
    as_hr(tenant, account)
    theirs = [p["body"] for p in feed(tenant)["posts"]]
    assert mine == theirs == ["From Sam", "From the company"]


def test_a_post_says_who_wrote_it(tenant, account):
    staff = person(tenant, first_name="Sam", last_name="Staff")
    as_staff(tenant, staff)
    p = post(tenant, "Hi")
    assert p["author"] == "Sam Staff"
    assert p["from_company"] is False

    as_hr(tenant, account)
    p = post(tenant, "Hello all")
    assert p["from_company"] is True
    assert p["author"]


def test_the_name_is_kept_as_it_was(tenant, account):
    """A post from somebody who has since left still reads correctly."""
    staff = person(tenant, first_name="Sam", last_name="Staff")
    as_staff(tenant, staff)
    post(tenant, "Before I went")
    as_hr(tenant, account)
    tenant.put(f"/api/employees/{staff['id']}", json={"first_name": "Renamed"})
    assert feed(tenant)["posts"][0]["author"] == "Sam Staff"


def test_nobody_signed_in_sees_nothing(client):
    assert client.get("/api/feed").status_code == 401


def test_another_business_sees_none_of_it(tenant, client, account):
    post(tenant, "Ours")
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    assert feed(client)["posts"] == []


# --- who may post --------------------------------------------------------------------

def test_staff_can_post_by_default(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    assert feed(tenant)["can_post"] is True
    post(tenant, "Allowed")


def test_and_hr_can_switch_that_off(tenant, account):
    staff = person(tenant)
    assert tenant.put("/api/feed/settings",
                      json={"staff_can_post": False}).status_code == 200

    as_staff(tenant, staff)
    assert feed(tenant)["can_post"] is False
    res = tenant.post("/api/feed", json={"body": "Not allowed"})
    assert res.status_code == 403, res.text

    # HR still can. A feed nobody can write to is nothing.
    as_hr(tenant, account)
    assert feed(tenant)["can_post"] is True
    post(tenant, "Still fine")


def test_an_empty_post_is_refused(tenant):
    assert tenant.post("/api/feed", json={"body": "   "}).status_code == 400


def test_a_picture_alone_is_a_post(tenant):
    p = post(tenant, "", image_data=PNG_DATA_URL)
    assert p["has_image"] is True
    assert p["body"] == ""


# --- pictures, which is where it can go wrong ------------------------------------------

def test_a_png_is_accepted_and_comes_back_as_a_png(tenant):
    p = post(tenant, "Look", image_data=PNG_DATA_URL)
    res = tenant.get(f"/api/feed/{p['id']}/image")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    assert res.content == PNG_BYTES


def test_the_picture_is_served_with_nosniff(tenant):
    """Without it a browser may decide the bytes are really HTML and run
    them. The declared type has to be the type.

    Set by the middleware every response passes through, not by the image
    endpoint - so this is the one test that would notice if that middleware
    were ever narrowed to skip API responses."""
    p = post(tenant, "Look", image_data=PNG_DATA_URL)
    res = tenant.get(f"/api/feed/{p['id']}/image")
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert "inline" in res.headers.get("content-disposition", "")


def test_an_svg_is_refused(tenant):
    """A logo drawn into a PDF is one thing. An image somebody uploads and
    everybody else's browser then renders is a place to put a script."""
    res = tenant.post("/api/feed", json={"body": "Look", "image_data": SVG_DATA_URL})
    assert res.status_code == 400, res.text
    assert "PNG, JPEG, GIF or WebP" in res.json()["detail"]


def test_something_that_is_not_a_picture_is_refused(tenant):
    for bad in ("data:text/html;base64,PHNjcmlwdD4=",
                "javascript:alert(1)",
                "data:image/png;base64,AAAA\\\"><script>",
                "https://example.com/x.png"):
        res = tenant.post("/api/feed", json={"body": "Look", "image_data": bad})
        assert res.status_code == 400, (bad, res.text)


def test_a_huge_picture_is_refused(tenant):
    huge = "data:image/png;base64," + ("A" * (main.FEED_IMAGE_MAX + 10))
    res = tenant.post("/api/feed", json={"body": "Look", "image_data": huge})
    assert res.status_code == 413, res.text


def test_a_post_with_no_picture_has_no_picture_to_fetch(tenant):
    p = post(tenant, "Words only")
    assert tenant.get(f"/api/feed/{p['id']}/image").status_code == 404


def test_the_picture_is_not_public(tenant, client):
    p = post(tenant, "Look", image_data=PNG_DATA_URL)
    client.post("/api/client/logout")
    assert client.get(f"/api/feed/{p['id']}/image").status_code == 401


def test_the_list_does_not_carry_every_picture_inline(tenant):
    """Twenty posts with a photo each would be forty megabytes of JSON. The
    list says a picture exists; the picture is fetched on its own."""
    post(tenant, "Look", image_data=PNG_DATA_URL)
    row = feed(tenant)["posts"][0]
    assert row["has_image"] is True
    assert "image_data" not in row


# --- likes -------------------------------------------------------------------------------

def test_a_like_counts_once(tenant):
    p = post(tenant, "Like me")
    res = tenant.post(f"/api/feed/{p['id']}/like").json()
    assert res == {"id": p["id"], "liked_by_me": True, "likes": 1}


def test_and_a_second_tap_takes_it_back(tenant):
    p = post(tenant, "Like me")
    tenant.post(f"/api/feed/{p['id']}/like")
    res = tenant.post(f"/api/feed/{p['id']}/like").json()
    assert res == {"id": p["id"], "liked_by_me": False, "likes": 0}


def test_two_people_are_two_likes(tenant, account):
    a = person(tenant)
    b = person(tenant)
    p = post(tenant, "Popular")
    as_staff(tenant, a)
    tenant.post(f"/api/feed/{p['id']}/like")
    as_staff(tenant, b)
    tenant.post(f"/api/feed/{p['id']}/like")

    as_hr(tenant, account)
    row = feed(tenant)["posts"][0]
    assert row["likes"] == 2
    assert row["liked_by_me"] is False


def test_the_feed_says_whether_i_liked_it(tenant):
    a = person(tenant)
    p = post(tenant, "Hmm")
    as_staff(tenant, a)
    tenant.post(f"/api/feed/{p['id']}/like")
    assert feed(tenant)["posts"][0]["liked_by_me"] is True


# --- comments ------------------------------------------------------------------------------

def test_a_comment_is_kept_and_listed_in_order(tenant):
    p = post(tenant, "Thoughts?")
    tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "First"})
    tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Second"})
    rows = tenant.get(f"/api/feed/{p['id']}/comments").json()
    assert [c["body"] for c in rows] == ["First", "Second"]
    assert feed(tenant)["posts"][0]["comments"] == 2


def test_an_empty_comment_is_refused(tenant):
    p = post(tenant, "Thoughts?")
    assert tenant.post(f"/api/feed/{p['id']}/comments",
                       json={"body": " "}).status_code == 400


def test_the_author_hears_about_a_comment(tenant):
    author = person(tenant, first_name="Sam", last_name="Author")
    reader = person(tenant, first_name="Lee", last_name="Reader")
    as_staff(tenant, author)
    p = post(tenant, "My post")
    as_staff(tenant, reader)
    tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Nice one"})

    as_staff(tenant, author)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("Lee Reader" in n["title"] for n in notes), notes


def test_but_not_about_their_own_comment(tenant):
    author = person(tenant)
    as_staff(tenant, author)
    p = post(tenant, "My post")
    before = len(tenant.get("/api/employee/notifications").json()["notifications"])
    tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Replying to myself"})
    after = len(tenant.get("/api/employee/notifications").json()["notifications"])
    assert after == before


# --- deleting --------------------------------------------------------------------------------

def test_staff_can_delete_their_own_post(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    p = post(tenant, "Oops")
    assert feed(tenant)["posts"][0]["can_delete"] is True
    assert tenant.delete(f"/api/feed/{p['id']}").status_code == 200
    assert feed(tenant)["posts"] == []


def test_but_not_somebody_elses(tenant):
    a = person(tenant)
    b = person(tenant)
    as_staff(tenant, a)
    p = post(tenant, "Mine")
    as_staff(tenant, b)
    assert feed(tenant)["posts"][0]["can_delete"] is False
    assert tenant.delete(f"/api/feed/{p['id']}").status_code == 403
    assert len(feed(tenant)["posts"]) == 1


def test_hr_can_delete_anybodys(tenant, account):
    a = person(tenant)
    as_staff(tenant, a)
    p = post(tenant, "Inappropriate")
    as_hr(tenant, account)
    assert feed(tenant)["posts"][0]["can_delete"] is True
    assert tenant.delete(f"/api/feed/{p['id']}").status_code == 200


def test_deleting_a_post_takes_its_likes_and_comments_with_it(tenant):
    p = post(tenant, "Going")
    tenant.post(f"/api/feed/{p['id']}/like")
    tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Bye"})
    tenant.delete(f"/api/feed/{p['id']}")
    with main.SessionLocal() as db:
        assert db.query(models.DBPostLike).filter(
            models.DBPostLike.post_id == p["id"]).count() == 0
        assert db.query(models.DBPostComment).filter(
            models.DBPostComment.post_id == p["id"]).count() == 0


def test_a_comment_can_be_deleted_by_its_author_or_hr(tenant, account):
    a = person(tenant)
    b = person(tenant)
    p = post(tenant, "Thread")
    as_staff(tenant, a)
    c = tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Mine"}).json()

    as_staff(tenant, b)
    assert tenant.delete(f"/api/feed/{p['id']}/comments/{c['id']}").status_code == 403
    as_staff(tenant, a)
    assert tenant.delete(f"/api/feed/{p['id']}/comments/{c['id']}").status_code == 200

    as_staff(tenant, a)
    c2 = tenant.post(f"/api/feed/{p['id']}/comments", json={"body": "Again"}).json()
    as_hr(tenant, account)
    assert tenant.delete(f"/api/feed/{p['id']}/comments/{c2['id']}").status_code == 200


# --- pinning ----------------------------------------------------------------------------------

def test_hr_can_pin_and_a_pinned_post_stays_at_the_top(tenant):
    old = post(tenant, "Important, from last week")
    post(tenant, "Newer")
    post(tenant, "Newest")
    assert tenant.post(f"/api/feed/{old['id']}/pin").json()["pinned"] is True
    assert [p["body"] for p in feed(tenant)["posts"]][0] == "Important, from last week"


def test_and_unpin(tenant):
    old = post(tenant, "Was important")
    post(tenant, "Newer")
    tenant.post(f"/api/feed/{old['id']}/pin")
    tenant.post(f"/api/feed/{old['id']}/pin")
    assert [p["body"] for p in feed(tenant)["posts"]] == ["Newer", "Was important"]


def test_staff_cannot_pin(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    p = post(tenant, "Pin me")
    assert feed(tenant)["posts"][0]["can_pin"] is False
    assert tenant.post(f"/api/feed/{p['id']}/pin").status_code == 403


# --- paging --------------------------------------------------------------------------------------

def test_the_feed_pages_by_id_not_by_number(tenant):
    """A page number shifts under you every time somebody posts. An id does
    not."""
    for i in range(main.FEED_PAGE + 5):
        post(tenant, f"Post {i}")
    first = feed(tenant)
    assert len(first["posts"]) == main.FEED_PAGE
    assert first["next_before"] > 0

    second = feed(tenant, before=first["next_before"])
    assert len(second["posts"]) == 5
    assert second["next_before"] == 0
    seen = [p["id"] for p in first["posts"]] + [p["id"] for p in second["posts"]]
    assert len(seen) == len(set(seen)), "a post appeared on two pages"


def test_pinned_posts_appear_once_on_the_first_page_only(tenant):
    pinned = post(tenant, "Pinned")
    tenant.post(f"/api/feed/{pinned['id']}/pin")
    for i in range(main.FEED_PAGE + 2):
        post(tenant, f"Post {i}")
    first = feed(tenant)
    second = feed(tenant, before=first["next_before"])
    everywhere = [p["id"] for p in first["posts"] + second["posts"]]
    assert everywhere.count(pinned["id"]) == 1
    assert first["posts"][0]["id"] == pinned["id"]


# --- reaching across ------------------------------------------------------------------------------

def test_another_business_cannot_touch_a_post(tenant, client, account):
    p = post(tenant, "Ours", image_data=PNG_DATA_URL)
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})

    assert client.get(f"/api/feed/{p['id']}/image").status_code == 404
    assert client.post(f"/api/feed/{p['id']}/like").status_code == 404
    assert client.post(f"/api/feed/{p['id']}/pin").status_code == 404
    assert client.delete(f"/api/feed/{p['id']}").status_code == 404
    assert client.post(f"/api/feed/{p['id']}/comments",
                       json={"body": "Hi"}).status_code == 404
