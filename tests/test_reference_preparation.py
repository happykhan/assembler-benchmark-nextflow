import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from benchlib.references import canonical_fasta, prepare_reference, read_fasta, sequence_statistics

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


class WholeReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.sequence = 'ACGT' * 30 + 'N'
        self.records = {'NC_123456.1': self.sequence}
        self.molecules = [dict(accession='NC_123456.1', type='chromosome', topology='circular',
                               **sequence_statistics(self.sequence))]
        self.source = gzip.compress(('>NC_123456.1 original chromosome\n' + self.sequence + '\n').encode())
        self.path = self.cache / 'whole.source.gz'
        self.path.write_bytes(self.source)
        canonical = canonical_fasta(self.records, self.molecules)
        self.row = {'id': 'whole', 'preparation': 'whole_genome', 'status': 'admitted',
                    'compression': 'gzip', 'download_sha256': hashlib.sha256(self.source).hexdigest(),
                    'canonical_fasta_sha256': hashlib.sha256(canonical).hexdigest(), 'molecules': self.molecules}

    def prepare(self, row=None):
        return prepare_reference({'references': [row or self.row]}, 'whole', self.cache, True)

    def test_whole_molecule_is_not_sliced_and_declares_native_topology(self):
        fasta, metadata = self.prepare()
        self.assertEqual(fasta.splitlines()[0], b'>NC_123456.1 circular=true')
        self.assertEqual(''.join(line.decode() for line in fasta.splitlines()[1:]), self.sequence)
        self.assertEqual(metadata['molecule_types'], {'NC_123456.1': 'chromosome'})
        self.assertEqual(metadata['molecules'][0]['ambiguous_bases'], 1)
        self.assertEqual(metadata['molecules'][0]['gc_bases'], 60)
        self.assertEqual(metadata['mode'], 'whole_genome')
        self.assertEqual(self.path.read_bytes(), self.source)

    def test_changed_inventory_sequence_or_canonical_hash_fails(self):
        for field, value in [('length_bp', 120), ('sequence_sha256', 'a' * 64),
                             ('gc_bases', 61), ('ambiguous_bases', 0)]:
            row = deepcopy(self.row)
            row['molecules'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'mismatch'):
                self.prepare(row)
        row = deepcopy(self.row)
        row['canonical_fasta_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'canonical FASTA checksum'):
            self.prepare(row)

    def test_missing_extra_duplicate_or_unversioned_molecules_are_rejected(self):
        for accession in ['NC_654321.1', 'NC_123456']:
            row = deepcopy(self.row)
            row['molecules'][0]['accession'] = accession
            with self.subTest(accession=accession), self.assertRaises(ValueError):
                self.prepare(row)
        row = deepcopy(self.row)
        row['molecules'].append(deepcopy(row['molecules'][0]))
        with self.assertRaisesRegex(ValueError, 'unique and versioned'):
            self.prepare(row)
        data = gzip.compress(('>NC_123456.1\n' + self.sequence + '\n>NC_222222.1\nACGT\n').encode())
        self.path.write_bytes(data)
        row = deepcopy(self.row)
        row['download_sha256'] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError, 'undeclared extra'):
            self.prepare(row)

    def test_whole_reference_cannot_be_unadmitted_or_sliced(self):
        for changed in [{'status': 'proposed'}, {'quick_slice_bases': 4}]:
            row = dict(self.row, **changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.prepare(row)

    def test_quick_bytes_remain_exact_and_oversized_slice_fails(self):
        row = {'id': 'whole', 'download_sha256': self.row['download_sha256'], 'quick_slice_bases': 4}
        # Quick deliberately requires unambiguous input, unlike the inventory parser.
        self.path.write_bytes(gzip.compress(b'>source\nACGTACGT\n'))
        row['download_sha256'] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        fasta, _ = self.prepare(row)
        self.assertEqual(fasta, b'>whole workflow_fixture linear=true\nACGT\n')
        row['quick_slice_bases'] = 9
        with self.assertRaisesRegex(ValueError, 'slice exceeds'):
            self.prepare(row)

    def test_malformed_source_fasta_is_rejected(self):
        for text in ['ACGT\n', '>a\nACGT\n>a\nACGT\n', '>a\n', '>a\nACGT!\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_fasta(text)
