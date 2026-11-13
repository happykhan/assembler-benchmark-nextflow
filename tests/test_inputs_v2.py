"""Scientific geometry, pair integrity and immutable shared input reuse."""
import copy
import gzip
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchlib.inputs_v2 import prepare_input
from benchlib.io import digest, fastq_records
from benchlib.preparation import PreparationError
from benchlib.references import canonical_fasta, sequence_statistics


class ScientificInputsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.cache=self.root/'cache';self.cache.mkdir()
        rng=random.Random(1)
        self.sequences={'CHR.1':''.join(rng.choice('ACGT') for _ in range(1200)),
                        'PL.1':''.join(rng.choice('ACGT') for _ in range(85))}
        self.molecules=[dict(accession=a,type='chromosome' if i==0 else 'plasmid',
                            topology='linear' if i==0 else 'circular',**sequence_statistics(s))
                        for i,(a,s) in enumerate(self.sequences.items())]
        source=self.cache/'source.fasta';source.write_text(''.join('>'+a+'\n'+s+'\n' for a,s in self.sequences.items()))
        dep={'id':'reference-source','kind':'reference','target':'source.fasta','source':{'path':'source.fasta'},'sha256':digest(source)}
        reference={'id':'test-reference','compression':'none','download_sha256':digest(source),
                   'canonical_fasta_sha256':__import__('hashlib').sha256(canonical_fasta(self.sequences,self.molecules)).hexdigest(),
                   'molecules':self.molecules}
        self.spec={'id':'input-test','dataset_id':'test-dataset','science_key':'a'*64,'read_technology':'long',
            'source_kind':'simulated','layout':'long_single','reference':reference,'dependencies':[dep['id']],
            'dataset':{'id':'test-dataset'},'recipe':{'method':'native-error-free-v2','coverage':3.5,
                'plasmid_relative_depth':0.25,'length_mean':200,'length_sd':40,'short_fraction':0.5,
                'short_length_mean':40,'short_length_sd':10,'seed':101}}
        self.plan={'dependencies':[dep]}

    def test_native_linear_and_circular_coordinates_exact_budgets_and_mixture(self):
        output=self.root/'prepared'
        receipt=prepare_input(self.spec,self.plan,self.cache,output)
        self.assertTrue(output.is_symlink());self.assertEqual(receipt['files'],['reads.fastq'])
        totals={a:0 for a in self.sequences};short=0
        for header,sequence,quality in fastq_records(output/'reads.fastq'):
            accession=header.removeprefix('@').split(':')[0]
            fields=dict(v.split('=') for v in header.split()[1:]);start=int(fields['start']);length=int(fields['length'])
            source=self.sequences[accession]
            if accession=='CHR.1':self.assertLessEqual(start+length,len(source))
            else:self.assertLessEqual(length,len(source))
            expected=(source+source)[start:start+length]
            if fields['strand']=='-':expected=expected.translate(str.maketrans('ACGT','TGCA'))[::-1]
            self.assertEqual(sequence,expected);self.assertEqual(quality,'I'*length)
            totals[accession]+=length
            if fields['mode']=='short':short+=length
        self.assertEqual(totals,{'CHR.1':4200,'PL.1':74})
        self.assertEqual(short,2137)
        self.assertEqual(receipt['observed']['total_bases'],4274)
        self.assertNotIn(str(self.root),json.dumps(receipt))

    def test_cached_input_and_reference_reused_without_simulation(self):
        self.spec['dependencies'].append('software-prepared-on-submission-host')
        first=prepare_input(self.spec,self.plan,self.cache,self.root/'first')
        with patch('benchlib.inputs_v2._native_reads',side_effect=AssertionError('No resimulation')):
            again=prepare_input(self.spec,self.plan,self.cache,self.root/'second')
        self.assertEqual(first,again)
        self.assertEqual((self.root/'first').resolve(),(self.root/'second').resolve())
        changed=copy.deepcopy(self.spec);changed['id']='input-second-seed';changed['recipe']['seed']=202
        prepare_input(changed,self.plan,self.cache,self.root/'third')
        self.assertEqual((self.root/'first/reference.fasta').resolve(),(self.root/'third/reference.fasta').resolve())
        self.assertEqual(len(list((self.cache/'references/prepared').iterdir())),1)

    def test_corrupted_accepted_input_rejected_without_overwrite(self):
        output=self.root/'prepared';prepare_input(self.spec,self.plan,self.cache,output)
        (output/'reads.fastq').write_text('corrupt')
        with self.assertRaisesRegex(PreparationError,'cache bytes invalid'):
            prepare_input(self.spec,self.plan,self.cache,self.root/'again')
        self.assertEqual((output/'reads.fastq').read_text(),'corrupt')
        self.assertFalse((self.root/'again').exists())

    def test_generated_reads_cannot_be_labelled_real(self):
        self.spec['source_kind']='real'
        with self.assertRaisesRegex(ValueError,'cannot be labelled real'):
            prepare_input(self.spec,self.plan,self.cache,self.root/'prepared')

    def real_spec(self,paired=False,mismatch=False):
        spec=copy.deepcopy(self.spec);spec.update(source_kind='real',read_technology='short' if paired else 'long',
            layout='short_paired' if paired else 'long_single',recipe={'method':'local-files-v1'})
        files={};dependencies=copy.deepcopy(self.plan['dependencies'])
        for role in (['r1','r2'] if paired else ['reads']):
            path=self.cache/(role+'.fastq.gz')
            names=['pair-a','pair-b'] if not mismatch or role!='r2' else ['pair-a']
            payload=''.join('@'+name+('/1' if role=='r1' else '/2' if role=='r2' else '')+'\nACGT\n+\nIIII\n' for name in names)
            path.write_bytes(gzip.compress(payload.encode(),mtime=0))
            source={'path':role+'.fastq.gz'}
            dependencies.append({'id':role,'kind':'real_reads','target':path.name,'source':source,'sha256':digest(path),'compression':'gzip'})
            files[role]={'source':source,'sha256':digest(path)}
        spec['dataset']={'id':'test-dataset','files':files,'sample_id':'SAMPLE1','reference_sample_id':'SAMPLE1','run_accession':'RUN1'}
        spec['dependencies']=[d['id'] for d in dependencies]
        return spec,{'dependencies':dependencies}

    def test_real_paired_input_identity_and_mate_validation(self):
        spec,plan=self.real_spec(paired=True)
        receipt=prepare_input(spec,plan,self.cache,self.root/'paired')
        self.assertEqual(receipt['source_kind'],'real');self.assertEqual(receipt['observed']['pair_count'],2)
        self.assertEqual(receipt['files'],['reads_1.fastq','reads_2.fastq'])

    def test_invalid_pairs_never_become_accepted_input(self):
        spec,plan=self.real_spec(paired=True,mismatch=True)
        with self.assertRaisesRegex(ValueError,'identifiers/counts differ'):
            prepare_input(spec,plan,self.cache,self.root/'paired')
        self.assertFalse((self.cache/'inputs/test-dataset/input-test').exists())

    def test_read_order_preserves_duplicate_records_qualities_and_pairing(self):
        spec,plan=self.real_spec(paired=True)
        for role in ('r1','r2'):
            path=self.cache/(role+'.fastq.gz');mate='1' if role=='r1' else '2'
            rows=['@same/'+mate+'\nACGT\n+\nIJKL\n']*2+['@other/'+mate+'\nAC\n+\nIJ\n']
            path.write_bytes(gzip.compress(''.join(rows).encode(),mtime=0))
            next(d for d in plan['dependencies'] if d['id']==role)['sha256']=digest(path)
        original=prepare_input(spec,plan,self.cache,self.root/'original')
        reordered=copy.deepcopy(spec);reordered['id']='input-ordered';reordered['recipe']['read_order']={'method':'length_ascending','seed':7}
        result=prepare_input(reordered,plan,self.cache,self.root/'ordered')
        self.assertEqual(result['observed']['read_order']['record_count'],3)
        for name in original['files']:
            before=list(fastq_records(self.root/'original'/name));after=list(fastq_records(self.root/'ordered'/name))
            self.assertEqual(sorted(before),sorted(after));self.assertEqual(len(after[0][1]),2)
        self.assertNotEqual(result['observed']['read_order']['source_order_sha256'],result['observed']['read_order']['output_order_sha256'])

    def test_art_exact_command_uses_total_depth_and_records_realised_statistics(self):
        # Binary execution is mocked here; actual ART is validated on the cluster.
        self.spec['reference']['molecules']=self.molecules[:1]
        source=self.cache/'source.fasta';source.write_text('>CHR.1\n'+self.sequences['CHR.1']+'\n')
        self.plan['dependencies'][0]['sha256']=digest(source)
        self.spec['reference'].update(download_sha256=digest(source),canonical_fasta_sha256=__import__('hashlib').sha256(canonical_fasta({'CHR.1':self.sequences['CHR.1']},self.molecules[:1])).hexdigest())
        spec=copy.deepcopy(self.spec);spec.update(layout='short_paired',read_technology='short',
            recipe={'method':'art-illumina-v1','version':'2016.06.05','profile':'HS25','read_length':150,
                'coverage':30,'coverage_convention':'total_read_bases_per_reference_base','fragment_mean':350,
                'fragment_sd':50,'seed':101,'boundary_policy':'linear_no_wrap'})
        def run(command,**kwargs):
            if command[1]=='--version':return subprocess.CompletedProcess(command,0,'ART Q version 2.5.8','')
            directory=Path(kwargs['cwd']);prefix=command[command.index('-o')+1]
            for mate in (1,2):
                (directory/(prefix+str(mate)+'.fq')).write_text(''.join('@pair-'+str(i)+'/'+str(mate)+'\n'+'A'*150+'\n+\n'+'I'*150+'\n' for i in range(120)))
            return subprocess.CompletedProcess(command,0)
        with patch('subprocess.run',side_effect=run):receipt=prepare_input(spec,self.plan,self.cache,self.root/'art')
        argv=receipt['commands'][0]['argv']
        self.assertEqual(argv[argv.index('-f')+1],'30')
        self.assertEqual(argv[argv.index('-nf')+1],'1');self.assertEqual(argv[argv.index('-k')+1],'150')
        self.assertEqual(receipt['observed']['total_bases'],36000)
        self.assertEqual(receipt['observed']['per_replicon'][0]['realised_coverage'],30)
        self.assertTrue(all(not value.startswith(str(self.root)) for value in argv))
