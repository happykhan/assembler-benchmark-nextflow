"""Beta publication preserves the existing website and recorded measurements."""
import json
from pathlib import Path
import tempfile
import unittest

from reporting.beta_site import render_beta
from reporting.common import digest


def fixture(root):
    base=root/'base';(base/'assets').mkdir(parents=True)
    (base/'index.html').write_text('<main id="main"><h1>Published benchmark</h1></main>')
    (base/'aggregate.html').write_text('Historical aggregate, unchanged')
    (base/'scenarios').mkdir();(base/'scenarios/index.html').write_text('Historical scenarios')
    (base/'methods.html').write_text('Historical methods')
    for name in ['genomicx.css','genomicx.js']:(base/'assets'/name).write_text('/* fixture */')
    bundle=root/'bundle';(bundle/'evidence/test').mkdir(parents=True)
    case={'id':'beta-fixture-baseline-seed-101','reference_id':'fixture','group':'gc-composition','seed':101}
    record={'case':case,'preset':'standard','assembler':'test-1','execution':{'status':'completed'},
            'assessment':{'status':'completed'},'sequence_outcome':'incomplete','resources':{},
            'replicons':[{'accession':'TEST.1','molecule_type':'chromosome','length_bp':1000,'contiguity':1.2,'complete':True}],
            'evidence_directory':'evidence/test'}
    (bundle/'results.json').write_text(json.dumps({'run_id':'TEST_FIXTURE_NOT_FOR_PUBLICATION','results':[record]}))
    (bundle/'slot-plan.json').write_text(json.dumps({'cases':[case],'reference_ids':['fixture'],
        'references':{'fixture':{'id':'fixture','organism':'Test fixture','molecules':[{'type':'chromosome','gc_bases':400,'length_bp':1000}]}}}))
    (bundle/'evidence/test/simulation.json').write_text(json.dumps({'observed':{'total_bases':30000,'read_count':30,'n50':1000}}))
    manifest={'schema_version':1,'run_id':'TEST_FIXTURE_NOT_FOR_PUBLICATION','expected_slots':1,'result_count':1,'complete':True,
              'files':{p.relative_to(bundle).as_posix():digest(p) for p in bundle.rglob('*') if p.is_file()}}
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    return bundle,base


class BetaSiteTests(unittest.TestCase):
    def test_preserves_existing_pages_and_uncapped_molecule_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle,base=fixture(root)
            before={p.relative_to(base):digest(p) for p in base.rglob('*') if p.is_file()}
            output=render_beta(bundle,base,root/'site')
            self.assertIn('/beta/',(output/'index.html').read_text())
            for path,checksum in before.items():
                self.assertEqual(digest(base/path),checksum)
                if str(path)!='index.html':self.assertEqual(digest(output/path),checksum)
            self.assertIn('1.2',(output/'beta/molecules.tsv').read_text())
            self.assertIn('incomplete',(output/'beta/results.tsv').read_text())
            self.assertTrue((output/'beta/contiguity.svg').is_file())

    def test_incomplete_run_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle,base=fixture(root)
            p=bundle/'manifest.json';m=json.loads(p.read_text());m['complete']=False;p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'complete Nextflow'):
                render_beta(bundle,base,root/'site')
            self.assertFalse((root/'site').exists())
