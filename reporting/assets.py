"""Build frontend assets on the controller; reuse them without Node on BMRC."""
import os
import shutil
import subprocess
from .common import digest, load

def ensure_assets(root):
    website = root / 'website'
    generated = website / 'generated'
    manifest = generated / 'build.json'
    sources = ('package.json', 'shell.jsx', 'site.css', 'graph.jsx', 'graph.css', 'origin-evidence.jsx', 'table-controls.js', 'mobile-matrix.js', 'dotplot.jsx', 'build.mjs')
    expected = {name: digest(website / name) for name in sources}
    if manifest.exists():
        info = load(manifest)
        if info.get('source_sha256') == expected and all(((generated / name).exists() and digest(generated / name) == sha for name, sha in info['sha256'].items())):
            return generated
    if not shutil.which('npm'):
        raise ValueError('Build the GenomicX website assets on the controller before syncing to BMRC')
    package = load(website / 'package.json')
    dependencies = {**package['dependencies'], **package.get('devDependencies', {})}
    installed = all(((website / 'node_modules' / name / 'package.json').exists() and load(website / 'node_modules' / name / 'package.json')['version'] == version for name, version in dependencies.items()))
    env = dict(os.environ, npm_config_cache=str(root / '.cache/npm'))
    if not installed:
        subprocess.run(['npm', 'install', '--package-lock=false', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=website, env=env, check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=website, env=env, check=True)
    if load(manifest).get('source_sha256') != expected:
        raise ValueError('Frontend sources changed during the build; retry before submission/publication')
    return generated
