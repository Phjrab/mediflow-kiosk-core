import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.local_llm_service import ProcessSnapshot
from services.ai_control.core import digest
from services.ai_control.lifecycle import (
    EngineAdapter, EngineState, OwnedMedGemmaEngine, OwnedProcessSpec,
    SequentialLifecycleAdapter,
)
from services.ai_control.operations import LifecycleFailure


class FakeEngine(EngineAdapter):
    def __init__(self, name, events, *, state='stopped', managed=True):
        self.name = name
        self.events = events
        self.state = state
        self.managed = managed
        self.desired = None

    def snapshot(self):
        receipt = None
        if self.state == 'running':
            receipt = {
                'artifact_id': 'fixture-' + self.name,
                'artifact_manifest_digest': 'a' * 64,
                'runtime_revision': 'fixture-runtime',
                'effective_config_digest': digest(self.desired) if self.desired else 'b' * 64,
            }
        return EngineState(self.state, self.managed, {'pid': 42}, receipt)

    def start(self, desired):
        self.events.append(('start', self.name))
        self.desired = desired
        self.state = 'running'

    def stop(self):
        self.events.append(('stop', self.name))
        self.state = 'stopped'


class FakeIngress:
    def __init__(self):
        self.events = []
        self.state = {'admission': 'open', 'deployment_generation': 2, 'raw_bypass_closed': True,
                      'source': 'managed_ingress', 'inflight': 0, 'unknown_inflight': 0}

    def snapshot(self):
        return dict(self.state)

    def close_admission(self):
        self.events.append('close')
        self.state['admission'] = 'closed'

    def drain(self, timeout):
        self.events.append(('drain', timeout))
        return not self.state['inflight'] and not self.state['unknown_inflight']

    def restore_admission(self, previous):
        self.events.append('restore_admission')
        self.state['admission'] = previous['admission']


class LifecycleAdapterTest(unittest.TestCase):
    def desired(self, profile):
        return {
            'active_profile': profile,
            'engines': {
                'chat': {'artifact_id': 'fixture-chat'},
                'vlm': {'artifact_id': 'fixture-vlm'},
            },
        }

    def test_sequential_switch_stops_owned_chat_before_starting_vlm(self):
        events = []
        chat = FakeEngine('chat', events, state='running')
        vlm = FakeEngine('vlm', events)
        lifecycle = SequentialLifecycleAdapter(chat=chat, vlm=vlm, ingress=FakeIngress())
        previous = lifecycle.snapshot()
        lifecycle.close_admission()
        self.assertTrue(lifecycle.drain(10))
        lifecycle.apply(self.desired('vlm_only'))
        receipt = lifecycle.verify(self.desired('vlm_only'))
        self.assertEqual(events, [('stop', 'chat'), ('start', 'vlm')])
        self.assertEqual(receipt['observed_profile'], 'vlm_only')
        lifecycle.restore(previous)
        self.assertEqual(events[-2:], [('stop', 'vlm'), ('start', 'chat')])

    def test_unmanaged_or_co_resident_process_blocks_without_stop(self):
        events = []
        lifecycle = SequentialLifecycleAdapter(
            chat=FakeEngine('chat', events, state='running', managed=False),
            vlm=FakeEngine('vlm', events), ingress=FakeIngress(),
        )
        with self.assertRaisesRegex(LifecycleFailure, 'unmanaged_process'):
            lifecycle.apply(self.desired('vlm_only'))
        self.assertEqual(events, [])

        lifecycle = SequentialLifecycleAdapter(
            chat=FakeEngine('chat', events, state='running'),
            vlm=FakeEngine('vlm', events, state='running'), ingress=FakeIngress(),
        )
        with self.assertRaisesRegex(LifecycleFailure, 'co_residency_unverified'):
            lifecycle.snapshot()

    def test_unknown_inflight_prevents_drain(self):
        ingress = FakeIngress()
        ingress.state['unknown_inflight'] = 1
        lifecycle = SequentialLifecycleAdapter(
            chat=FakeEngine('chat', []), vlm=FakeEngine('vlm', []), ingress=ingress,
        )
        lifecycle.close_admission()
        self.assertFalse(lifecycle.drain(1))

    def test_medgemma_owner_adapter_never_stops_pid_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_path = root / 'medgemma.pid.json'
            executable = '/fixture/python3'
            argv = (executable, '-m', 'services.medgemma.app')
            record = {
                'version': 1, 'pid': 4242, 'uid': os.geteuid(),
                'executable': executable, 'argv': list(argv), 'cwd': str(root),
                'start_ticks': 100, 'boot_id': 'fixture-boot',
            }
            pid_path.write_text(json.dumps(record), encoding='utf-8')
            pid_path.chmod(0o600)
            reused = ProcessSnapshot(
                4242, os.geteuid(), executable, argv, str(root), 'S', 101, 'fixture-boot'
            )
            stopped = []
            engine = OwnedMedGemmaEngine(
                OwnedProcessSpec(pid_path, os.geteuid(), executable, argv, str(root)),
                start=lambda _desired: None, stop=stopped.append,
                receipt=lambda: {}, unmanaged_present=lambda: False,
                read_snapshot=lambda _pid: reused,
            )
            state = engine.snapshot()
            self.assertFalse(state.managed)
            self.assertEqual(state.state, 'identity_mismatch')
            with self.assertRaisesRegex(LifecycleFailure, 'unmanaged_process'):
                engine.stop()
            self.assertEqual(stopped, [])

    def test_medgemma_owner_adapter_stops_only_exact_recorded_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_path = root / 'medgemma.pid.json'
            executable = '/fixture/python3'
            argv = (executable, '-m', 'services.medgemma.app')
            record = {
                'version': 1, 'pid': 4242, 'uid': os.geteuid(),
                'executable': executable, 'argv': list(argv), 'cwd': str(root),
                'start_ticks': 100, 'boot_id': 'fixture-boot',
            }
            pid_path.write_text(json.dumps(record), encoding='utf-8')
            pid_path.chmod(0o600)
            live = ProcessSnapshot(
                4242, os.geteuid(), executable, argv, str(root), 'S', 100, 'fixture-boot'
            )
            stopped = []

            def stop(pid):
                stopped.append(pid)
                pid_path.unlink()

            engine = OwnedMedGemmaEngine(
                OwnedProcessSpec(pid_path, os.geteuid(), executable, argv, str(root)),
                start=lambda _desired: None, stop=stop,
                receipt=lambda: {'artifact_id': 'fixture'}, unmanaged_present=lambda: False,
                read_snapshot=lambda _pid: live,
            )
            self.assertTrue(engine.snapshot().managed)
            engine.stop()
            self.assertEqual(stopped, [4242])


if __name__ == '__main__':
    unittest.main()
