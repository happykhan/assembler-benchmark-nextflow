"""Atomic scoped replacement, upgrades and portable current packages."""
import json
import multiprocessing
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from benchlib.current_results import export_subset,load_current,publish_result,refresh_summaries,result_identity,set_catalogue_metadata,validate_package


def record(case='one', version='1.0', order=1, status='measured'):
    return {'schema_version':2,'case':{'id':case,'science_key':'science-'+case,'dataset_id':'dataset','input_id':'input','collections':['broad'],'scenarios':['composition'],'read_technology':'long','source_kind':'simulated','scientific_repeat_id':None,'description':'Software contract fixture'},'workflow':{'id':'assembler-default','version':version,'version_order':order},'status':status,'metrics':[{'name':'contiguity','value':1.2,'unit':'ratio','method':'fixture-alignment'}] if status=='measured' else [],'input':{'description':'Small fixture'}}


def worker(root,case,source,queue):
    try:
        publish_result(root,record(case),{'assembly.fasta':source},{'input':{'record':{'kind':'reference'},'files':{'reference.fasta':source}}});queue.put('ok')
    except Exception as error:queue.put(repr(error))


class CurrentResultsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.directory=Path(tmp.name);self.root=self.directory/'results';self.source=self.directory/'source.fasta';self.source.write_text('>fixture\nACGT\n')

    def publish(self,case='one',**kwargs):
        return publish_result(self.root,record(case,**kwargs),{'assembly.fasta':self.source},{'input':{'record':{'kind':'reference'},'files':{'reference.fasta':self.source}}})

    def test_stable_identity_matches_catalogue(self):
        from benchlib.catalogue import result_identity as other
        self.assertEqual(result_identity('one','assembler-default'),other('one','assembler-default'))
        self.assertNotEqual(result_identity('one','assembler-default','technical-2'),result_identity('one','assembler-default'))

    def test_failure_removes_old_success_artifacts_and_preserves_unrelated(self):
        old=self.publish();other=self.publish('other');new=publish_result(self.root,record(status='execution_failure'),{'stderr.log':self.source})
        self.assertEqual(old['result_id'],new['result_id']);self.assertFalse((self.root/old['package']).exists())
        self.assertTrue((self.root/other['package']/'artifacts/assembly.fasta').is_file())
        self.assertFalse((self.root/new['package']/'artifacts/assembly.fasta').exists())
        self.assertEqual({r['case']['id']:r['status'] for r in load_current(self.root)},{'one':'execution_failure','other':'measured'})
        self.assertEqual(len(list((self.root/'packages'/old['result_id']).iterdir())),1)

    def test_upgrade_and_downgrade_guard(self):
        old=self.publish();new=self.publish(version='2.0',order=2);self.assertEqual(old['result_id'],new['result_id']);self.assertFalse((self.root/old['package']).exists())
        for version,order in [('1.0',1),('different',2),('2.0',3)]:
            with self.subTest(version=version),self.assertRaises(ValueError):self.publish(version=version,order=order)
        self.assertEqual(load_current(self.root)[0]['workflow']['version'],'2.0')

    def test_science_identity_cannot_change_silently(self):
        old=self.publish();changed=record();changed['case']['science_key']='different'
        with self.assertRaisesRegex(ValueError,'new case identity'):publish_result(self.root,changed)
        self.assertTrue((self.root/old['package']).is_dir())

    def test_configuration_cannot_change_under_a_version_upgrade(self):
        before=record();before['workflow']['configuration']={'mode':'raw'}
        publish_result(self.root,before)
        after=record(version='2.0',order=2);after['workflow']['configuration']={'mode':'high-quality'}
        with self.assertRaisesRegex(ValueError,'new configuration ID'):publish_result(self.root,after)
        self.assertEqual(load_current(self.root)[0]['workflow']['configuration'],{'mode':'raw'})

    def test_shared_dependency_once_and_conflict_rejected(self):
        self.publish();self.publish('second');self.assertEqual(len(list((self.root/'dependencies').iterdir())),1)
        self.source.write_text('>changed\nTTTT\n')
        with self.assertRaisesRegex(ValueError,'different bytes or metadata'):self.publish('third')
        self.assertEqual(len(load_current(self.root)),2)

    def test_interruption_does_not_displace_current(self):
        old=self.publish()
        with patch('benchlib.current_results._copy_artifacts',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):publish_result(self.root,record(),{'new.fasta':self.source})
        self.assertTrue((self.root/old['package']/'artifacts/assembly.fasta').is_file())
        self.assertEqual(len(list((self.root/'packages'/old['result_id']).iterdir())),1)

    def test_absolute_paths_traversal_and_corruption_rejected(self):
        bad=record();bad['provenance']={'work':'/original/work'}
        with self.assertRaisesRegex(ValueError,'absolute work-directory'):publish_result(self.root,bad)
        with self.assertRaisesRegex(ValueError,'escapes its package'):publish_result(self.root,record(),{'../escape':self.source})
        row=self.publish();package=self.root/row['package'];(package/'artifacts/assembly.fasta').write_text('corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'):validate_package(package)
        with self.assertRaisesRegex(ValueError,'checksum'):load_current(self.root)

    def test_results_only_summary_invalidation_and_metadata(self):
        self.publish();self.assertFalse((self.root/'index.html').exists())
        set_catalogue_metadata(self.root,{'collections':{'broad':{'title':'Broad data','question':'Recovery?'}},'scenarios':{}})
        refresh_summaries(self.root);summary=self.root/'summaries/scenario/composition';validate_package(summary)
        self.assertIn('measured',(summary/'index.html').read_text())
        publish_result(self.root,record(status='assessment_failure'));self.assertFalse(summary.exists())
        refresh_summaries(self.root);self.assertIn('assessment_failure',(summary/'index.html').read_text())
        self.assertEqual(json.loads((self.root/'catalogue.json').read_text())['collections']['broad']['title'],'Broad data')

    def test_catalogue_metadata_merges_incremental_selections(self):
        self.publish()
        set_catalogue_metadata(self.root,{'collections':{'first':{'title':'First'}},'scenarios':{'one':{'question':'First question'}}})
        set_catalogue_metadata(self.root,{'collections':{'second':{'title':'Second'}},'scenarios':{'two':{'question':'Second question'}}})
        catalogue=json.loads((self.root/'catalogue.json').read_text())
        self.assertEqual(set(catalogue['collections']),{'first','second'})
        self.assertEqual(set(catalogue['scenarios']),{'one','two'})
        self.assertEqual(len(load_current(self.root)),1)

    def test_subset_portable_without_original_store_or_work(self):
        first=self.publish();self.publish('second');output=self.directory/'portable';export_subset(self.root,output,[first['result_id']])
        self.source.unlink();shutil.rmtree(self.root);rows=load_current(output);self.assertEqual(len(rows),1)
        catalogue=json.loads((output/'catalogue.json').read_text());package=output/catalogue['results'][0]['package'];validate_package(package)
        self.assertTrue((package/'index.html').is_file());self.assertTrue((package/'measurements.tsv').is_file())
        self.assertEqual(len(list((output/'dependencies').rglob('reference.fasta'))),1)
        self.assertFalse(any(p.is_symlink() for p in output.rglob('*')))
        publish_result(output,record(version='2.0',order=2,status='execution_failure'));self.assertEqual(load_current(output)[0]['status'],'execution_failure')

    def test_not_run_and_scientific_repeat_are_explicit(self):
        unrun=record(status='not_run');publish_result(self.root,unrun)
        unrun['metrics']=[{'name':'breadth','value':1,'unit':'fraction','method':'fixture'}]
        with self.assertRaisesRegex(ValueError,'cannot contain measured'):publish_result(self.root,unrun)
        for index in [1,2]:
            repeated=record();repeated['case'].update(scientific_repeat_id='technical-'+str(index),scientific_repeat={'id':'technical-'+str(index),'kind':'technical','index':index})
            publish_result(self.root,repeated)
        self.assertEqual(len(load_current(self.root)),3)
        repeated['case']['scientific_repeat']['id']='mismatched'
        with self.assertRaisesRegex(ValueError,'must match'):publish_result(self.root,repeated)

    def test_concurrent_publishers_share_one_dependency(self):
        context=multiprocessing.get_context('spawn');queue=context.Queue();processes=[context.Process(target=worker,args=(str(self.root),case,str(self.source),queue)) for case in ['first','second']]
        for process in processes:process.start()
        for process in processes:process.join(30);self.assertEqual(process.exitcode,0)
        outcomes=[queue.get(timeout=5) for _ in processes];self.assertEqual(outcomes,['ok','ok'])
        self.assertEqual(len(load_current(self.root)),2);self.assertEqual(len(list((self.root/'dependencies').iterdir())),1)
