"""A whole-genome case cannot consume an unverified or sliced reference."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from benchlib.io import digest

spec = importlib.util.spec_from_file_location('standard_simulation', Path(__file__).resolve().parents[1] / 'bin/simulate-reads.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StandardSimulationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.reference = self.directory / 'reference.fasta'
        self.reference.write_text('>TEST.1 circular=true\nACGTACGT\n')
        self.case = {'preset': 'standard', 'reference_id': 'whole'}
        self.provenance = self.directory / 'reference.json'
        self.record = {'id': 'whole', 'reference_sha256': digest(self.reference),
                       'mode': 'whole_genome', 'status': 'admitted',
                       'molecules': [{'type': 'chromosome', 'topology': 'circular'}]}
        self.save()

    def save(self):
        self.provenance.write_text(json.dumps(self.record))

    def test_native_whole_chromosome_is_accepted(self):
        self.assertEqual(module.verify_reference(self.reference, self.case, self.provenance), self.record)

    def test_missing_changed_or_quick_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'requires verified reference provenance'):
            module.verify_reference(self.reference, self.case)
        for change in ({'reference_sha256': 'wrong'}, {'mode': 'quick_fragment'},
                       {'status': 'proposed'}, {'id': 'another'}):
            with self.subTest(change=change):
                self.provenance.write_text(json.dumps(dict(self.record, **change)))
                with self.assertRaises(ValueError):
                    module.verify_reference(self.reference, self.case, self.provenance)

    def test_unsupported_multi_replicon_and_missing_circular_header_are_rejected(self):
        self.record['molecules'].append({'type': 'plasmid', 'topology': 'circular'})
        self.save()
        with self.assertRaisesRegex(ValueError, 'one verified chromosome'):
            module.verify_reference(self.reference, self.case, self.provenance)
        self.record['molecules'].pop()
        self.reference.write_text('>TEST.1\nACGTACGT\n')
        self.record['reference_sha256'] = digest(self.reference)
        self.save()
        with self.assertRaisesRegex(ValueError, 'does not declare native circular'):
            module.verify_reference(self.reference, self.case, self.provenance)
