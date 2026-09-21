import io
import unittest
from unittest import mock

from PIL import Image

from utils.ai_config import AIError, VLMConfig
from utils.runtime_receipt import validate_runtime_expectation, validate_runtime_receipt
from utils.vlm_client import ROLE_PATH, analyze_eye


def expectation(**overrides):
    value = {
        'node_id': 'jetson-b', 'artifact_id': 'fixture-vlm',
        'artifact_manifest_digest': 'a' * 64, 'runtime_revision': 'fixture-runtime',
        'config_revision': 2, 'deployment_generation': 3,
        'effective_config_digest': 'b' * 64,
    }
    value.update(overrides)
    return value


def image_bytes():
    output = io.BytesIO()
    Image.new('RGB', (16, 16), 'white').save(output, format='PNG')
    return output.getvalue()


class RuntimeReceiptTest(unittest.TestCase):
    def test_closed_schema_rejects_stale_generation_and_extra_fields(self):
        expected = expectation()
        prompt_digest = __import__('hashlib').sha256(ROLE_PATH.read_text(encoding='utf-8').strip().encode()).hexdigest()
        receipt = {**expected, 'prompt_digest': prompt_digest}
        self.assertEqual(validate_runtime_receipt(receipt, expected, prompt_digest=prompt_digest), receipt)
        with self.assertRaisesRegex(AIError, 'runtime_receipt_mismatch'):
            validate_runtime_receipt({**receipt, 'deployment_generation': 4}, expected, prompt_digest=prompt_digest)
        with self.assertRaisesRegex(AIError, 'invalid_runtime_expectation'):
            validate_runtime_expectation({**expected, 'extra': True})

    def test_client_requires_matching_receipt_when_run_is_pinned(self):
        expected = expectation()
        analysis = {
            'schema_version': '1.0', 'analysis_status': 'abstain',
            'image_quality': {'assessable': False, 'reasons': ['fixture']},
            'visual_observations': [], 'suggested_label': None,
            'limitations': ['fixture'], 'brief_explanation': 'fixture',
        }
        config = VLMConfig(
            'http', '127.0.0.1', 8081, '', 'medgemma_custom_v1',
            'google/medgemma-test-fixture', 'secret', max_new_tokens=64,
        )
        response = {'vision_ingested': True, 'analysis': analysis, 'runtime_receipt': {**expected, 'prompt_digest': '0' * 64}}
        with mock.patch('utils.vlm_client.post_json', return_value=response):
            with self.assertRaisesRegex(AIError, 'runtime_receipt_mismatch'):
                analyze_eye(config, image_bytes(), runtime_expectation=expected)


if __name__ == '__main__':
    unittest.main()
