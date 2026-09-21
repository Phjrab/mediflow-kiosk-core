import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from utils.artifact_manifest import load_candidates, verify_component


ROOT = Path(__file__).resolve().parents[1]


def fixture_manifest(path: Path, name: str, content: bytes) -> Path:
    item = {
        'path': name,
        'size': len(content),
        'sha256': hashlib.sha256(content).hexdigest(),
    }
    payload = {
        'schema_version': 1,
        'artifacts': {
            'general_llm': {
                'origin_model': 'example/text',
                'revision': 'a' * 40,
                'files': [item],
            },
            'medgemma_source': {
                'origin_model': 'example/vision',
                'revision': 'b' * 40,
                'files': [item],
            },
            'medgemma_gguf': {
                'origin_model': 'example/vision',
                'revision': 'b' * 40,
                'files': [item],
            },
        },
    }
    manifest = path / 'manifest.json'
    manifest.write_text(json.dumps(payload), encoding='utf-8')
    return manifest


class ArtifactManifestTest(unittest.TestCase):
    def test_repository_candidate_manifest_is_structurally_valid(self):
        payload = load_candidates(ROOT / 'config' / 'ai_artifact_candidates.json')
        self.assertTrue(payload['constraints']['general_llm_model_download_performed'])
        self.assertTrue(payload['constraints']['general_llm_device_runtime_verification_performed'])
        self.assertTrue(payload['constraints']['medgemma_model_download_performed'])
        self.assertTrue(payload['constraints']['medgemma_device_runtime_verification_performed'])
        self.assertTrue(payload['constraints']['medgemma_e1_provenance_approved'])
        self.assertFalse(payload['constraints']['medgemma_real_data_verification_performed'])
        self.assertTrue(payload['constraints']['medgemma_e1_api_device_verification_performed'])
        self.assertEqual(
            payload['runtime_candidates']['medgemma_ollama_probe']['verification_status'],
            'SYNTHETIC_IMAGE_GPU_PROBE_VERIFIED_JETSON_B_2026-09-20',
        )
        self.assertEqual(
            payload['artifacts']['general_llm']['verification_status'],
            'DEVICE_VERIFIED_JETSON_B_2026-09-20',
        )
        self.assertEqual(
            payload['artifacts']['medgemma_gguf']['verification_status'],
            'SOURCE_ATTESTED_CUSTOM_API_SYNTHETIC_IMAGE_DEVICE_VERIFIED_JETSON_B_2026-09-21',
        )

    def test_matching_local_file_verifies_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b'pinned-model-fixture'
            (root / 'model.bin').write_bytes(content)
            manifest = fixture_manifest(root, 'model.bin', content)
            result = verify_component(manifest, 'general_llm', root)
            self.assertEqual(result['status'], 'VERIFIED')
            self.assertEqual(result['files'][0]['size'], len(content))

    def test_digest_or_size_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture_manifest(root, 'model.bin', b'expected')
            (root / 'model.bin').write_bytes(b'changeXX')
            with self.assertRaisesRegex(ValueError, 'artifact_digest_mismatch'):
                verify_component(manifest, 'general_llm', root)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b'fixture'
            target = root / 'target.bin'
            target.write_bytes(content)
            (root / 'model.bin').symlink_to(target)
            manifest = fixture_manifest(root, 'model.bin', content)
            with self.assertRaisesRegex(ValueError, 'artifact_symlink_rejected'):
                verify_component(manifest, 'general_llm', root)

    def test_local_llm_launcher_is_pinned_and_does_not_acquire_artifacts(self):
        source = (ROOT / 'scripts' / 'run_local_llm_candidate.sh').read_text(encoding='utf-8')
        self.assertIn('391fac16460f15233a7740550d858ac96df3419d', source)
        self.assertIn('--component general_llm', source)
        self.assertIn('--api-key-file', source)
        self.assertIn('--parallel 1', source)
        self.assertIn('--n-gpu-layers all', source)
        self.assertIn('--no-cache-prompt', source)
        self.assertIn('--no-webui', source)
        for forbidden in ('git clone', 'git pull', 'curl ', 'wget ', 'pip install', 'docker pull'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
