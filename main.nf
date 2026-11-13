nextflow.enable.dsl = 2
import groovy.json.JsonOutput
import static BenchmarkUtils.readPlan
import static BenchmarkUtils.shellQuote
import static BenchmarkUtils.sourceHash
import static BenchmarkUtils.sourcesUnder

// Controller-only lifecycle metadata; scientific cache keys do not depend on it.
def workLifecycle = [managed:false, runId:null]
def invokeWorkLifecycle(List arguments) {
    def process = new ProcessBuilder(arguments.collect { it.toString() })
        .redirectError(ProcessBuilder.Redirect.INHERIT).start()
    def output = process.inputStream.getText('UTF-8')
    if (process.waitFor() != 0) throw new IllegalStateException('Work lifecycle registration failed; see cleanup diagnostic above')
    return new groovy.json.JsonSlurper().parseText(output)
}
include { SETUP; ADMIT_INPUT; PREPARE_INPUT } from './modules/local/preparation'
include { ASSEMBLE; ASSESS; PUBLISH; NOT_APPLICABLE } from './modules/local/execution'
include { AGGREGATE; RENDER_WEBSITE } from './modules/local/reporting'

workflow {
    if (!params.help) {
        def runId = workflow.sessionId.toString()
        def result = invokeWorkLifecycle([params.bootstrap_python, projectDir.resolve('bin/cleanup.py'), 'begin',
            '--work-dir', workflow.workDir.toString(), '--cache-dir', file(params.cache_dir).toString(),
            '--outdir', file(params.outdir).toString(), '--project', projectDir.toString(), '--run-id', runId,
            '--controller-pid', java.lang.ProcessHandle.current().pid().toString(), '--allow-unowned-existing'])
        workLifecycle.managed = result.status == 'registered'
        workLifecycle.runId = runId
        if (!workLifecycle.managed) log.info result.reason
    }
    def presetCollections = [quick:'quick', standard:'simulated-native-genomes']
    if (params.preset && !presetCollections.containsKey(params.preset.toString()))
        error 'Unknown preset: ' + params.preset + '. Choose quick or standard.'
    if (params.help) {
        log.info '''
Single-isolate bacterial genome assembly benchmarks
  --preset quick|standard         Convenience collection selection; inspect Standard budget first
  --collections quick             Select collections (default: small validation)
  --preset quick|standard         Collection shorthand; inspect Standard before running
  --scenarios plasmids,gc-composition --cases ID,ID --workflows ID,ID
  --all                           All eligible declared cases; not a smoke test
  --catalogue PATH                Current catalogue or explicit local input manifest
  --cache_dir PATH --outdir PATH   Shared input cache and modular current results
  --plan_only                     Plan/inspect only; no downloads/installations
  --prepare_only                  Downloads/runtime only; no simulation
  --offline                       Require prepared data/software; never fetch
  --results_only                  Scientific packages, no hosted site build
  --render_only                   Render existing current packages without science
  --pilot_reports                 Label the optional website and exports as pilot validation
  --rerun                         Rerun selected assemblies, replacing current results
Profiles: local, bmrc, slurm; pixi/native_tools; singularity/apptainer/docker.
transfer_host places downloads on the submission host; simulation stays on compute.
'''
    } else if (params.render_only) {
        RENDER_WEBSITE(Channel.value([]), sourceHash(projectDir, sourcesUnder(projectDir, ['reporting/current_assets']) + ['reporting/current_site.py', 'bin/render-current.py']))
    } else {
        def selectedCollections = (params.collections ?: '').toString().tokenize(',')
        if (params.preset) selectedCollections += presetCollections[params.preset.toString()]
        def selection = [cases:params.cases, scenarios:params.scenarios, collections:selectedCollections.unique().join(','), workflows:params.workflows, all_eligible:params.all]
        def catalogueFile = file(params.catalogue, checkIfExists:true)
        def catalogueDocument = new groovy.json.JsonSlurper().parseText(catalogueFile.text)
        def registry = catalogueDocument.containsKey('reference_registry') ? catalogueDocument.reference_registry : 'assets/references.json'
        def registrySources = registry ? [projectDir.resolve(registry.toString()).toString()] : []
        SETUP(selection, catalogueFile, sourceHash(projectDir, ['bin/setup.py', 'benchlib/setup.py', 'benchlib/catalogue.py', 'benchlib/workflow_options.py', 'benchlib/preparation.py', 'benchlib/runtime_v2.py'] + registrySources))
        if (!params.plan_only) {
            def plan = SETUP.out.plan.map { readPlan(it) }
            def definitions = plan.map { p -> [collections:p.collections, scenarios:p.scenarios,
                selection:[expected_result_ids:p.slots.collect { it.result_id } + p.exclusions.collect { it.result_id }, plan_sha256:p.plan_sha256]] }
            def inputRows = plan.flatMap { p -> p.inputs.collect { input ->
                def deps = p.dependencies.findAll { it.id in input.dependencies }
                tuple(input, [schema_version:2, inputs:[input], dependencies:deps])
            }}
            ADMIT_INPUT(inputRows, sourceHash(projectDir, ['bin/admit.py', 'benchlib/preparation.py']))
            if (!params.prepare_only) {
                PREPARE_INPUT(ADMIT_INPUT.out, sourceHash(projectDir, ['bin/prepare-input.py', 'benchlib/inputs_v2.py', 'benchlib/references.py', 'benchlib/io.py']))
                def slotRows = PREPARE_INPUT.out.combine(plan).flatMap { input, dependencies, admitted, prepared, p ->
                    p.slots.findAll { it.input_id == input.id }.collect { slot ->
                        def scientificCase = slot.case.subMap(['id','dataset_id','input_id','science_key','read_technology','source_kind','recipe','scientific_repeat','scientific_repeat_id'])
                        def scientificWorkflow = slot.workflow.subMap(['id','tool','adapter','version','version_order','environment','manifest','configuration','resources'])
                        scientificWorkflow.runtime_dependencies = p.dependencies.findAll { it.id in slot.workflow.dependencies && it.kind in ['software','software_environment'] }.collect { it.subMap(['id','environment','manifest','manifest_sha256','lock_sha256','manager']) }
                        tuple([result_id:slot.result_id, case_id:slot.case_id, workflow_id:slot.workflow_id, case:scientificCase, workflow:scientificWorkflow], prepared.toRealPath())
                    }
                }
                ASSEMBLE(slotRows, sourceHash(projectDir, ['bin/run-assembly.py', 'benchlib/assembly.py', 'benchlib/workflow_options.py', 'benchlib/adapters.py', 'benchlib/miniasm.py', 'bin/run-miniasm.py', 'benchlib/process.py', 'benchlib/io.py']))
                ASSESS(ASSEMBLE.out, sourceHash(projectDir, ['bin/assess.py', 'benchlib/measurement.py', 'benchlib/assessment.py', 'benchlib/process.py', 'benchlib/io.py']))
                def currentSlots = plan.flatMap { p -> p.slots.collect { slot -> tuple(slot.result_id, slot + [input_definition:p.inputs.find { it.id == slot.input_id }]) } }
                def assessedSlots = ASSESS.out.map { core, prepared, execution, assessment -> tuple(core.result_id, prepared, execution, assessment) }
                def decorated = assessedSlots.join(currentSlots).map { id, prepared, execution, assessment, slot -> tuple(slot, prepared, execution, assessment) }
                PUBLISH(decorated, sourceHash(projectDir, ['bin/benchmark.py', 'benchlib/current_results.py', 'benchlib/descriptions.py']))
                NOT_APPLICABLE(plan.flatMap { it.exclusions }, sourceHash(projectDir, ['bin/benchmark.py', 'benchlib/current_results.py']))
                def publications = PUBLISH.out.mix(NOT_APPLICABLE.out).toList()
                AGGREGATE(publications, definitions, sourceHash(projectDir, ['bin/benchmark.py', 'benchlib/current_results.py', 'benchlib/selection_status.py']))
                if (!params.results_only) {
                    RENDER_WEBSITE(AGGREGATE.out, sourceHash(projectDir, sourcesUnder(projectDir, ['reporting/current_assets']) + ['reporting/current_site.py', 'bin/render-current.py']))
                }
            }
        }
    }
}


workflow.onComplete {
    if (workLifecycle.managed) {
        try {
            invokeWorkLifecycle([params.bootstrap_python, projectDir.resolve('bin/cleanup.py'), 'finish',
                '--work-dir', workflow.workDir.toString(), '--run-id', workLifecycle.runId,
                workflow.success ? '--success' : '--failed'])
        } catch (Exception error) {
            log.warn 'Work lifecycle completion could not be recorded; cleanup will remain refused: ' + error.message
        }
    }
}
