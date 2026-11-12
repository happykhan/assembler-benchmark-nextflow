import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process IMPORT_RESULTS {
    publishDir params.outdir, mode: 'copy', overwrite: false
    cpus 1
    input:
    path source
    output:
    path 'archive', emit: bundle
    path 'archive.import.json', emit: receipt
    script:
    def interpreter = params.runtime == 'pixi' ? "pixi run --locked --manifest-path ${shellQuote(projectDir.toString() + '/environments/pixi.toml')} python" : 'python3'
    """
    ${interpreter} ${shellQuote(projectDir.toString() + '/bin/import-results.py')} --source ${shellQuote(source)} --out-dir archive
    """
}

process RENDER_WEBSITE {
    cpus 1
    memory '4 GB'
    time '2 h'
    publishDir params.outdir, mode: 'copy', overwrite: true
    input:
    path bundle
    val sourceFingerprint
    output:
    path 'website'
    script:
    def interpreter = params.runtime == 'pixi' ? "pixi run --locked --manifest-path ${shellQuote(projectDir.toString() + '/environments/pixi.toml')} python" : 'python3'
    """
    ${interpreter} ${shellQuote(projectDir.toString() + '/bin/render-website.py')} --bundle ${shellQuote(bundle)} --out-dir website
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
      --out-dir bundle --expected-slots ${expectedSlots} --run-id ${shellQuote(params.run_id)} --plan ${shellQuote(plan)} --runtime-receipt ${shellQuote(runtimeReceipt)} --input-diagnostics ${inputDiagnostics.collect { shellQuote(it) }.join(' ')}
    """
}
