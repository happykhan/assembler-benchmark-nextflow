"""Exercise the real Nextflow channel/cache regression using metadata only."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
NF=os.environ.get('BENCHMARK_NEXTFLOW')

@unittest.skipUnless(NF,'Set BENCHMARK_NEXTFLOW for the real metadata-only Nextflow regression')
class PlanChannelTests(unittest.TestCase):
    def test_parallel_consumers_keep_all_slots_and_existing_task_cache_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'lib').mkdir()
            shutil.copyfile(ROOT/'lib/BenchmarkUtils.groovy',root/'lib/BenchmarkUtils.groovy')
            cases=[{'id':f'order-{i//3}-repeat-{i%3+1}','track':'diagnostic',
                    'recipe':{'order':i//3,'repeat':i%3+1}} for i in range(12)]
            (root/'plan.json').write_text(json.dumps({'cases':cases}))
            (root/'main.nf').write_text('''import groovy.json.JsonSlurper
import static BenchmarkUtils.readPlan
process PROBE {
    tag "${meta.id}"
    cpus 1
    memory '64 MB'
    input:
    val meta
    output:
    val meta
    script:
    'true'
}
workflow {
    def spec=Channel.value(file(params.plan)).map { params.raw ? new JsonSlurper().parse(it.toFile()) : readPlan(it) }
    def cases=spec.flatMap { it.cases }
    if (!params.raw) {
        cases.filter { it.track != 'diagnostic' }.toList().subscribe { assert it.size()==0 }
    }
    def selected=cases.filter { it.track=='diagnostic' }
    PROBE(selected)
    PROBE.out.toList().subscribe { rows ->
        assert rows.size()==12
        new File(params.observed).text=groovy.json.JsonOutput.toJson(rows.collect { it.id }.sort())
    }
}
''')
            def run(raw,resume=False):
                label='original' if raw else 'repaired'
                command=[str(Path(NF).resolve()),'-log',str(root/(label+'.log')),'run',str(root/'main.nf'),
                    '--plan',str(root/'plan.json'),'--raw',str(raw).lower(),'--observed',str(root/(label+'.json')),
                    '-w',str(root/'work'),'-with-trace',str(root/(label+'.tsv'))]
                if resume:command.append('-resume')
                result=subprocess.run(command,cwd=root,env=dict(os.environ,NXF_ANSI_LOG='false',NXF_OFFLINE='true'),capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                return label
            run(True)
            run(False,True)
            self.assertEqual(json.loads((root/'original.json').read_text()),json.loads((root/'repaired.json').read_text()))
            with (root/'repaired.tsv').open() as stream: rows=list(csv.DictReader(stream,delimiter='\t'))
            self.assertEqual(len(rows),12)
            self.assertTrue(all(r['status']=='CACHED' for r in rows),rows)
