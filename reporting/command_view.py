"""Display saved invocations and describe only arguments actually recorded."""
import html
import shlex
SOURCES = {'flye': ('Flye 2.9.6 manual', 'https://github.com/mikolmogorov/Flye/blob/2.9.6/docs/USAGE.md'), 'flye-meta': ('Flye 2.9.6 manual', 'https://github.com/mikolmogorov/Flye/blob/2.9.6/docs/USAGE.md'), 'raven': ('Raven 1.8.3 command definitions', 'https://github.com/lbcb-sci/raven/blob/1.8.3/RavenExe/src/main.cc'), 'plassembler': ('Plassembler 1.9.0 command definitions', 'https://github.com/gbouras13/plassembler/blob/v1.9.0/src/plassembler/__init__.py'), 'miniasm': ('Miniasm workflow documentation', 'https://github.com/lh3/miniasm#readme'), 'miniasm-plus': ('Minipolish 0.2.1 workflow documentation', 'https://github.com/rrwick/Minipolish/tree/v0.2.1')}
FLAGS = {'flye': {'--nano-hq': 'Supply reads using Flye’s high-quality Nanopore input mode.', '--out-dir': 'Directory for assembly output.', '--threads': 'Number of parallel threads requested.', '--meta': 'Enable the metagenome / uneven-coverage mode.', '--deterministic': 'Run the initial disjointig assembly stage single-threaded; later stages can still use the requested threads. This flag is tested for repeatability, not treated as a guarantee.'}, 'raven': {'-t': 'Number of threads requested.', '-F': 'Write the assembly graph in GFA format to this file.'}, 'miniasm': {'-x': 'Minimap2 preset: ava-ont computes all-versus-all Nanopore read overlaps.', '-t': 'Number of minimap2 overlap threads. Miniasm layout is single-threaded.', '-f': 'Read sequences used by miniasm to write unitig sequences.'}, 'plassembler': {'--longreads': 'Input long-read FASTQ file.', '--outdir': 'Directory for output files.', '--threads': 'Number of threads requested.', '--skip_qc': 'Skip the workflow’s read-QC filtering step.', '--skip_mash': 'Skip the Mash comparison against PLSDB.', '--no_chromosome': 'Use the plasmid-only workflow without an input chromosome; this skips the initial Flye stage in Plassembler.', '--keep_chromosome': 'Retain the chromosome assembly file during cleanup.', '--prefix': 'Prefix for output filenames.', '--chromosome': 'Lower-bound chromosome-length threshold, in base pairs.'}}

def render_command(record, case=None, collapsed=True):
    from .report import execution_evidence
    e = lambda value: html.escape(str(value), quote=True)
    command = record.get('command', [])
    if not isinstance(command, list) or not command or (not all((isinstance(arg, str) for arg in command))):
        if collapsed:
            return '<details class="command-used"><summary>Command used and flags</summary><p id="command-used">No command was recorded for this execution.</p></details>'
        return '<h3 id="command-used">Command used and flags</h3><p>No command was recorded for this execution.</p>'
    evidence = execution_evidence(record, case)
    command = evidence['command']
    tool = record.get('tool')
    definitions = FLAGS.get('flye' if tool == 'flye-meta' else 'miniasm' if tool == 'miniasm-plus' else tool, {})
    if tool == 'miniasm-plus':
        definitions = {**definitions, '--threads': 'Threads used by Minipolish for alignment and Racon polishing.', '--rounds': 'Two full Racon rounds after the initial constituent-read polish, matching the upstream default.'}
    body = '<details class="command-used"><summary>Command used and flags</summary><div id="command-used">' if collapsed else '<h3 id="command-used">Command used and flags</h3><div>'
    body += f"""<p class="muted">Recorded tool version: {e(record.get('version') or 'not recorded')}</p>"""
    steps = evidence.get('assembly_workflow', {}).get('steps', []) if tool in ('miniasm', 'miniasm-plus') else []
    if steps:
        for step in steps:
            text = shlex.join(step['command']) + ' > ' + shlex.quote(step['stdout_file'])
            reused = ' · reused source stage' if step.get('reused_source_stage') else ''
            if step.get('status') == 'not_run_empty_source_assembly':
                reused = ' · not run: source Miniasm assembly is empty'
            body += f"""<h4>{e(step['name'] + reused)}</h4><pre class="recorded-command"><code>{e(text)}</code></pre>"""
        body += '<p>Final Minipolish GFA segment sequences are copied into the scored FASTA. Runtime includes the source Miniasm stages and polishing.</p>' if tool == 'miniasm-plus' else '<p>Unitig sequences are copied from GFA segment records into FASTA. No polishing step is run.</p>'
    else:
        body += f'<pre class="recorded-command"><code>{e(shlex.join(command))}</code></pre>'
    if any(('<workdir>' in arg for arg in command)):
        body += '<p class="muted"><code>&lt;workdir&gt;</code> marks the benchmark work directory.</p>'
    body += '<dl class="command-options">'
    if tool == 'plassembler' and len(command) > 1 and (command[1] == 'long'):
        body += '<dt><code>long</code></dt><dd>Long-read-only workflow.</dd>'
    arguments = [arg for step in steps for arg in step['command'][1:]] if steps else command[1:]
    for flag in dict.fromkeys((arg.split('=', 1)[0] for arg in arguments if arg.startswith('-'))):
        body += f"<dt><code>{e(flag)}</code></dt><dd>{e(definitions.get(flag, 'No description is included here; consult the tool documentation.'))}</dd>"
    if tool == 'raven':
        body += '<dt>Input file</dt><dd>The positional argument supplies the read file.</dd>'
    body += '</dl>'
    if tool in SOURCES:
        title, url = SOURCES[tool]
        body += f'<p class="muted">Flag descriptions: <a href="{e(url)}">{e(title)}</a>.</p>'
    return body + ('</div></details>' if collapsed else '</div>')
