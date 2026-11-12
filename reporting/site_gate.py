"""Offline static-release safeguards. No network, cluster or sequence operations."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from .common import ROOT, digest, load
DEFAULT_POLICY = {'max_total_bytes': 64 * 1024 * 1024, 'max_file_bytes': 5 * 1024 * 1024, 'max_files': 1500}

class PageLinks(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.base = None
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'base':
            self.base = attrs.get('href')
        else:
            for name in ('href', 'src'):
                if attrs.get(name):
                    self.links.append(attrs[name])

def check_site(output, policy=None):
    root = Path(output).resolve()
    policy = {**DEFAULT_POLICY, **(policy or {})}
    errors, pages = ([], {})
    files = [p for p in root.rglob('*') if p.is_file()]
    total = sum((p.stat().st_size for p in files))
    if not files:
        errors.append('Website is empty')
    if total > policy['max_total_bytes']:
        errors.append(f"Website exceeds total byte budget: {total} > {policy['max_total_bytes']}")
    if len(files) > policy['max_files']:
        errors.append(f"Website exceeds file-count budget: {len(files)} > {policy['max_files']}")
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or root not in path.resolve().parents:
            errors.append(f'Published symlink or escaped file: {relative}')
            continue
        if path.stat().st_size > policy['max_file_bytes']:
            errors.append(f'File exceeds byte budget: {relative}')
        parts = path.relative_to(root).parts
        in_data = parts[0] == 'data' or (len(parts) > 2 and parts[0] == 'batches' and (parts[2] == 'data'))
        if path.suffix in {'.zip', '.gz', '.fastq', '.fasta', '.fa', '.gfa', '.md'} or (in_data and path.suffix == '.json' and (path.name != 'overview.json')):
            errors.append(f'Bulk/backend artefact in presentation build: {relative}')
        if path.suffix == '.html':
            parser = PageLinks()
            parser.feed(path.read_text())
            pages[path] = parser
    checked = 0
    for page, parsed in pages.items():
        base = 'https://release.invalid/' + page.relative_to(root).as_posix()
        if parsed.base:
            base = urljoin(base, parsed.base)
        for link in parsed.links:
            target = urlsplit(urljoin(base, link))
            if target.netloc != 'release.invalid' or target.scheme not in ('http', 'https'):
                continue
            checked += 1
            path = (root / unquote(target.path).lstrip('/')).resolve()
            if path != root and root not in path.parents:
                errors.append(f'Link escapes website: {page.relative_to(root)} -> {link}')
                continue
            candidates = [path / 'index.html'] if path.is_dir() or target.path.endswith('/') else [path, path.with_suffix('.html') if not path.suffix else path, path / 'index.html']
            found = next((p for p in candidates if p.is_file()), None)
            if not found:
                errors.append(f'Broken local link: {page.relative_to(root)} -> {link}')
            elif target.fragment and found in pages and (unquote(target.fragment) not in pages[found].ids):
                errors.append(f'Broken local anchor: {page.relative_to(root)} -> {link}')
    return {'schema_version': 1, 'status': 'fail' if errors else 'pass', 'website_bytes': total, 'public_files': sum((not any((v.startswith('.') for v in p.relative_to(root).parts)) for p in files)), 'total_files': len(files), 'html_pages': len(pages), 'local_links_checked': checked, 'policy': policy, 'errors': errors}

def check_release(bundle, output, snapshots=None, policy=None):
    """Bind a rendered website to its validated bundle and immutable snapshots."""
    from .bundle import load_bundle, result_id
    bundle, output = (Path(bundle).resolve(), Path(output).resolve())
    snapshots = Path(snapshots) if snapshots is not None else ROOT / 'published'
    report = check_site(output, policy)
    try:
        manifest, documents = load_bundle(bundle)
        marker = load(output / '.results-render.json')
        if marker.get('bundle_manifest_sha256') != digest(bundle / 'manifest.json'):
            raise ValueError('Website render marker belongs to a different bundle')
        receipt = load(output / '.site-files.json')
        current_files = receipt_files(output)
        if receipt.get('files') != current_files:
            raise ValueError('Rendered website files changed since the render receipt')
        sources = {s['batch']: s for s in manifest['sources']}
        preserved = 0
        for document in documents:
            source = sources[document['batch']]
            name = source['filename']
            if Path(name).name != name:
                raise ValueError('Snapshot filename is not a simple name')
            path = snapshots / name
            if digest(path) != source['sha256']:
                raise ValueError(f'Snapshot hash changed: {name}')
            frozen = load(path)
            for key in ('config', 'scenarios', 'inputs'):
                if document.get(key) != frozen.get(key):
                    raise ValueError(f'Changed source {key}: {name}')
            original = {result_id(row): row for row in frozen['results']}
            current = {result_id(row): row for row in document['results']}
            if original.keys() != current.keys():
                raise ValueError(f'Changed execution identities: {name}')
            for slug, row in current.items():
                if any((row.get(key) != value for key, value in original[slug].items())):
                    raise ValueError(f'Changed original score or source field: {name}/{slug}')
                plot = row.get('report_evidence', {}).get('dotplot', {})
                if plot.get('status') == 'available':
                    for key in ('assembly_sha256', 'truth_sha256'):
                        if not row.get(key) or plot.get('input_hashes', {}).get(key) != row[key]:
                            raise ValueError(f'Mismatched plot evidence: {name}/{slug}/{key}')
                origins = row.get('report_evidence', {}).get('reference_origins', {})
                if origins.get('nodes') or origins.get('node_intervals'):
                    expected = {'assembly_sha256': row.get('assembly_sha256'), 'truth_sha256': row.get('truth_sha256'), 'gfa_sha256': (row.get('graph_artifacts') or {}).get('graph', {}).get('source', {}).get('file_sha256')}
                    for key in ('assembly_sha256', 'gfa_sha256'):
                        if not expected[key] or origins.get('source_hashes', {}).get(key) != expected[key]:
                            raise ValueError(f'Mismatched graph origin evidence: {name}/{slug}/{key}')
                    for node in origins.get('node_intervals', {}).values():
                        if any((not value or node.get('input_hashes', {}).get(key) != value for key, value in expected.items())):
                            raise ValueError(f'Mismatched node interval evidence: {name}/{slug}')
                preserved += 1
        report['preserved_source_records'] = preserved
    except (ValueError, KeyError, OSError, TypeError) as error:
        report['errors'].append(str(error))
    report['status'] = 'fail' if report['errors'] else 'pass'
    return report

def require_site(output):
    report = check_site(output)
    if report['status'] != 'pass':
        raise ValueError('Static release gate failed: ' + '; '.join(report['errors'][:5]))
    return report

def write_site_receipt(output):
    from .common import save
    root = Path(output)
    files = receipt_files(root)
    save(root / '.site-files.json', {'schema_version': 1, 'files': files})

def receipt_files(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file() and p.name != '.site-files.json' and ('.vercel' not in p.relative_to(root).parts)}
