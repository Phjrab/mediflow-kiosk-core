import base64
import hashlib
import io
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services.medgemma import app as service


def fixture_image() -> str:
    output = io.BytesIO()
    Image.new('RGB', (16, 16), (30, 60, 90)).save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


class MedGemmaServiceContractTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'MEDGEMMA_API_KEY': 'fixture-token'})
        self.environment.start()
        service.runtime.update(
            backend=None, model=None, processor=None, manifest=None,
            device_map=None, cli=None,
        )
        self.client = service.app.test_client()

    def tearDown(self):
        service.runtime.update(
            backend=None, model=None, processor=None, manifest=None,
            device_map=None, cli=None,
        )
        self.environment.stop()

    def headers(self):
        return {'Authorization': 'Bearer fixture-token'}

    def payload(self, **context):
        role = service.ROLE_PATH.read_text(encoding='utf-8').strip()
        return {
            'model': service.EXPECTED_MODEL_ID,
            'max_new_tokens': 64,
            'prompt_digest': hashlib.sha256(role.encode('utf-8')).hexdigest(),
            'class_mapping': {'3': 'normal'},
            'context': context,
            'image': {'mime_type': 'image/png', 'data_base64': fixture_image()},
        }

    def test_readiness_requires_auth_and_loaded_vision_runtime(self):
        self.assertEqual(self.client.get('/readyz').status_code, 401)
        response = self.client.get('/readyz', headers=self.headers())
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['vision_ready'])
        self.assertEqual(
            self.client.post('/v1/analyze-eye', headers=self.headers(), json=self.payload()).status_code,
            503,
        )

    def test_prompt_digest_and_forbidden_context_fail_before_generation(self):
        service.runtime.update(model=object(), processor=object(), device_map=['cuda:0'])
        wrong_prompt = self.payload()
        wrong_prompt['prompt_digest'] = '0' * 64
        self.assertEqual(
            self.client.post('/v1/analyze-eye', headers=self.headers(), json=wrong_prompt).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                '/v1/analyze-eye', headers=self.headers(), json=self.payload(prediction='normal')
            ).status_code,
            400,
        )

    def test_runtime_source_requires_local_files_and_cuda(self):
        source = Path('services/medgemma/app.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('local_files_only=True'), 2)
        self.assertIn("if not torch.cuda.is_available()", source)
        self.assertIn("non-CUDA model placement rejected", source)
        self.assertNotIn('force_download=True', source)

    def test_llama_cpp_backend_preserves_custom_api_contract(self):
        analysis = {
            'schema_version': '1.0',
            'analysis_status': 'abstain',
            'image_quality': {'assessable': False, 'reasons': ['synthetic fixture']},
            'visual_observations': ['blue square'],
            'suggested_label': None,
            'limitations': ['not medical data'],
            'brief_explanation': 'Synthetic fixture only.',
        }
        service.runtime.update(
            backend='llama_cpp_cli', model='/private/model.gguf',
            processor='/private/mmproj.gguf', manifest={},
            device_map=['cuda:0:text', 'cpu:mmproj'], cli='/private/llama-mtmd-cli',
        )
        with patch.object(service, '_llama_cpp_generate', return_value=analysis) as generate:
            response = self.client.post(
                '/v1/analyze-eye', headers=self.headers(), json=self.payload(source='fixture')
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['vision_ingested'])
        self.assertEqual(response.get_json()['analysis'], analysis)
        self.assertEqual(generate.call_count, 1)

    def test_llama_cpp_generation_is_offline_bounded_and_removes_temp_image(self):
        analysis = {'schema_version': '1.0'}
        observed = {}

        def fake_run(command, **kwargs):
            image_path = Path(command[command.index('--image') + 1])
            observed['image_path'] = image_path
            observed['mode'] = image_path.stat().st_mode & 0o777
            observed['command'] = command
            observed['kwargs'] = kwargs
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(analysis), stderr=''
            )

        service.runtime.update(
            backend='llama_cpp_cli', model='/private/model.gguf',
            processor='/private/mmproj.gguf', cli='/private/llama-mtmd-cli',
        )
        image = Image.new('RGB', (16, 16), (30, 60, 90))
        with patch.object(service.subprocess, 'run', side_effect=fake_run):
            result = service._llama_cpp_generate(image, 'fixture prompt', 64)
        self.assertEqual(result, analysis)
        self.assertEqual(observed['mode'], 0o600)
        self.assertFalse(observed['image_path'].exists())
        self.assertIn('--offline', observed['command'])
        self.assertIn('--no-mmproj-offload', observed['command'])
        self.assertIn('--json-schema', observed['command'])
        self.assertNotIn('--log-disable', observed['command'])
        self.assertEqual(observed['kwargs']['timeout'], 180)
        self.assertIs(observed['kwargs']['stdin'], subprocess.DEVNULL)

    def test_llama_cpp_accepts_strict_json_emitted_on_stderr(self):
        analysis = {'schema_version': '1.0'}

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 0, stdout='', stderr=json.dumps(analysis)
            )

        service.runtime.update(
            backend='llama_cpp_cli', model='/private/model.gguf',
            processor='/private/mmproj.gguf', cli='/private/llama-mtmd-cli',
        )
        image = Image.new('RGB', (16, 16), (30, 60, 90))
        with patch.object(service.subprocess, 'run', side_effect=fake_run):
            result = service._llama_cpp_generate(image, 'fixture prompt', 64)
        self.assertEqual(result, analysis)


if __name__ == '__main__':
    unittest.main()
