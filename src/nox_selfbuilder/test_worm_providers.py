"""Official bounded provider tests. HTTP is fully mocked; no secrets/network."""
import unittest
from datetime import datetime, timezone
from src.nox_selfbuilder.worms import plan_day, WormHold, inspect_evidence
from src.nox_selfbuilder.worm_providers import (
    approved_provider_map, github_repositories, youtube_public_video_search,
)

TASKS = plan_day(datetime(2026, 11, 1, tzinfo=timezone.utc))
GH = next(t for t in TASKS if t.provider == "github_api")
YT = next(t for t in TASKS if t.provider == "youtube_api")


class ProvidersTest(unittest.TestCase):
    def test_public_github_official_api_and_data_only_records(self):
        urls = []
        def fetch(url, *, host):
            urls.append((url, host))
            return {"items": [
                {"html_url": "https://github.com/example/plugin", "full_name": "example/plugin",
                 "description": "A verified-looking module requiring independent review",
                 "stargazers_count": 123, "archived": False},
                {"html_url": "https://untrusted.example/evil", "full_name": "evil/evil",
                 "description": "unsafe", "stargazers_count": 1000000},
            ]}
        out = github_repositories(GH, fetch=fetch)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["license"], "REVIEW_REQUIRED")
        self.assertEqual(urls[0][1], "api.github.com")
        self.assertTrue(urls[0][0].startswith("https://api.github.com/search/repositories?"))
        self.assertEqual(inspect_evidence(GH, out[0], source_host="github.com")["code_executed"], False)

    def test_youtube_requires_native_key_and_uses_official_api_not_scraping(self):
        with self.assertRaises(WormHold):
            youtube_public_video_search(YT, api_key="", fetch=lambda *_: {})
        def fetch(url, *, host):
            self.assertEqual(host, "www.googleapis.com")
            self.assertTrue(url.startswith("https://www.googleapis.com/youtube/v3/search?"))
            return {"items": [{"id": {"videoId": "abcdefghijk"}, "snippet": {
                "title": "Interesting animation breakdown",
                "description": "Real reference, check rights first",
                "publishedAt": "2026-10-10T00:00:00Z"}}]}
        out = youtube_public_video_search(YT, api_key="abcdefgh12345678", fetch=fetch)
        self.assertEqual(out[0]["url"], "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(out[0]["license"], "REVIEW_REQUIRED")
        self.assertEqual(inspect_evidence(YT, out[0], source_host="www.youtube.com")["status"],
                         "SOURCE_OBSERVED_REVIEW_REQUIRED")

    def test_missing_tiktok_provider_does_not_pretend_access(self):
        p, h = approved_provider_map(github_enabled=True, official_fetch=lambda *_: {})
        self.assertEqual(set(p), {"github_api"})
        self.assertNotIn("tiktok_approved_api", p)
        self.assertEqual(h, {"github_api": "github.com"})

    def test_wrong_task_is_denied(self):
        with self.assertRaises(WormHold):
            github_repositories(YT, fetch=lambda *_: {})
        with self.assertRaises(WormHold):
            youtube_public_video_search(GH, api_key="abcdefgh12345678", fetch=lambda *_: {})


if __name__ == "__main__":
    unittest.main()
