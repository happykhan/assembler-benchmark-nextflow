"""Offline scientific-contract regression tests for the native diagnostic port."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import io
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from diagnostic_core.common import digest,fasta,fingerprint,save,write_fasta
from diagnostic_core.planning import build_plan
from diagnostic_core.reads import exact_reads
from diagnostic_core.preparation import prepare,check_reference,admit_references
from diagnostic_core.topology import output_topology
from diagnostic_core.scoring import equivalent,evaluate
from diagnostic_core.assessment import assess
from diagnostic_core.read_order import records,record_fingerprints,permutation,sequence_fingerprint
from diagnostic_core.comparison import compare_results
from diagnostic_core.diagnostics import summarise_paf
from diagnostic_core.assessments import continuous_assessment
from benchlib.diagnostic_planning import build_diagnostic_plan

ROOT=Path(__file__).resolve().parents[1]


def make_case(category='S1',linear=False):
    sequence='AACCGTATGGAAGTCACATCGATGCTAGTCCGATGGCATACCTAGGTACA'
    reference={'refseq_accession':'TEST.1','replicon_name':'fixture','length_bp':len(sequence),
        'molecule_type':'plasmid','topology':'linear' if linear else 'circular',
        'sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest()}
    simulation={'model':'exact-linear-anchored-v1' if linear else 'exact-lognormal-v1',
        'seed':17,'chromosome_depth':30,'plasmid_relative_depth':1,'length_mean':20,
        'length_sd':5,'length_min':10,'length_max':35,'circular_read_limit':'one_circumference',
        'fastq_phred':40,'minimum_breadth':1 if linear else .99}
    if linear:simulation.update(linear_terminal_reads_per_end=2,linear_terminal_read_length=20)
    case={'id':'fixture-'+category.lower(),'title':'Offline test','category':category,
        'replicons':[reference],'simulation':simulation,'profile_id':'fixture-v1'}
    case['fingerprint']=fingerprint(case)
    return case,sequence


class DiagnosticContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_complete_legacy_case_and_repeat_matrices(self):
        expected={'S1':(2,8),'S2':(10,40),'S3':(2,120),'S4':(12,48),'S5':(6,24),'S6':(6,24),'S7':(12,48)}
        for group,counts in expected.items():
            plan=build_plan(group)
            self.assertEqual((len(plan['cases']),len(plan['executions'])),counts)
            for case in plan['cases']:
                self.assertEqual(case['fingerprint'],fingerprint({k:v for k,v in case.items() if k!='fingerprint'}))
        repeat=build_plan('S3')['executions']
        self.assertEqual({r['threads'] for r in repeat},{1,4})
        self.assertEqual({r['repeat'] for r in repeat},{1,2,3,4,5})
        self.assertEqual({r['mode'] for r in repeat if r['tool']=='flye'},{'default','deterministic'})
        self.assertTrue(all(r['deferred'] for r in build_plan('S6')['executions']))

    def test_native_plan_has_one_bound_assembler_per_run_instance(self):
        plan=build_diagnostic_plan(ROOT,'quick',['S5'],assemblers=['flye'])
        self.assertTrue(plan['slots'])
        self.assertEqual(len(plan['slots']),len(plan['cases']))
        self.assertTrue(all(c['track']=='diagnostic' for c in plan['cases']))
        self.assertTrue(all(c['diagnostic_case']['truth_type']=='native_complement' for c in plan['cases']))
        self.assertTrue(all(all(r['topology']=='linear' for r in c['diagnostic_case']['replicons']) for c in plan['cases']))
        self.assertEqual(plan['resource_policy']['queue_capacity'],1000)
        with self.assertRaisesRegex(ValueError,'deferred'):
            build_diagnostic_plan(ROOT,'standard',['S6'])

    def test_reference_admission_uses_pinned_sequence_not_format(self):
        case,sequence=make_case();path=self.root/'test.fasta'
        write_fasta(path,{'TEST.1':sequence})
        self.assertEqual(check_reference(case['replicons'][0],path,case['replicons'][0]['sequence_sha256']),sequence)
        write_fasta(path,{'TEST.1':sequence[:-1]+'T'})
        with self.assertRaisesRegex(ValueError,'checksum'):
            check_reference(case['replicons'][0],path,case['replicons'][0]['sequence_sha256'])

    def test_exact_sampling_is_byte_repeatable_and_retains_terminal_anchors(self):
        case,sequence=make_case(linear=True)
        a=exact_reads(case,{'TEST.1':sequence},self.root/'a')
        b=exact_reads(case,{'TEST.1':sequence},self.root/'b')
        self.assertEqual(a['status'],'valid')
        self.assertEqual(a['reads_sha256'],b['reads_sha256'])
        self.assertGreaterEqual(a['replicons'][0]['left_terminal_read_count'],2)
        self.assertGreaterEqual(a['replicons'][0]['right_terminal_read_count'],2)
        self.assertFalse(equivalent(sequence,sequence[2:]+sequence[:2],'linear'))
        self.assertTrue(equivalent(sequence,sequence[2:]+sequence[:2],'circular'))

    def test_duplicate_and_embedded_full_copies_do_not_pass(self):
        case,seq=make_case();truth=self.root/'truth.fasta';out=self.root/'out.fasta'
        write_fasta(truth,{'TEST.1':seq})
        for assembly in ({'a':seq,'b':seq},{'a':seq,'embedded':'G'+seq+'T'}):
            write_fasta(out,assembly)
            result=evaluate(case,truth,out)
            self.assertEqual(result['status'],'fail')
        write_fasta(out,{'rotated':seq[5:]+seq[:5]})
        self.assertEqual(evaluate(case,truth,out)['status'],'pass')

    def test_native_prepare_and_assess_bind_input_and_execution(self):
        case,seq=make_case();cache=self.root/'cache';cache.mkdir()
        write_fasta(cache/'TEST.1.fasta',{'TEST.1':seq})
        meta={'id':'native-fixture','track':'diagnostic','diagnostic_case':case,'reference_id':'fixture','preset':'quick'}
        out=self.root/'prepared';manifest=prepare(meta,cache,out,offline=True)
        self.assertEqual(manifest['status'],'completed')
        self.assertEqual(manifest['reads_sha256'],digest(out/'reads.fastq'))
        assembly=self.root/'assembly.fasta';write_fasta(assembly,{'assembled':seq})
        execution=self.root/'execution.json'
        save(execution,{'status':'completed','assembler':'fixture-1','reads_sha256':manifest['reads_sha256'],
            'assembly_sha256':digest(assembly),'elapsed_seconds':1})
        result=assess(meta,out/'truth.fasta',out/'reference.json',out/'input.json',assembly,execution,'fixture-1',self.root/'result.json')
        self.assertEqual(result['assessment']['status'],'completed')
        self.assertEqual(result['sequence_outcome'],'pass')
        # A post-execution changed sequence is an assessment error, never absence.
        write_fasta(assembly,{'assembled':seq[:-1]})
        changed=assess(meta,out/'truth.fasta',out/'reference.json',out/'input.json',assembly,execution,'fixture-1',self.root/'changed.json')
        self.assertEqual(changed['assessment']['status'],'error')
        self.assertIsNone(changed['sequence_outcome'])
        save(execution,{'status':'software_error','assembler':'fixture-1','reads_sha256':manifest['reads_sha256'],'exit_code':139})
        failed=assess(meta,out/'truth.fasta',out/'reference.json',out/'input.json',assembly,execution,'fixture-1',self.root/'failed.json')
        self.assertEqual(failed['assessment']['status'],'not_run')
        self.assertIsNone(failed['sequence_outcome'])

    def test_plassembler_chr_only_strict_endpoint_keeps_output_roles(self):
        case,seq=make_case()
        case['replicons'][0]['molecule_type']='chromosome'
        case['fingerprint']=fingerprint({k:v for k,v in case.items() if k!='fingerprint'})
        cache=self.root/'cache';cache.mkdir();write_fasta(cache/'TEST.1.fasta',{'TEST.1':seq})
        meta={'id':'chr-control','track':'diagnostic','diagnostic_case':case,
              'reference_id':'fixture','preset':'quick','assembler_options':{'plassembler_no_chromosome':False}}
        prepared=self.root/'prepared';manifest=prepare(meta,cache,prepared,True)
        task=self.root/'tool';(task/'tool-output').mkdir(parents=True)
        (task/'tool-output/benchmark_plasmids.fasta').write_text('')
        chromosome=task/'tool-output/chromosome.fasta';write_fasta(chromosome,{'retained':seq})
        assembly=task/'assembly.fasta';assembly.write_bytes(chromosome.read_bytes())
        execution=task/'execution.json'
        save(execution,{'status':'completed','assembler':'plassembler-fixture','tool':'plassembler',
              'reads_sha256':manifest['reads_sha256'],'assembly_sha256':digest(assembly),
              'retained_chromosome_sha256':digest(chromosome),'elapsed_seconds':1})
        result=assess(meta,prepared/'truth.fasta',prepared/'reference.json',prepared/'input.json',
                      assembly,execution,'plassembler-fixture',self.root/'plassembler.json')
        self.assertEqual(result['assessment']['status'],'completed')
        self.assertEqual(result['sequence_outcome'],'pass')
        self.assertEqual(result['evaluation']['contig_count'],0)
        self.assertEqual(result['signatures']['reference_independent']['contig_count'],1)
        evidence=self.root/result['evidence_directory']
        self.assertTrue((evidence/'final-plasmids.fasta').is_file())
        self.assertTrue((evidence/'retained-chromosome.fasta').is_file())
        from benchlib.report import verify_evidence
        verify_evidence(result,evidence,evidence)

    def test_normalized_plassembler_and_mapper_failures_preserve_exact_endpoint(self):
        case,seq=make_case();chromosome_seq=seq[::-1]
        chromosome_ref=copy.deepcopy(case['replicons'][0]);chromosome_ref.update(refseq_accession='CHR.1',replicon_name='chromosome',molecule_type='chromosome',sequence_sha256=hashlib.sha256(chromosome_seq.encode()).hexdigest())
        case['replicons'].insert(0,chromosome_ref)
        case['fingerprint']=fingerprint({k:v for k,v in case.items() if k!='fingerprint'})
        cache=self.root/'cache';cache.mkdir()
        write_fasta(cache/'TEST.1.fasta',{'TEST.1':seq});write_fasta(cache/'CHR.1.fasta',{'CHR.1':chromosome_seq})
        meta={'id':'normalized','track':'diagnostic','diagnostic_case':case,'reference_id':'fixture','preset':'quick',
              'assembler_options':{'plassembler_no_chromosome':False}}
        prepared=self.root/'prepared';manifest=prepare(meta,cache,prepared,True)
        task=self.root/'tool';(task/'tool-output').mkdir(parents=True)
        plasmids=task/'tool-output/benchmark_plasmids.fasta';chromosome=task/'tool-output/chromosome.fasta'
        write_fasta(plasmids,{'1':seq});write_fasta(chromosome,{'1':chromosome_seq})
        assembly=task/'assembly.fasta';write_fasta(assembly,{'final_plasmids:1':seq,'retained_chromosome:1':chromosome_seq})
        sources=[{'role':role,'file':str(path.relative_to(task)),'sha256':digest(path),'bytes':path.stat().st_size}
                 for role,path in [('final_plasmids',plasmids),('retained_chromosome',chromosome)]]
        contig_sources=[{'contig_id':role+':1','source_role':role,'source_contig_id':'1'} for role in ('final_plasmids','retained_chromosome')]
        execution=task/'execution.json'
        record={'status':'completed','assembler':'plassembler-fixture','tool':'plassembler',
                'reads_sha256':manifest['reads_sha256'],'assembly_sha256':digest(assembly),
                'retained_chromosome_sha256':digest(chromosome),'assembly_sources':sources,'contig_sources':contig_sources,'elapsed_seconds':1}
        save(execution,record)
        (task/'tool-output/benchmark_summary.tsv').write_text('contig\tlength\tcircularity\n1\t'+str(len(seq))+'\tcircular\n')
        (task/'tool-output/flye_output').mkdir()
        write_fasta(task/'tool-output/flye_output/assembly.fasta',{'initial_chr':chromosome_seq})
        (task/'tool-output/flye_output/assembly_info.txt').write_text('#seq_name length cov. circ.\ninitial_chr '+str(len(seq))+' 30 Y\n')
        def measured(command,out,err,cwd):
            Path(out).write_text('final_plasmids:1\t'+str(len(seq))+'\t0\t'+str(len(seq))+'\t+\tTEST.1\t'+str(len(seq))+'\t0\t'+str(len(seq))+'\t'+str(len(seq))+'\t'+str(len(seq))+'\t60\ttp:A:P\tcg:Z:'+str(len(seq))+'M\n')
            Path(err).write_text('')
            return {'exit_code':0,'elapsed_seconds':.1,'process_tree_peak_rss_bytes':123}
        with patch('diagnostic_core.mapping.subprocess.run',return_value=SimpleNamespace(stdout='2.28')),patch('diagnostic_core.mapping.measured_run',side_effect=measured) as mapper:
            result=assess(meta,prepared/'truth.fasta',prepared/'reference.json',prepared/'input.json',assembly,execution,'plassembler-fixture',self.root/'mapped.json',run_mapping=True,cpus=3)
        self.assertEqual(result['assessment']['status'],'completed')
        self.assertEqual(result['sequence_outcome'],'pass')
        self.assertEqual(result['evaluation']['contig_count'],1)
        self.assertEqual(result['signatures']['reference_independent']['contig_count'],2)
        self.assertTrue(result['signatures']['reference_independent']['circular_representation_sha256'])
        self.assertEqual(result['diagnostics']['status'],'completed')
        self.assertEqual(result['resources']['assessment_mapper_process_tree_peak_rss_bytes'],123)
        self.assertIn('asm5',mapper.call_args.args[0]);self.assertIn('3',mapper.call_args.args[0])
        self.assertTrue((self.root/result['evidence_directory']/'alignment.paf').is_file())
        def failure(command,out,err,cwd):
            Path(out).write_text('partial')
            Path(err).write_text('mapper failure')
            return {'exit_code':1,'elapsed_seconds':.2,'process_tree_peak_rss_bytes':321}
        with patch('diagnostic_core.mapping.subprocess.run',return_value=SimpleNamespace(stdout='2.28')),patch('diagnostic_core.mapping.measured_run',side_effect=failure):
            failed=assess(meta,prepared/'truth.fasta',prepared/'reference.json',prepared/'input.json',assembly,execution,'plassembler-fixture',self.root/'mapper-failed.json',run_mapping=True)
        self.assertEqual(failed['assessment']['status'],'completed')
        self.assertEqual(failed['sequence_outcome'],'pass')
        self.assertEqual(failed['diagnostics']['status'],'error')
        self.assertEqual(failed['resources']['assessment_mapper_process_tree_peak_rss_bytes'],321)
        self.assertNotIn('replicons',failed['diagnostics'])
        self.assertTrue(failed['diagnostics']['partial_paf_sha256'])
        # Corrupt role mapping must fail even though the normalized file hash matches.
        record['contig_sources'][0]['source_contig_id']='wrong';save(execution,record)
        corrupt=assess(meta,prepared/'truth.fasta',prepared/'reference.json',prepared/'input.json',assembly,execution,'plassembler-fixture',self.root/'wrong-mapping.json')
        self.assertEqual(corrupt['assessment']['status'],'error')
        self.assertIsNone(corrupt['sequence_outcome'])

    def test_repeat_mode_and_thread_meta_do_not_change_frozen_read_bytes(self):
        case,seq=make_case();cache=self.root/'cache';cache.mkdir()
        write_fasta(cache/'TEST.1.fasta',{'TEST.1':seq})
        common={'track':'diagnostic','diagnostic_case':case,'reference_id':'fixture'}
        a=prepare({**common,'id':'repeat-1','repeat':1,'threads':1,'mode':'default'},cache,self.root/'one',True)
        b=prepare({**common,'id':'repeat-2','repeat':2,'threads':4,'mode':'deterministic'},cache,self.root/'two',True)
        self.assertEqual(a['reads_sha256'],b['reads_sha256'])
        self.assertEqual(a['reads_gzip_sha256'],b['reads_gzip_sha256'])
        self.assertNotEqual(a['case'],b['case'])

    def test_concurrent_reference_cache_downloads_use_unique_atomic_paths(self):
        case,seq=make_case();cache=self.root/'shared-cache'
        barrier=Barrier(2)
        def response(*args,**kwargs):
            barrier.wait(timeout=5)
            return io.BytesIO(('>TEST.1\n'+seq+'\n').encode())
        with patch('diagnostic_core.preparation.urllib.request.urlopen',side_effect=response):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(admit_references,case,cache) for _ in range(2)]
                outputs=[future.result(timeout=10) for future in futures]
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(list(cache.iterdir()),[cache/'TEST.1.fasta'])

    def test_tool_circularity_labels_are_bound_without_using_reference(self):
        case,seq=make_case();task=self.root/'flye';(task/'tool-output').mkdir(parents=True)
        assembly=task/'assembly.fasta';write_fasta(assembly,{'contig_1':seq})
        (task/'tool-output/assembly_info.txt').write_text('#seq_name length cov. circ.\ncontig_1 '+str(len(seq))+' 30 Y\n')
        evidence=self.root/'metadata';evidence.mkdir()
        labels,receipt=output_topology(task,{'tool':'flye'},assembly,evidence)
        self.assertEqual(labels,{'contig_1':True})
        self.assertTrue(receipt['sources'][0]['file_sha256'])
        self.assertTrue((evidence/'final-assembly_info.txt').is_file())
        # A claim with the wrong length cannot enable circular normalisation.
        (task/'tool-output/assembly_info.txt').write_text('#seq_name length cov. circ.\ncontig_1 99 30 Y\n')
        labels,_=output_topology(task,{'tool':'flye'},assembly,evidence)
        self.assertEqual(labels,{})

    def test_full_record_multiset_preserves_duplicates_and_quality(self):
        items=[b'@a\nACG\n+\nIII\n',b'@a\nACG\n+\nIII\n',b'@b\nTTA\n+\nJJJ\n']
        a=record_fingerprints(items);b=record_fingerprints(items[::-1])
        self.assertEqual(a['record_multiset_sha256'],b['record_multiset_sha256'])
        self.assertNotEqual(a['record_order_sha256'],b['record_order_sha256'])
        self.assertNotEqual(a['record_multiset_sha256'],record_fingerprints(items[:2])['record_multiset_sha256'])
        self.assertNotEqual(a['record_multiset_sha256'],record_fingerprints([items[0].replace(b'III',b'JJJ'),*items[1:]])['record_multiset_sha256'])
        self.assertEqual(permutation(30,9),permutation(30,9))

    def test_s7_stages_only_admitted_frozen_source(self):
        case,seq=make_case();source=self.root/'frozen'
        original=exact_reads(case,{'TEST.1':seq},source)
        s7=copy.deepcopy(case);s7.pop('fingerprint');s7.update(id='s7-fixture-shuffle-1',category='S7',read_order={'order_id':'shuffle-1','repeat':1});s7['fingerprint']=fingerprint(s7)
        declared={'case_id':case['id'],'input_manifest_sha256':digest(source/'input.json'),'reads_sha256':original['reads_sha256'],
                  'truth_sha256_for_provenance_only':original['truth_sha256']}
        meta={'id':'s7-run','track':'diagnostic','diagnostic_case':s7,'input_recipe':{'source':declared,'order':{'id':'shuffle-1','shuffle_seed':1}}}
        result=prepare(meta,self.root/'unused-cache',self.root/'permuted',True,source)
        before=record_fingerprints(records(source/'reads.fastq.gz'))
        self.assertEqual(result['read_order']['record_multiset_sha256'],before['record_multiset_sha256'])
        self.assertNotEqual(result['read_order']['record_order_sha256'],before['record_order_sha256'])
        with self.assertRaisesRegex(ValueError,'frozen-input-dir'):
            prepare(meta,self.root/'unused-cache',self.root/'missing',True)

    def test_unknown_circularity_does_not_hide_end_changes(self):
        seq='AACCGTATGG'
        a=sequence_fingerprint([('a',seq)]);b=sequence_fingerprint([('b',seq[2:]+seq[:2])])
        self.assertNotEqual(a['end_sensitive_sha256'],b['end_sensitive_sha256'])
        self.assertIsNone(a['circular_representation_sha256'])
        a=sequence_fingerprint([('a',seq)],{'a':True});b=sequence_fingerprint([('b',seq[2:]+seq[:2])],{'b':True})
        self.assertEqual(a['circular_representation_sha256'],b['circular_representation_sha256'])

    def test_continuous_s6_has_no_binary_endpoint(self):
        case,_=make_case('S6')
        self.assertEqual(continuous_assessment(case)['status'],'unscored')
        self.assertFalse(continuous_assessment(case)['binary_endpoint_validated'])

    def test_paf_measurement_rejects_malformed_coordinates(self):
        case,_=make_case();path=self.root/'bad.paf';path.write_text('bad\tPAF\n')
        with self.assertRaisesRegex(ValueError,'PAF line'):
            summarise_paf(case,path)

    def test_s7_reference_failures_never_change_agreement_and_missing_is_incomplete(self):
        cases=[];results=[];slots=[]
        for order in ('original','shuffle-1'):
            for repeat in (1,2):
                identifier=order+'-'+str(repeat)
                case={'id':identifier,'category':'S7','legacy_case_id':identifier,'threads':4,'mode':'default','repeat':repeat,
                      'diagnostic_case':{'read_order':{'order_id':order}},'input_recipe':{'source':{'case_id':'frozen'}}}
                cases.append(case);slots.append({'case_id':identifier,'assembler':'tool-1'})
                results.append({'case':case,'assembler':'tool-1','assessment':{'status':'completed'},'sequence_outcome':'fail',
                    'signatures':{'reference_independent':{'end_sensitive_sha256':'same','circular_representation_sha256':None}},
                    'read_order_input':{'record_count':20,'record_multiset_sha256':'same-input','record_order_sha256':order}})
        plan={'cases':cases,'slots':slots,'assembler_definitions':{'tool-1':{'version':'1'}},'plan_sha256':'fixture'}
        result=compare_results(results,plan)['groups'][0]
        self.assertEqual(result['end_sensitive']['verdict'],'No order effect observed')
        self.assertTrue(result['end_sensitive']['complete'])
        self.assertFalse(result['circular_representation']['complete'])
        missing=compare_results(results[:-1],plan)['groups'][0]
        self.assertFalse(missing['complete'])
        self.assertIn('Not assessed',missing['end_sensitive']['verdict'])
        results[0]['read_order_input']['record_multiset_sha256']='changed'
        self.assertFalse(compare_results(results,plan)['groups'][0]['input_equivalence_verified'])

if __name__=='__main__':unittest.main()
