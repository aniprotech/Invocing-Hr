# HMRC payroll filings (RTI)

Every UK payday has to be reported to HMRC on or before the day: a **Full Payment
Submission** (who was paid what, tax and National Insurance taken) and, when
there is something that is not a payment, an **Employer Payment Summary**. The
Payroll screen has an **HMRC filings** panel for it (UK payroll only).

The code is in `backend/hmrc_rti.py`; HMRC's own published rules it checks every
message against are in `backend/hmrc/` (see `backend/hmrc/README.md`).

## What works now, and what waits for HMRC

| | |
|---|---|
| Build a Full Payment Submission from a pay day's payslips | works |
| Check it against HMRC's own XML Schema and business rules, naming the person and the field | works - this is the whole of "Check" |
| Employer Payment Summary (a month with no pay, Employment Allowance, statutory pay to recover) | works |
| Send to HMRC, poll for the answer, record it | **built but never run against HMRC** - it needs the Vendor ID and address below |
| The IRmark (a hash HMRC can use to confirm the message was not changed) | **built from HMRC's description, unconfirmed** - leave `HMRC_RTI_IRMARK` off until HMRC's test service accepts it |

Nothing is sent until every item in the panel's list is done. Until then **Check**
still works for any business that has entered its PAYE references.

## One-off: what the platform needs from HMRC

HMRC recognises payroll *software*, not each business. Write to the Software
Developer Support Team, **SDSTeam@hmrc.gov.uk**, say you are building RTI
payroll software, and ask for:

1. a **Vendor ID**
2. test access: a test Government Gateway user ID and password, and the **address
   of the test Gateway** to send to
3. the **recognition test scenarios** you have to pass before the software is
   recognised, and what HMRC wants to see for each
4. whether **live** filing needs recognition first, and how long it takes
   (HMRC's own target is about 10 working days; confirm with them)
5. a check of our **IRmark** against their test service

Then on the Railway service that serves aniprotech.com, add:

```
HMRC_VENDOR_ID=...                 # the Vendor ID from HMRC
HMRC_RTI_ENDPOINT=...              # the Gateway address from HMRC (test first)
HMRC_ENCRYPTION_KEY=...            # any long random string; keeps businesses' Gateway passwords encrypted
HMRC_RTI_MODE=test                 # stays test until HMRC has recognised the software
HMRC_RTI_IRMARK=                   # set to 1 only after HMRC's test service accepts our IRmark
```

`HMRC_ENCRYPTION_KEY` must be set **before** any business saves a Gateway
password, and must not change afterwards, or each business has to enter its
password again. Do not reuse `SECRET_KEY`.

While `HMRC_RTI_MODE=test` the Gateway is told to check and answer without
recording anything, so nothing can reach a real employer's HMRC record.

## Per business: what each employer enters (Payroll > HMRC filings > Your HMRC details)

From the HMRC employer letter or the PAYE for employers online account:

- **Tax office number** - the part of the PAYE reference before the slash (`123` in `123/AB456`)
- **PAYE reference** - the part after it (`AB456`)
- **Accounts Office reference** - like `123PA00012345`
- **Government Gateway user ID and password** for PAYE for employers online
- a **contact** name, email and phone

And on each employee (UK payroll): **NI number, date of birth, gender (M or F),
usual weekly hours (a band A to E), a home address/postcode**, and for a new
starter the **starter declaration (A, B or C)**.

## A new tax year

HMRC publishes a new pack each April. Until `backend/hmrc/rim/<year>/` has it
(steps in `backend/hmrc/README.md`) the panel says the new year's definitions are
not installed and nothing is sent for that year.

## Not covered yet

Statutory pay (SMP, SPP, SAP) on the payslip, payrolled benefits and company
cars, seconded or occupational-pension starters, employees with more than one
job under one PAYE scheme, foreign addresses, corrections to an earlier year,
and NI number verification. The panel lists these too.
