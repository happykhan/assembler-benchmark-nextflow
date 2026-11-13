import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process SETUP {
    executor 'local'
    cpus 1
    memory '1 GB'
    time '2 h'
    input:
    val selection
    path catalogue
    val sourceFingerprint
    output:
    path 'plan.json', emit: plan
    path 'preparation.json', emit: inventory
    script:
    def flags = (params.offline ? ' --offline' : '') + (params.plan_only ? ' --plan-only' : '') + ' --runtime '+shellQuote(params.runtime)
    if (params.container_runtime) flags += ' --container-runtime '+shellQuote(params.container_runtime)+' --container-image '+shellQuote(params.container_image)
    def prefix = params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/setup.py')} \
      --selection ${shellQuote(JsonOutput.toJson(selection))} --catalogue ${shellQuote(catalogue)} --cache-dir ${shellQuote(file(params.cache_dir).toString())} ${flags}
    """
}

process ADMIT_INPUT {
    tag "${input.id}"
    cpus 1
    memory '1 GB'
    time '2 h'
    input:
    tuple val(input), val(dependencies)
    val sourceFingerprint
    output:
    tuple val(input), val(dependencies), path('admitted.json')
    script:
    def prefix = params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/admit.py')} \
      --input ${shellQuote(JsonOutput.toJson(input))} --dependencies ${shellQuote(JsonOutput.toJson(dependencies))} \
      --cache-dir ${shellQuote(file(params.cache_dir).toString())} ${params.offline ? '--offline' : ''}
    """
}

process PREPARE_INPUT {
    tag "${input.id}"
    cpus 1
    memory '4 GB'
    time '2 h'
    input:
    tuple val(input), val(dependencies), path(admitted)
    val sourceFingerprint
    output:
    tuple val(input), val(dependencies), path(admitted), path('prepared')
    script:
    def environment = input.recipe.method == 'art-illumina-v1' ? 'art-2016-06-05' : 'default'
    def prefix = params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    export BENCH_PIXI_ENV='${environment}'
    ${prefix}bench-run python ${shellQuote(projectDir.toString()+'/bin/prepare-input.py')} \
      --input ${shellQuote(JsonOutput.toJson(input))} --dependencies ${shellQuote(JsonOutput.toJson(dependencies))} \
      --cache-dir ${shellQuote(file(params.cache_dir).toString())}
    """
}
