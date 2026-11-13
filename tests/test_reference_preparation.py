"""Reusable reference inventory validation; transport uses common preparation."""
from copy import deepcopy
import unittest
from benchlib.references import canonical_fasta,read_fasta,sequence_statistics,validate_molecules,validate_reference_definition

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.sequence='ACGT'*30+'N';self.records={'NC_123456.1':self.sequence}
        self.molecules=[dict(accession='NC_123456.1',type='chromosome',topology='circular',**sequence_statistics(self.sequence))]
        self.definition={'preparation':'whole_genome','status':'admitted','download_sha256':'a'*64,'canonical_fasta_sha256':'b'*64,'molecules':self.molecules}

    def test_canonical_preserves_whole_native_molecule_and_topology(self):
        validate_reference_definition(self.definition)
        fasta=canonical_fasta(self.records,self.molecules).decode()
        self.assertEqual(fasta.splitlines()[0],'>NC_123456.1 circular=true')
        self.assertEqual(''.join(fasta.splitlines()[1:]),self.sequence)
        self.assertEqual(self.molecules[0]['gc_bases'],60)
        self.assertEqual(self.molecules[0]['ambiguous_bases'],1)

    def test_wrong_inventory_or_sequence_is_rejected(self):
        for field,value in [('length_bp',120),('sequence_sha256','c'*64),('gc_bases',61),('ambiguous_bases',0)]:
            molecules=deepcopy(self.molecules);molecules[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'mismatch'):
                validate_molecules(self.records,molecules)
        with self.assertRaisesRegex(ValueError,'undeclared extra'):
            validate_molecules(dict(self.records,extra='ACGT'),self.molecules)

    def test_admission_and_inventory_are_explicit(self):
        for change in [{'status':'proposed'},{'quick_slice_bases':4}]:
            with self.assertRaises(ValueError):validate_reference_definition(dict(self.definition,**change))
        for name in ['NC_123456','NC_654321.1']:
            molecules=deepcopy(self.molecules);molecules[0]['accession']=name
            with self.assertRaises(ValueError):
                validate_reference_definition(dict(self.definition,molecules=molecules))
                validate_molecules(self.records,molecules)
        with self.assertRaises(ValueError):
            validate_reference_definition(dict(self.definition,molecules=self.molecules*2))

    def test_malformed_fasta_rejected(self):
        for text in ['ACGT\n','>a\nACGT\n>a\nACGT\n','>a\n','>a\nACGT!\n']:
            with self.subTest(text=text),self.assertRaises(ValueError):read_fasta(text)
