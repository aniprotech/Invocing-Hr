# HMRC payroll filing definitions (RTI)

The files in `rim/<tax year>/` are **HMRC's, unmodified**. They are what
`backend/hmrc_rti.py` checks every Full Payment Submission and Employer Payment
Summary against before it can be sent: the XML Schema (`.xsd`) for the shape of
a message, and the Schematron business rules (`.sch`, compiled by HMRC to
`.xslt`) for the rules HMRC applies at its end.

`rim/2026-27/SHA256SUMS` records the hash of each file as downloaded; a test
fails if any file differs, so a stray edit or a line-ending conversion is
caught (`.gitattributes` stops git converting them).

## Where they came from

GOV.UK, *Real Time Information: Release Information Pack*, published by HMRC.

| What | Source |
|---|---|
| RTI Release Information Pack, 2026-27, v1.0 (`RTI-RIM-2027-v1-0.zip`, sha256 `e6768cec…89a32`) | https://assets.publishing.service.gov.uk/media/689313c9a34b939141463fa2/RTI-RIM-2027-v1-0.zip |
| RTI Data Item Guide 2026-27, v1.0 | https://assets.publishing.service.gov.uk/media/68c969d107d9e92bc5517b81/RTI-Data-Item-Guide-2026-2027-v1-0.odt |

The pack (`RTI-RIM-2027-v1-0.zip`) holds `FullPaymentSubmission-2027-v1-0`,
`EmployerPaymentSummary-2027-v1-0`, `NINOverificationRequest-v1-2` and
`envelope-v2-0-HMRC.xsd`. The zip, the specification PDF and the data item guide
are not kept in git (they are large and add nothing at runtime); re-download them
from the addresses above.

`envelope-v2-0-HMRC.xsd` is kept for reference but is not loaded: it imports the
W3C XML-signature schema from a web address, and the platform does not fetch
anything at run time. The envelope is built by `hmrc_rti.govtalk_message`, and
HMRC's own rules (which read the envelope as well as the body) are run on the
whole message.

## A new tax year

HMRC publishes a new pack each year (for 2027-28 look for `RTI-RIM-2028-…`).
To add it:

1. Download the pack and unzip it.
2. Create `rim/2027-28/` and copy in that year's `FullPaymentSubmission-…` and
   `EmployerPaymentSummary-…` `.xsd`, `.xslt` and `.sch`.
3. `cd rim/2027-28 && sha256sum *.xsd *.xslt *.sch > SHA256SUMS`
4. Check the *RTI schema changes* note HMRC publishes alongside it, and update
   `hmrc_rti.py` for any new or changed field.
5. Run the tests.

Until step 2 is done the app says, in its readiness list, that the new year's
definitions are not installed, and will not send for that year.
