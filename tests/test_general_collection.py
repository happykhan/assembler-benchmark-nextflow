"""Frozen cohort and lossless archive admission regressions; no scientific downloads."""
import copy
import gzip
import hashlib
import io
import json
import multiprocessing
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from benchlib.general_inputs import _range, _publish, locked, obtain_reads, obtain_reference, prepare_general_input
from benchlib.general_planning import build_general_plan, load_collection, validate_general_plan
from benchlib.io import digest

ROOT = Path(__file__).resolve().parents[1]


def _reference_worker(manifest, directory, cache, start, results):
    start.wait(10)
    try:
        reference = obtain_reference(manifest, Path(directory), Path(cache), False)
        results.put(('ok', reference.read_bytes()))
    except Exception as error:
        results.put(('error', repr(error)))


def _killed_owner(path, ready):
    with locked(Path(path)):
        Path(path).parent.joinpath('interrupted.partial').write_bytes(b'original interrupted transfer')
        ready.set()
        # Parent terminates this process; the lock must remain fail-closed.
        time.sleep(30)


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


class SharedCacheCoordinationTests(unittest.TestCase):
    def test_concurrent_processes_share_one_download_and_extract_distinct_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            archive=root/'fixture-source.tar.gz'
            references={'first':b'>chr1\nACGT\n','second':b'>chr2\nTGCA\n'}
            with tarfile.open(archive,'w:gz') as stream:
                for name,data in references.items():
                    member=tarfile.TarInfo('reference_genomes/'+name+'.fasta');member.size=len(data)
                    stream.addfile(member,io.BytesIO(data))
            payload=archive.read_bytes()
            requests=[]
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append(self.path)
                    self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers()
                    time.sleep(0.15)  # Second process reaches the lock during the first transfer.
                    self.wfile.write(payload)
                def log_message(self,*args):
                    pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            serving=threading.Thread(target=lambda:server.serve_forever(poll_interval=0.01),daemon=True)
            serving.start()
            ctx=multiprocessing.get_context('spawn');start=ctx.Event();results=ctx.Queue()
            processes=[]
            cache=root/'cache';cache.mkdir()
            legacy=cache/'.reference-archive.lock';legacy.write_text('retained advisory lock file')
            try:
                for name,data in references.items():
                    target=cache/name;target.mkdir()
                    manifest={'case':{'id':name},'truth_sha256':hashlib.sha256(data).hexdigest(),
                        'source_reference_archive':{'name':'reference_genomes.tar.gz','size':len(payload),
                            'computed_md5':hashlib.md5(payload).hexdigest(),
                            'download_url':f'http://127.0.0.1:{server.server_port}/archive'}}
                    p=ctx.Process(target=_reference_worker,args=(manifest,str(target),str(cache),start,results))
                    p.start();processes.append(p)
                start.set()
                outcomes=[results.get(timeout=15) for _ in processes]
                for p in processes:
                    p.join(10);self.assertEqual(p.exitcode,0)
                self.assertEqual(sorted(outcomes),sorted(('ok',value) for value in references.values()))
                self.assertEqual(requests,['/archive'])
                self.assertEqual((cache/'reference_genomes.tar.gz').read_bytes(),payload)
                self.assertEqual(legacy.read_text(),'retained advisory lock file')
                self.assertFalse((cache/'.reference-archive.lock.d').exists())
            finally:
                for p in processes:
                    if p.is_alive():
                        p.terminate();p.join(5)
                server.shutdown();server.server_close();serving.join(5)

    def test_killed_owner_leaves_inspectable_lock_and_partial_without_automatic_steal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'.reference-archive.lock'
            ctx=multiprocessing.get_context('spawn');ready=ctx.Event()
            p=ctx.Process(target=_killed_owner,args=(str(path),ready));p.start()
            try:
                self.assertTrue(ready.wait(10))
                owner_path=root/'.reference-archive.lock.d/owner.json'
                owner=owner_path.read_bytes()
                self.assertEqual(json.loads(owner)['pid'],p.pid)
                p.terminate();p.join(5)
                self.assertFalse(p.is_alive())
                with self.assertRaisesRegex(TimeoutError,'No stale lock was removed'):
                    with locked(path,timeout_seconds=0.04,poll_seconds=0.01):
                        self.fail('Killed holder lock must not be stolen')
                self.assertEqual(owner_path.read_bytes(),owner)
                self.assertEqual((root/'interrupted.partial').read_bytes(),b'original interrupted transfer')
            finally:
                if p.is_alive():
                    p.terminate();p.join(5)

    def test_missing_owner_metadata_times_out_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cache.lock'
            lock=Path(str(path)+'.d');lock.mkdir()
            with self.assertRaisesRegex(TimeoutError,'metadata unavailable'):
                with locked(path,timeout_seconds=0,poll_seconds=0.01):
                    self.fail('Uncertain lock must not be entered')
            self.assertTrue(lock.is_dir())

    def test_interrupted_legacy_partial_is_preserved_and_never_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=GeneralInputTests().fixture(root)
            candidate=root/'fixture/reads.fastq.gz.partial'
            candidate.write_bytes(b'old interrupted bytes')
            prepare_general_input(case,admission,root,root/'out',offline=True)
            self.assertEqual(candidate.read_bytes(),b'old interrupted bytes')
            self.assertEqual(digest(root/'fixture/reads.fastq.gz'),admission['manifest']['reads_sha256'])

    def test_failed_transfer_retry_keeps_partial_and_uses_a_new_verified_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);case,admission,_=GeneralInputTests().fixture(root)
            archive=root/'reads.tar';data=archive.read_bytes();archive.unlink()
            size=admission['manifest']['read_archive_member']['size']
            header=data[:512];payload=data[512:512+size]
            with patch('benchlib.general_inputs._range',side_effect=[io.BytesIO(header),io.BytesIO(payload[:3])]):
                with self.assertRaisesRegex(ValueError,'Truncated published archive transfer'):
                    prepare_general_input(case,admission,root,root/'out')
            candidates=list((root/'fixture').glob('reads.fastq.gz.partial-*'))
            self.assertEqual(len(candidates),1)
            self.assertEqual(candidates[0].read_bytes(),payload[:3])
            self.assertFalse((root/'fixture/reads.fastq.gz').exists())
            with patch('benchlib.general_inputs._range',side_effect=[io.BytesIO(header),io.BytesIO(payload)]):
                prepare_general_input(case,admission,root,root/'out')
            self.assertEqual(candidates[0].read_bytes(),payload[:3])
            self.assertEqual((root/'fixture/reads.fastq.gz').read_bytes(),payload)
            self.assertFalse((root/'fixture/.prepare.lock.d').exists())

    def test_publication_cannot_replace_an_existing_conflicting_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/'input';original.write_bytes(b'original')
            candidate=root/'input.partial-attempt';candidate.write_bytes(b'new')
            def validate(path):
                if path.read_bytes()!=b'new':
                    raise ValueError('Published input differs')
            with self.assertRaisesRegex(ValueError,'differs'):
                _publish(candidate,original,validate)
            self.assertEqual(original.read_bytes(),b'original')
            self.assertEqual(candidate.read_bytes(),b'new')


if __name__ == '__main__':
    unittest.main()
