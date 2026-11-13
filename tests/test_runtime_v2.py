"""Pinned runtime inventory is read-only; offline provisioning cannot fetch."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchlib.io import digest
from benchlib.preparation import PreparationError
from benchlib.runtime_v2 import inspect_dependency, prepare_dependency


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.project=self.root/'project';self.cache=self.root/'cache'
        self.manifest=self.project/'environments/pixi.toml';self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text('[workspace]\nname="fixture"\n')
        self.lock=self.manifest.with_name('pixi.lock');self.lock.write_text('fixture lock\n')
        self.prefix=self.manifest.parent/'.pixi/envs/fixture'
        self.item={'id':'fixture-runtime','kind':'software','environment':'fixture',
                   'manifest':'environments/pixi.toml','target':'software/fixture.json',
                   'executables':['raven'],'packages':{'raven-assembler':'1.8.3'},
                   'manifest_sha256':digest(self.manifest),'lock_sha256':digest(self.lock)}

    def install_fixture(self):
        (self.prefix/'bin').mkdir(parents=True,exist_ok=True)
        for name in ('python','minimap2','raven'):
            binary=self.prefix/'bin'/name;binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o755)
        (self.prefix/'conda-meta').mkdir(exist_ok=True)
        (self.prefix/'conda-meta/raven.json').write_text(json.dumps({'name':'raven-assembler','version':'1.8.3'}))

    def receipt(self):
        self.install_fixture()
        path=self.cache/self.item['target'];path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'environment':'fixture','manifest_sha256':digest(self.manifest),
            'lock_sha256':digest(self.lock),'executables':{n:digest(self.prefix/'bin'/n) for n in ('python','minimap2','raven')}}))

    def test_inventory_uses_no_subprocess_or_network(self):
        self.receipt()
        with patch('subprocess.run',side_effect=AssertionError('no runtime commands in inventory')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('no network')):
            result=inspect_dependency(self.item,self.project,self.cache)
        self.assertEqual(result['status'],'cached')

    def test_missing_or_corrupt_receipts_and_binaries_are_detected(self):
        self.assertEqual(inspect_dependency(self.item,self.project,self.cache)['status'],'missing')
        self.receipt();binary=self.prefix/'bin/raven';binary.write_text('changed')
        self.assertEqual(inspect_dependency(self.item,self.project,self.cache)['status'],'invalid')
        with patch('subprocess.run',side_effect=AssertionError('invalid runtimes are not silently replaced')):
            with self.assertRaises(PreparationError):prepare_dependency(self.item,self.project,self.cache,offline=True)
        path=self.cache/self.item['target'];path.write_text('malformed JSON')
        self.assertEqual(inspect_dependency(self.item,self.project,self.cache)['status'],'invalid')

    def test_declared_lock_and_manifest_hashes_cannot_be_rebound_by_new_receipt(self):
        self.receipt()
        for field in ('lock_sha256','manifest_sha256'):
            with self.subTest(field=field):
                changed=dict(self.item,**{field:'0'*64})
                self.assertEqual(inspect_dependency(changed,self.project,self.cache)['status'],'invalid')

    def test_nonexecutable_binary_is_not_ready(self):
        self.receipt();(self.prefix/'bin/raven').chmod(0o644)
        self.assertEqual(inspect_dependency(self.item,self.project,self.cache)['status'],'invalid')

    def test_package_version_must_match_declared_configuration(self):
        self.receipt();(self.prefix/'conda-meta/raven.json').write_text(json.dumps({'name':'raven-assembler','version':'2.0.0'}))
        self.assertEqual(inspect_dependency(self.item,self.project,self.cache)['status'],'invalid')

    def test_offline_preparation_inspects_only_and_never_installs(self):
        with patch('subprocess.run',side_effect=AssertionError('offline must not invoke Pixi')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('offline must not fetch')):
            with self.assertRaisesRegex(PreparationError,'prepare this environment online'):
                prepare_dependency(self.item,self.project,self.cache,offline=True)
            self.assertFalse((self.cache/self.item['target']).exists())
            self.receipt()
            self.assertEqual(prepare_dependency(self.item,self.project,self.cache,offline=True)['status'],'cached')

    def test_changed_lock_during_install_does_not_publish_receipt(self):
        def install(command,**kwargs):
            self.install_fixture();self.lock.write_text('changed during install')
            return subprocess.CompletedProcess(command,0,'','')
        with patch('shutil.which',return_value='/fixture/pixi'),patch('subprocess.run',side_effect=install):
            with self.assertRaises(PreparationError):prepare_dependency(self.item,self.project,self.cache)
        self.assertFalse((self.cache/self.item['target']).exists())

    def test_missing_installer_is_actionable_without_subprocess(self):
        with patch('shutil.which',return_value=None),patch('subprocess.run',side_effect=AssertionError('no installer')):
            with self.assertRaisesRegex(PreparationError,'Pixi'):
                prepare_dependency(self.item,self.project,self.cache)

    def image_fixture(self):
        item={'id':'image','kind':'container_image','runtime':'apptainer',
              'target':'images/runtime.sif','source':'docker://example.test/runtime@sha256:'+'a'*64}
        image=self.cache/item['target'];image.parent.mkdir(parents=True);image.write_bytes(b'fixture SIF bytes')
        image.with_name(image.name+'.receipt.json').write_text(json.dumps({'source':item['source'],'sha256':digest(image)}))
        return item,image

    def test_local_sif_inventory_binds_source_and_bytes_without_engine_or_network(self):
        item,image=self.image_fixture()
        with patch('subprocess.run',side_effect=AssertionError('inventory never pulls')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('no network')):
            self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'cached')
            self.assertEqual(prepare_dependency(item,self.project,self.cache,offline=True)['status'],'cached')
            self.assertEqual(inspect_dependency(dict(item,source='docker://different@sha256:'+'b'*64),self.project,self.cache)['status'],'invalid')
            image.write_bytes(b'corrupt')
            self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'invalid')

    def test_missing_offline_sif_never_pulls(self):
        item={'id':'image','kind':'container_image','runtime':'apptainer','target':'images/missing.sif',
              'source':'docker://example.test/runtime@sha256:'+'a'*64}
        with patch('subprocess.run',side_effect=AssertionError('offline pull forbidden')):
            with self.assertRaisesRegex(PreparationError,'no network attempted'):
                prepare_dependency(item,self.project,self.cache,offline=True)

    def test_sif_descriptor_and_transport_aliases_keep_exact_digest_binding(self):
        item,image=self.image_fixture();reference=item['source'].removeprefix('docker://')
        with patch('subprocess.run',side_effect=AssertionError('cached SIF does not invoke engine')):
            for source in (reference,{'url':reference},{'url':'docker://'+reference}):
                self.assertEqual(inspect_dependency(dict(item,source=source),self.project,self.cache)['status'],'cached')
            wrong=reference.rsplit(':',1)[0]+':'+'b'*64
            self.assertEqual(inspect_dependency(dict(item,source={'url':wrong}),self.project,self.cache)['status'],'invalid')
            image.write_bytes(b'corrupted SIF')
            self.assertEqual(inspect_dependency(dict(item,source={'url':reference}),self.project,self.cache)['status'],'invalid')

    def test_oci_uri_without_transport_is_normalised_for_sif_engine(self):
        item={'id':'image','kind':'container_image','runtime':'apptainer','target':'images/runtime.sif',
              'source':'example.test/runtime@sha256:'+'a'*64}
        commands=[]
        def command(argv,**kwargs):
            commands.append(argv)
            if argv[1]=='pull':Path(argv[2]).write_bytes(b'new SIF')
            return subprocess.CompletedProcess(argv,0,'','')
        with patch('shutil.which',return_value='/fixture/apptainer'),patch('subprocess.run',side_effect=command):
            self.assertEqual(prepare_dependency(item,self.project,self.cache)['status'],'cached')
        self.assertEqual(commands[0][-1],'docker://'+item['source'])

    def docker_fixture(self):
        source='example.test/runtime@sha256:'+'a'*64
        item={'id':'docker-image','kind':'container_image','runtime':'docker','target':'images/docker.json','source':source}
        image={'Id':'sha256:'+'c'*64,'RepoDigests':[source]}
        return item,image

    def test_docker_inventory_only_inspects_exact_local_digest_without_pull_or_sif(self):
        item,image=self.docker_fixture();commands=[]
        def inspect(command,**kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command,0,json.dumps(image),'')
        with patch('shutil.which',return_value='/fixture/docker'),patch('subprocess.run',side_effect=inspect), \
             patch('urllib.request.urlopen',side_effect=AssertionError('no direct network')):
            self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'cached')
        self.assertTrue(all(c[1:3]==['image','inspect'] for c in commands))
        self.assertFalse(self.cache.exists())

    def test_missing_docker_image_never_pulls_offline(self):
        item,_=self.docker_fixture();commands=[]
        def absent(command,**kwargs):
            commands.append(command);return subprocess.CompletedProcess(command,1,'','No such image')
        with patch('shutil.which',return_value='/fixture/docker'),patch('subprocess.run',side_effect=absent):
            self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'missing')
            with self.assertRaisesRegex(PreparationError,'no network attempted'):
                prepare_dependency(item,self.project,self.cache,offline=True)
        self.assertTrue(all(c[1:3]==['image','inspect'] for c in commands))

    def test_explicit_online_docker_pull_then_verified_offline_reuse(self):
        item,image=self.docker_fixture();commands=[];present=False
        def engine(command,**kwargs):
            nonlocal present
            commands.append(command)
            if command[1]=='pull':
                present=True;return subprocess.CompletedProcess(command,0,'','')
            return subprocess.CompletedProcess(command,0,json.dumps(image),'') if present else subprocess.CompletedProcess(command,1,'','No such image')
        with patch('shutil.which',return_value='/fixture/docker'),patch('subprocess.run',side_effect=engine):
            self.assertEqual(prepare_dependency(item,self.project,self.cache)['status'],'cached')
            self.assertEqual(prepare_dependency(item,self.project,self.cache,offline=True)['status'],'cached')
        pulls=[c for c in commands if c[1]=='pull']
        self.assertEqual(pulls,[['/fixture/docker','pull',item['source']]])
        self.assertEqual(json.loads((self.cache/item['target']).read_text())['image_id'],image['Id'])
        self.assertFalse(list(self.cache.rglob('*.sif')))

    def test_docker_digest_id_and_preparation_receipt_mismatches_are_invalid(self):
        item,image=self.docker_fixture()
        with patch('shutil.which',return_value='/fixture/docker'):
            bad=dict(image,RepoDigests=['wrong@sha256:'+'b'*64])
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(bad),'')):
                self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'invalid')
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(image),'')):
                self.assertEqual(inspect_dependency(dict(item,image_id='sha256:'+'d'*64),self.project,self.cache)['status'],'invalid')
                receipt=self.cache/item['target'];receipt.parent.mkdir(parents=True)
                receipt.write_text(json.dumps({'source':item['source'],'image_id':'sha256:'+'e'*64}))
                self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'invalid')

    def test_native_mode_inspects_paths_without_install_or_version_commands(self):
        self.install_fixture();item=dict(self.item,manager='native')
        def executable(name):
            path=self.prefix/'bin'/name
            return str(path) if path.is_file() else None
        with patch('shutil.which',side_effect=executable),patch('subprocess.run',side_effect=AssertionError('native does not install')):
            result=inspect_dependency(item,self.project,self.cache)
            self.assertEqual(result['status'],'cached')
            self.assertIn('checked at invocation',result['version_verification'])
            self.assertEqual(prepare_dependency(item,self.project,self.cache,offline=True)['status'],'cached')
            (self.prefix/'bin/raven').unlink()
            self.assertEqual(inspect_dependency(item,self.project,self.cache)['status'],'missing')
            with self.assertRaisesRegex(PreparationError,'never installed'):
                prepare_dependency(item,self.project,self.cache)
