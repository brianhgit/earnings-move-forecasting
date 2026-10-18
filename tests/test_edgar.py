"""data/edgar.py. Offline: fake SEC JSON in a temp folder, no network."""

import json

import pandas as pd
import pytest

from btb.data import edgar
from btb.schema import validate

MAIN = "CIK0000000042.json"
PAGE = "CIK0000000042-submissions-001.json"


def _cols(rows):
    """rows of (form, items, acceptanceDateTime, accessionNumber) -> SEC parallel lists."""
    return {"form": [r[0] for r in rows], "items": [r[1] for r in rows],
            "acceptanceDateTime": [r[2] for r in rows], "accessionNumber": [r[3] for r in rows]}


def _write_snapshot(folder):
    recent = _cols([
        ("8-K", "2.02,9.01", "2024-07-18T20:01:22.000Z", "A-summer"),     # EDT: 16:01
        ("8-K", "2.02", "2024-01-23T21:05:00.000Z", "A-winter"),          # EST: 16:05
        ("8-K/A", "2.02,9.01", "2024-07-19T20:00:00.000Z", "A-amend"),    # amendment
        ("8-K", "12.02,9.01", "2024-05-01T20:00:00.000Z", "A-12.02"),     # not item 2.02
        ("8-K", "5.02", "2024-03-01T20:00:00.000Z", "A-5.02"),            # not earnings
        ("10-Q", "", "2024-07-19T20:00:00.000Z", "A-10q"),
        ("8-K", "2.02", "2019-04-16T20:02:00.000Z", "A-dup"),             # also on the older page
    ])
    older = _cols([
        ("8-K", " 9.01 , 2.02 ", "2019-04-16T20:02:00.000Z", "A-dup"),
        ("8-K", "2.02", "2016-10-17T20:01:00.000Z", "A-2016"),            # before edgar_start
        ("8-K", "2.02", "2017-01-18T21:01:00.000Z", "A-2017"),
    ])
    (folder / MAIN).write_text(json.dumps({"cik": "42", "filings": {"recent": recent, "files": [{"name": PAGE}]}}))
    (folder / PAGE).write_text(json.dumps(older))   # older pages: columns at the top level


def test_parse_filters_dedupes_and_converts(tmp_path):
    _write_snapshot(tmp_path)
    df = edgar.parse_filings(tmp_path)
    validate(df, "filings")
    assert list(df.columns) == ["cik", "accession", "form", "items", "accept_ts_et"]
    assert df["accession"].tolist() == ["A-2017", "A-dup", "A-winter", "A-summer"]   # sorted by time
    assert (df["cik"] == 42).all() and df["cik"].dtype == "int64"
    assert (df["form"] == "8-K").all()
    ts = df.set_index("accession")["accept_ts_et"]
    assert ts["A-summer"] == pd.Timestamp("2024-07-18 16:01:22")
    assert ts["A-winter"] == pd.Timestamp("2024-01-23 16:05:00")
    assert ts["A-2017"] == pd.Timestamp("2017-01-18 16:01:00")
    assert df["accept_ts_et"].dt.tz is None


def test_parse_eastern_setting_keeps_wall_clock(tmp_path, monkeypatch):
    _write_snapshot(tmp_path)
    monkeypatch.setattr(edgar, "ACCEPTANCE_TZ", "America/New_York")
    ts = edgar.parse_filings(tmp_path).set_index("accession")["accept_ts_et"]
    assert ts["A-summer"] == pd.Timestamp("2024-07-18 20:01:22")


def test_parse_refuses_unset_timezone(tmp_path, monkeypatch):
    _write_snapshot(tmp_path)
    monkeypatch.setattr(edgar, "ACCEPTANCE_TZ", None)
    with pytest.raises(ValueError):
        edgar.parse_filings(tmp_path)


def test_parse_empty_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        edgar.parse_filings(tmp_path)


class _FakeResponse:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode()
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_download_saves_main_and_older_pages_and_never_overwrites(tmp_path, monkeypatch):
    calls = []

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, timeout):
            calls.append((url, self.headers.get("User-Agent")))
            if url.endswith(MAIN):
                return _FakeResponse({"cik": "42", "filings": {"recent": _cols([]), "files": [{"name": PAGE}]}})
            return _FakeResponse(_cols([]))

    monkeypatch.setattr(edgar, "RAW", tmp_path)
    monkeypatch.setattr(edgar.requests, "Session", FakeSession)
    monkeypatch.setattr(edgar.time, "sleep", lambda s: None)

    edgar.download("20240101", [42])
    folder = tmp_path / "edgar" / "20240101"
    assert sorted(p.name for p in folder.iterdir()) == sorted([MAIN, PAGE])
    assert [u for u, _ in calls] == [f"{edgar.BASE_URL}/{MAIN}", f"{edgar.BASE_URL}/{PAGE}"]
    assert all(ua == edgar.USER_AGENT for _, ua in calls)

    with pytest.raises(FileExistsError):
        edgar.download("20240101", [42])
