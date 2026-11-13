"""Versioned assembler declarations use tested adapters, never shell templates."""
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib



@dataclass(frozen=True)
class FlyeAdapter:
    executable: str = 'flye'
    package: str = 'flye'
    assembly_relative: str = 'tool-output/assembly.fasta'
    graph_relative: str = 'tool-output/assembly_graph.gfa'

    def command(self, reads, cpus, options=None):
        options = validate_options(options)
        command = [self.executable, '--' + options.get('flye_input_mode', 'nano-raw'), str(reads), '--out-dir', 'tool-output', '--threads', str(cpus)]
        if options.get('flye_meta'):
            command.append('--meta')
        if options.get('deterministic'):
            command.append('--deterministic')
        return command


@dataclass(frozen=True)
class RavenAdapter:
    executable: str = 'raven'
    package: str = 'raven-assembler'
    assembly_relative: str = 'stdout.log'
    graph_relative: str = 'assembly.gfa'

    def command(self, reads, cpus, options=None):
        return [self.executable, '--threads', str(cpus), '--graphical-fragment-assembly', 'assembly.gfa', str(reads)]


def validate_options(options=None):
    options = dict(options or {})
    allowed = {'flye_input_mode', 'flye_meta', 'deterministic', 'plassembler_raw_flag',
               'plassembler_no_chromosome', 'plassembler_chromosome_threshold'}
    if set(options) - allowed:
        raise ValueError('Unknown assembly options: ' + ', '.join(sorted(set(options) - allowed)))
    if options.get('flye_input_mode', 'nano-raw') not in ('nano-raw', 'nano-hq', 'pacbio-raw', 'pacbio-hifi'):
        raise ValueError('Unsupported Flye input mode')
    for key in allowed - {'flye_input_mode', 'plassembler_chromosome_threshold'}:
        if key in options and type(options[key]) is not bool:
            raise ValueError('Assembly flag must be boolean: ' + key)
    threshold = options.get('plassembler_chromosome_threshold', 400000)
    if type(threshold) is not int or threshold < 1:
        raise ValueError('Invalid chromosome threshold')
    return options


@dataclass(frozen=True)
class PlassemblerAdapter:
    executable: str = 'plassembler'
    package: str = 'plassembler'
    assembly_relative: str = 'tool-output/benchmark_plasmids.fasta'
    graph_relative: str = 'tool-output/assembly_graph.gfa'

    def command(self, reads, cpus, options=None):
        options = validate_options(options)
        command = [self.executable, 'long', '--longreads', str(reads), '--outdir', 'tool-output',
                   '--threads', str(cpus), '--skip_qc', '--skip_mash', '--prefix', 'benchmark',
                   '--chromosome', str(options.get('plassembler_chromosome_threshold', 400000))]
        command.append('--no_chromosome' if options.get('plassembler_no_chromosome') else '--keep_chromosome')
        if options.get('plassembler_raw_flag'):
            command.append('--raw_flag')
        return command


@dataclass(frozen=True)
class MiniasmAdapter:
    executable: str = 'miniasm'
    package: str = 'miniasm'
    assembly_relative: str = 'tool-output/assembly.fasta'
    graph_relative: str = 'tool-output/assembly_graph.gfa'

    def command(self, reads, cpus, options=None):
        return [self.executable, '-f', str(reads), 'overlaps.paf']


@dataclass(frozen=True)
class MinipolishAdapter:
    executable: str = 'minipolish'
    tool: str = 'miniasm-plus'
    package: str = 'minipolish'
    assembly_relative: str = 'tool-output/assembly.fasta'
    graph_relative: str = 'tool-output/assembly_graph.gfa'

    def command(self, reads, cpus, options=None):
        return [self.executable, '--threads', str(cpus), '--rounds', '2', str(reads), 'assembly.raw.gfa']


ADAPTERS = {'flye': FlyeAdapter(), 'raven': RavenAdapter(), 'plassembler': PlassemblerAdapter(),
            'miniasm': MiniasmAdapter(), 'miniasm-plus': MinipolishAdapter()}



def verify_version(observed, expected, executable):
    """Accept a single exact release, with a known optional program label/build."""
    label = re.escape(executable)
    pattern = (r'(?:(?:' + label + r')(?:\s*,?\s*(?:version\s*)?|\s+v?))?'
               r'v?' + re.escape(expected) + r'(?:-(?:r|b)[0-9]+)?')
    if not isinstance(observed, str) or not re.fullmatch(pattern, observed.strip(), flags=re.IGNORECASE):
        raise ValueError('Pinned version mismatch for ' + executable + ': ' + str(observed))
    return observed.strip()


def environment_versions(definition, project):
    """Expose exact executable pins for every multi-stage assembly dependency."""
    content = tomllib.loads((Path(project) / definition['manifest']).read_text())
    env = content['environments'][definition['environment']]
    features = env if isinstance(env, list) else env.get('features', [])
    dependencies = dict(content.get('dependencies', {}))
    for feature in features:
        dependencies.update(content['feature'][feature].get('dependencies', {}))
    binaries = {'minimap2': 'minimap2', 'miniasm': 'miniasm', 'minipolish': 'minipolish', 'racon': 'racon'}
    versions = {}
    for binary, package in binaries.items():
        if package not in dependencies:
            continue
        pin = dependencies[package]
        if isinstance(pin, dict):
            pin = pin.get('version')
        if not isinstance(pin, str) or not re.fullmatch(r'==[0-9]+(?:\.[0-9]+)+', pin):
            raise ValueError('Multi-stage assembly dependency requires an exact release pin: ' + binary)
        versions[binary] = pin[2:]
    return versions
