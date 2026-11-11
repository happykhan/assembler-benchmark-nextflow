"""Ownership and lifecycle settings cannot be bypassed at launch."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / 'bin'
sys.path.insert(0, str(BIN))
SPEC = importlib.util.spec_from_file_location('launch', BIN / 'launch.py')
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)
import cleanup


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / 'work'
        self.outdir = self.root / 'results'
        self.reference = self.root / 'references'
        self.bundle = self.outdir / 'bundle'
        runtime = patch.object(launch, 'prepare_environments', return_value={'status': 'prepared'})
        self.prepare = runtime.start()
        self.addCleanup(runtime.stop)

    def launch(self, extra=()):
        return launch.launch_run('quick-test', self.outdir, self.work, self.reference,
                                 nextflow='nextflow-test', nextflow_args=extra)

    def export_bundle(self):
        self.bundle.mkdir(parents=True)
        plan = json.loads((self.outdir / 'selected-plan.json').read_text())
        results = [{'case': {'id': slot['case_id']}, 'assembler': slot['assembler'],
                    'execution': {'status': 'software_error'},
                    'assessment': {'status': 'not_run'}} for slot in plan['slots']]
        (self.bundle / 'results.json').write_text(json.dumps(results))
        manifest = {'schema_version': 1, 'run_id': 'quick-test', 'complete': True,
                    'expected_slots': len(results), 'result_count': len(results),
                    'expected_slot_plan': plan['slots'],
                    'retention': {'assemblies': [], 'graphs': []},
                    'files': {'results.json': cleanup.sha256(self.bundle / 'results.json')}}
        manifest['plan_sha256'] = cleanup.sha256(self.outdir / 'selected-plan.json')
        (self.bundle / 'manifest.json').write_text(json.dumps(manifest))

    def test_passthrough_cannot_override_owned_settings(self):
        options = ['--run_id', '--run_id=other', '--outdir', '--outdir=/elsewhere',
                   '--reference_dir', '--reference_dir=/elsewhere', '-w', '-w=/elsewhere',
                   '-w/elsewhere', '-work-dir', '-work-dir=/elsewhere', '--work-dir']
        options += ['--plan=other.json', '--cases=other', '--assemblers=other']
        for option in options:
            with self.subTest(option=option), patch.object(launch.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'owned run/directory'):
                    self.launch(['--', option, '/elsewhere'])
                run.assert_not_called()
                self.assertFalse(self.work.exists())

    def test_launcher_uses_same_lock_as_cleanup(self):
        self.work.mkdir()
        with cleanup.lifecycle_lock(self.work), patch.object(launch.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'launch or cleanup owns'):
                self.launch()
            run.assert_not_called()
        self.assertFalse((self.work / cleanup.MARKER).exists())

    def test_successful_export_removes_active_marker_and_preserves_identity(self):
        def simulate_nextflow(command):
            self.assertTrue((self.work / cleanup.ACTIVE).exists())
            with self.assertRaisesRegex(ValueError, 'launch or cleanup owns'):
                with cleanup.lifecycle_lock(self.work):
                    self.fail('Launcher must hold lock during Nextflow')
            self.assertIn('-profile', command)
            self.export_bundle()
            return subprocess.CompletedProcess(command, 0)
        with patch.object(launch.subprocess, 'run', side_effect=simulate_nextflow):
            self.assertEqual(self.launch(['--', '-profile', 'slurm,pixi', '-resume']), 0)
        self.assertFalse((self.work / cleanup.ACTIVE).exists())
        marker = json.loads((self.work / cleanup.MARKER).read_text())
        self.assertEqual(marker, {'run_id': 'quick-test', 'bundle_path': str(self.bundle),
                                  'reference_dir': str(self.reference)})

    def test_failed_run_retains_active_marker_for_review_and_resume(self):
        with patch.object(launch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(self.launch(), 1)
        self.assertTrue((self.work / cleanup.ACTIVE).exists())

    def test_incomplete_or_corrupt_export_does_not_clear_active_marker(self):
        def bad_export(command):
            self.export_bundle()
            (self.bundle / 'results.json').write_text('corrupt')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(launch.subprocess, 'run', side_effect=bad_export):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                self.launch()
        self.assertTrue((self.work / cleanup.ACTIVE).exists())

    def test_protected_ancestors_and_output_reference_overlap_fail_before_launch(self):
        paths = [cleanup.REPOSITORY.parent, Path.home().resolve().parent,
                 self.outdir, self.outdir / 'nested', self.reference,
                 self.reference / 'nested']
        for path in paths:
            with self.subTest(path=str(path)), patch.object(launch.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    launch.launch_run('quick-test', self.outdir, path, self.reference)
                run.assert_not_called()

    def test_nonempty_unowned_work_directory_is_not_adopted(self):
        self.work.mkdir()
        (self.work / 'original.txt').write_text('retain')
        with patch.object(launch.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'existing non-empty'):
                self.launch()
            run.assert_not_called()
        self.assertEqual((self.work / 'original.txt').read_text(), 'retain')

    def test_selection_typo_stops_before_scheduling_or_creating_work(self):
        with patch.object(launch.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Unknown case'):
                launch.launch_run('quick-test', self.outdir, self.work, self.reference, cases='typo')
        run.assert_not_called()
        self.assertFalse(self.work.exists())

    def test_changed_selection_requires_a_new_run(self):
        with patch.object(launch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            self.launch()
            with self.assertRaisesRegex(ValueError, 'Run plan changed'):
                launch.launch_run('quick-test', self.outdir, self.work, self.reference, assemblers='raven')

    def test_export_from_another_plan_does_not_clear_active_marker(self):
        def wrong_export(command):
            self.export_bundle()
            p = self.bundle / 'manifest.json'
            manifest = json.loads(p.read_text())
            manifest['plan_sha256'] = 'a' * 64
            p.write_text(json.dumps(manifest))
            return subprocess.CompletedProcess(command, 0)
        with patch.object(launch.subprocess, 'run', side_effect=wrong_export):
            with self.assertRaisesRegex(ValueError, 'frozen run plan'):
                self.launch()
        self.assertTrue((self.work / cleanup.ACTIVE).exists())

    def test_runtime_setup_failure_prevents_nextflow_submission(self):
        self.prepare.side_effect = RuntimeError('Environment installation failed')
        with patch.object(launch.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'installation failed'):
                self.launch(['--', '-profile', 'slurm,pixi'])
        run.assert_not_called()

    def test_multiple_runtime_profiles_fail_before_work_creation(self):
        with patch.object(launch.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'exactly one runtime'):
                self.launch(['--', '-profile', 'pixi,docker'])
        run.assert_not_called()
        self.assertFalse(self.work.exists())


if __name__ == '__main__':
    unittest.main()
