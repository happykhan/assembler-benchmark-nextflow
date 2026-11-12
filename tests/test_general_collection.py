"""Frozen cohort and lossless archive admission regressions; no scientific downloads."""
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from benchlib.general_inputs import _range, obtain_reads, prepare_general_input
from benchlib.general_planning import build_general_plan, load_collection, validate_general_plan
from benchlib.io import digest

ROOT = Path(__file__).resolve().parents[1]


class GeneralCollectionTests(unittest.TestCase):
    def test_exact_fifty_and_original_admission_bindings(self):
        selection, inputs = load_collection(ROOT)
        self.assertEqual(len(inputs), 50)
        self.assertEqual(selection['archives']['reads']['id'], 20188401)
        self.assertEqual(selection['archives']['references']['id'], 20188407)
        self.assertEqual(sum(d['plasmid_count'] for d in selection['datasets']), 50)
        for row in inputs.values():
            manifest = row['manifest']
            self.assertEqual(manifest['read_archive_member']['name'], manifest['case']['id'] + '.fastq.gz')
            self.assertEqual(len(row['source_sha256']), 64)

    def test_selection_frozen_before_execution_and_no_fifth_outcome(self):
        plan = build_general_plan(ROOT)
        self.assertEqual(plan['expected_slots'], 200)
        self.assertEqual(len(plan['assembler_definitions']), 4)
        self.assertEqual(validate_general_plan(ROOT, plan), plan)
        self.assertNotIn('miniasm', plan['assemblers'])
        edited = copy.deepcopy(plan)
        edited['read_inputs'][plan['cases'][0]['id']]['manifest']['reads_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_general_plan(ROOT, edited)

    def test_selectors_reject_unknown_duplicates_and_wrong_preset(self):
        for arguments in ({'cases':'missing'}, {'cases':'a,a'}, {'groups':'metagenomics'}, {'preset':'quick'}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                build_general_plan(ROOT, assemblers='flye', **arguments)
        selection, _ = load_collection(ROOT)
        name = selection['datasets'][0]['id']
        plan = build_general_plan(ROOT, cases=name, assemblers='flye')
        self.assertEqual([r['id'] for r in plan['cases']], [name])
        self.assertEqual(plan['expected_slots'], 1)

    def test_changed_frozen_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'assets/general', root / 'assets/general')
            p = root / 'assets/general/inputs.json'
            p.write_text(p.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'Frozen general source changed'):
                load_collection(root)


class GeneralInputTests(unittest.TestCase):
    def fixture(self, root):
        reference = b'>NC_000001.1\nACGTACGT\n'
        fastq = b'@original one\r\nACGT\r\n+original\r\nIIII\r\n@two\nAC\n+\nII\n'
        zipped = gzip.compress(fastq, mtime=0)
        member = tarfile.TarInfo('fixture.fastq.gz')
        member.size = len(zipped)
        header = member.tobuf()
        archive = header + zipped + b'\0' * ((-len(zipped)) % 512) + b'\0' * 1024
        (root / 'reads.tar').write_bytes(archive)
        manifest = {'case': {'id':'fixture', 'replicons':[{'refseq_accession':'NC_000001.1', 'length_bp':8, 'molecule_type':'chromosome'}]},
            'status':'valid', 'reads_sha256':hashlib.sha256(zipped).hexdigest(),
            'truth_sha256':hashlib.sha256(reference).hexdigest(),
            'source_read_archive':{'name':'reads.tar','size':len(archive),'download_url':'https://invalid.example/reads'},
            'source_reference_archive':{'name':'references.tar.gz','size':1,'computed_md5':'unused'},
            'read_archive_member':{'name':member.name,'offset':512,'size':len(zipped),'header_sha256':hashlib.sha256(header).hexdigest()},
            'statistics':{'read_count':2,'total_read_bases':6,'read_n50_bp':4,'uncompressed_fastq_sha256':hashlib.sha256(fastq).hexdigest()}}
        case = dict(manifest['case'],track='general',input_policy='published_frozen_bytes_no_resimulation')
        d=root/'fixture';d.mkdir();(d/'reference.fasta').write_bytes(reference)
        return case, {'manifest':manifest,'source_sha256':'a'*64}, fastq

    def test_offline_tar_admission_preserves_original_fastq_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,fastq=self.fixture(root)
            out=root/'result'
            with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
                record=prepare_general_input(case,admission,root,out,offline=True)
                repeated=prepare_general_input(case,admission,root,out,offline=True)
            self.assertEqual((out/'reads.fastq').read_bytes(),fastq)
            self.assertEqual(record,repeated)
            self.assertEqual(record['reads_sha256'],digest(out/'reads.fastq'))
            self.assertNotEqual(record['reads_sha256'],record['published_compressed_reads_sha256'])
            self.assertEqual(record['original_admission'],admission['manifest'])

    def test_corrupt_member_header_reference_and_read_checksum_rejected(self):
        for kind in ('header','reference','reads'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);case,admission,_=self.fixture(root)
                if kind=='header':
                    p=root/'reads.tar';data=bytearray(p.read_bytes());data[0]^=1;p.write_bytes(data)
                elif kind=='reference':
                    (root/'fixture/reference.fasta').write_text('changed')
                else:
                    admission['manifest']['reads_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'differ'):
                    prepare_general_input(case,admission,root,root/'out',offline=True)

    def test_corrupt_cached_decompression_rejected_without_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=self.fixture(root)
            prepare_general_input(case,admission,root,root/'out',offline=True)
            (root/'fixture/reads.fastq').write_text('bad')
            with self.assertRaisesRegex(ValueError,'differ'):
                prepare_general_input(case,admission,root,root/'out',offline=True)

    def test_missing_offline_reads_never_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=self.fixture(root)
            (root/'reads.tar').unlink()
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                with self.assertRaisesRegex(ValueError,'Offline published input absent'):
                    prepare_general_input(case,admission,root,root/'out',offline=True)

    def test_offline_reference_archive_is_verified_and_extracted_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=self.fixture(root)
            reference=(root/'fixture/reference.fasta').read_bytes()
            (root/'fixture/reference.fasta').unlink()
            archive=root/'references.tar.gz'
            with tarfile.open(archive,'w:gz') as stream:
                member=tarfile.TarInfo('reference_genomes/fixture.fasta');member.size=len(reference)
                stream.addfile(member,io.BytesIO(reference))
            admission['manifest']['source_reference_archive'].update(
                size=archive.stat().st_size,computed_md5=hashlib.md5(archive.read_bytes()).hexdigest())
            result=prepare_general_input(case,admission,root,root/'out',offline=True)
            self.assertEqual((root/'out/reference.fasta').read_bytes(),reference)
            self.assertEqual(result['reference_sha256'],hashlib.sha256(reference).hexdigest())

    def test_online_member_uses_two_exact_ranges_and_offline_cache_reuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=self.fixture(root)
            data=(root/'reads.tar').read_bytes();(root/'reads.tar').unlink()
            source=admission['manifest']['source_read_archive'];member=admission['manifest']['read_archive_member']
            requested=[]
            def response(request,timeout):
                requested.append(request.headers['Range'])
                start,end=map(int,request.headers['Range'][6:].split('-'))
                stream=io.BytesIO(data[start:end+1]);stream.status=206
                stream.headers={'Content-Range':f"bytes {start}-{end}/{source['size']}"}
                return stream
            with patch('urllib.request.urlopen',side_effect=response):
                prepare_general_input(case,admission,root,root/'out')
            self.assertEqual(requested,['bytes=0-511',f"bytes=512-{511+member['size']}"])
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                prepare_general_input(case,admission,root,root/'out',offline=True)

    def test_existing_provenance_must_not_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=self.fixture(root)
            prepare_general_input(case,admission,root,root/'out',offline=True)
            p=root/'out/input.json';p.write_text('{"status":"different"}')
            with self.assertRaisesRegex(ValueError,'provenance differs'):
                prepare_general_input(case,admission,root,root/'out',offline=True)
            self.assertEqual(json.loads(p.read_text()),{'status':'different'})

    def test_online_range_refuses_full_archive_response(self):
        response=io.BytesIO(b'full archive');response.status=200;response.headers={}
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'refusing entire'):
                _range({'size':1000,'download_url':'https://invalid.example'},512,10)


if __name__ == '__main__':
    unittest.main()
