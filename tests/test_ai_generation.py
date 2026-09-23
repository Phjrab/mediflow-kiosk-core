import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils.ai_config import AIError, LocalConfig
from utils.ai_generation import GenerationConfigStore, GenerationSettings, validate_values
from utils.llm_client import local_chat


class GenerationConfigTest(unittest.TestCase):
    def test_versioned_save_is_private_and_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generation.json"
            store = GenerationConfigStore(path, max_tokens_cap=512)
            initial = store.load(legacy_max_tokens=256)
            self.assertEqual((initial.generation_revision, initial.source), (0, "legacy_effective"))
            saved = store.save(0, {"temperature": 0, "top_p": 0.9, "max_tokens": 128}, legacy_max_tokens=256)
            self.assertEqual(saved.generation_revision, 1)
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            with self.assertRaisesRegex(AIError, "stale_generation_revision"):
                store.save(0, {"temperature": 0.2, "top_p": 0.8, "max_tokens": 64}, legacy_max_tokens=256)

    def test_strict_numeric_validation_rejects_bool_nan_and_range_bypass(self):
        invalid = (
            {"temperature": True, "top_p": 0.9, "max_tokens": 64},
            {"temperature": math.nan, "top_p": 0.9, "max_tokens": 64},
            {"temperature": 0.2, "top_p": 0, "max_tokens": 64},
            {"temperature": 0.2, "top_p": 0.9, "max_tokens": True},
            {"temperature": 0.2, "top_p": 0.9, "max_tokens": 513},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(AIError, "invalid_generation_config"):
                validate_values(value, max_tokens_cap=512)

    def test_request_payload_uses_exact_snapshot(self):
        config = LocalConfig("http", "127.0.0.1", 1, "/v1", "fixture", "secret", max_tokens=512)
        snapshot = GenerationSettings(4, 0, 0.85, 123)
        response = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        with mock.patch("utils.llm_client.post_json", return_value=response) as post:
            self.assertEqual(local_chat(config, "system", "question", snapshot), "ok")
        payload = post.call_args.args[2]
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["top_p"], 0.85)
        self.assertEqual(payload["max_tokens"], 123)


if __name__ == "__main__":
    unittest.main()
