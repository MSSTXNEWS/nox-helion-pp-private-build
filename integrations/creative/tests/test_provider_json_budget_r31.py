"""Source-only regression: local Creative provider JSON must not accept truncated prefixes.

No external Ollama/ComfyUI requests; local urlopen is patched. This is not
a Windows E07 runtime test.
"""
import io
import unittest
from unittest.mock import patch

from integrations.creative.nox_fastpack import engine


class ProviderJsonAdmission(unittest.TestCase):
    def test_provider_response_bounded_strict_json_object(self):
        oversized=b'{"ok":true}'+b' ' * 8_000_000+b'UNTRUSTED'
        samples=(
            (b'{"ok":true}',True),
            (b'[]',False),
            (oversized,False),
            (b'{"ok":true}TRAILING',False),
        )
        for body,allowed in samples:
            with self.subTest(nbytes=len(body),allowed=allowed):
                with patch.object(engine,"urlopen",return_value=io.BytesIO(body)):
                    if allowed:
                        self.assertEqual(engine._get("http://127.0.0.1:11434/api/tags"),{"ok":True})
                    else:
                        with self.assertRaises(ValueError):
                            engine._get("http://127.0.0.1:11434/api/tags")


    def test_local_model_tag_catalog_rejects_malformed_rows(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            studio=engine.Studio(root)
            for tags in (None, [None], [{"name": ""}], [42]):
                with self.subTest(tags=tags):
                    with patch.object(engine,"_get",return_value={"models":tags}):
                        with self.assertRaises(engine.StudioError):
                            studio._text("Hi")
            responses=[{"models":[{"name":"qwen3:4b"}]},{"response":"Hola"}]
            with patch.object(engine,"_get",side_effect=responses):
                self.assertEqual(studio._text("Hello"),"Hola")


if __name__=="__main__":
    unittest.main()
