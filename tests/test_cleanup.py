"""Cleanup must fail closed and preserve scientific outputs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('cleanup', Path(__file__).resolve().parents[1] / 'bin/cleanup.py')
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / 'bundle'
        self.work = self.root / 'work'
        self.references = self.root / 'references'
        for directory in (self.bundle, self.work, self.references):
            directory.mkdir()
        (self.references / 'reference.fasta').write_text('>reference\nACTG\n')
        (self.work / 'reads.fastq').write_text('@read\nACTG\n+\nIIII\n')
        assembly = 'assemblies/example/flye/assembly.fasta'
        (self.bundle / assembly).parent.mkdir(parents=True)
        (self.bundle / assembly).write_text('>assembly\nACTG\n')
        self.results = [{'case': {'id': 'example'}, 'assembler': 'flye',
                         'execution': {'status': 'completed'},
                         'assessment': {'status': 'completed'}}]
        self.manifest = {'schema_version': 1, 'run_id': 'quick-test', 'complete': True,
                         'expected_slots': 1, 'result_count': 1,
                         'retention': {'assemblies': [assembly], 'graphs': []}}
        self.marker = {'run_id': 'quick-test', 'bundle_path': str(self.bundle),
                       'reference_dir': str(self.references)}
        self.save_marker()
        self.save_bundle()

    def save_marker(self):
        (self.work / cleanup.MARKER).write_text(json.dumps(self.marker))

    def save_bundle(self):
        (self.bundle / 'results.json').write_text(json.dumps(self.results))
        self.manifest['files'] = {
            path.relative_to(self.bundle).as_posix(): cleanup.sha256(path)
            for path in self.bundle.rglob('*') if path.is_file() and path.name != 'manifest.json'}
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_dry_run_preserves_work_bundle_and_references(self):
        result = cleanup.cleanup(self.bundle, self.work)
        self.assertEqual(result['action'], 'dry_run')
        self.assertTrue((self.work / 'reads.fastq').is_file())
        self.assertTrue((self.references / 'reference.fasta').is_file())
        self.assertFalse((self.work / cleanup.LOCK).exists())

    def test_apply_requires_exact_run_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'confirm-run-id'):
            cleanup.cleanup(self.bundle, self.work, apply=True, confirm_run_id='another-run')
        self.assertTrue(self.work.exists())

    def test_confirmed_apply_removes_only_owned_work(self):
        result = cleanup.cleanup(self.bundle, self.work, apply=True, confirm_run_id='quick-test')
        self.assertEqual(result['action'], 'delete')
        self.assertFalse(self.work.exists())
        self.assertTrue((self.references / 'reference.fasta').is_file())
        cleanup.validate_bundle(self.bundle)

    def test_corrupt_evidence_blocks_cleanup(self):
        (self.bundle / 'results.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            cleanup.cleanup(self.bundle, self.work)

    def test_active_run_blocks_cleanup(self):
        (self.work / cleanup.ACTIVE).touch()
        with self.assertRaisesRegex(ValueError, 'workflow is active'):
            cleanup.cleanup(self.bundle, self.work)

    def test_ownership_and_reference_paths_are_checked(self):
        for field, value, message in [('run_id', 'wrong', 'different run'),
                                      ('bundle_path', '/elsewhere', 'different bundle'),
                                      ('reference_dir', str(self.work), 'reference cache')]:
            with self.subTest(field=field):
                original = self.marker[field]
                self.marker[field] = value
                self.save_marker()
                with self.assertRaisesRegex(ValueError, message):
                    cleanup.cleanup(self.bundle, self.work)
                self.marker[field] = original

    def test_path_escape_and_symlinks_are_rejected(self):
        self.manifest['files']['../outside'] = 'a' * 64
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'Unsafe manifest path'):
            cleanup.cleanup(self.bundle, self.work)
        self.save_bundle()
        alias = self.root / 'work-link'
        alias.symlink_to(self.work, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            cleanup.cleanup(self.bundle, alias)

    def test_unindexed_files_and_missing_retention_are_rejected(self):
        (self.bundle / 'unindexed.txt').touch()
        with self.assertRaisesRegex(ValueError, 'every retained bundle file'):
            cleanup.cleanup(self.bundle, self.work)
        self.manifest['retention']['assemblies'] = []
        self.save_bundle()
        with self.assertRaisesRegex(ValueError, 'missing retained final assemblies'):
            cleanup.cleanup(self.bundle, self.work)

    def test_infrastructure_or_assessment_errors_block_cleanup(self):
        for status, assessment in [('infrastructure_error', 'not_run'), ('completed', 'error')]:
            with self.subTest(status=status, assessment=assessment):
                self.results[0]['execution']['status'] = status
                self.results[0]['assessment']['status'] = assessment
                self.save_bundle()
                with self.assertRaisesRegex(ValueError, 'prevents cleanup'):
                    cleanup.cleanup(self.bundle, self.work)

    def test_software_failure_is_accounted_without_sequence_claim(self):
        self.results[0]['execution']['status'] = 'software_error'
        self.results[0]['assessment']['status'] = 'not_run'
        self.manifest['retention']['assemblies'] = []
        self.save_bundle()
        self.assertEqual(cleanup.cleanup(self.bundle, self.work)['action'], 'dry_run')

    def test_shared_lifecycle_lock_blocks_cleanup_without_active_marker(self):
        with cleanup.lifecycle_lock(self.work):
            with self.assertRaisesRegex(ValueError, 'launch or cleanup owns'):
                cleanup.cleanup(self.bundle, self.work)
        self.assertTrue((self.work / 'reads.fastq').exists())

    def test_lifecycle_lock_survives_work_directory_recreation(self):
        with cleanup.lifecycle_lock(self.work):
            original = self.root / 'original-work'
            self.work.rename(original)
            self.work.mkdir()
            with self.assertRaisesRegex(ValueError, 'launch or cleanup owns'):
                with cleanup.lifecycle_lock(self.work):
                    self.fail('Recreating work must not replace the lock inode')

    def test_protected_ancestors_and_overlapping_paths_are_rejected(self):
        candidates = [Path.home().resolve(), Path.home().resolve().parent,
                      cleanup.REPOSITORY, cleanup.REPOSITORY.parent]
        for path in candidates:
            with self.subTest(path=str(path)):
                with self.assertRaisesRegex(ValueError, 'protected directory'):
                    cleanup.validate_paths(path, self.bundle, self.references)
        for path in (self.bundle, self.bundle.parent, self.bundle / 'nested',
                     self.references, self.references / 'nested'):
            with self.subTest(path=str(path)):
                with self.assertRaisesRegex(ValueError, 'overlaps'):
                    cleanup.validate_paths(path, self.bundle, self.references)


if __name__ == '__main__':
    unittest.main()
