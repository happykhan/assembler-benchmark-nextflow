"""Public projection of current packages: no scientific execution or bulky data."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from benchlib.current_results import publish_result,set_catalogue_metadata,load_current
from reporting.current_site import render_current,validate_site


def make_store(directory):
    directory=Path(directory);sources=directory/'sources';sources.mkdir(parents=True)
    (sources/'graph.json').write_text(json.dumps({'status':'available','nodes':[{'id':'segment1','length_bp':1000},{'id':'segment2','length_bp':500}],'edges':[{'source':'segment1','target':'segment2'}]}))
    (sources/'dotplot.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 180"><rect width="100%" height="100%" fill="white"/><path d="M40 140 L540 30" stroke="#245db4" stroke-width="2"/><text x="40" y="170" font-size="14">Recorded software-fixture alignment</text></svg>')
    (sources/'alignments.tsv').write_text('query\treference\nfixture-contig\tfixture-reference\n')
    (sources/'assembly.fasta').write_text('>fixture\nASSEMBLY_SEQUENCE_NOT_PUBLIC\n')
    (sources/'stdout.log').write_text('RAW_LOG_NOT_PUBLIC')
    root=directory/'results'
    set_catalogue_metadata(root,{'collections':{'mixed':{'title':'Mixed software validation','question':'Can current short/long packages be compared without merging their methods?','scientific_scope':'Software fixtures, not scientific benchmark findings.'},'unused':{'title':'Unrun collection','question':'No results yet.'}},'scenarios':{'gc-composition':{'title':'GC and composition','question':'What measurements are available for this selected family?'},'plasmids':{'title':'Plasmids','question':'Which workflows are explicitly eligible for these inputs?'}}})
    records=[]
    for identity,technology,source,workflow,status in [('long-sim','long','simulated','raven','measured'),('short-sim','short','simulated','skesa','measured'),('long-real','long','real','raven','execution_failure'),('short-na','short','simulated','skesa','not_applicable')]:
        record={'schema_version':2,'case':{'id':identity,'title':identity.replace('-',' '),'science_key':'science-'+identity,'dataset_id':'dataset-'+identity,'input_id':'input-'+identity,'collections':['mixed'],'scenarios':['gc-composition'] if status=='measured' else ['plasmids'],'read_technology':technology,'source_kind':source,'scientific_repeat_id':None,'recipe':{'seed':101},'sampling_seed':101},'workflow':{'id':workflow+'-default','tool':workflow,'version':'1.0','version_order':1,'colour':'#f58518' if workflow=='raven' else '#54a24b','configuration':{'mode':'default'}},'status':status,'metrics':[{'name':'reference_breadth','value':.995,'unit':'fraction','method':'software-fixture-union','primary':True},{'name':'workflow_wall_seconds','value':12.5,'unit':'s','method':'software-fixture-wall'}] if status=='measured' else [],'reason':'Declared software fixture status','input':{'observed':{'read_count':300,'pair_count':150 if technology=='short' else None,'total_bases':3000000,'n50':11000},'reference':{'organism':'Software reference fixture'}},'experiment':{'description':'Software fixture only; no biological claim'}}
        artifacts={name:{'source':sources/name,'role':role} for name,role in [('assembly.fasta','assembly'),('stdout.log','stdout')]}
        if status=='measured':artifacts.update({name:{'source':sources/name,'role':role} for name,role in [('graph.json','graph_model'),('dotplot.svg','alignment_plot'),('alignments.tsv','alignment_coordinates')]})
        publish_result(root,record,artifacts);records.append(record)
    return root,records


class CurrentSiteTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.directory=Path(tmp.name);self.root,self.records=make_store(self.directory);self.site=self.directory/'site'

    def test_multiple_packages_render_once_with_methods_and_typed_filters(self):
        with patch('subprocess.run',side_effect=AssertionError('Rendering must not execute scientific tools')):
            report=render_current(self.root,self.site)
        self.assertEqual(report['status'],'pass');self.assertEqual(report['errors'],[])
        home=(self.site/'index.html').read_text();self.assertIn('Broad benchmarks',home);self.assertIn('Targeted scenarios',home);self.assertNotIn('metric-plot',home)
        comparison=(self.site/'broad/mixed.html').read_text()
        for text in ['Can current short/long packages','Read technology','Data source','Not applicable','Assembly failed','software-fixture-union']:self.assertIn(text,comparison)
        self.assertIn('Not run',(self.site/'broad/unused.html').read_text())
        self.assertEqual(len(list((self.site/'artifacts').rglob('graph.json'))),2)
        forbidden={'.fasta','.fa','.fna','.fastq','.fq','.gfa','.paf','.log'}
        self.assertFalse(any(p.suffix in forbidden for p in self.site.rglob('*')))
        self.assertFalse(any('ASSEMBLY_SEQUENCE_NOT_PUBLIC' in p.read_text() or 'RAW_LOG_NOT_PUBLIC' in p.read_text() for p in self.site.rglob('*') if p.suffix in {'.json','.html','.tsv'}))
        public=json.loads(next((self.site/'results').glob('*.json')).read_text());self.assertNotIn('package',public);self.assertNotIn('dependency_packages',public)

    def test_failure_rerender_removes_stale_graph_and_success_measurements(self):
        render_current(self.root,self.site);record=copy.deepcopy(self.records[0]);record.update(status='assessment_failure',metrics=[],sequence_outcome=None)
        before={p for p in (self.site/'artifacts').rglob('graph.json')};publish_result(self.root,record)
        render_current(self.root,self.site);after={p for p in (self.site/'artifacts').rglob('graph.json')};self.assertEqual(len(before-after),1)
        current=[r for r in load_current(self.root) if r['case']['id']=='long-sim'][0]
        page=(self.site/'results'/(current['result_id']+'.html')).read_text();self.assertIn('Assessment failed',page);self.assertNotIn('data-graph-transform',page)

    def test_site_copy_does_not_need_original_results_or_source_files(self):
        render_current(self.root,self.site);copied=self.directory/'copy';shutil.copytree(self.site,copied)
        shutil.rmtree(self.root);shutil.rmtree(self.directory/'sources')
        self.assertEqual(validate_site(copied)['status'],'pass')
        self.assertTrue((copied/'assets/plex-sans.woff2').is_file())

    def test_not_run_and_repeats_are_not_collapsed(self):
        base=copy.deepcopy(self.records[0])
        base.update(status='not_run',metrics=[],reason='Selected but not executed')
        base['case']['id']='unrun-case';base['case']['science_key']='science-unrun-case'
        publish_result(self.root,base)
        for index in [1,2]:
            repeated=copy.deepcopy(self.records[0]);repeated['case'].update(scientific_repeat_id='technical-'+str(index),scientific_repeat={'id':'technical-'+str(index),'kind':'technical','index':index})
            publish_result(self.root,repeated)
        render_current(self.root,self.site)
        comparison=(self.site/'broad/mixed.html').read_text()
        self.assertIn('Selected but not executed',comparison)
        self.assertIn('data-status="not_run"',comparison)
        self.assertIn('technical 1',comparison);self.assertIn('technical 2',comparison)
        self.assertEqual(len(list((self.site/'results').glob('*.json'))),7)
        self.assertIn('technical-1',(self.site/'data/measurements.tsv').read_text())

    def test_refuses_unowned_output_and_preserves_scientific_output(self):
        self.site.mkdir();(self.site/'unrelated.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError,'not owned'):render_current(self.root,self.site)
        self.assertEqual((self.site/'unrelated.txt').read_text(),'keep')
        with self.assertRaisesRegex(ValueError,'scientific results'):render_current(self.root,self.root)
        self.assertEqual(len(load_current(self.root)),4)
