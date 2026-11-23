"""Offline regressions for owner-allowlisted Hunter source validation.

No network, S03, model, scheduler, or native worker access.
"""
import contextlib
import io
import json
import sqlite3
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from pathlib import Path
import tempfile
import unittest

import nox_hunter as hunter


class HunterURLSafetyTests(unittest.TestCase):
    def test_malformed_urls_are_typed_holds(self):
        for value in (
            "https://[bad/rss",           # urlsplit raises ValueError
            "https://example.org:bad/rss", # .port raises ValueError
            "https://example.org:99999/rss",
            "https://localhost./rss",
            "https://127.0.0.1./rss",
            "https://10.10.10.10./rss",
            "https://0177.0.0.1/rss",
            "https://2130706433/rss",
            "https://0x7f000001/rss",
            "https://@example.org/rss",    # empty userinfo is still forbidden
            "https://example.org/rs\nss", # urllib otherwise strips LF
            "https://example.org/rs\tss",
            42, None,
        ):
            with self.subTest(value=value), self.assertRaises(hunter.HunterError):
                hunter._canonical_url(value)

    def test_idna_aliases_cannot_reach_private_or_local_hosts(self):
        # Resolver IDNA normalization can turn these into loopback endpoints.
        for hostname in (
            "127。0。0。1", "127．0．0．1", "127｡0｡0｡1",
            "ⅼocalhost", "localhost。", "0x7f．0．0．1",
        ):
            with self.subTest(hostname=hostname), self.assertRaises(hunter.HunterError):
                hunter._canonical_url("https://" + hostname + "/rss")

    def test_unicode_allowlisted_public_domain_uses_exact_ascii_idna(self):
        source = hunter._validate_source({
            "id": "idnfeed", "kind": "rss", "url": "https://bücher.example/feed",
            "allowed_hosts": ["bücher.example"], "interval_seconds": 3600,
        })
        self.assertEqual(source["url"], "https://xn--bcher-kva.example/feed")
        self.assertEqual(source["allowed_hosts"], ["xn--bcher-kva.example"])
        with self.assertRaises(hunter.HunterError):
            hunter._validate_url("https://buсher.example/feed", source["allowed_hosts"])

    def test_valid_https_and_tracking_dedup_still_work(self):
        value = hunter._canonical_url("https://example.org/rss?utm_source=x&a=1")
        self.assertEqual(value, "https://example.org/rss?a=1")
        self.assertEqual(
            hunter._canonical_url("https://EXAMPLE.ORG./rss?utm_source=x&a=1"),
            "https://example.org/rss?a=1",
        )

    def test_unhashable_source_kind_is_typed_hold(self):
        base = {"id": "feed", "url": "https://example.org/rss",
                "kind": [], "allowed_hosts": ["example.org"], "interval_seconds": 3600}
        with self.assertRaises(hunter.HunterError):
            hunter._validate_source(base)

    def test_invalid_candidate_links_are_quarantined_not_attributed_to_feed(self):
        source = hunter._validate_source({
            "id": "feed", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        parsed = [
            {"title": "valid", "url": "/article", "content": "verified-link candidate", "published": "2026-11-20"},
            {"title": "missing", "url": "", "content": "should not be from feed homepage", "published": ""},
            {"title": "unsafe", "url": "javascript:alert(1)", "content": "unsafe", "published": ""},
            {"title": "userinfo", "url": "https://name:password@example.org/post", "content": "unsafe", "published": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"stub", None, None, "application/rss+xml", False)), \
                 patch.object(hunter, "_parse", return_value=parsed):
                out = hunter.poll_due([source], state, now=1000.0)
                self.assertEqual(out[0]["added"], 1)
                self.assertEqual(out[0]["quarantined"], 3)
                # A second due poll deduplicates; no forged feed-source row.
                out2 = hunter.poll_due([source], state, now=1100.0)
                self.assertEqual(out2[0]["added"], 0)
            with sqlite3.connect(state) as conn:
                rows = conn.execute("SELECT item_url FROM items ORDER BY item_url").fetchall()
                rejected = conn.execute("SELECT item_digest, reason FROM item_quarantine").fetchall()
            self.assertEqual(rows, [("https://example.org/article",)])
            self.assertEqual(len(rejected), 3)
            self.assertTrue(all(len(digest) == 64 and reason == "INVALID_ITEM_URL"
                                for digest, reason in rejected))
            self.assertFalse(any("password" in repr(row) for row in rejected))

    def test_atom_enclosure_or_self_cannot_impersonate_article_provenance(self):
        source = hunter._validate_source({
            "id": "atom", "kind": "atom", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom">'
                b'<entry><title>Attachment only</title>'
                b'<link rel="enclosure" href="https://example.org/file.zip"/></entry>'
                b'<entry><title>Self only</title>'
                b'<link rel="self" href="https://example.org/api/item"/></entry>'
                b'<entry><title>Actual article</title>'
                b'<link rel="enclosure" href="https://example.org/other.zip"/>'
                b'<link rel="alternate" href="https://example.org/article"/></entry>'
                b'</feed>')
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(
                    feed, None, None, "application/atom+xml", False)):
                result = hunter.poll_due([source], state, now=1000.0)[0]
            self.assertEqual((result["added"], result["quarantined"]), (1, 2))
            with sqlite3.connect(state) as conn:
                saved = conn.execute("SELECT title,item_url FROM items").fetchall()
            self.assertEqual(saved, [("Actual article", "https://example.org/article")])
        # Preserve RSS's unqualified text-only <link> convention.
        rss = (b'<rss><channel><item><title>RSS article</title>'
               b'<link>https://example.org/rss-item</link></item></channel></rss>')
        self.assertEqual(hunter._feed_items(rss)[0]["url"],
                         "https://example.org/rss-item")

    def test_atom_binary_alternate_is_not_article_provenance(self):
        # An Atom exporter may advertise a ZIP as rel=alternate. Its declared
        # media type is not a citable article; prefer a later HTML alternate,
        # and quarantine entries that contain only a binary link.
        source = hunter._validate_source({
            "id": "atom-media", "kind": "atom",
            "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom">'
                b'<entry><title>Archive only</title>'
                b'<link rel="alternate" type="application/zip" '
                b'href="https://example.org/export.zip"/></entry>'
                b'<entry><title>Real article</title>'
                b'<link rel="alternate" type="application/octet-stream" '
                b'href="https://example.org/data.bin"/>'
                b'<link rel="alternate" type="text/html; charset=utf-8" '
                b'href="https://example.org/article"/></entry>'
                b'<entry><title>Paper PDF</title>'
                b'<link rel="alternate" type="application/pdf" '
                b'href="https://example.org/paper.pdf"/></entry>'
                b'</feed>')
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(
                    feed, None, None, "application/atom+xml", False)):
                result = hunter.poll_due([source], state, now=1000.0)[0]
            self.assertEqual((result["added"], result["quarantined"]), (2, 1))
            with sqlite3.connect(state) as conn:
                saved = conn.execute(
                    "SELECT title,item_url FROM items ORDER BY title").fetchall()
            self.assertEqual(saved, [
                ("Paper PDF", "https://example.org/paper.pdf"),
                ("Real article", "https://example.org/article"),
            ])

    def test_untyped_artifact_links_quarantine_without_poisoning_publications(self):
        # Alternate != article: real Atom feeds omit type, and RSS links can
        # point straight at ZIPs. A query suffix must not disguise the path.
        source = hunter._validate_source({
            "id": "atom-artifacts", "kind": "atom",
            "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom">'
                b'<entry><title>ZIP only</title><link rel="alternate" '
                b'href="https://example.org/build.ZIP?download=1"/></entry>'
                b'<entry><title>HTML fallback</title><link rel="alternate" '
                b'href="/weights.gguf"/><link rel="alternate" '
                b'href="/article"/></entry>'
                b'<entry><title>Paper PDF</title><link rel="alternate" '
                b'href="/paper.pdf"/></entry>'
                b'</feed>')
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(
                    feed, None, None, "application/atom+xml", False)):
                result = hunter.poll_due([source], db, now=1000.0)[0]
            self.assertEqual((result["added"], result["quarantined"]), (2, 1))
            with sqlite3.connect(db) as conn:
                rows = conn.execute("SELECT title,item_url FROM items ORDER BY title").fetchall()
            self.assertEqual(rows, [
                ("HTML fallback", "https://example.org/article"),
                ("Paper PDF", "https://example.org/paper.pdf"),
            ])
        # The item-level fence applies to RSS, GitHub and Crossref candidates too.
        for suffix in ("/media.zip", "/weights.GGUF?raw=1", "/installer.exe"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                    hunter.HunterError, "binary artifact"):
                hunter._item_record(source, {
                    "title": "Not an article", "url": suffix,
                    "content": "Must not become provenance", "published": "",
                }, 1000.0)

    def test_json_surrogates_quarantine_only_bad_candidates(self):
        # A legal JSON escape can decode to an invalid lone surrogate.
        # Source config fails cleanly, while malformed feed items are
        # quarantined without undoing a valid candidate in the same poll.
        invalid = chr(0xD800)
        with self.assertRaises(hunter.HunterError):
            hunter._canonical_url("https://example.org/rss?bad=" + invalid)
        source = hunter._validate_source({
            "id": "jsonfeed", "kind": "github_releases",
            "url": "https://example.org/releases",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        decoded = [
            {"title": "valid", "url": "https://example.org/post", "content": "normal", "published": ""},
            {"title": "broken" + invalid, "url": "https://example.org/bad", "content": "raw", "published": ""},
            {"title": "unsafe", "url": "https://example.org/" + invalid, "content": "raw", "published": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"json", None, None, "application/json", False)), \
                 patch.object(hunter, "_parse", return_value=decoded):
                result = hunter.poll_due([source], db, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual((result[0]["added"], result[0]["quarantined"]), (1, 2))
            with sqlite3.connect(db) as conn:
                items = conn.execute("SELECT title FROM items").fetchall()
                holds = conn.execute("SELECT item_digest, reason FROM item_quarantine").fetchall()
            self.assertEqual(items, [("valid",)])
            self.assertEqual(len(holds), 2)
            self.assertTrue(all(len(digest) == 64 and reason == "INVALID_ITEM_URL"
                                for digest, reason in holds))

    def test_invalid_published_unicode_quarantines_only_bad_item(self):
        # GitHub JSON allows escaped lone surrogates in published_at. These
        # must never reach SQLite and roll back a healthy sibling entry.
        bad_date = "2026-" + chr(0xD800)
        source = hunter._validate_source({
            "id": "releases", "kind": "github_releases",
            "url": "https://example.org/releases",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        items = [
            {"title": "healthy", "content": "valid", "url": "/good",
             "published": "2026-11-20"},
            {"title": "broken", "content": "valid", "url": "/bad",
             "published": bad_date},
            {"title": "wrong-date-type", "content": "valid", "url": "/bad-type",
             "published": ["not", "a", "date"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"json", None, None,
                                                               "application/json", False)), \
                 patch.object(hunter, "_parse", return_value=items):
                result = hunter.poll_due([source], db, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual((result[0]["added"], result[0]["quarantined"]), (1, 2))
            with sqlite3.connect(db) as conn:
                saved = conn.execute("SELECT title,published FROM items").fetchall()
                rejected = conn.execute("SELECT item_digest FROM item_quarantine").fetchall()
            self.assertEqual(saved, [("healthy", "2026-11-20")])
            self.assertEqual(len(rejected), 2)
            self.assertTrue(all(len(row[0]) == 64 for row in rejected))

    def test_github_release_metadata_never_fabricates_text_or_dates(self):
        # JSON metadata structures must not turn into Python-repr "evidence";
        # GitHub created_at is not an actual publication event.
        rows = [
            {"name": ["fake"], "tag_name": {"fake": "tag"},
             "html_url": "https://github.com/example/repo/releases/tag/draft",
             "body": {"fake": "notes"}, "created_at": "2026-11-10"},
            {"name": None, "tag_name": " v1.2 ",
             "html_url": "https://github.com/example/repo/releases/tag/v1.2",
             "body": " real notes ", "published_at": "2026-11-20T12:00:00Z"},
            {"name": {"fake": "title"}, "tag_name": [],
             "html_url": [], "body": ["fake", "text"], "created_at": "2026-11-15"},
        ]
        found = hunter._github_items(json.dumps(rows).encode("utf-8"))
        self.assertEqual(found, [
            {"title": "", "url": rows[0]["html_url"], "content": "", "published": ""},
            {"title": "v1.2", "url": rows[1]["html_url"], "content": "real notes",
             "published": "2026-11-20T12:00:00Z"},
        ])

    def test_crossref_empty_or_malformed_titles_are_not_fabricated(self):
        # Crossref title=[] was formerly stored as the literal "[]".
        # Keep URL-only provenance, but never invent a paper title.
        rows = [
            {"DOI": "10.1234/empty", "title": [], "URL": "https://doi.org/10.1234/empty"},
            {"DOI": "10.1234/missing", "URL": "https://doi.org/10.1234/missing"},
            {"DOI": "10.1234/object", "title": {"fake": "title"}, "URL": "https://doi.org/10.1234/object"},
            {"DOI": "10.1234/list", "title": [None, "", "  actual title  "], "URL": "https://doi.org/10.1234/list"},
            {"DOI": "10.1234/scalar", "title": "  real scalar  ", "URL": "https://doi.org/10.1234/scalar"},
        ]
        got = hunter._crossref_items(json.dumps({"message": {"items": rows}}).encode("utf-8"))
        self.assertEqual([item["title"] for item in got], ["", "", "", "actual title", "real scalar"])
        self.assertEqual(len({item["url"] for item in got}), 5)
        self.assertTrue(all(item["published"] == "" for item in got))

    def test_crossref_nontext_doi_and_url_never_fabricate_links(self):
        # JSON arrays/objects are not DOI identifiers or URL strings. Do not
        # turn repr([...]) into a seemingly legitimate doi.org reference.
        rows = [
            {"DOI": ["10.1234/fake"], "title": ["Bad DOI"], "URL": None},
            {"DOI": {"value": "10.1234/fake"}, "title": ["Bad object DOI"], "URL": []},
            {"DOI": "10.1234/real", "title": ["Valid fallback"], "URL": {}},
            {"DOI": "10.1234/override", "title": ["Explicit URL"],
             "URL": "https://doi.org/10.1234/explicit"},
        ]
        got = hunter._crossref_items(json.dumps(
            {"message": {"items": rows}}).encode("utf-8"))
        self.assertEqual([item["title"] for item in got],
                         ["Bad DOI", "Bad object DOI", "Valid fallback", "Explicit URL"])
        self.assertEqual([item["url"] for item in got], [
            "", "", "https://doi.org/10.1234/real",
            "https://doi.org/10.1234/override",
        ])

    def test_crossref_conflicting_url_cannot_override_valid_doi(self):
        # Crossref's DOI is the persistent record identity. Its URL field
        # sometimes points elsewhere or is corrupt; never attribute evidence
        # for DOI A to a different DOI B or an unrelated host.
        rows = [
            {"DOI": "10.1234/actual", "title": ["Actual"],
             "URL": "https://doi.org/10.1234/other"},
            {"DOI": "10.1234/actual-2", "title": ["Publisher"],
             "URL": "https://example.net/unrelated"},
            {"DOI": "10.1234/actual-3", "title": ["Malformed URL"],
             "URL": "https://localhost/private"},
            {"DOI": None, "title": ["URL only"],
             "URL": "https://example.org/no-doi"},
        ]
        got = hunter._crossref_items(json.dumps(
            {"message": {"items": rows}}).encode("utf-8"))
        self.assertEqual([row["url"] for row in got], [
            "https://doi.org/10.1234/actual",
            "https://doi.org/10.1234/actual-2",
            "https://doi.org/10.1234/actual-3",
            "https://example.org/no-doi",
        ])

    def test_crossref_malformed_text_doi_does_not_forge_provenance(self):
        # Reject forged provenance and escape DOI query/fragment delimiters.
        rows = [
            {"DOI": "not-a-doi", "title": ["invalid"]},
            {"DOI": "10.1234", "title": ["missing suffix"]},
            {"DOI": "10.123/id", "title": ["short prefix"]},
            {"DOI": "10.1234/with space", "title": ["whitespace"]},
            {"DOI": "10.1234/" + chr(0xD800), "title": ["invalid Unicode"]},
            {"DOI": " 10.1234/valid ", "title": ["valid"]},
            {"DOI": "10.1234/part?query#fragment", "title": ["escaped delimiters"]},
        ]
        found = hunter._crossref_items(json.dumps(
            {"message": {"items": rows}}).encode("utf-8"))
        self.assertEqual([item["url"] for item in found], [
            "", "", "", "", "",
            "https://doi.org/10.1234/valid",
            "https://doi.org/10.1234/part%3Fquery%23fragment",
        ])

    def test_crossref_nontext_abstract_is_not_fabricated(self):
        # Malformed abstract metadata must not become a Python repr presented
        # as an authentic research abstract. Healthy HTML text still survives.
        rows = [
            {"DOI": "10.1234/object-abstract", "title": ["Object"],
             "abstract": {"fabricated": "claim"}},
            {"DOI": "10.1234/list-abstract", "title": ["List"],
             "abstract": ["fabricated", "claim"]},
            {"DOI": "10.1234/real-abstract", "title": ["Real"],
             "abstract": "<p>Real peer-reviewed abstract</p>"},
        ]
        got = hunter._crossref_items(json.dumps({"message": {"items": rows}}).encode("utf-8"))
        self.assertEqual([item["content"] for item in got],
                         ["", "", "Real peer-reviewed abstract"])
        self.assertEqual(len(got), 3)
        self.assertTrue(all(item["url"].startswith("https://doi.org/") for item in got))

    def test_crossref_malformed_date_parts_preserve_healthy_siblings(self):
        # Bad Crossref dates must not roll back the entire read-only feed.
        # A string cannot be converted into a fake character-by-character date.
        source = hunter._validate_source({
            "id": "crossref", "kind": "crossref",
            "url": "https://api.crossref.org/works",
            "allowed_hosts": ["api.crossref.org"], "interval_seconds": 60,
        })
        rows = [
            {"DOI": "10.1234/valid", "title": ["good"], "URL": "https://doi.org/10.1234/valid",
             "published-online": {"date-parts": [[2026, 11, 20]]}},
            {"DOI": "10.1234/scalar", "title": ["scalar-date"],
             "URL": "https://doi.org/10.1234/scalar",
             "published-online": {"date-parts": [2026]}},
            {"DOI": "10.1234/string", "title": ["string-date"],
             "URL": "https://doi.org/10.1234/string",
             "published-online": {"date-parts": ["2026-11-20"]}},
            {"DOI": "10.1234/invalid-month", "title": ["invalid-month"],
             "URL": "https://doi.org/10.1234/invalid-month",
             "published-online": {"date-parts": [[2026, 99, 20]]}},
            {"DOI": "10.1234/invalid-day", "title": ["invalid-day"],
             "URL": "https://doi.org/10.1234/invalid-day",
             "published-online": {"date-parts": [[2026, 2, 31]]}},
            {"DOI": "10.1234/leap", "title": ["leap"],
             "URL": "https://doi.org/10.1234/leap",
             "published-online": {"date-parts": [[2024, 2, 29]]}},
            {"DOI": "10.1234/normalized", "title": ["normalized"],
             "URL": "https://doi.org/10.1234/normalized",
             "published-online": {"date-parts": [[2026, 2, 3]]}},
            {"DOI": "10.1234/created", "title": ["created-only"],
             "URL": "https://doi.org/10.1234/created",
             "created": {"date-parts": [[2026, 11, 20]]}},
            {"DOI": "10.1234/fallback", "title": ["fallback-online"],
             "URL": "https://doi.org/10.1234/fallback",
             "published-print": {"date-parts": [[2026, 2, 30]]},
             "published-online": {"date-parts": [[2026, 1, 5]]}},
            {"DOI": "10.1234/issued", "title": ["issued-year"],
             "URL": "https://doi.org/10.1234/issued",
             "issued": {"date-parts": [[2025]]}},
        ]
        body = json.dumps({"message": {"items": rows}}).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            with patch.object(hunter, "_fetch", return_value=(body, None, None,
                                                               "application/json", False)):
                result = hunter.poll_due([source], state, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual(result[0]["added"], 10)
            with sqlite3.connect(state) as conn:
                found = conn.execute("SELECT title,published FROM items ORDER BY title").fetchall()
            self.assertEqual(found, [
                ("created-only", ""),
                ("fallback-online", "2026-01-05"),
                ("good", "2026-11-20"),
                ("invalid-day", ""),
                ("invalid-month", ""),
                ("issued-year", "2025"),
                ("leap", "2024-02-29"),
                ("normalized", "2026-02-03"),
                ("scalar-date", ""),
                ("string-date", ""),
            ])

    def test_publication_date_correction_preserves_prior_candidate_version(self):
        # Publication metadata is part of evidence provenance. Preserve both
        # observations even when a feed changes only its publication date.
        source = hunter._validate_source({
            "id": "feed", "kind": "rss", "url": "https://example.org/rss",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        first = {"title": "Stable title", "url": "/article",
                 "content": "Same abstract", "published": "2026-11-20"}
        corrected = {**first, "published": "2026-11-21"}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch",
                              return_value=(b"stub", None, None, "application/rss+xml", False)), \
                 patch.object(hunter, "_parse",
                              side_effect=[[first], [corrected], [corrected]]):
                one = hunter.poll_due([source], state, now=1000.0)
                two = hunter.poll_due([source], state, now=1100.0)
                three = hunter.poll_due([source], state, now=1200.0)
            self.assertEqual([x[0]["added"] for x in (one, two, three)],
                             [1, 1, 0])
            with sqlite3.connect(state) as conn:
                versions = conn.execute(
                    "SELECT published,content_sha256 FROM items "
                    "WHERE source_id='feed' ORDER BY first_seen_at"
                ).fetchall()
            self.assertEqual([v[0] for v in versions],
                             ["2026-11-20", "2026-11-21"])
            self.assertEqual(len({v[1] for v in versions}), 2)

    def test_publication_provenance_upgrade_does_not_duplicate_legacy_rows(self):
        source = hunter._validate_source({
            "id": "feed", "kind": "rss", "url": "https://example.org/rss",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        item = {"title": "Stable", "url": "/article",
                "content": "Abstract", "published": "2026-11-20"}
        old_digest = hunter.hashlib.sha256(b"Stable\nAbstract").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with sqlite3.connect(state) as conn:
                hunter._init_db(conn)
                conn.execute(
                    "INSERT INTO items VALUES(?,?,?,?,?,?,?)",
                    ("feed", "https://example.org/article", old_digest,
                     "Stable", "Abstract", "2026-11-20", 900.0),
                )
                conn.commit()
            with patch.object(hunter, "_fetch",
                              return_value=(b"stub", None, None, "application/rss+xml", False)), \
                 patch.object(hunter, "_parse", side_effect=[[item], [{**item, "published": "2026-11-21"}]]):
                unchanged = hunter.poll_due([source], state, now=1000.0)
                corrected = hunter.poll_due([source], state, now=1100.0)
            self.assertEqual(unchanged[0]["added"], 0)
            self.assertEqual(corrected[0]["added"], 1)
            with sqlite3.connect(state) as conn:
                dates = [x[0] for x in conn.execute(
                    "SELECT published FROM items ORDER BY first_seen_at")]
            self.assertEqual(dates, ["2026-11-20", "2026-11-21"])

    def test_html_page_uses_its_real_source_url(self):
        source = hunter._validate_source({
            "id": "page", "kind": "html_page", "url": "https://example.org/page",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        record = hunter._item_record(source, {"title": "page", "content": "text",
                                               "url": source["url"], "published": ""}, 1000.0)
        self.assertEqual(record[1], source["url"])

    def test_http_error_receipts_redact_urls_and_query_credentials(self):
        canary = "SENSITIVE_QUERY_CANARY_DO_NOT_STORE"
        endpoint = "https://example.org/feed?token=" + canary
        source = hunter._validate_source({
            "id": "sensitive", "kind": "rss", "url": endpoint,
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            failures = [
                (HTTPError(endpoint, 401, "denied " + canary, {}, None),
                 "HTTPError: status=401"),
                (URLError("connection failed for " + endpoint),
                 "URLError: str"),
            ]
            for step, (raised, expected) in enumerate(failures):
                with patch.object(hunter, "_fetch", side_effect=raised):
                    result = hunter.poll_due([source], db, now=1000.0 + step * 600)
                self.assertEqual(result[0]["status"], "error")
                self.assertEqual(result[0]["error"], expected)
                self.assertNotIn(canary, json.dumps(result))
            with sqlite3.connect(db) as conn:
                saved = conn.execute("SELECT last_error FROM source_state WHERE source_id=?",
                                     ("sensitive",)).fetchone()[0]
                self.assertEqual(saved, "URLError: str")
                self.assertNotIn(canary, saved)

    def test_http_304_rechecks_cached_body_against_current_size_budget(self):
        # A smaller later max_bytes must not be bypassed by a 304 cached body.
        source = hunter._validate_source({
            "id": "cached", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        cached = {"body": b"x" * 2048, "etag": "v1",
                  "last_modified": None, "content_type": "application/rss+xml"}
        not_modified = HTTPError(source["url"], 304, "Not Modified", {}, None)
        with patch.object(hunter, "build_opener") as opener:
            opener.return_value.open.side_effect = not_modified
            with self.assertRaisesRegex(hunter.HunterError, "cached response exceeds max_bytes"):
                hunter._fetch(source, cached, max_bytes=1024)
            body, etag, modified, content_type, reused = hunter._fetch(
                source, cached, max_bytes=2048)
        self.assertEqual(body, cached["body"])
        self.assertEqual(etag, "v1")
        self.assertIsNone(modified)
        self.assertEqual(content_type, "application/rss+xml")
        self.assertTrue(reused)

    def test_http_cache_blob_is_lazy_until_304(self):
        # Even a large old BLOB must not be loaded into Python heap on HTTP 200.
        source = hunter._validate_source({
            "id": "lazy", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })

        class FreshResponse:
            headers = {"ETag": "new"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"<rss/>"

        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(str(Path(tmp) / "state.sqlite"))
            conn.row_factory = sqlite3.Row
            try:
                hunter._init_db(conn)
                conn.execute(
                    "INSERT INTO http_cache(source_id,url,etag,last_modified,content_type,"
                    "body,fetched_at,checked_at) VALUES(?,?,?,?,?,?,?,?)",
                    ("lazy", source["url"], "old", None, "application/rss+xml",
                     sqlite3.Binary(b"x" * (2 * 1024 * 1024)), 10, 10),
                )
                conn.commit()
                sql = []
                conn.set_trace_callback(sql.append)
                with patch.object(hunter, "build_opener") as opener, \
                     patch.object(hunter, "_parse", return_value=[]):
                    opener.return_value.open.return_value = FreshResponse()
                    first = hunter._poll_one(conn, source, 1000, 1024)
                    self.assertEqual(first["status"], "polled")
                    self.assertFalse(any("SELECT body FROM http_cache" in q for q in sql))
                    # Revalidating 304 must not update body or amplify the WAL.
                    # An UPDATE OF body trigger makes this a database-level
                    # assertion instead of just checking a SQL string.
                    conn.execute(
                        "CREATE TRIGGER reject_unchanged_body BEFORE UPDATE OF body "
                        "ON http_cache BEGIN SELECT RAISE(ABORT, '304 rewrote body'); END"
                    )
                    sql.clear()
                    opener.return_value.open.side_effect = HTTPError(
                        source["url"], 304, "Not Modified", {}, None)
                    second = hunter._poll_one(conn, source, 1100, 1024)
                    self.assertEqual(second["status"], "not_modified")
                    self.assertEqual(sum("SELECT body FROM http_cache" in q for q in sql), 1)
                body, fetched, checked = conn.execute(
                    "SELECT body,fetched_at,checked_at FROM http_cache "
                    "WHERE source_id='lazy'").fetchone()
                self.assertEqual(body, b"<rss/>")
                self.assertEqual(fetched, 1000)
                self.assertEqual(checked, 1100)
            finally:
                conn.close()

    def test_cli_returns_structured_config_error_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "sources.json"
            state = Path(tmp) / "state.sqlite"
            config.write_text(json.dumps({"schema": hunter.SCHEMA, "sources": [{
                "id": "feed", "kind": "rss", "url": "https://[bad/rss",
                "allowed_hosts": ["example.org"], "interval_seconds": 3600
            }]}), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = hunter.main(["--config", str(config), "--state", str(state)])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(stderr.getvalue())["status"], "config_error")
            self.assertFalse(state.exists())


    def test_late_poll_error_rolls_back_all_candidate_rows_and_cache(self):
        # A parser/normalizer failure after a healthy first item previously
        # returned status=error while committing that first item anyway.
        source = hunter._validate_source({
            "id": "atomic", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        xml = (b"<rss><channel>"
               b"<item><title>first</title><link>https://example.org/1</link></item>"
               b"<item><title>second</title><link>https://example.org/2</link></item>"
               b"</channel></rss>")
        actual_record = hunter._item_record
        calls = [0]

        def fail_second(*args):
            calls[0] += 1
            if calls[0] == 2:
                raise ValueError("synthetic late failure")
            return actual_record(*args)

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            with (patch.object(hunter, "_fetch", return_value=(
                    xml, None, None, "application/rss+xml", False)),
                  patch.object(hunter, "_item_record", side_effect=fail_second)):
                result = hunter.poll_due([source], db, now=1000)[0]
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["added"], 0)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM items").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT count(*) FROM http_cache").fetchone()[0], 0)
                failures, error = conn.execute(
                    "SELECT failures,last_error FROM source_state WHERE source_id='atomic'"
                ).fetchone()
                self.assertEqual(failures, 1)
                self.assertEqual(error, "ValueError")

            with patch.object(hunter, "_fetch", return_value=(
                    xml, None, None, "application/rss+xml", False)):
                healthy = hunter.poll_due([source], db, now=1100)[0]
            self.assertEqual(healthy["status"], "polled")
            self.assertEqual(healthy["added"], 2)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM items").fetchone()[0], 2)
                self.assertEqual(conn.execute("SELECT count(*) FROM http_cache").fetchone()[0], 1)

    def test_oversized_candidate_count_holds_before_partial_persistence(self):
        # Even compact 25 MiB-or-less sources may contain thousands of entries.
        # Reject the whole response: never silently truncate provenance,
        # partially insert candidates or cache an unprocessed feed.
        limit = hunter.MAX_ITEMS_PER_POLL
        over_xml = (b"<rss><channel>" +
                    b"<item><title>x</title><link>https://example.org/x</link></item>" * (limit + 1) +
                    b"</channel></rss>")
        with self.assertRaisesRegex(hunter.HunterError, "item count budget"):
            hunter._feed_items(over_xml)
        over_releases = json.dumps([{"tag_name": "v"}] * (limit + 1)).encode()
        with self.assertRaisesRegex(hunter.HunterError, "item count budget"):
            hunter._github_items(over_releases)
        over_crossref = json.dumps({"message": {"items": [{}] * (limit + 1)}}).encode()
        with self.assertRaisesRegex(hunter.HunterError, "item count budget"):
            hunter._crossref_items(over_crossref)

        source = hunter._validate_source({
            "id": "feed", "kind": "rss", "url": "https://example.org/rss",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(
                over_xml, None, None, "application/rss+xml", False
            )):
                failed = hunter.poll_due([source], state, now=1000)[0]
            self.assertEqual(failed["status"], "error")
            self.assertEqual(failed["error"], "HunterError: source exceeds item count budget")
            with sqlite3.connect(state) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM items").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT count(*) FROM http_cache").fetchone()[0], 0)

            good_xml = (b"<rss><channel><item><title>healthy</title>"
                        b"<link>https://example.org/good</link></item></channel></rss>")
            with patch.object(hunter, "_fetch", return_value=(
                good_xml, None, None, "application/rss+xml", False
            )):
                recovered = hunter.poll_due([source], state, now=1100)[0]
            self.assertEqual(recovered["status"], "polled")
            self.assertEqual(recovered["added"], 1)


    def test_3b02_embedded_xhtml_hidden_subtrees_are_not_source_facts(self):
        # Atom XHTML content may embed real XML child tags; itertext() used
        # to flatten their script/style/template bodies into trusted evidence.
        xml = (b'<feed xmlns="http://www.w3.org/2005/Atom">'
               b'<entry><title>Visible research</title>'
               b'<link rel="alternate" href="https://example.org/article"/>'
               b'<content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">'
               b'Visible <script>FORGED_INSTRUCTION</script>'
               b'<style>FAKE_STYLE</style><template>FAKE_TEMPLATE</template>'
               b'<svg>FAKE_SVG</svg><span>published observation</span> tail'
               b'</div></content></entry></feed>')
        source = hunter._validate_source({
            "id": "xhtml", "kind": "atom",
            "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(
                    xml, None, None, "application/atom+xml", False)):
                result = hunter.poll_due([source], db, now=1000)[0]
            self.assertEqual((result["status"], result["added"]), ("polled", 1))
            with sqlite3.connect(db) as conn:
                title, content, url = conn.execute(
                    "SELECT title, content, item_url FROM items").fetchone()
        self.assertEqual(title, "Visible research")
        self.assertEqual(url, "https://example.org/article")
        self.assertIn("Visible", content)
        self.assertIn("published observation", content)
        self.assertIn("tail", content)
        for injected in ("FORGED_INSTRUCTION", "FAKE_STYLE",
                         "FAKE_TEMPLATE", "FAKE_SVG"):
            self.assertNotIn(injected, content)


    def test_3b01_hidden_html_excluded_from_page_rss_and_crossref(self):
        raw = (
            "<html><head><title>Unpublished preview</title></head><body>"
            "<template><p>Draft hallucination</p></template>"
            "<p>Verified release 🧠</p>"
            "<svg><text>Private annotation</text></svg>"
            "</body></html>"
        )
        page = H._page_items(raw.encode("utf-8"), "https://example.org/release")
        self.assertEqual(page, [{
            "title": "Verified release 🧠",
            "content": "Verified release 🧠",
            "published": "",
            "url": "https://example.org/release",
        }])
        escaped_html = (
            "<head>Hidden premise</head><template>False certainty</template>"
            "<p>Source-linked answer</p>"
        )
        self.assertEqual(H._plain(escaped_html), "Source-linked answer")
        feed = (
            "<rss><channel><item><title>Article</title>"
            "<link>https://example.org/article</link>"
            "<description><![CDATA[" + escaped_html + "]]></description>"
            "</item></channel></rss>"
        )
        self.assertEqual(H._feed_items(feed.encode("utf-8"))[0]["content"],
                         "Source-linked answer")
        crossref = (
            b'{"message":{"items":[{"DOI":"10.1234/test","title":["Article"],'
            b'"abstract":"<head>Private draft</head><p>Published only</p>"}]}}'
        )
        self.assertEqual(H._crossref_items(crossref)[0]["content"], "Published only")


if __name__ == "__main__":
    unittest.main()
