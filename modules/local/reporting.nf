import groovy.json.JsonOutput
import static BenchmarkUtils.shellQuote

process AGGREGATE {
    cpus 1
    cache false
    input:
    val publications
    val definitions
    val sourceFingerprint
    output:
    path 'aggregated.json'
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/benchmark.py')} aggregate \
      --outdir ${shellQuote(file(params.outdir).toString())} --definitions ${shellQuote(JsonOutput.toJson(definitions))}
    """
}

process RENDER_WEBSITE {
    cpus 1
    memory '4 GB'
    cache false
    input:
    val completed
    val sourceFingerprint
    output:
    path 'rendered.json'
    script:
    def prefix=params.network_blocker ? shellQuote(params.network_blocker)+' ' : ''
    """
    ${prefix}${shellQuote(params.bootstrap_python)} ${shellQuote(projectDir.toString()+'/bin/render-current.py')} \
      --results ${shellQuote(file(params.outdir).toString())} --outdir ${shellQuote(file(params.outdir).resolve('website').toString())} ${params.pilot_reports ? '--pilot' : ''}
    ${prefix}${shellQuote(params.bootstrap_python)} -c 'import json;json.dump({"status":"rendered"},open("rendered.json","w"))'
    """
}
