"""Versioned assembler declarations use tested adapters, never shell templates."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


IDENTIFIER = re.compile(r'[a-z][a-z0-9_-]*\Z')
ENVIRONMENT = re.compile(r'[a-z][a-z0-9-]*\Z')
VERSION = re.compile(r'[0-9]+(?:\.[0-9]+)+(?:[a-z0-9_-]+)?\Z')


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



def load_registry(path):
    registry = json.loads(Path(path).read_text())
    if registry.get('schema_version') != 1 or not isinstance(registry.get('assemblers'), list):
        raise ValueError('Unsupported assembler registry schema')
    definitions = {}
    for row in registry['assemblers']:
        required = {'id', 'tool', 'version', 'adapter', 'environment', 'manifest', 'container', 'status'}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError('Assembler definition must contain exactly: ' + ', '.join(sorted(required)))
        tool, version = row['tool'], row['version']
        if not isinstance(tool, str) or not IDENTIFIER.fullmatch(tool):
            raise ValueError('Invalid assembler tool name')
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError('Invalid pinned assembler version')
        if row['id'] != tool + '-' + version or row['id'] in definitions:
            raise ValueError('Assembler ID must be unique and bind its exact tool/version')
        if row['adapter'] not in ADAPTERS or getattr(ADAPTERS[row['adapter']], 'tool', ADAPTERS[row['adapter']].executable) != tool:
            raise ValueError('Assembler must use a tested adapter for its executable')
        if not isinstance(row['environment'], str) or not ENVIRONMENT.fullmatch(row['environment']):
            raise ValueError('Invalid pinned environment name')
        manifest = Path(row['manifest'])
        if manifest.is_absolute() or '..' in manifest.parts or manifest.suffix != '.toml':
            raise ValueError('Manifest must be a project-relative TOML path')
        if row['container'] is not None and (not isinstance(row['container'], str) or '@sha256:' not in row['container']):
            raise ValueError('Container definitions require a digest-pinned image or null')
        if row['status'] != 'admitted':
            raise ValueError('Only admitted assembler definitions can run')
        definitions[row['id']] = dict(row)
    aliases = registry.get('aliases', {})
    if not isinstance(aliases, dict):
        raise ValueError('Assembler aliases must be a mapping')
    for alias, target in aliases.items():
        if not isinstance(alias, str) or not IDENTIFIER.fullmatch(alias) or alias in definitions or target not in definitions:
            raise ValueError('Alias must resolve directly to an admitted immutable ID')
    return {'schema_version': 1, 'aliases': dict(aliases), 'assemblers': definitions}


def resolve_assembler(registry, selection):
    identifier = registry['aliases'].get(selection, selection)
    if identifier not in registry['assemblers']:
        raise ValueError('Unknown assembler or version: ' + str(selection))
    return dict(registry['assemblers'][identifier])


def validate_environment(definition, project):
    """Catch a version declaration that lacks its matching isolated environment."""
    manifest = Path(project) / definition['manifest']
    content = tomllib.loads(manifest.read_text())
    environment = content.get('environments', {}).get(definition['environment'])
    if environment is None:
        raise ValueError('Declared assembler environment is absent from its manifest')
    features = environment if isinstance(environment, list) else environment.get('features', [])
    dependencies = dict(content.get('dependencies', {}))
    for name in features:
        dependencies.update(content.get('feature', {}).get(name, {}).get('dependencies', {}))
    package = ADAPTERS[definition['adapter']].package
    pin = dependencies.get(package)
    if isinstance(pin, dict):
        pin = pin.get('version')
    if pin != '==' + definition['version']:
        raise ValueError('Assembler environment must pin exactly the declared executable version')
    return manifest


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
