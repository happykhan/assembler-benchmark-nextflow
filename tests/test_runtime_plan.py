"""Standalone preparation and Nextflow resolve the same runtime dependencies."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from benchlib.catalogue import canonical_digest
from benchlib.io import digest
from benchlib.preparation import PreparationError,plan_preparation
from benchlib.runtime_v2 import runtime_plan,inspect_dependency

ROOT=Path(__file__).resolve().parents[1]
IMAGE='ghcr.io/prefix-dev/pixi@sha256:'+'a'*64


class RuntimePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name);self.project=self.directory/'project'
        self.manifest=self.project/'environments/pixi.toml';self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text('fixture manifest\n');self.manifest.with_name('pixi.lock').write_text('fixture lock\n')
        self.plan={'schema_version':2,'dependencies':[{'id':'software-raven','kind':'software',
            'environment':'raven-test','manifest':'environments/pixi.toml','executables':['raven'],
            'target':'software/raven.json'}],'inputs':[{'id':'input'}],
            'slots':[{'case_id':'case','workflow_id':'raven-default','input_id':'input'}],
            'cases':[{'id':'case','science_key':'science'}]}

    def test_resolution_is_deterministic_nonmutating_and_keeps_scientific_identities(self):
        original=copy.deepcopy(self.plan)
        result=runtime_plan(self.plan,self.project,'pixi','apptainer',IMAGE)
        self.assertEqual(self.plan,original)
        for key in ('inputs','slots','cases'):self.assertEqual(result[key],original[key])
        self.assertEqual(result['plan_sha256'],canonical_digest({k:v for k,v in result.items() if k!='plan_sha256'}))
        self.assertEqual(runtime_plan(result,self.project,'pixi','apptainer',IMAGE),result)

    def test_no_eligible_slots_does_not_require_or_prepare_an_image(self):
        plan=dict(self.plan,dependencies=[],slots=[])
        for engine in ('docker','singularity','apptainer'):
            with self.subTest(engine=engine):
                result=runtime_plan(plan,self.project,'pixi',engine,None)
                self.assertEqual(result['dependencies'],[])
                work=plan_preparation(result,self.directory/'cache',self.project)
                self.assertNotIn(engine,{b['id'] for b in work['bootstrap']})

    def test_container_pin_and_target_type_match_runtime(self):
        for engine in ('docker','singularity','apptainer'):
            with self.subTest(engine=engine):
                with self.assertRaisesRegex(PreparationError,'digest-pinned'):
                    runtime_plan(self.plan,self.project,'pixi',engine,'example/runtime:latest')
                result=runtime_plan(self.plan,self.project,'pixi',engine,IMAGE)
                image=next(d for d in result['dependencies'] if d['kind']=='container_image')
                self.assertEqual(image['source'],{'url':IMAGE})
                self.assertEqual(image['target'],'images/'+'a'*64+('.json' if engine=='docker' else '.sif'))

    def test_native_does_not_require_pixi_bootstrap(self):
        result=runtime_plan(self.plan,self.project,'native');software=result['dependencies'][0]
        self.assertEqual(software['manager'],'native')
        self.assertEqual(software['manifest_sha256'],digest(self.manifest))
        self.assertEqual(software['lock_sha256'],digest(self.manifest.with_name('pixi.lock')))
        work=plan_preparation(result,self.directory/'cache',self.project,inspectors={'software':inspect_dependency})
        bootstrap={b['id'] for b in work['bootstrap']}
        self.assertNotIn('pixi',bootstrap);self.assertNotIn('native',bootstrap);self.assertIn('raven',bootstrap)

    def test_augmenting_frozen_plan_does_not_silently_replace_declared_pins(self):
        plan=copy.deepcopy(self.plan);plan['dependencies'][0]['lock_sha256']='0'*64
        result=runtime_plan(plan,self.project,'pixi','apptainer',IMAGE)
        software=next(d for d in result['dependencies'] if d['kind']=='software')
        self.assertEqual(software['lock_sha256'],'0'*64)
        work=plan_preparation(result,self.directory/'cache',self.project,inspectors={'software':inspect_dependency})
        self.assertEqual(next(i for i in work['items'] if i['kind']=='software')['status'],'invalid')

    def test_missing_source_manifest_is_reported_by_inventory(self):
        self.manifest.unlink()
        result=runtime_plan(self.plan,self.project)
        work=plan_preparation(result,self.directory/'cache',self.project,inspectors={'software':inspect_dependency})
        self.assertEqual(work['items'][0]['status'],'missing')
        self.assertIn('manifest',work['items'][0]['reason'])

    def test_cli_and_nextflow_setup_declare_identical_runtime_dependencies(self):
        cache=self.directory/'cache';work_path=self.directory/'standalone.json'
        runtime=['--runtime','native','--container-runtime','apptainer','--container-image',IMAGE]
        first=subprocess.run([sys.executable,str(ROOT/'bin/prepare.py'),'--cases','quick-long',
            '--cache-dir',str(cache),'--dry-run','--out',str(work_path)]+runtime,
            cwd=self.directory,text=True,capture_output=True)
        self.assertEqual(first.returncode,0,first.stderr)
        second=subprocess.run(
            [sys.executable,str(ROOT/'bin/setup.py'),'--selection',json.dumps({'cases':'quick-long'}),
             '--catalogue',str(ROOT/'assets/catalogue.json'),'--cache-dir',str(cache),'--plan-only']+runtime,
            cwd=self.directory,text=True,capture_output=True)
        self.assertEqual(second.returncode,0,second.stderr)
        a=json.loads(work_path.read_text());b=json.loads((self.directory/'preparation.json').read_text())
        keys=('id','kind','manager','environment','manifest','manifest_sha256','lock_sha256','target','source')
        normalise=lambda work:[{k:row[k] for k in keys if k in row} for row in work['items']]
        self.assertEqual(normalise(a),normalise(b));self.assertFalse(cache.exists())
