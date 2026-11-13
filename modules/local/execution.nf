import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process ASSEMBLE {
    tag "${slot.case_id}/${slot.workflow_id}"
    cpus { slot.workflow.resources.cpus }
    memory { "${slot.workflow.resources.memory_gb} GB" }
    time { "${slot.workflow.resources.time_minutes} min" }
    cache (params.rerun ? false : 'deep')
    input:
    tuple val(slot), path(prepared)
    val sourceFingerprint
    output:
    tuple val(slot), path(prepared), path('execution')
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    export BENCH_PIXI_ENV=${shellQuote(slot.workflow.environment)}
    export BENCH_PIXI_MANIFEST=${shellQuote(projectDir.resolve(slot.workflow.manifest).toString())}
    ${prefix}bench-run python ${shellQuote(projectDir.toString()+'/bin/run-assembly.py')} \
      --prepared ${shellQuote(prepared)} --workflow ${shellQuote(JsonOutput.toJson(slot.workflow))}
    """
}

process ASSESS {
    tag "${slot.case_id}/${slot.workflow_id}"
    cpus 1
    memory '4 GB'
    input:
    tuple val(slot), path(prepared), path(execution)
    val sourceFingerprint
    output:
    tuple val(slot), path(prepared), path(execution), path('assessment')
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}bench-run python ${shellQuote(projectDir.toString()+'/bin/assess.py')} \
      --prepared ${shellQuote(prepared)} --execution ${shellQuote(execution)} --slot ${shellQuote(JsonOutput.toJson(slot))}
    """
}

process PUBLISH {
    tag "${slot.case_id}/${slot.workflow_id}"
    cache false
    cpus 1
    input:
    tuple val(slot), path(prepared), path(execution), path(assessment)
    val sourceFingerprint
    output:
    path 'published.json'
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/benchmark.py')} publish \
      --prepared ${shellQuote(prepared)} --execution ${shellQuote(execution)} --assessment ${shellQuote(assessment)} --slot ${shellQuote(JsonOutput.toJson(slot))} --outdir ${shellQuote(file(params.outdir).toString())}
    """
}

process NOT_APPLICABLE {
    tag "${slot.case_id}/${slot.workflow_id}"
    cache false
    cpus 1
    input:
    val slot
    val sourceFingerprint
    output:
    path 'published.json'
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/benchmark.py')} exclude \
      --slot ${shellQuote(JsonOutput.toJson(slot))} --outdir ${shellQuote(file(params.outdir).toString())}
    """
}
