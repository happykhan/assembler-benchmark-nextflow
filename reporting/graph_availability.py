"""Describe graph evidence availability independently of assembly correctness."""
GRAPH_FLAGS = ('-F', '-U', '--graphical-fragment-assembly', '--unitig-graphical-fragment-assembly')

def graph_requested(command):
    return any((isinstance(arg, str) and (arg in GRAPH_FLAGS or arg.startswith(('--graphical-fragment-assembly=', '--unitig-graphical-fragment-assembly=')) or (arg.startswith(('-F', '-U')) and len(arg) > 2)) for arg in command))

def graph_availability(record, artifact):
    graph = artifact.get('graph') or {}
    status = graph.get('status')
    if status == 'available':
        return {'status': 'available', 'title': 'Recorded assembly graph', 'description': 'Saved GFA metadata are available.'}
    if record.get('status') == 'not_run':
        return {'status': 'not_run', 'title': 'Not run', 'description': 'This execution was not run, so no assembly graph is expected.'}
    if status == 'invalid' or artifact.get('status') == 'invalid':
        return {'status': 'invalid', 'title': 'Graph metadata failed validation', 'description': artifact.get('reason') or graph.get('reason') or 'The graph metadata are unreadable or do not match their recorded sources.'}
    if status == 'unsupported':
        return {'status': 'unsupported', 'title': 'Graph exceeds supported limits', 'description': graph.get('reason') or 'The saved graph could not be fully parsed within the reporting limits.'}
    command = record.get('command') or []
    if record.get('tool') == 'raven' and command and (not graph_requested(command)):
        return {'status': 'not_requested', 'title': 'Graph output was not requested', 'description': 'This Raven command saved the assembly FASTA but did not request a GFA with -F or -U. The missing graph does not indicate a corrupt assembly.'}
    return {'status': 'not_collected', 'title': 'Graph unavailable', 'description': artifact.get('reason') or graph.get('reason') or 'No usable GFA metadata were collected for this execution.'}
