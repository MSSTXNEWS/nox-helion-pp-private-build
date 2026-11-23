#!/usr/bin/env python3
"""3B01: Hunter never publishes HTML template/head text as factual evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nox_hunter as H


class HtmlProvenanceRegression(unittest.TestCase):
    def test_hidden_html_fences_apply_to_page_and_embedded_sources(self):
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
