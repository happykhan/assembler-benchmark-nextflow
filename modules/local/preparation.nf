import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process PREPARE_RUN {
    // Provision on the submission host before any compute tasks need software.
    executor 'local'
    cpus 1
    memory '1 GB'
    time '2 h'
    publishDir params.outdir, mode: 'copy', overwrite: true
    input:
    path suppliedPlan
    val selection
    val sourceFingerprint
    output:
    path 'selected-plan.json', emit: plan
    path 'environment-preparation.json', emit: receipt
    script:
    def interpreter = params.runtime == 'pixi' ?
        "pixi run --locked --manifest-path ${shellQuote(projectDir.toString() + '/environments/pixi.toml')} python" : 'python3'
    def planOption = suppliedPlan ? "--plan ${shellQuote(suppliedPlan)}" : ''
    """
    ${interpreter} ${shellQuote(projectDir.toString() + '/bin/prepare-run.py')} \
      --selection-json ${shellQuote(JsonOutput.toJson(selection))} ${planOption} \
      --runtime '${params.runtime}' --runtime-image ${shellQuote(task.container ?: '')} --out selected-plan.json --receipt environment-preparation.json \
      --existing-plan ${shellQuote(file("${params.outdir}/selected-plan.json").toString())}
    """
}

process PREPARE_REFERENCE {
    tag "${referenceId}"
    cpus 1
    input:
    val referenceId
    path registry
    val sourceFingerprint
    output:
    tuple val(referenceId), path('reference.fasta'), path('reference.json')
    script:
    def offline = params.offline ? '--offline' : ''
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${shellQuote(projectDir.toString() + '/bin/prepare-reference.py')} --registry ${shellQuote(registry)} \
      --id '${referenceId}' --reference-dir ${shellQuote(params.reference_dir)} ${offline}
    """
}

process SIMULATE_READS {
    publishDir { "${params.outdir}/prepared/${meta.id}" }, mode: 'copy', enabled: params.prepare_only
    tag "${meta.id}"
    cpus { simulationPolicy.cpus }
    time { "${simulationPolicy.time_minutes} min" }
    input:
    tuple val(meta), path(reference), path(provenance)
    val sourceFingerprint
    val simulationPolicy
    output:
    tuple val(meta), path(reference), path(provenance), path('reads.fastq'), path('simulation.json')
    script:
    def spec = shellQuote(JsonOutput.toJson(meta))
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${shellQuote(projectDir.toString() + '/bin/simulate-reads.py')} --reference ${shellQuote(reference)} \
      --case-json ${spec} --reference-provenance ${shellQuote(provenance)} --out reads.fastq --metadata simulation.json
    """
}

process PREPARE_REAL_READS {
    publishDir { "${params.outdir}/prepared/${meta.id}" }, mode: 'copy', enabled: params.prepare_only
    tag "${meta.id}"
    cpus 1
    time '2 h'
    input:
    tuple val(meta), path(reference), path(provenance)
    path plan
    val sourceFingerprint
    output:
    tuple val(meta), path(reference), path(provenance), path('reads.fastq'), path('input.json')
    script:
    def offline = params.offline ? '--offline' : ''
    """
    bench-run python ${shellQuote(projectDir.toString() + '/bin/prepare-real-reads.py')} \
      --case-json ${shellQuote(JsonOutput.toJson(meta))} --plan ${shellQuote(plan)} \
      --reference ${shellQuote(reference)} --reference-provenance ${shellQuote(provenance)} \
      --cache ${shellQuote(params.read_cache)} ${offline}
    """
}

process PREPARE_COLLECTION_INPUT {
    publishDir { "${params.outdir}/prepared/${meta.id}" }, mode: 'copy', enabled: params.prepare_only
    tag "${meta.id}"
    cpus 1
    time '2 h'
    input:
    val meta
    path plan
    val sourceFingerprint
    output:
    tuple val(meta), path('reference.fasta'), path('reference.json'), path('reads.fastq'), path('input.json')
    script:
    def offline = params.offline ? '--offline' : ''
    def helper = meta.track == 'general' ? 'prepare-general-input.py' : 'prepare-diagnostic-input.py'
    def frozenSource = meta.input_recipe?.source?.case_id
    def sourceOption = meta.track == 'diagnostic' && frozenSource && params.diagnostic_source_dir ?
        " --frozen-input-dir ${shellQuote(file(params.diagnostic_source_dir).resolve(frozenSource))}" : ''
    def options = meta.track == 'general' ? "--plan ${shellQuote(plan)} --cache ${shellQuote(params.read_cache)}" :
        "--reference-dir ${shellQuote(params.reference_dir)} --out-dir ."
    """
    bench-run python ${shellQuote(projectDir.toString() + '/bin/' + helper)} ${options} \
      --case-json ${shellQuote(JsonOutput.toJson(meta))} ${offline} ${sourceOption}
    """
}

process REAL_READ_DIAGNOSTICS {
    tag "${meta.id}"
    cpus 4
    memory '8 GB'
    time '1 h'
    input:
    tuple val(meta), path(reference), path(provenance), path(reads), path(inputMetadata)
    val sourceFingerprint
    output:
    path "${meta.id}.read-diagnostics"
    script:
    """
    bench-run python ${shellQuote(projectDir.toString() + '/bin/diagnose-real-reads.py')} \
      --reference ${shellQuote(reference)} --reads ${shellQuote(reads)} \
      --input-provenance ${shellQuote(inputMetadata)} --cpus ${task.cpus}
    mv read-diagnostics ${shellQuote(meta.id + ".read-diagnostics")}
    """
}

process LIST_CHOICES {
    executor 'local'
    cpus 1
    publishDir params.outdir, mode: 'copy', overwrite: true
    output:
    path 'catalogue.json'
    script:
    def interpreter = params.runtime == 'pixi' ? "pixi run --locked --manifest-path ${shellQuote(projectDir.toString() + '/environments/pixi.toml')} python" : 'python3'
    """
    ${interpreter} ${shellQuote(projectDir.toString() + '/bin/plan.py')} --list > catalogue.json
    """
}
