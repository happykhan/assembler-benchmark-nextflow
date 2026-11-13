"""Shared preparation never admits incomplete bytes or silently fetches offline."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from benchlib.preparation import (PreparationError, execute_work_list, file_sha256,
                                 item_lock, plan_preparation)

ROOT = Path(__file__).resolve().parents[1]


class Server:
    def __init__(self, data, truncated=False, ranges=True):
        self.data,self.requests,self.truncated,self.ranges = data,0,truncated,ranges
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                owner.requests += 1
                time.sleep(.05)
                bounds = self.headers.get('Range')
                if bounds and owner.ranges:
                    start,end = map(int,bounds.removeprefix('bytes=').split('-'))
                    payload = owner.data[start:end+1]
                    self.send_response(206)
                    self.send_header('Content-Range','bytes %s-%s/%s'%(start,end,len(owner.data)))
                else:
                    payload = owner.data;self.send_response(200)
                self.send_header('Content-Length',str(len(payload)));self.end_headers()
                self.wfile.write(payload[:3] if owner.truncated else payload)
                self.close_connection = True
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%s/data'%self.server.server_port

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.cache = self.root/'cache'
        self.data = b'known exact input bytes\n'*100

    def source(self, data=None, **options):
        server = Server(self.data if data is None else data,**options)
        self.addCleanup(server.close)
        return server

    def plan(self, source, **changes):
        item = {'id':'reference-source','kind':'reference','target':'references/shared/source.fasta',
                'source':source,'sha256':hashlib.sha256(self.data).hexdigest(),'size_bytes':len(self.data)}
        item.update(changes)
        return {'dependencies':[item],'inputs':[{'id':'input-one','dependencies':[item['id']]}]}

    def test_dry_run_inventory_has_no_writes_network_or_installations(self):
        plan = self.plan({'url':'https://must-not-be-contacted.invalid/input'})
        plan['dependencies'].append({'id':'environment','kind':'software','environment':'test',
                                     'manifest':'environments/pixi.toml','target':'software/test.json'})
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')), \
             patch('subprocess.run',side_effect=AssertionError('installation forbidden')):
            work = plan_preparation(plan,self.cache,ROOT)
        self.assertFalse(self.cache.exists())
        self.assertEqual([r['status'] for r in work['items']],['missing','missing'])
        self.assertEqual(work['known_download_bytes'],len(self.data))
        self.assertEqual(work['items'][1]['source']['url'],'https://must-not-be-contacted.invalid/input')
        self.assertIn('bootstrap',work)

    def test_real_online_transport_then_offline_and_online_reuse_without_fetch(self):
        server = self.source();plan = self.plan({'url':server.url})
        work = plan_preparation(plan,self.cache,ROOT)
        ready = execute_work_list(work)
        self.assertTrue(ready['ready']);self.assertEqual(server.requests,1)
        target = self.cache/plan['dependencies'][0]['target']
        self.assertEqual(target.read_bytes(),self.data)
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
            for offline in (False,True):
                work = plan_preparation(plan,self.cache,ROOT,offline=offline)
                self.assertEqual(work['items'][0]['status'],'cached')
                self.assertTrue(execute_work_list(work)['ready'])
        self.assertEqual(server.requests,1)

    def test_offline_missing_and_corrupt_cache_fail_without_network(self):
        plan = self.plan({'url':'https://not-contacted.invalid/input'})
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
            work = plan_preparation(plan,self.cache,ROOT,offline=True)
            with self.assertRaisesRegex(PreparationError,'Offline dependency'):
                execute_work_list(work)
            target = self.cache/plan['dependencies'][0]['target'];target.parent.mkdir(parents=True)
            target.write_bytes(b'corrupt')
            work = plan_preparation(plan,self.cache,ROOT,offline=True)
            self.assertEqual(work['items'][0]['status'],'invalid')
            with self.assertRaisesRegex(PreparationError,'Invalid dependency'):
                execute_work_list(work)
            self.assertEqual(target.read_bytes(),b'corrupt')

    def test_interrupted_download_never_creates_an_admitted_target(self):
        server = self.source(truncated=True);plan = self.plan({'url':server.url})
        with self.assertRaises((PreparationError,OSError)):
            execute_work_list(plan_preparation(plan,self.cache,ROOT))
        target = self.cache/plan['dependencies'][0]['target']
        self.assertFalse(target.exists())
        self.assertTrue(list(target.parent.glob('*.partial-*')))
        self.assertEqual(plan_preparation(plan,self.cache,ROOT)['items'][0]['status'],'missing')

    def test_two_processes_requesting_same_item_fetch_once(self):
        server = self.source();plan = self.plan({'url':server.url});path = self.root/'plan.json'
        path.write_text(json.dumps(plan))
        code = 'import json,sys;from benchlib.preparation import plan_preparation,execute_work_list;execute_work_list(plan_preparation(json.load(open(sys.argv[1])),sys.argv[2],sys.argv[3]))'
        env = dict(os.environ,PYTHONPATH=str(ROOT))
        processes = [subprocess.Popen([sys.executable,'-c',code,str(path),str(self.cache),str(ROOT)],
                                     env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            stdout,stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,stderr.decode())
        self.assertEqual(server.requests,1)
        self.assertEqual((self.cache/plan['dependencies'][0]['target']).read_bytes(),self.data)

    def test_local_unpinned_source_is_bound_by_receipt_and_change_is_rejected(self):
        source = self.root/'local.fastq';source.write_bytes(self.data)
        plan = self.plan({'path':str(source)},sha256=None)
        ready = execute_work_list(plan_preparation(plan,self.cache,ROOT),offline=True)
        self.assertTrue(ready['ready'])
        source.write_bytes(b'changed source')
        inventory = plan_preparation(plan,self.cache,ROOT)
        self.assertEqual(inventory['items'][0]['status'],'invalid')
        self.assertIn('Local source changed',inventory['items'][0]['reason'])

    def test_source_subset_dependency_closure_and_target_escape(self):
        source = self.root/'source';source.write_bytes(self.data)
        plan = self.plan({'path':str(source)})
        plan['dependencies'].append({'id':'other','kind':'file','target':'other','source':{'path':'missing'}})
        work = plan_preparation(plan,self.cache,ROOT,input_ids=['input-one'])
        self.assertEqual([i['id'] for i in work['items']],['reference-source'])
        with self.assertRaisesRegex(ValueError,'Unknown selected input'):
            plan_preparation(plan,self.cache,ROOT,input_ids=['unknown'])
        plan['dependencies'][0]['target'] = '../outside'
        with self.assertRaisesRegex(ValueError,'cache-relative'):
            plan_preparation(plan,self.cache,ROOT)

    def test_killed_owner_is_not_stolen(self):
        self.cache.mkdir()
        code = 'import sys,time;from pathlib import Path;from benchlib.preparation import item_lock;\nwith item_lock(Path(sys.argv[1]),"locked-target"):\n print("locked",flush=True);time.sleep(30)'
        process = subprocess.Popen([sys.executable,'-c',code,str(self.cache)],env=dict(os.environ,PYTHONPATH=str(ROOT)),
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'locked')
            process.kill();process.wait(timeout=5)
            with self.assertRaisesRegex(TimeoutError,'no lock was removed'):
                with item_lock(self.cache,'locked-target',timeout_seconds=.01,poll_seconds=.005):pass
            self.assertEqual(len(list((self.cache/'.locks').glob('*.lock'))),1)
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close();process.stderr.close()

    def test_stale_work_list_rechecks_admitted_cache_before_offline_execution(self):
        server = self.source();plan = self.plan({'url':server.url})
        stale = plan_preparation(plan,self.cache,ROOT,offline=True)
        execute_work_list(plan_preparation(plan,self.cache,ROOT))
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
            self.assertTrue(execute_work_list(stale)['ready'])

    def test_archive_range_header_and_payload_are_verified(self):
        payload = self.data
        handle = io.BytesIO()
        with tarfile.open(fileobj=handle,mode='w') as archive:
            member = tarfile.TarInfo('reads.fastq.gz');member.size = len(payload)
            archive.addfile(member,io.BytesIO(payload))
        data = handle.getvalue();server = self.source(data=data)
        source = {'url':server.url,'range':{'offset':512,'length':len(payload),'total_size':len(data)},
                  'tar_header':{'offset':0,'name':'reads.fastq.gz','sha256':hashlib.sha256(data[:512]).hexdigest()}}
        plan = self.plan(source,kind='published_reads')
        execute_work_list(plan_preparation(plan,self.cache,ROOT))
        self.assertEqual(server.requests,2)
        self.assertEqual((self.cache/plan['dependencies'][0]['target']).read_bytes(),payload)

    def test_range_server_ignoring_range_is_rejected_without_whole_archive_admission(self):
        server = self.source(ranges=False)
        source = {'url':server.url,'range':{'offset':0,'length':len(self.data),'total_size':len(self.data)}}
        with self.assertRaisesRegex(PreparationError,'exact archive range'):
            execute_work_list(plan_preparation(self.plan(source),self.cache,ROOT))
        self.assertFalse((self.cache/'references/shared/source.fasta').exists())

    def test_reference_archive_is_an_admitted_file_dependency(self):
        source=self.root/'reference.tar.gz';source.write_bytes(self.data)
        plan=self.plan({'path':str(source)},kind='reference_archive')
        result=execute_work_list(plan_preparation(plan,self.cache,ROOT),offline=True)
        self.assertEqual(result['items'][0]['status'],'cached')

    def test_runtime_inventory_is_read_only_and_execution_uses_explicit_handler(self):
        plan = {'dependencies':[{'id':'test-env','kind':'software','manager':'python3','environment':'fixture'}]}
        calls = []
        inspector = lambda item,project,cache: {'status':'missing','reason':'No receipt'}
        handler = lambda item,project,cache,offline=False: calls.append(offline) or {'status':'cached'}
        work = plan_preparation(plan,self.cache,ROOT,inspectors={'software':inspector})
        self.assertFalse(calls);self.assertFalse(self.cache.exists())
        self.assertTrue(execute_work_list(work,offline=True,handlers={'software':handler})['ready'])
        self.assertEqual(calls,[True])

    def test_missing_bootstrap_is_reported_before_execution(self):
        plan = {'dependencies':[],'bootstrap_executables':['definitely-unavailable-bootstrap-7c33']}
        work = plan_preparation(plan,self.cache,ROOT)
        self.assertFalse(work['ready'])
        self.assertTrue(any(r['status']=='missing' for r in work['bootstrap']))
        with self.assertRaisesRegex(PreparationError,'Unavailable bootstrap'):
            execute_work_list(work)
        self.assertFalse(self.cache.exists())

    def test_unresolved_or_legacy_plan_is_not_silently_reported_ready(self):
        with self.assertRaisesRegex(ValueError,'resolved common plan'):
            plan_preparation({'schema_version':1,'cases':[]},self.cache,ROOT)
        self.assertFalse(self.cache.exists())
