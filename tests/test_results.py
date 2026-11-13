import tempfile
from pathlib import Path
import unittest
from benchlib.assessment import outcome, parse_paf, summarise

class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paf = Path(self.temp.name) / 'alignment.paf'
        self.references = {'reference': 'A' * 1000}
        self.queries = {'contig': 'A' * 2000}

    def parse(self, text):
        self.paf.write_text(text)
        return parse_paf(self.paf, self.references, self.queries)

    def test_contiguity_is_uncapped_and_longest_alignment_selected(self):
        alignments = self.parse('contig\t2000\t0\t1100\t+\treference\t3000\t400\t1500\t1098\t1100\t60\tcg:Z:1100M\n')
        result = summarise(self.references, alignments)[0]
        self.assertAlmostEqual(result['contiguity'], 1.1)
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['identity'], 1098 / 1100)
        self.assertEqual(result['max_indel_bp'], 0)

    def test_split_alignments_do_not_establish_completion(self):
        alignments = self.parse('contig\t2000\t0\t500\t+\treference\t3000\t0\t500\t500\t500\t60\tcg:Z:500M\n'
                                'contig\t2000\t500\t1000\t+\treference\t3000\t500\t1000\t500\t500\t60\tcg:Z:500M\n')
        result = summarise(self.references, alignments)[0]
        self.assertEqual(result['contiguity'], .5)
        self.assertEqual(outcome([result], 1), 'incomplete')

    def test_short_alignment_has_no_accuracy_measurement(self):
        alignments = self.parse('contig\t2000\t0\t250\t+\treference\t3000\t0\t250\t250\t250\t60\tcg:Z:250M\n')
        result = summarise(self.references, alignments)[0]
        self.assertFalse(result['identity_measured'])
        self.assertIsNone(result['identity'])
        self.assertIsNone(result['max_indel_bp'])

    def test_invalid_cigar_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CIGAR span'):
            self.parse('contig\t2000\t0\t500\t+\treference\t3000\t0\t500\t500\t500\t60\tcg:Z:499M\n')
