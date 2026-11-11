import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('reference_preparation', Path(__file__).resolve().parents[1] / 'bin/prepare-reference.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreparationTests(unittest.TestCase):
    def test_offline_uses_verified_original_bytes_and_declares_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            data = gzip.compress(b'>chromosome\nACGTACGT\n')
            (cache / 'fixture.source.gz').write_bytes(data)
            registry = {'references': [{'id': 'fixture', 'download_sha256': hashlib.sha256(data).hexdigest(), 'quick_slice_bases': 4}]}
            fasta, metadata = module.prepare(registry, 'fixture', cache, True)
            self.assertIn(b'ACGT\n', fasta)
            self.assertEqual(metadata['interval_zero_based'], [0, 4])
            self.assertFalse(metadata['headline_eligible'])
            (cache / 'fixture.source.gz').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                module.prepare(registry, 'fixture', cache, True)

    def test_offline_missing_reference_does_not_attempt_download(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = {'references': [{'id': 'missing', 'download_sha256': 'a'*64, 'quick_slice_bases': 4}]}
            with self.assertRaisesRegex(ValueError, 'Offline reference missing'):
                module.prepare(registry, 'missing', Path(directory), True)
