"""Owned-work cleanup fails closed and preserves shared/current data."""
import fcntl,json,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
from benchlib.cleanup import MARKER,cleanup_work,finish_work,register_work
ROOT=Path(__file__).resolve().parents[1]
class CleanupTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name).resolve()
        self.work=self.root/'work';self.cache=self.root/'cache';self.results=self.root/'current';self.project=self.root/'project'
        for p in [self.cache,self.results,self.project]:p.mkdir()
        (self.cache/'reads.fastq').write_bytes(b'READS'*5000);(self.results/'unrelated.txt').write_text('retain')
        self.controller=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);self.addCleanup(self.stop)
    def stop(self):
        if self.controller.poll() is None:self.controller.terminate()
        self.controller.wait(timeout=10)
    def begin(self,**kw):
        return register_work(self.work,self.cache,self.results,self.project,'test-run',controller_pid=self.controller.pid,controller_host=socket.gethostname(),**kw)
    def completed(self):
        self.begin();(self.work/'temporary.txt').write_text('owned');finish_work(self.work,'test-run',True);self.stop()
    def test_dry_run_preserves_symlink_targets(self):
        self.completed();(self.work/'shared').symlink_to(self.cache,target_is_directory=True)
        r=cleanup_work(self.work);self.assertEqual(r['status'],'planned');self.assertEqual(r['symlinks'],1);self.assertLess(r['logical_file_bytes'],25000);self.assertTrue(self.work.exists())
    def test_execute_removes_only_owned_work(self):
        self.completed();(self.work/'shared').symlink_to(self.cache,target_is_directory=True)
        self.assertEqual(cleanup_work(self.work,execute=True)['status'],'removed');self.assertFalse(self.work.exists());self.assertEqual((self.cache/'reads.fastq').read_bytes(),b'READS'*5000);self.assertEqual((self.results/'unrelated.txt').read_text(),'retain')
    def test_active_failed_and_live_controller_refused(self):
        self.begin()
        with self.assertRaisesRegex(ValueError,'active/failed'):cleanup_work(self.work)
        finish_work(self.work,'test-run',True)
        with self.assertRaisesRegex(ValueError,'still active'):cleanup_work(self.work,execute=True)
        self.stop();p=self.work/MARKER;m=json.loads(p.read_text());m.update(state='failed',success=False);p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'active/failed'):cleanup_work(self.work,execute=True)
    def test_unowned_never_adopted_or_removed(self):
        self.work.mkdir();(self.work/'foreign.txt').write_text('unrelated')
        with self.assertRaisesRegex(ValueError,'cannot be adopted'):self.begin()
        self.assertEqual(self.begin(allow_unowned_existing=True)['status'],'unmanaged')
        with self.assertRaisesRegex(ValueError,'unowned'):cleanup_work(self.work,execute=True)
        self.assertEqual((self.work/'foreign.txt').read_text(),'unrelated')
    def test_protected_and_symlink_roots_refused(self):
        for p in [self.cache,self.cache/'nested',self.results,self.results/'nested',self.root,self.project]:
            with self.subTest(p=p),self.assertRaises(ValueError):register_work(p,self.cache,self.results,self.project,'unsafe')
        self.work.symlink_to(self.cache,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symbolic link'):cleanup_work(self.work,execute=True)
    def test_unknown_controller_host_refused(self):
        self.completed();p=self.work/MARKER;m=json.loads(p.read_text());m['controller']['host']='unknown.invalid';p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'unknown on this host'):cleanup_work(self.work)
    def test_substituted_root_and_marker_symlink_refused(self):
        self.completed();saved=self.root/'saved';self.work.rename(saved);self.work.mkdir();(self.work/MARKER).write_bytes((saved/MARKER).read_bytes())
        with self.assertRaisesRegex(ValueError,'identity changed'):cleanup_work(self.work,execute=True)
        (self.work/MARKER).unlink();(self.work/MARKER).symlink_to(saved/MARKER)
        with self.assertRaisesRegex(ValueError,'unowned'):cleanup_work(self.work)
    def test_wrong_finish_and_parallel_lock_refused(self):
        self.begin()
        with self.assertRaisesRegex(ValueError,'does not own'):finish_work(self.work,'wrong-run',True)
        finish_work(self.work,'test-run',True);self.stop();lock=self.work.parent/('.'+self.work.name+'.benchmark-lifecycle.lock')
        with lock.open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Another workflow'):cleanup_work(self.work,execute=True)
    def test_current_packages_must_validate(self):
        self.completed();(self.results/'catalogue.json').write_text('{"schema_version":999}')
        with self.assertRaises(ValueError):cleanup_work(self.work,execute=True)
        self.assertTrue(self.work.exists())
    def test_cli_dry_run_default(self):
        self.completed();r=subprocess.run([sys.executable,str(ROOT/'bin/cleanup.py'),'--work-dir',str(self.work)],text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(r.stdout)['status'],'planned');self.assertTrue(self.work.exists())
        r=subprocess.run([sys.executable,str(ROOT/'bin/cleanup.py'),'--work-dir',str(self.cache),'--execute'],text=True,capture_output=True)
        self.assertEqual(r.returncode,2);self.assertTrue((self.cache/'reads.fastq').exists())
