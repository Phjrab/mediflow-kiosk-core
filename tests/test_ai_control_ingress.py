import hashlib
import tempfile
import unittest
from pathlib import Path

from services.ai_control.core import ControlError
from services.ai_control.ingress import IngressJournal
from services.ai_control.ingress_app import (
    UpstreamCompletionUnknown, UpstreamUnavailable, create_app,
)


def expectation(generation=3):
    return {
        'node_id': 'jetson-b', 'artifact_id': 'fixture-chat',
        'artifact_manifest_digest': 'a' * 64, 'runtime_revision': 'fixture-runtime',
        'config_revision': 2, 'deployment_generation': generation,
        'effective_config_digest': 'b' * 64,
    }


class ManagedIngressTest(unittest.TestCase):
    def make_journal(self, root):
        journal = IngressJournal(root / 'ingress.sqlite3')
        self.assertEqual(journal.initialize(), 0)
        return journal

    def test_raw_bypass_and_active_lease_block_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = self.make_journal(Path(directory))
            with self.assertRaisesRegex(ControlError, 'raw_ingress_bypass'):
                journal.open(deployment_generation=3, raw_bypass_closed=False)
            journal.open(deployment_generation=3, raw_bypass_closed=True)
            lease = journal.admit('chat', expected_generation=3)
            journal.close()
            self.assertFalse(journal.drain(0))
            journal.complete(lease)
            self.assertTrue(journal.drain(0))

    def test_restart_converts_active_to_unknown_and_requires_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.make_journal(root)
            journal.open(deployment_generation=3, raw_bypass_closed=True)
            lease = journal.admit('vlm')
            restarted = IngressJournal(root / 'ingress.sqlite3')
            self.assertEqual(restarted.initialize(), 1)
            state = restarted.snapshot()
            self.assertEqual((state['admission'], state['unknown_inflight']), ('closed', 1))
            with self.assertRaisesRegex(ControlError, 'activity_unknown'):
                restarted.reconcile_unknown(lease, backend_completion_verified=False)
            restarted.reconcile_unknown(lease, backend_completion_verified=True)
            restarted.open(deployment_generation=3, raw_bypass_closed=True)
            self.assertEqual(restarted.snapshot()['unknown_inflight'], 0)

    def test_gateway_strips_control_fields_and_returns_e3_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'key'
            key.write_text('fixture-secret\n', encoding='ascii')
            key.chmod(0o600)
            journal = self.make_journal(root)
            journal.open(deployment_generation=3, raw_bypass_closed=True)
            calls = []

            def forward(route, payload):
                calls.append((route, payload))
                return 200, {'choices': [{'message': {'content': 'fixture'}, 'finish_reason': 'stop'}]}

            app = create_app(
                journal=journal, forward=forward, runtime_snapshot=expectation,
                chat_key_file=str(key), vlm_key_file=str(key),
            )
            payload = {
                'model': 'fixture',
                'messages': [{'role': 'system', 'content': 'fixture role'}],
                'stream': False, 'expected_runtime': expectation(),
                'prompt_digest': hashlib.sha256(b'fixture role').hexdigest(),
            }
            response = app.test_client().post(
                '/v1/chat/completions', json=payload,
                headers={'Authorization': 'Bearer fixture-secret'},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('expected_runtime', calls[0][1])
            self.assertNotIn('prompt_digest', calls[0][1])
            self.assertEqual(response.get_json()['runtime_receipt']['deployment_generation'], 3)
            self.assertEqual(journal.snapshot()['inflight'], 0)

    def test_transport_loss_quarantines_ingress_and_drift_never_forwards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'key'
            key.write_text('fixture-secret\n', encoding='ascii')
            key.chmod(0o600)
            journal = self.make_journal(root)
            journal.open(deployment_generation=3, raw_bypass_closed=True)
            calls = []

            def forward(route, payload):
                calls.append(route)
                raise UpstreamCompletionUnknown()

            app = create_app(
                journal=journal, forward=forward, runtime_snapshot=expectation,
                chat_key_file=str(key), vlm_key_file=str(key),
            )
            client = app.test_client()
            drift = client.post('/v1/chat/completions', json={
                'expected_runtime': expectation(4), 'prompt_digest': 'c' * 64,
            }, headers={'Authorization': 'Bearer fixture-secret'})
            self.assertEqual(drift.status_code, 409)
            self.assertEqual(calls, [])
            lost = client.post('/v1/chat/completions', json={}, headers={
                'Authorization': 'Bearer fixture-secret'
            })
            self.assertEqual(lost.status_code, 503)
            self.assertEqual(journal.snapshot()['admission'], 'closed')
            self.assertEqual(journal.snapshot()['unknown_inflight'], 1)

    def test_upstream_unavailable_before_send_completes_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'key'
            key.write_text('fixture-secret\n', encoding='ascii')
            key.chmod(0o600)
            journal = self.make_journal(root)
            journal.open(deployment_generation=3, raw_bypass_closed=True)

            def forward(_route, _payload):
                raise UpstreamUnavailable()

            app = create_app(
                journal=journal, forward=forward, runtime_snapshot=expectation,
                chat_key_file=str(key), vlm_key_file=str(key),
            )
            response = app.test_client().post(
                '/v1/analyze-eye', json={},
                headers={'Authorization': 'Bearer fixture-secret'},
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()['status'], 'backend_unavailable')
            state = journal.snapshot()
            self.assertEqual((state['admission'], state['inflight'], state['unknown_inflight']),
                             ('open', 0, 0))


if __name__ == '__main__':
    unittest.main()
