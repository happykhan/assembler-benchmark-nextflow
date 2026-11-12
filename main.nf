nextflow.enable.dsl = 2
import static BenchmarkUtils.readPlan
import static BenchmarkUtils.sourceHash
import static BenchmarkUtils.sourcesUnder
include { PREPARE_RUN; PREPARE_REFERENCE; SIMULATE_READS; PREPARE_REAL_READS; PREPARE_COLLECTION_INPUT; REAL_READ_DIAGNOSTICS; LIST_CHOICES } from './modules/local/preparation'
include { ASSEMBLE; ASSESS } from './modules/local/execution'
include { IMPORT_RESULTS; RENDER_WEBSITE; EXPORT_RESULTS } from './modules/local/reporting'

workflow {
    if (params.help) {
        log.info """
Single-isolate bacterial long-read assembly benchmarks
  --preset quick|standard          Workflow check or admitted scientific selection
  --track simulated|real|general|diagnostic
  --groups S1,S5                   Select diagnostic groups (or named aliases)
  --cases ID,ID --assemblers ID,ID  Select cases and exact tool versions
  --plan_only                      Freeze/review selection; no scientific tasks
  --prepare_only                   Prepare selected inputs; no assemblies
  --list                           List admitted choices
  --offline                        Require previously verified input caches
  --import_bundle PATH             Import sealed results and render website only
  --diagnostic_source_dir PATH     Original S7 input directories under case IDs
  --outdir PATH -resume            Output directory and Nextflow cache reuse
Profiles: pixi (default), singularity, apptainer, docker; local, slurm, bmrc
"""
    } else if (params.list) {
        LIST_CHOICES()
    } else if (params.import_bundle) {
        IMPORT_RESULTS(file(params.import_bundle, checkIfExists: true))
        RENDER_WEBSITE(IMPORT_RESULTS.out.bundle, sourceHash(projectDir, sourcesUnder(projectDir, ['reporting', 'website', 'schemas'])))
    } else {
        // Shared caches must exist before a container engine can bind them.
        file(params.reference_dir).mkdirs()
        file(params.read_cache).mkdirs()
        // A reporting repair must not rerun a cached assembler on unchanged inputs.
        def referenceSource = sourceHash(projectDir, ['bin/prepare-reference.py', 'benchlib/references.py', 'assets/references.json'])
        def simulationSource = sourceHash(projectDir, ['bin/simulate-reads.py', 'benchlib/io.py', 'benchlib/standard_reads.py'])
        def assemblySource = sourceHash(projectDir, ['bin/run-assembler.py', 'benchlib/io.py', 'benchlib/process.py', 'benchlib/adapters.py', 'benchlib/miniasm.py', 'bin/run-miniasm.py', 'assets/assemblers.json'])
        def assessmentSource = sourceHash(projectDir, ['bin/assess-assembly.py', 'benchlib/assessment.py', 'benchlib/paper_recovery.py', 'benchlib/process.py', 'bin/assess-diagnostic.py', 'benchlib/evidence.py'] + sourcesUnder(projectDir, ['diagnostic_core']))
        def exportSource = sourceHash(projectDir, ['bin/export-results.py', 'benchlib/assessment.py', 'benchlib/report.py'] + sourcesUnder(projectDir, ['reporting']))
        def runtimeProfiles = workflow.profile.tokenize(',').findAll { it in ['pixi', 'docker', 'singularity', 'apptainer', 'native_tools'] }
        if (runtimeProfiles.size() > 1) error 'Choose exactly one runtime profile.'
        if (runtimeProfiles.any { it in ['docker', 'singularity', 'apptainer'] } &&
            !(params.container_image ==~ /.+@sha256:[a-f0-9]{64}/))
            error 'Container runtimes require a digest-pinned runtime image.'
        def validationSource = sourceHash(projectDir, ['bin/prepare-run.py', 'benchlib/bootstrap.py', 'benchlib/runtime.py', 'bin/plan.py', 'benchlib/planning.py', 'benchlib/adapters.py',
            'benchlib/references.py', 'benchlib/real_planning.py', 'benchlib/real_data.py', 'assets/real-pilot.json', 'assets/assemblers.json', 'assets/quick.json', 'assets/standard.json', 'assets/references.json', 'assets/groups.json', 'benchlib/general_planning.py', 'benchlib/general_inputs.py', 'benchlib/diagnostic_planning.py', 'bin/prepare-general-input.py', 'bin/prepare-diagnostic-input.py'] + sourcesUnder(projectDir, ['assets/general', 'assets/diagnostics', 'diagnostic_core']))
        def selection = [track: params.track, preset: params.preset, groups: params.groups, cases: params.cases, assemblers: params.assemblers]
        PREPARE_RUN(params.plan ? file(params.plan, checkIfExists: true) : [], selection, validationSource)
        if (!params.plan_only) {
            def spec = PREPARE_RUN.out.plan.map {
                def plan = readPlan(it)
                if (plan.track == 'diagnostic' && plan.cases.any { it.category == 'S7' } && !params.diagnostic_source_dir)
                    error 'S7 requires --diagnostic_source_dir containing its admitted original input. Select other groups or supply that cache.'
                plan
            }
            def cases = spec.flatMap { it.cases }
            def freshReferences = spec.flatMap { plan -> plan.track in ['general', 'diagnostic'] ? [] : plan.reference_ids }
            PREPARE_REFERENCE(freshReferences, file("${projectDir}/assets/references.json"), referenceSource)
            def preparedCases = cases.filter { !(it.track in ['general', 'diagnostic']) }
            def inputs = preparedCases.map { tuple(it.reference_id, it) }
                .combine(PREPARE_REFERENCE.out, by: 0).map { id, meta, reference, provenance -> tuple(meta, reference, provenance) }
            def inputTracks = inputs.branch {
                real: it[0].track == 'real'
                simulated: true
            }
            def realSource = sourceHash(projectDir, ['bin/prepare-real-reads.py', 'benchlib/real_inputs.py', 'benchlib/io.py'])
            PREPARE_REAL_READS(inputTracks.real, PREPARE_RUN.out.plan, realSource)
            REAL_READ_DIAGNOSTICS(PREPARE_REAL_READS.out, sourceHash(projectDir, ['bin/diagnose-real-reads.py', 'benchlib/read_diagnostics.py', 'benchlib/assessment.py', 'benchlib/process.py']))
            SIMULATE_READS(inputTracks.simulated, simulationSource, spec.map { it.resource_policy.simulation ?: [cpus: 1, time_minutes: 30] })
            PREPARE_COLLECTION_INPUT(cases.filter { it.track in ['general', 'diagnostic'] }, PREPARE_RUN.out.plan, validationSource)
            def allInputs = SIMULATE_READS.out.mix(PREPARE_REAL_READS.out).mix(PREPARE_COLLECTION_INPUT.out)
            if (!params.prepare_only) {
                def selectedSlots = allInputs.combine(spec).flatMap { meta, reference, provenance, reads, inputMetadata, plan ->
                    plan.slots.findAll { it.case_id == meta.id }.collect { slot ->
                        def definition = new LinkedHashMap(plan.assembler_definitions[slot.assembler])
                        definition.resources = [cpus: meta.threads ?: plan.resource_policy.assembly.cpus,
                            memory_gb: (plan.resource_policy.assembly.memory_gb_by_tool ?: [:]).get(definition.tool, plan.resource_policy.assembly.default_memory_gb),
                            time_minutes: definition.tool == 'plassembler' ? Math.min(120, plan.resource_policy.assembly.time_minutes as int) : plan.resource_policy.assembly.time_minutes]
                        tuple(meta, reference, provenance, reads, inputMetadata, definition)
                    }
                }
                ASSEMBLE(selectedSlots, assemblySource)
                ASSESS(ASSEMBLE.out, assessmentSource)
                EXPORT_RESULTS(ASSESS.out.results.collect(), ASSESS.out.evidence.collect(), spec.map { it.expected_slots }, PREPARE_RUN.out.plan, PREPARE_RUN.out.receipt, REAL_READ_DIAGNOSTICS.out.toList(), exportSource)
                RENDER_WEBSITE(EXPORT_RESULTS.out, sourceHash(projectDir, sourcesUnder(projectDir, ['reporting', 'website', 'schemas'])))
                EXPORT_RESULTS.out.ifEmpty { error 'No complete result bundle was exported.' }
                    .subscribe { log.info "Results bundle: ${params.outdir}/bundle/index.html" }
            }
        }
    }
}
