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

    def command(self, reads, cpus):
        return [self.executable, '--nano-raw', str(reads), '--out-dir', 'tool-output', '--threads', str(cpus)]


@dataclass(frozen=True)
class RavenAdapter:
    executable: str = 'raven'
    package: str = 'raven-assembler'
    assembly_relative: str = 'stdout.log'
    graph_relative: str = 'assembly.gfa'

    def command(self, reads, cpus):
        return [self.executable, '--threads', str(cpus), '--graphical-fragment-assembly', 'assembly.gfa', str(reads)]


ADAPTERS = {'flye': FlyeAdapter(), 'raven': RavenAdapter()}


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
        if row['adapter'] not in ADAPTERS or ADAPTERS[row['adapter']].executable != tool:
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
