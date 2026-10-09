"""HMRC's definition files are HMRC's. If one is edited, or git converts its
line endings, a filing could pass our check and be refused by HMRC (or the
reverse), so each is held to the hash it had when downloaded."""
import hashlib
import os

import pytest

import hmrc_rti


def folders():
    return [os.path.join(hmrc_rti.RIM_DIR, d) for d in sorted(os.listdir(hmrc_rti.RIM_DIR)) if os.path.isdir(os.path.join(hmrc_rti.RIM_DIR, d))]


def test_there_is_a_folder_for_each_supported_year():
    assert folders() and all(os.path.exists(os.path.join(f, "SHA256SUMS")) for f in folders())


@pytest.mark.parametrize("folder", folders())
def test_every_file_is_exactly_as_downloaded(folder):
    listed = {}
    for line in open(os.path.join(folder, "SHA256SUMS"), encoding="utf-8"):
        line = line.strip()
        if line:
            digest, name = line.split(None, 1)
            listed[name.lstrip("*")] = digest
    on_disk = {n for n in os.listdir(folder) if n.endswith((".xsd", ".xslt", ".sch"))}
    assert set(listed) == on_disk, "a definition file was added or removed without updating SHA256SUMS"
    for name, digest in listed.items():
        with open(os.path.join(folder, name), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == digest, f"{name} is not the file HMRC published"


def test_each_year_has_both_filings():
    for year in hmrc_rti.supported_years():
        for kind in ("FPS", "EPS"):
            for ext in (".xsd", ".xslt", ".sch"):
                assert os.path.exists(hmrc_rti.schema_path(kind, year, ext))
