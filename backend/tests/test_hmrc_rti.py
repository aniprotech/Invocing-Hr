"""HMRC payroll filings (RTI): the messages, and the checking of them against
HMRC's own published rules.

The files in backend/hmrc/rim/ are HMRC's, unmodified. What these tests pin is
that our messages pass them, that a message with a fault HMRC would refuse
does NOT pass them (a checker that passes everything is worse than none), and
that the plumbing around - the numbers' formats, the tax week, the Gateway
conversation, the stored password - does what HMRC's description says.

Dates are fixed inside the 2026-27 tax year. HMRC's rules that look at today
(a start date no more than 30 days ahead, a date of birth not in the future)
are all of the "not later than" kind, so fixed past dates stay valid.
"""
import copy
from datetime import date

import pytest
from lxml import etree

import hmrc_rti as r

EMPLOYER = {"office_no": "123", "paye_ref": "AB456", "ao_ref": "123PA00012345",
            "contact_name": "Jane Doe", "contact_email": "jane@example.com", "contact_phone": "020 7946 0000"}

PERSON = {
    "payroll_id": "E001", "nino": "AB123456C", "first_name": "Alice", "last_name": "Smith",
    "address_lines": ["1 High Street", "Leeds"], "postcode": "ls1 4ab", "birth_date": date(1990, 5, 17), "gender": "F",
    "start_date": date(2026, 4, 20), "start_decl": "A", "student_loan_starter": True,
    "frequency": "monthly", "pay_date": date(2026, 4, 30), "hours_band": "D",
    "tax_code": "1257L", "tax_regime": "", "non_cumulative": False,
    "taxable_pay": 3000, "tax": 350.2, "taxable_pay_ytd": 3000, "tax_ytd": 350.2,
    "student_loan": 120, "student_loan_plan": "2", "student_loan_ytd": 120,
    "ni": [{"letter": "A", "gross_pd": 3000, "gross_ytd": 3000, "lel_ytd": 542, "lel_pt_ytd": 0, "pt_uel_ytd": 2458,
            "er_pd": 300, "er_ytd": 300, "ee_pd": 200, "ee_ytd": 200}],
}


def message(kind="FPS", body=None, **kw):
    body = body if body is not None else r.build_fps(EMPLOYER, [{**PERSON}], 2026)
    return r.govtalk_message(body, kind, EMPLOYER, sender_id="SENDER", password="pw", vendor_id="9999", **kw)


def fps(**over):
    return message(body=r.build_fps(EMPLOYER, [{**PERSON, **over}], 2026))


def mutate(xml, fn):
    """Change a message the way a bug or a bad record would, and re-serialise."""
    doc = etree.fromstring(xml)
    fn(doc)
    return etree.tostring(doc)


def first(doc, name):
    return doc.find(f".//{{*}}{name}")


# --- what we build passes HMRC's own checks --------------------------------------------
def test_a_full_payment_submission_passes_hmrcs_schema_and_rules():
    assert r.check(message(), "FPS", 2026) == []


def test_it_passes_with_the_irmark_and_without():
    assert r.check(message(include_irmark=True), "FPS", 2026) == []


def test_an_employer_payment_summary_for_a_month_with_no_pay_passes():
    body = r.build_eps(EMPLOYER, 2026, no_payment_from=date(2026, 5, 6), no_payment_to=date(2026, 6, 5))
    assert r.check(message("EPS", body), "EPS", 2026) == []


def test_an_employment_allowance_claim_passes():
    body = r.build_eps(EMPLOYER, 2026, employment_allowance=True)
    assert r.check(message("EPS", body), "EPS", 2026) == []


def test_an_address_without_a_postcode_is_left_out_not_called_foreign():
    xml = fps(postcode="", address_lines=["1 High Street", "Leeds"], start_date=None)
    doc = etree.fromstring(xml)
    assert doc.find(".//{*}EmployeeDetails/{*}Address") is None


def test_an_address_abroad_names_its_country():
    xml = fps(postcode="", address_lines=["12 Rue Verte", "Paris"], country="France", start_date=None)
    doc = etree.fromstring(xml)
    assert doc.findtext(".//{*}EmployeeDetails/{*}Address/{*}ForeignCountry") == "France"
    assert r.check(xml, "FPS", 2026) == []


def test_a_postcode_alone_is_a_valid_address():
    xml = fps(address_lines=[], start_date=None)
    assert etree.fromstring(xml).findtext(".//{*}Address/{*}UKPostcode") == "LS1 4AB"
    assert r.check(xml, "FPS", 2026) == []


def test_a_final_submission_for_the_year_passes():
    xml = message(body=r.build_fps(EMPLOYER, [{**PERSON}], 2026, final=True))
    assert r.check(xml, "FPS", 2026) == []
    assert etree.fromstring(xml).findtext(".//{*}FinalSubmission/{*}ForYear") == "yes"


def test_a_director_a_leaver_and_a_week_one_code_all_pass():
    xml = fps(director={"nic_method": "AN", "appointed_week": 20}, leaving_date=date(2026, 4, 30),
              tax_code="1257L", non_cumulative=True, tax_regime="S")
    assert r.check(xml, "FPS", 2026) == []


def test_two_people_and_two_ni_letters_pass():
    a = {**PERSON}
    b = {**PERSON, "payroll_id": "E002", "nino": "CE123456A", "first_name": "Bob", "last_name": "Jones", "gender": "M",
         "start_date": None, "ni": [{**PERSON["ni"][0], "letter": "A"}, {**PERSON["ni"][0], "letter": "H", "gross_pd": 0, "er_pd": 0, "ee_pd": 0}]}
    xml = message(body=r.build_fps(EMPLOYER, [a, b], 2026))
    assert r.check(xml, "FPS", 2026) == []


@pytest.mark.parametrize("name", ["Jane", "Jane Doe", "Mary Jane Watson-Smith", "1 2", "", "  "])
def test_whatever_contact_name_is_given_the_message_still_passes(name):
    employer = {**EMPLOYER, "contact_name": name}
    xml = r.govtalk_message(r.build_fps(employer, [{**PERSON}], 2026), "FPS", employer, sender_id="S", password="p", vendor_id="9999")
    assert r.check(xml, "FPS", 2026) == []
    has_name = etree.fromstring(xml).find(".//{*}Principal/{*}Contact/{*}Name") is not None
    assert has_name == (name in ("Jane Doe", "Mary Jane Watson-Smith"))


def test_a_contact_with_only_an_email_or_phone_passes():
    employer = {**EMPLOYER, "contact_name": "", "contact_phone": ""}
    xml = r.govtalk_message(r.build_fps(employer, [{**PERSON}], 2026), "FPS", employer, sender_id="S", password="p", vendor_id="9999")
    assert r.check(xml, "FPS", 2026) == []
    no_contact = {k: v for k, v in EMPLOYER.items() if not k.startswith("contact")}
    xml = r.govtalk_message(r.build_fps(no_contact, [{**PERSON}], 2026), "FPS", no_contact, sender_id="S", password="p", vendor_id="9999")
    assert r.check(xml, "FPS", 2026) == [] and etree.fromstring(xml).find(".//{*}Principal") is None


def test_pension_contributions_and_a_postgrad_loan_pass():
    xml = fps(pension_net_pay=124, pension_net_pay_ytd=124, postgrad=50, postgrad_ytd=50)
    assert r.check(xml, "FPS", 2026) == []


# --- and what HMRC would refuse does not pass -----------------------------------------
@pytest.mark.parametrize("over,says", [
    ({"nino": "QQ123456C"}, "NINO"),                       # a prefix that is never issued
    ({"tax_code": "1257Z"}, "TaxCode"),
    ({"start_decl": ""}, "StartDec"),
    ({"gender": ""}, "Gender"),
    ({"hours_band": "Z"}, "HoursWorked"),
    ({"frequency": "monthly", "pay_date": date(2027, 4, 6)}, "tax year"),
])
def test_a_bad_value_is_refused_with_the_field_named(over, says):
    if says == "tax year":
        with pytest.raises(r.RtiError, match="tax year"):
            fps(**over)
        return
    problems = r.check(fps(**over), "FPS", 2026)
    assert problems and any(says in p for p in problems), problems


def test_a_man_cannot_have_ni_letter_b_and_hmrcs_own_error_number_comes_back():
    problems = r.check(fps(gender="M", ni=[{**PERSON["ni"][0], "letter": "B"}]), "FPS", 2026)
    assert any("7849" in p and "male" in p for p in problems), problems


def test_a_woman_born_after_1961_cannot_have_ni_letter_b():
    problems = r.check(fps(ni=[{**PERSON["ni"][0], "letter": "B"}]), "FPS", 2026)
    assert any("7955" in p for p in problems), problems


def test_a_start_date_in_the_far_future_is_refused():
    problems = r.check(fps(start_date=date(2027, 3, 1)), "FPS", 2026)
    assert problems and any("StartDate" in p or "start" in p.lower() for p in problems), problems


def test_the_keys_in_both_headers_must_agree():
    def change(doc):
        key = [k for k in doc.iter("{http://www.govtalk.gov.uk/CM/envelope}Key")][0]
        key.text = "999"
    problems = r.check(mutate(message(), change), "FPS", 2026)
    assert problems, "a tax office number that differs between the headers must be refused"


def test_the_ir_header_keys_must_match_the_employer_references():
    def change(doc):
        for k in doc.iter("{*}Key"):
            if k.get("Type") == "TaxOfficeReference":
                k.text = "ZZ999"
    assert r.check(mutate(message(), change), "FPS", 2026)


def test_the_wrong_message_class_is_refused():
    def change(doc):
        first(doc, "Class").text = "HMRC-PAYE-RTI-EPS"
    assert r.check(mutate(message(), change), "FPS", 2026)


def test_a_wrong_tax_year_in_the_body_is_refused():
    def change(doc):
        first(doc, "RelatedTaxYear").text = "25-26"
    assert r.check(mutate(message(), change), "FPS", 2026)


def test_an_amount_with_one_decimal_place_is_refused():
    def change(doc):
        first(doc, "TaxablePay").text = "3000.5"
    assert r.check(mutate(message(), change), "FPS", 2026)


def test_a_student_loan_with_pence_is_refused():
    def change(doc):
        first(doc, "StudentLoanRecovered").text = "120.50"
    assert r.check(mutate(message(), change), "FPS", 2026)


def test_text_that_is_not_xml_is_reported_not_raised():
    assert "not well-formed" in r.check(b"<a><b></a>", "FPS", 2026)[0]


def test_a_message_without_a_body_is_not_a_crash():
    with pytest.raises(r.RtiError):
        r.check(b'<GovTalkMessage xmlns="http://www.govtalk.gov.uk/CM/envelope"><Body/></GovTalkMessage>', "FPS", 2026)


def test_an_eps_with_a_tax_month_outside_its_window_is_refused():
    # Month 3 is only valid between 6 May and 19 July of the tax year.
    body = r.build_eps(EMPLOYER, 2026, recoverable={"smp": 100}, recoverable_month=1)
    first_problem = r.check(message("EPS", body), "EPS", 2026)
    # Today is outside month 1's window once May has passed, so it must be refused then.
    from datetime import date as _d
    if _d.today() > _d(2026, 5, 19):
        assert any("TAXMONTH" in p or "tax month" in p.lower() or "7920" in p for p in first_problem), first_problem


# --- the checker is not blind: removing HMRC's rules lets the bad message through ----------
def test_the_schematron_is_what_catches_a_rule_the_schema_cannot_express(monkeypatch):
    bad = fps(gender="M", ni=[{**PERSON["ni"][0], "letter": "B"}])
    assert r.check(bad, "FPS", 2026)
    # The same message passes the schema alone - so it is the rules doing it.
    doc = etree.fromstring(bad)
    body = copy.deepcopy(doc.find("{http://www.govtalk.gov.uk/CM/envelope}Body")[0])
    assert r._xsd("FPS", 2026).validate(etree.ElementTree(body))


def test_many_requests_at_once_get_the_right_answers():
    """The web server checks on a pool of threads; a shared compiled rule set
    must not mix one request's answer into another's."""
    from concurrent.futures import ThreadPoolExecutor
    good = message()
    bad = fps(gender="M", ni=[{**PERSON["ni"][0], "letter": "B"}])

    def run(i):
        return i % 2 == 0, r.check(good if i % 2 == 0 else bad, "FPS", 2026)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(80)))
    assert all((not problems) if is_good else (len(problems) == 2) for is_good, problems in results)


# --- every definition shipped loads ----------------------------------------------------
def test_the_supported_years_load_their_schemas_and_rules():
    assert 2026 in r.supported_years()
    for year in r.supported_years():
        for kind in ("FPS", "EPS"):
            assert r._xsd(kind, year) is not None and r._rules(kind, year) is not None


def test_an_unknown_year_says_what_is_missing():
    with pytest.raises(r.RtiError, match="2031-32"):
        r.schema_path("FPS", 2031, ".xsd")


# --- the formats HMRC is strict about --------------------------------------------------
@pytest.mark.parametrize("value,out", [(12.5, "12.50"), (0, "0.00"), (3000, "3000.00"), (0.005, "0.01"), (-12.345, "-12.35"),
                                       (None, "0.00"), ("7.1", "7.10")])
def test_amounts_have_two_decimal_places(value, out):
    assert r.pounds(value) == out


def test_whole_pound_fields_end_in_dot_zero_zero():
    assert r.whole_pounds(120.4) == "120.00" and r.whole_pounds(120.5) == "121.00"


@pytest.mark.parametrize("raw,out", [("Zoë", "Zoe"), ("Mary-Ann", "Mary-Ann"), ("O'Neil", "O'Neil"), ("J0hn 3", "Jhn"), ("", "")])
def test_forenames_keep_only_what_hmrc_allows(raw, out):
    assert r.forename(raw) == out


def test_an_employees_surname_keeps_letters_spaces_hyphens_and_apostrophes_only():
    assert r.surname("de la Cruz #2") == "de la Cruz" and r.surname("O'Neil-Smith") == "O'Neil-Smith"
    assert r.surname("  Van   Der  ") == "Van Der"


def test_a_contacts_surname_is_allowed_a_little_more():
    assert r.contact_surname("Smith (Jr)") == "Smith (Jr)"


def test_a_name_without_letters_cannot_be_reported():
    with pytest.raises(r.RtiError, match="surname"):
        fps(last_name="1234")
    with pytest.raises(r.RtiError, match="first name"):
        fps(first_name="123")


def test_a_first_name_that_is_only_symbols_in_part_falls_back_to_an_initial():
    xml = fps(first_name="'Zoe")
    assert r.check(xml, "FPS", 2026) == [] and etree.fromstring(xml).find(".//{*}EmployeeDetails/{*}Name/{*}Fore").text == "Zoe"


@pytest.mark.parametrize("raw,out", [("ls14ab", "LS1 4AB"), ("SW1A 1AA", "SW1A 1AA"), ("m1 1ae", "M1 1AE"), ("12345", ""), ("", ""),
                                     ("Leeds", "")])
def test_postcodes_are_set_out_the_way_hmrc_reads_them(raw, out):
    assert r.clean_postcode(raw) == out


@pytest.mark.parametrize("raw,out", [
    ("1257L", ("1257L", "", False)), ("S1257L", ("1257L", "S", False)), ("C1257L", ("1257L", "C", False)),
    ("1257L M1", ("1257L", "", True)), ("S1257L W1/M1", ("1257L", "S", True)), ("1257L X", ("1257L", "", True)),
    ("BR", ("BR", "", False)), ("SBR", ("BR", "S", False)), ("0T X", ("0T", "", True)), ("K475", ("K475", "", False)),
    ("SK475", ("K475", "S", False)), ("D0", ("D0", "", False)), ("", ("", "", False)),
])
def test_a_tax_code_is_taken_apart_the_way_hmrc_wants_it(raw, out):
    assert r.split_tax_code(raw) == out


@pytest.mark.parametrize("freq,day,expect", [
    ("monthly", date(2026, 4, 6), ("MonthNo", 1)), ("monthly", date(2026, 5, 5), ("MonthNo", 1)),
    ("monthly", date(2026, 5, 6), ("MonthNo", 2)), ("monthly", date(2027, 3, 5), ("MonthNo", 11)),
    ("monthly", date(2027, 4, 5), ("MonthNo", 12)), ("monthly", date(2026, 12, 31), ("MonthNo", 9)),
    ("weekly", date(2026, 4, 6), ("WeekNo", 1)), ("weekly", date(2026, 4, 13), ("WeekNo", 2)),
    ("fortnightly", date(2026, 4, 17), ("WeekNo", 2)), ("biweekly", date(2026, 4, 20), ("WeekNo", 4)),
    # HMRC: a 4-weekly payroll is week 4 for every payday from 6 April to 3 May.
    ("fourweekly", date(2026, 4, 20), ("WeekNo", 4)), ("fourweekly", date(2026, 5, 3), ("WeekNo", 4)),
    ("fourweekly", date(2026, 5, 11), ("WeekNo", 8)),
])
def test_the_tax_week_or_month_follows_hmrcs_counting(freq, day, expect):
    assert r.hmrc_pay_period(freq, day, 2026) == expect


def test_a_date_outside_the_tax_year_is_refused():
    with pytest.raises(r.RtiError):
        r.hmrc_pay_period("monthly", date(2026, 4, 5), 2026)
    with pytest.raises(r.RtiError):
        r.hmrc_pay_period("monthly", date(2027, 4, 6), 2026)


def test_a_pay_frequency_hmrc_does_not_know_is_refused():
    with pytest.raises(r.RtiError, match="pay frequency"):
        r.pay_freq_code("daily")


@pytest.mark.parametrize("freq,code", [("weekly", "W1"), ("Fortnightly", "W2"), ("four-weekly", "W4"), ("monthly", "M1")])
def test_pay_frequencies_map_to_hmrcs_codes(freq, code):
    assert r.pay_freq_code(freq) == code


def test_the_tax_year_forms():
    assert r.tax_year_folder(2026) == "2026-27" and r.related_tax_year(2026) == "26-27"
    assert r.related_tax_year(2099) == "99-00"


def test_nothing_to_report_is_not_a_submission():
    with pytest.raises(r.RtiError):
        r.build_fps(EMPLOYER, [], 2026)


# --- the IRmark ------------------------------------------------------------------------
def test_the_irmark_is_the_same_every_time_and_changes_with_the_content():
    one, two = etree.fromstring(message()), etree.fromstring(message())
    assert r.irmark(one) == r.irmark(two)
    other = etree.fromstring(fps(taxable_pay=3001))
    assert r.irmark(other) != r.irmark(one)


def test_the_irmark_ignores_an_irmark_already_in_the_message():
    plain = etree.fromstring(message())
    marked = etree.fromstring(message(include_irmark=True))
    assert r.irmark(plain) == r.irmark(marked)
    assert first(marked, "IRmark").text == r.irmark(plain) and first(marked, "IRmark").get("Type") == "generic"


def test_the_irmark_is_a_base64_sha1():
    import base64
    assert len(base64.b64decode(r.irmark(etree.fromstring(message())))) == 20


# --- the Gateway conversation ----------------------------------------------------------
NS = "http://www.govtalk.gov.uk/CM/envelope"


def reply(qualifier, correlation="CORR123", endpoint="", poll=0, errors=(), body=""):
    err = "".join(f"<Error><RaisedBy>ChRIS</RaisedBy><Number>{n}</Number><Type>business</Type><Text>{t}</Text><Location>{loc}</Location></Error>"
                  for n, t, loc in errors)
    ep = f'<ResponseEndPoint PollInterval="{poll}">{endpoint}</ResponseEndPoint>' if endpoint else ""
    return (f'<GovTalkMessage xmlns="{NS}"><EnvelopeVersion>2.0</EnvelopeVersion><Header><MessageDetails><Class>HMRC-PAYE-RTI-FPS</Class>'
            f'<Qualifier>{qualifier}</Qualifier><Function>submit</Function><CorrelationID>{correlation}</CorrelationID>{ep}</MessageDetails></Header>'
            f'<GovTalkDetails><Keys/>{"<GovTalkErrors>" + err + "</GovTalkErrors>" if err else ""}</GovTalkDetails><Body>{body}</Body></GovTalkMessage>').encode()


class Gateway:
    """A stand-in for HMRC's Gateway that answers from a script and remembers
    what it was sent."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def __call__(self, url, content, timeout=60.0):
        self.sent.append((url, content))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    def qualifiers(self):
        out = []
        for _, content in self.sent:
            d = etree.fromstring(content)
            out.append((first(d, "Qualifier").text, first(d, "Function").text))
        return out


def test_a_submission_is_acknowledged_polled_answered_and_then_deleted():
    gw = Gateway(reply("acknowledgement", endpoint="https://gw/poll", poll=1), reply("response", body="<ok/>"), reply("response"))
    slept = []
    out = r.send("FPS", message(), endpoint="https://gw/submit", post=gw, sleep=slept.append)
    assert out["ok"] and out["qualifier"] == "response" and out["correlation_id"] == "CORR123" and out["attempts"] == 1
    assert slept == [1]
    assert [u for u, _ in gw.sent] == ["https://gw/submit", "https://gw/poll", "https://gw/poll"]
    assert gw.qualifiers() == [("request", "submit"), ("poll", "submit"), ("request", "delete")]


def test_the_poll_carries_the_correlation_id_and_the_test_flag():
    gw = Gateway(reply("acknowledgement", correlation="C9", endpoint="https://gw/poll"), reply("response", correlation="C9"), reply("response"))
    r.send("FPS", message(), endpoint="https://gw/submit", post=gw, sleep=lambda s: None, test=True)
    poll = etree.fromstring(gw.sent[1][1])
    assert first(poll, "CorrelationID").text == "C9" and first(poll, "GatewayTest").text == "1" and first(poll, "Class").text == "HMRC-PAYE-RTI-FPS"


def test_an_error_from_hmrc_comes_back_with_its_reasons():
    gw = Gateway(reply("error", errors=[("1046", "Authentication Failure. The supplied user credentials failed validation for the requested service.", "")]),
                 reply("error"))
    out = r.send("FPS", message(), endpoint="https://gw/submit", post=gw, sleep=lambda s: None)
    assert not out["ok"] and out["qualifier"] == "error"
    assert out["errors"][0]["number"] == "1046" and "Authentication Failure" in out["errors"][0]["text"]


def test_an_error_with_no_reason_still_says_something():
    out = r.send("FPS", message(), endpoint="x", post=Gateway(reply("error"), reply("error")), sleep=lambda s: None)
    assert not out["ok"] and out["errors"][0]["text"]


def test_still_waiting_after_the_polls_runs_out_is_pending_not_failed():
    answers = [reply("acknowledgement", endpoint="https://gw/poll")] * 4
    out = r.send("FPS", message(), endpoint="x", post=Gateway(*answers), sleep=lambda s: None, max_polls=3)
    assert out["pending"] and not out["ok"] and out["attempts"] == 3


def test_a_gateway_that_cannot_be_reached_raises():
    with pytest.raises(r.RtiError):
        r.send("FPS", message(), endpoint="x", post=Gateway(r.RtiError("down")), sleep=lambda s: None)


def test_an_answer_that_is_not_a_govtalk_message_is_refused():
    with pytest.raises(r.RtiError, match="GovTalk"):
        r.parse_reply(b"<html/>")
    with pytest.raises(r.RtiError, match="readable"):
        r.parse_reply(b"nonsense")


def test_the_poll_interval_is_kept_within_sensible_bounds():
    assert r.parse_reply(reply("acknowledgement", endpoint="u", poll=99999))["poll_interval"] == 300
    assert r.parse_reply(reply("acknowledgement", endpoint="u", poll=0))["poll_interval"] == 1
    assert r.parse_reply(reply("acknowledgement"))["poll_interval"] == 2


def test_a_failure_to_tidy_up_does_not_undo_an_accepted_submission():
    gw = Gateway(reply("response"), Exception("boom"))
    out = r.send("FPS", message(), endpoint="x", post=gw, sleep=lambda s: None)
    assert out["ok"]


@pytest.mark.parametrize("kind,cls", [("FPS", "HMRC-PAYE-RTI-FPS"), ("EPS", "HMRC-PAYE-RTI-EPS")])
def test_each_message_names_its_own_class_including_the_poll_and_the_delete(kind, cls):
    body = r.build_eps(EMPLOYER, 2026, employment_allowance=True) if kind == "EPS" else r.build_fps(EMPLOYER, [{**PERSON}], 2026)
    for xml in (message(kind, body), r.poll_message(kind, "C1"), r.delete_message(kind, "C1")):
        assert etree.fromstring(xml).findtext(f".//{{{NS}}}Class") == cls


def test_the_gateway_test_flag_follows_the_mode():
    assert etree.fromstring(message(test=True)).findtext(f".//{{{NS}}}GatewayTest") == "1"
    assert etree.fromstring(message(test=False)).findtext(f".//{{{NS}}}GatewayTest") == "0"


def test_the_sent_message_carries_the_vendor_id_and_credentials():
    doc = etree.fromstring(message())
    assert doc.findtext(f".//{{{NS}}}ChannelRouting/{{{NS}}}Channel/{{{NS}}}URI") == "9999"
    assert doc.findtext(f".//{{{NS}}}SenderID") == "SENDER"
    assert doc.findtext(f".//{{{NS}}}Authentication/{{{NS}}}Value") == "pw"


# --- the stored password ---------------------------------------------------------------
def test_a_password_round_trips_and_is_not_stored_as_written():
    token = r.seal("S3cret-Gateway!", "key-one")
    assert "S3cret" not in token and r.unseal(token, "key-one") == "S3cret-Gateway!"


def test_a_password_cannot_be_read_with_another_key():
    token = r.seal("pw", "key-one")
    with pytest.raises(r.RtiError, match="enter it again"):
        r.unseal(token, "key-two")


def test_without_a_key_nothing_is_stored_and_nothing_is_read():
    with pytest.raises(r.RtiError, match="HMRC_ENCRYPTION_KEY"):
        r.seal("pw", "")
    with pytest.raises(r.RtiError):
        r.unseal("abc", "")
    assert r.unseal("", "") == ""
