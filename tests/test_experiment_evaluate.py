import io
import tempfile
import unittest

from PIL import Image

from experiments.evaluate import compare_runs, evaluate_run, export_report
from experiments.store import ExperimentStore
from utils.ai_config import AIError


def image_bytes(color):
    output = io.BytesIO()
    Image.new('RGB', (20, 20), color=color).save(output, format='PNG')
    return output.getvalue()


def metadata(index, **overrides):
    value = {
        'patient_group_id': f'group-{index}',
        'capture_id': f'capture-{index}',
        'source_asset_ref': f'asset-{index}',
        'modality': 'external_eye_webcam',
        'selected_eye': 'L',
        'engineering_fixture': False,
        'synthetic': False,
        'permission_ref': 'approved-study-fixture',
        'retention_policy_ref': 'retention-policy-fixture',
        'retention_until': '2030-12-31',
        'split': 'test',
    }
    value.update(overrides)
    return value


def result(digest, status, label=None):
    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': status,
            'image_quality': {
                'assessable': status == 'assessed',
                'reasons': [] if status == 'assessed' else ['fixture'],
            },
            'visual_observations': ['fixture'] if status == 'assessed' else [],
            'suggested_label': label,
            'limitations': ['engineering metric fixture'],
            'brief_explanation': 'fixture output',
        },
        'provenance': {'input_digest': digest},
    }


class ExperimentEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExperimentStore(self.temp.name, queue_max=20, allow_real_data=True)

    def tearDown(self):
        self.temp.cleanup()

    def create_run(self, engineering=False):
        return self.store.create_run(
            'E1_vlm_image',
            {'temperature': 0},
            {'origin_model': 'fixture', 'revision': 'fixture'},
            engineering_fixture=engineering,
        )

    def execute(self, sample, run, status='assessed', label='3', fail=False):
        self.store.enqueue(sample['sample_id'], run['run_id'])
        job = self.store.claim_next()
        if fail:
            self.store.fail(job['job_id'], job['lease_token'], 'backend_unavailable')
        else:
            self.store.finish(
                job['job_id'], job['lease_token'], result(sample['roi_digest'], status, label)
            )

    def assessed_metrics(self, actual_and_predicted):
        run = self.create_run()
        for index, (actual, predicted) in enumerate(actual_and_predicted):
            sample = self.store.register_sample(image_bytes('white'), metadata(index))
            self.store.add_reference_label(sample['sample_id'], actual, 'manual-fixture')
            self.execute(sample, run, label=predicted)
        return evaluate_run(self.store, run['run_id'])['clinical_metrics']

    def test_macro_f1_all_classes_correct(self):
        metrics = self.assessed_metrics([(label, label) for label in '01234'])
        self.assertEqual(metrics['answered_accuracy'], 1.0)
        self.assertEqual(metrics['macro_f1_answered_subset'], 1.0)
        self.assertTrue(all(value['f1'] == 1.0 for value in metrics['per_class'].values()))

    def test_macro_f1_includes_class_with_no_correct_predictions(self):
        metrics = self.assessed_metrics([('0', '0'), ('0', '0'), ('1', '0'), ('1', '0')])
        self.assertEqual(metrics['per_class']['1']['support'], 2)
        self.assertIsNone(metrics['per_class']['1']['precision'])
        self.assertEqual(metrics['per_class']['1']['recall_answered_subset'], 0.0)
        self.assertEqual(metrics['per_class']['1']['f1'], 0.0)
        self.assertAlmostEqual(metrics['macro_f1_answered_subset'], 1 / 3)

    def test_macro_f1_five_class_complete_misclassification(self):
        predicted_by_actual = {'0': '0', '1': '2', '2': '1', '3': '4', '4': '3'}
        metrics = self.assessed_metrics([
            (actual, predicted_by_actual[actual])
            for actual in '01234' for _ in range(10)
        ])
        self.assertEqual(metrics['N_assessed'], 50)
        self.assertEqual(metrics['answered_accuracy'], 0.2)
        for label in '01234':
            self.assertEqual(metrics['per_class'][label]['support'], 10)
            self.assertEqual(metrics['per_class'][label]['f1'], 1.0 if label == '0' else 0.0)
        # Hand calculation: (1 + 0 + 0 + 0 + 0) / 5 = 0.2.
        self.assertAlmostEqual(metrics['macro_f1_answered_subset'], 0.2)

    def test_macro_f1_excludes_only_absent_classes(self):
        metrics = self.assessed_metrics([('0', '0'), ('1', '1')])
        for label in '234':
            self.assertEqual(metrics['per_class'][label]['support'], 0)
            self.assertIsNone(metrics['per_class'][label]['f1'])
        self.assertEqual(metrics['macro_f1_answered_subset'], 1.0)

    def test_macro_f1_all_predictions_wrong_is_zero(self):
        metrics = self.assessed_metrics([('0', '1'), ('1', '0')])
        self.assertEqual(metrics['answered_accuracy'], 0.0)
        self.assertEqual(metrics['per_class']['0']['f1'], 0.0)
        self.assertEqual(metrics['per_class']['1']['f1'], 0.0)
        self.assertEqual(metrics['macro_f1_answered_subset'], 0.0)

    def test_denominators_include_abstain_and_technical_failure(self):
        run = self.create_run()
        samples = [
            self.store.register_sample(image_bytes(color), metadata(index))
            for index, color in enumerate(('red', 'green', 'blue'), start=1)
        ]
        for sample in samples:
            self.store.add_reference_label(sample['sample_id'], '3', 'manual-fixture')
        self.execute(samples[0], run, 'assessed', '3')
        self.execute(samples[1], run, 'abstain', None)
        self.execute(samples[2], run, fail=True)

        report = evaluate_run(self.store, run['run_id'])
        metrics = report['clinical_metrics']
        self.assertEqual(metrics['N_eligible'], 3)
        self.assertEqual(metrics['N_assessed'], 1)
        self.assertEqual(metrics['N_correct'], 1)
        self.assertEqual(metrics['N_abstain'], 1)
        self.assertEqual(metrics['N_technical_failure'], 1)
        self.assertAlmostEqual(metrics['coverage'], 1 / 3)
        self.assertEqual(metrics['answered_accuracy'], 1.0)
        self.assertAlmostEqual(metrics['end_to_end_correct_fraction'], 1 / 3)

    def test_engineering_fixture_never_emits_medical_accuracy(self):
        fixture_store_dir = tempfile.TemporaryDirectory()
        try:
            store = ExperimentStore(fixture_store_dir.name)
            sample = store.register_sample(
                image_bytes('white'),
                {
                    **metadata('fixture'),
                    'engineering_fixture': True,
                    'synthetic': True,
                    'permission_ref': None,
                    'retention_policy_ref': None,
                    'retention_until': None,
                    'split': 'engineering_fixture',
                },
            )
            run = store.create_run(
                'E1_vlm_image', {}, {'origin_model': 'fake'}, engineering_fixture=True
            )
            store.add_reference_label(sample['sample_id'], '3', 'synthetic-fixture')
            store.enqueue(sample['sample_id'], run['run_id'])
            job = store.claim_next()
            store.finish(job['job_id'], job['lease_token'], result(sample['roi_digest'], 'assessed', '3'))
            report = evaluate_run(store, run['run_id'])
            self.assertEqual(report['evaluation_status'], 'ENGINEERING_FIXTURE_NO_MEDICAL_METRICS')
            self.assertIsNone(report['clinical_metrics'])
        finally:
            fixture_store_dir.cleanup()

    def test_patient_group_split_leakage_stops_evaluation(self):
        run = self.create_run()
        for index, split in ((1, 'validation'), (2, 'test')):
            sample = self.store.register_sample(
                image_bytes('white'),
                metadata(index, patient_group_id='same-patient', split=split),
            )
            self.execute(sample, run)
        with self.assertRaisesRegex(AIError, 'split_leakage'):
            evaluate_run(self.store, run['run_id'])

    def test_no_reference_labels_and_exports_are_explicit(self):
        run = self.create_run()
        sample = self.store.register_sample(image_bytes('white'), metadata(1))
        self.execute(sample, run)
        report = evaluate_run(self.store, run['run_id'])
        self.assertEqual(report['evaluation_status'], 'NO_REFERENCE_LABELS')
        with tempfile.TemporaryDirectory() as output:
            paths = export_report(self.store, run['run_id'], output)
            markdown = paths['markdown'].read_text(encoding='utf-8')
            self.assertIn('NO_REFERENCE_LABELS', markdown)
            self.assertIn('not medical performance', markdown)

    def test_pairwise_agreement_is_not_named_accuracy(self):
        sample = self.store.register_sample(image_bytes('white'), metadata(1))
        left, right = self.create_run(), self.create_run()
        self.execute(sample, left, 'assessed', '3')
        self.execute(sample, right, 'assessed', '3')
        comparison = compare_runs(self.store, left['run_id'], right['run_id'])
        self.assertEqual(comparison['agreement_rate_paired_assessed'], 1.0)
        self.assertFalse(comparison['agreement_is_accuracy'])


if __name__ == '__main__':
    unittest.main()
