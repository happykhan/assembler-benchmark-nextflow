"""Immutable version declarations resolve through tested, argv-based adapters."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from benchlib.adapters import ADAPTERS, load_registry, resolve_assembler, validate_environment


ROOT = Path(__file__).resolve().parents[1]


class AdapterTests(unittest.TestCase):
    def test_aliases_resolve_to_the_same_immutable_definition(self):
        registry = load_registry(ROOT / 'assets/assemblers.json')
        self.assertEqual(resolve_assembler(registry, 'flye'), resolve_assembler(registry, 'flye-2.9.6'))
        self.assertNotEqual(resolve_assembler(registry, 'flye')['environment'],
                            resolve_assembler(registry, 'raven')['environment'])

    def test_adapter_arguments_preserve_paths_without_shell_interpretation(self):
        reads = Path('/reads/a file;echo injected.fastq')
        for adapter in ADAPTERS.values():
            command = adapter.command(reads, 3)
            self.assertIn(str(reads), command)
            self.assertIn('3', command)
            self.assertEqual(command[0], adapter.executable)

    def test_environment_must_exist_and_pin_the_declared_version(self):
        registry = load_registry(ROOT / 'assets/assemblers.json')
        declared = resolve_assembler(registry, 'flye')
        self.assertEqual(validate_environment(declared, ROOT), ROOT / 'environments/pixi.toml')
        with self.assertRaisesRegex(ValueError, 'absent'):
            validate_environment(dict(declared, environment='missing'), ROOT)
        with self.assertRaisesRegex(ValueError, 'pin exactly'):
            validate_environment(dict(declared, version='2.9.7'), ROOT)

    def test_second_version_needs_no_new_adapter_code(self):
        raw = json.loads((ROOT / 'assets/assemblers.json').read_text())
        new = dict(raw['assemblers'][0], id='flye-2.9.7', version='2.9.7', environment='flye-2-9-7')
        raw['assemblers'].append(new)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'assemblers.json'
            path.write_text(json.dumps(raw))
            registry = load_registry(path)
        current = resolve_assembler(registry, 'flye-2.9.6')
        next_version = resolve_assembler(registry, 'flye-2.9.7')
        self.assertEqual(current['adapter'], next_version['adapter'])
        self.assertNotEqual(current['id'], next_version['id'])
        self.assertEqual(resolve_assembler(registry, 'flye')['id'], current['id'])

    def test_unknown_versions_and_alias_targets_are_rejected(self):
        registry = load_registry(ROOT / 'assets/assemblers.json')
        with self.assertRaisesRegex(ValueError, 'Unknown assembler'):
            resolve_assembler(registry, 'flye-999.0')
        raw = json.loads((ROOT / 'assets/assemblers.json').read_text())
        raw['aliases']['next'] = 'flye-999.0'
        self.assert_invalid(raw, 'Alias')

    def test_duplicate_ids_version_drift_and_untested_commands_are_rejected(self):
        raw = json.loads((ROOT / 'assets/assemblers.json').read_text())
        duplicate = copy.deepcopy(raw)
        duplicate['assemblers'].append(duplicate['assemblers'][0])
        self.assert_invalid(duplicate, 'unique')
        changed = copy.deepcopy(raw)
        changed['assemblers'][0]['version'] = '2.9.7'
        self.assert_invalid(changed, 'exact tool/version')
        changed = copy.deepcopy(raw)
        changed['assemblers'][0]['command'] = 'echo unsupported'
        self.assert_invalid(changed, 'exactly')
        changed = copy.deepcopy(raw)
        changed['assemblers'][0]['adapter'] = 'shell'
        self.assert_invalid(changed, 'tested adapter')

    def test_escaped_manifests_and_unpinned_containers_are_rejected(self):
        raw = json.loads((ROOT / 'assets/assemblers.json').read_text())
        for change in ({'manifest': '../elsewhere/pixi.toml'}, {'manifest': '/tmp/pixi.toml'},
                       {'container': 'image:latest'}, {'status': 'candidate'}):
            with self.subTest(change=change):
                changed = copy.deepcopy(raw)
                changed['assemblers'][0].update(change)
                self.assert_invalid(changed)

    def assert_invalid(self, value, message=''):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'assemblers.json'
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, message):
                load_registry(path)
