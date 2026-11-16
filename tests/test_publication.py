"""Static pilot composition preserves established reports and shared bytes."""
import json
from pathlib import Path
import tempfile
import unittest
from reporting.publication import compose_pilot,compose_standard
from reporting.current_site import validate_site


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.base=self.root/'base';self.pilot=self.root/'pilot';self.output=self.root/'output'
        self.base.mkdir();self.pilot.mkdir()
        (self.base/'index.html').write_text('<h1>Established benchmark</h1><a href="performance.html">Results</a>')
        (self.base/'performance.html').write_text('<h1>Existing report</h1>')
        (self.base/'vercel.json').write_text('{"cleanUrls":true}')
        (self.pilot/'publication.json').write_text(json.dumps({'kind':'pilot','measured_results':2,'unique_inputs':1,'not_applicable':0}))
        (self.pilot/'data').mkdir();(self.pilot/'data/views').mkdir();(self.pilot/'results').mkdir()
        for name in ('one','two'):(self.pilot/'data/views'/(name+'.tsv')).write_text('fixture\tvalue\nexample\t1\n')
        (self.pilot/'index.html').write_text('<h1>Pilot validation</h1><a href="data/views/two.tsv">Download</a>')
        (self.pilot/'results/result.json').write_text(json.dumps({'artifacts':{'fixture':{'path':'../data/views/two.tsv'}}}))

    def test_preserves_existing_reports_and_rewrites_shared_downloads(self):
        result=compose_pilot(self.base,self.pilot,self.output)
        self.assertEqual(result['status'],'pass')
        self.assertEqual((self.output/'performance.html').read_bytes(),(self.base/'performance.html').read_bytes())
        self.assertIn('Nextflow pilot reports',(self.output/'index.html').read_text())
        self.assertIn('data/views/one.tsv',(self.output/'pilot/index.html').read_text())
        self.assertFalse((self.output/'pilot/data/views/two.tsv').exists())
        self.assertEqual(json.loads((self.output/'pilot/results/result.json').read_text())['artifacts']['fixture']['path'],'../data/views/one.tsv')
        self.assertEqual(validate_site(self.output/'pilot')['status'],'pass')
        self.assertTrue((self.pilot/'data/views/two.tsv').exists())

    def test_requires_pilot_declaration_and_fresh_output(self):
        (self.pilot/'publication.json').write_text('{"kind":"unlabelled"}')
        with self.assertRaisesRegex(ValueError,'explicit pilot'):compose_pilot(self.base,self.pilot,self.output)
        with self.assertRaisesRegex(ValueError,'fresh directory'):compose_pilot(self.base,self.pilot,self.base)

    def test_standard_preserves_pilot_and_pins_batch_rewrite_without_copying_it(self):
        pilot_entry='<section id="nextflow-pilot-entry"><h2>Pilot reports</h2></section>'
        (self.base/'index.html').write_text('<h1>Established benchmark</h1>'+pilot_entry)
        (self.base/'pilot').mkdir();(self.base/'pilot/index.html').write_text('unchanged pilot')
        (self.base/'batches').mkdir();(self.base/'batches/saved.tsv').write_text('retained archive bytes')
        declaration={'kind':'standard','measured_results':2,'recorded_results':2,'unique_inputs':1,'not_applicable':0,'summary':'Two measured outcomes.','sampling_seeds':[101]}
        (self.pilot/'publication.json').write_text(json.dumps(declaration))
        archive={'origin':'https://archive.example.org','deployment_id':'immutable-deployment'}
        result=compose_standard(self.base,self.pilot,self.output,archive=archive)
        home=(self.output/'index.html').read_text()
        self.assertIn(pilot_entry,home);self.assertIn('nextflow-standard-entry',home)
        self.assertEqual((self.output/'pilot/index.html').read_text(),'unchanged pilot')
        self.assertFalse((self.output/'batches').exists());self.assertTrue((self.base/'batches/saved.tsv').is_file())
        self.assertIn('batches/saved.tsv',result['archived_files'])
        config=json.loads((self.output/'vercel.json').read_text())
        self.assertEqual(config['rewrites'],[{'source':'/batches/:path*','destination':'https://archive.example.org/batches/:path*'}])
        self.assertEqual(result['changed_base_files'],['index.html','vercel.json'])
