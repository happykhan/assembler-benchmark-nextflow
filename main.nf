nextflow.enable.dsl = 2
import groovy.json.JsonOutput
import groovy.json.JsonSlurper

def shellQuote(value) {
    "'" + value.toString().replace("'", "'\"'\"'") + "'"
}

def sourceHash(project, names) {
    def digest = java.security.MessageDigest.getInstance('SHA-256')
    (names + ['environments/pixi.toml', 'environments/pixi.lock', 'bin/bench-run']).unique().sort().each { name ->
        digest.update(name.getBytes('UTF-8'))
        digest.update(file("${project}/${name}").bytes)
    }
    digest.digest().encodeHex().toString()
}

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
      --reads ${shellQuote(reads)} --out-dir tool-output --cpus ${task.cpus}
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
    bench-run python ${shellQuote(projectDir.toString() + '/bin/assess-assembly.py')} --reference ${shellQuote(reference)} \
      --assembly ${shellQuote(toolOutput.toString() + '/assembly.fasta')} --execution ${shellQuote(toolOutput.toString() + '/execution.json')} \
      ${meta.track == 'real' ? '--input-provenance' : '--simulation'} ${shellQuote(simulation)} --reference-provenance ${shellQuote(provenance)} \
      --case-json ${spec} --assembler '${assemblerDef.id}' --out '${meta.id}__${assemblerDef.id}.result.json'
    """
}

process EXPORT_RESULTS {
    cpus 1
    publishDir params.outdir, mode: 'copy', overwrite: true
    input:
    path results
    path evidence
    val expectedSlots
    path plan
    path runtimeReceipt
    path inputDiagnostics
    val sourceFingerprint
    output:
    path 'bundle'
    script:
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${shellQuote(projectDir.toString() + '/bin/export-results.py')} --results ${results.collect { shellQuote(it) }.join(' ')} \
      --out-dir bundle --expected-slots ${expectedSlots} --run-id '${params.run_id}' --plan ${shellQuote(plan)} --runtime-receipt ${shellQuote(runtimeReceipt)} --input-diagnostics ${inputDiagnostics.collect { shellQuote(it) }.join(' ')}
    """
}

workflow {
    // Shared caches must exist before a container engine can bind them.
    file(params.reference_dir).mkdirs()
    file(params.read_cache).mkdirs()
    // A reporting repair must not rerun a cached assembler on unchanged inputs.
    def referenceSource = sourceHash(projectDir, ['bin/prepare-reference.py', 'benchlib/references.py', 'assets/references.json'])
    def simulationSource = sourceHash(projectDir, ['bin/simulate-reads.py', 'benchlib/io.py'])
    def assemblySource = sourceHash(projectDir, ['bin/run-assembler.py', 'benchlib/io.py', 'benchlib/process.py', 'benchlib/adapters.py', 'assets/assemblers.json'])
    def assessmentSource = sourceHash(projectDir, ['bin/assess-assembly.py', 'benchlib/assessment.py', 'benchlib/paper_recovery.py', 'benchlib/process.py'])
    def exportSource = sourceHash(projectDir, ['bin/export-results.py', 'benchlib/assessment.py', 'benchlib/report.py'])
    def runtimeProfiles = workflow.profile.tokenize(',').findAll { it in ['pixi', 'docker', 'singularity', 'apptainer', 'native_tools'] }
    if (runtimeProfiles.size() > 1) error 'Choose exactly one runtime profile.'
    if (runtimeProfiles.any { it in ['docker', 'singularity', 'apptainer'] } &&
        !(params.container_image ==~ /.+@sha256:[a-f0-9]{64}/))
        error 'Container runtimes require a digest-pinned runtime image.'
    def validationSource = sourceHash(projectDir, ['bin/prepare-run.py', 'benchlib/bootstrap.py', 'benchlib/runtime.py', 'bin/plan.py', 'benchlib/planning.py', 'benchlib/adapters.py',
        'benchlib/references.py', 'benchlib/real_planning.py', 'benchlib/real_data.py', 'assets/real-pilot.json', 'assets/assemblers.json', 'assets/quick.json', 'assets/standard.json', 'assets/references.json', 'assets/groups.json'])
    def selection = [track: params.track, preset: params.preset, groups: params.groups, cases: params.cases, assemblers: params.assemblers]
    PREPARE_RUN(params.plan ? file(params.plan, checkIfExists: true) : [], selection, validationSource)
    def spec = PREPARE_RUN.out.plan.map { new JsonSlurper().parse(it.toFile()) }
    def admittedReferences = spec.flatMap { it.reference_ids }
    def cases = spec.flatMap { it.cases }
    def assemblerDefinitions = spec.flatMap { plan ->
        plan.assemblers.collect { id ->
            def definition = new LinkedHashMap(plan.assembler_definitions[id])
            definition.resources = [cpus: plan.resource_policy.assembly.cpus,
                memory_gb: plan.resource_policy.assembly.memory_gb_by_tool.get(definition.tool, plan.resource_policy.assembly.default_memory_gb),
                time_minutes: plan.resource_policy.assembly.time_minutes]
            def lockName = java.nio.file.Paths.get(definition.manifest).resolveSibling('pixi.lock').toString()
            definition.manifest_sha256 = plan.source_file_sha256[definition.manifest]
            definition.lock_sha256 = plan.source_file_sha256[lockName]
            definition
        }
    }
    PREPARE_REFERENCE(admittedReferences, file("${projectDir}/assets/references.json"), referenceSource)
    def inputs = cases.map { tuple(it.reference_id, it) }
        .combine(PREPARE_REFERENCE.out, by: 0).map { id, meta, reference, provenance -> tuple(meta, reference, provenance) }
    def inputTracks = inputs.branch {
        real: it[0].track == 'real'
        simulated: true
    }
    def realSource = sourceHash(projectDir, ['bin/prepare-real-reads.py', 'benchlib/real_inputs.py', 'benchlib/io.py'])
    PREPARE_REAL_READS(inputTracks.real, PREPARE_RUN.out.plan, realSource)
    REAL_READ_DIAGNOSTICS(PREPARE_REAL_READS.out, sourceHash(projectDir, ['bin/diagnose-real-reads.py', 'benchlib/read_diagnostics.py', 'benchlib/assessment.py', 'benchlib/process.py']))
    SIMULATE_READS(inputTracks.simulated, simulationSource, spec.map { it.resource_policy.simulation ?: [cpus: 1, time_minutes: 30] })
    ASSEMBLE(SIMULATE_READS.out.mix(PREPARE_REAL_READS.out).combine(assemblerDefinitions), assemblySource)
    ASSESS(ASSEMBLE.out, assessmentSource)
    EXPORT_RESULTS(ASSESS.out.results.collect(), ASSESS.out.evidence.collect(), spec.map { it.expected_slots }, PREPARE_RUN.out.plan, PREPARE_RUN.out.receipt, REAL_READ_DIAGNOSTICS.out.toList(), exportSource)
    EXPORT_RESULTS.out.ifEmpty { error 'No complete result bundle was exported.' }
        .subscribe { log.info "Results bundle: ${params.outdir}/bundle/index.html" }
}
