import re
TOOLS = {'flye': 'Flye', 'raven': 'Raven', 'plassembler': 'Plassembler', 'miniasm-plus': 'Miniasm + Minipolish'}
OUTCOMES = {'fully_complete': 'All molecules complete', 'chromosome_complete': 'Chromosome complete; plasmids incomplete', 'incomplete': 'Incomplete assembly', 'empty': 'Empty assembly', 'did_not_complete': 'Did not complete', 'execution_error': 'Execution or assessment error'}
DATASET_ID = re.compile('\\d{3}_GCF_\\d{9}\\.\\d+\\Z')
