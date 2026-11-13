"""Explicit scientific options implemented by each supported argv adapter."""

ALLOWED={
    'flye':{'flye_input_mode','flye_meta','deterministic'},
    'plassembler':{'plassembler_raw_flag','plassembler_no_chromosome','plassembler_chromosome_threshold'},
    'raven':set(),'skesa':set(),'miniasm':set(),'miniasm-plus':set(),
}


def workflow_options(tool,configuration):
    if tool not in ALLOWED:raise ValueError('Unsupported assembler tool: '+str(tool))
    if not isinstance(configuration,dict):raise ValueError('Workflow configuration must be an object')
    if configuration.get('mode','default')!='default':
        raise ValueError('Unsupported workflow mode; declare implemented options explicitly')
    options={k:v for k,v in configuration.items() if k!='mode'}
    unknown=set(options)-ALLOWED[tool]
    if unknown:raise ValueError('Unsupported '+tool+' options: '+', '.join(sorted(unknown)))
    for key,value in options.items():
        if key=='flye_input_mode':
            if value not in ('nano-raw','nano-hq','pacbio-raw','pacbio-hifi'):raise ValueError('Unsupported Flye input mode')
        elif key=='plassembler_chromosome_threshold':
            if type(value) is not int or value<1:raise ValueError('Invalid chromosome threshold')
        elif type(value) is not bool:raise ValueError('Workflow flags must be boolean: '+key)
    return options
