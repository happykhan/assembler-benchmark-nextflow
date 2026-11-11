nextflow.enable.dsl = 2
import groovy.json.JsonOutput
import groovy.json.JsonSlurper

def sourceHash(project, names) {
    def digest = java.security.MessageDigest.getInstance('SHA-256')
    (names + ['environments/pixi.toml', 'environments/pixi.lock', 'bin/bench-run']).unique().sort().each { name ->
        digest.update(name.getBytes('UTF-8'))
        digest.update(file("${project}/${name}").bytes)
    }
    digest.digest().encodeHex().toString()
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
    bench-run python ${projectDir}/bin/prepare-reference.py --registry ${registry} \
      --id '${referenceId}' --reference-dir '${params.reference_dir}' ${offline}
    """
}

process SIMULATE_READS {
    tag "${meta.id}"
    cpus 1
    input:
    tuple val(meta), path(reference), path(provenance)
    val sourceFingerprint
    output:
    tuple val(meta), path(reference), path(provenance), path('reads.fastq'), path('simulation.json')
    script:
    def spec = JsonOutput.toJson(meta)
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${projectDir}/bin/simulate-reads.py --reference ${reference} \
      --case-json '${spec}' --out reads.fastq --metadata simulation.json
    """
}

process ASSEMBLE {
    tag "${meta.id}/${assembler}"
    memory { assembler == 'flye' ? '16 GB' : '4 GB' }
    input:
    tuple val(meta), path(reference), path(provenance), path(reads), path(simulation), val(assembler)
    val sourceFingerprint
    output:
    tuple val(meta), path(reference), path(provenance), path(simulation), val(assembler), path('tool-output')
    script:
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${projectDir}/bin/run-assembler.py --assembler '${assembler}' \
      --reads ${reads} --out-dir tool-output --cpus ${task.cpus}
    """
}

process ASSESS {
    tag "${meta.id}/${assembler}"
    cpus 1
    input:
    tuple val(meta), path(reference), path(provenance), path(simulation), val(assembler), path(toolOutput)
    val sourceFingerprint
    output:
    path '*.result.json', emit: results
    path '*.result.evidence', emit: evidence
    script:
    def spec = JsonOutput.toJson(meta)
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${projectDir}/bin/assess-assembly.py --reference ${reference} \
      --assembly ${toolOutput}/assembly.fasta --execution ${toolOutput}/execution.json \
      --simulation ${simulation} --reference-provenance ${provenance} \
      --case-json '${spec}' --assembler '${assembler}' --out '${meta.id}__${assembler}.result.json'
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
    val sourceFingerprint
    output:
    path 'bundle'
    script:
    """
    export BENCH_SOURCE_SHA256='${sourceFingerprint}'
    bench-run python ${projectDir}/bin/export-results.py --results ${results.join(' ')} \
      --out-dir bundle --expected-slots ${expectedSlots} --run-id '${params.run_id}' --plan ${plan}
    """
}

workflow {
    // Helper source and locked dependencies participate in every resume key.
    def digest = java.security.MessageDigest.getInstance('SHA-256')
    def sources = (file("${projectDir}/bin/*").findAll { it.isFile() } +
                   file("${projectDir}/benchlib/*.py") + file("${projectDir}/assets/*.json") +
                   [file("${projectDir}/main.nf"), file("${projectDir}/nextflow.config"),
                    file("${projectDir}/environments/pixi.toml"), file("${projectDir}/environments/pixi.lock")])
    sources.sort { it.toString() }.each { digest.update(it.getName().getBytes('UTF-8')); digest.update(it.bytes) }
    def fingerprint = digest.digest().encodeHex().toString()
    // A reporting repair must not rerun a cached assembler on unchanged inputs.
    def referenceSource = sourceHash(projectDir, ['bin/prepare-reference.py', 'assets/references.json'])
    def simulationSource = sourceHash(projectDir, ['bin/simulate-reads.py', 'benchlib/io.py'])
    def assemblySource = sourceHash(projectDir, ['bin/run-assembler.py', 'benchlib/io.py', 'benchlib/process.py'])
    def assessmentSource = sourceHash(projectDir, ['bin/assess-assembly.py', 'benchlib/assessment.py', 'benchlib/process.py'])
    def exportSource = sourceHash(projectDir, ['bin/export-results.py', 'benchlib/assessment.py', 'benchlib/report.py'])
    if (params.preset != 'quick') error 'Standard is not admitted yet. Develop and validate Quick first.'
    def cases = new JsonSlurper().parse(file("${projectDir}/assets/quick.json").toFile())
    def registry = new JsonSlurper().parse(file("${projectDir}/assets/assemblers.json").toFile())
    def selectedGroups = params.groups ? params.groups.tokenize(',') : []
    def selectedCases = params.cases ? params.cases.tokenize(',') : []
    cases = cases.findAll { (!selectedGroups || it.group in selectedGroups) && (!selectedCases || it.id in selectedCases) }
    if (!cases) error 'No implemented Quick cases match this selection.'
    def assemblers = params.assemblers.tokenize(',').unique()
    if (!assemblers || assemblers.any { !registry.containsKey(it) }) error 'Unknown assembler; see assets/assemblers.json.'
    def plan = file("${params.outdir}/selected-plan.json")
    plan.parent.mkdirs()
    plan.text = JsonOutput.prettyPrint(JsonOutput.toJson([schema_version: 1, cases: cases, assemblers: assemblers, workflow_source_sha256: fingerprint]))
    PREPARE_REFERENCE(Channel.fromList(cases.collect { it.reference_id }.unique()), file("${projectDir}/assets/references.json"), referenceSource)
    def inputs = Channel.fromList(cases).map { tuple(it.reference_id, it) }
        .combine(PREPARE_REFERENCE.out, by: 0).map { id, meta, reference, provenance -> tuple(meta, reference, provenance) }
    SIMULATE_READS(inputs, simulationSource)
    ASSEMBLE(SIMULATE_READS.out.combine(Channel.fromList(assemblers)), assemblySource)
    ASSESS(ASSEMBLE.out, assessmentSource)
    EXPORT_RESULTS(ASSESS.out.results.collect(), ASSESS.out.evidence.collect(), cases.size() * assemblers.size(), plan, exportSource)
}
