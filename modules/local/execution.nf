import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process ASSEMBLE {
    tag "${meta.id}/${assemblerDef.id}"
    cpus { assemblerDef.resources.cpus }
    memory { "${assemblerDef.resources.memory_gb} GB" }
    time { "${assemblerDef.resources.time_minutes} min" }
    input:
    tuple val(meta), path(reference), path(provenance), path(reads), path(simulation), val(assemblerDef)
    val sourceFingerprint
    output:
    tuple val(meta), path(reference), path(provenance), path(simulation), val(assemblerDef), path('tool-output')
    script:
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    export BENCH_PIXI_ENV='${assemblerDef.environment}'
    export BENCH_PIXI_MANIFEST=${shellQuote(projectDir.toString() + '/' + assemblerDef.manifest)}
    bench-run python ${shellQuote(projectDir.toString() + '/bin/run-assembler.py')} --assembler '${assemblerDef.id}' \
      --reads ${shellQuote(reads)} --out-dir tool-output --cpus ${task.cpus} --options-json ${shellQuote(JsonOutput.toJson(meta.assembler_options ?: meta.assembly_options ?: [:]))}
    """
}

process ASSESS {
    tag "${meta.id}/${assemblerDef.id}"
    cpus 1
    input:
    tuple val(meta), path(reference), path(provenance), path(simulation), val(assemblerDef), path(toolOutput)
    val sourceFingerprint
    output:
    path '*.result.json', emit: results
    path '*.result.evidence', emit: evidence
    script:
    def spec = shellQuote(JsonOutput.toJson(meta))
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${shellQuote(projectDir.toString() + (meta.track == 'diagnostic' ? '/bin/assess-diagnostic.py' : '/bin/assess-assembly.py'))} --reference ${shellQuote(reference)} \
      --assembly ${shellQuote(toolOutput.toString() + '/assembly.fasta')} --execution ${shellQuote(toolOutput.toString() + '/execution.json')} \
      ${meta.track in ['real', 'general', 'diagnostic'] ? '--input-provenance' : '--simulation'} ${shellQuote(simulation)} --reference-provenance ${shellQuote(provenance)} \
      --case-json ${spec} --assembler '${assemblerDef.id}' --out '${meta.id}__${assemblerDef.id}.result.json'
    """
}
