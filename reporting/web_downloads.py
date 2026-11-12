"""Publish presentation assets only; backend evidence stays in its source bundle."""
import html
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

def deduplicate_evidence_assets(root):
    """Share byte-identical tables/figures without merging any scientific records."""
    groups = defaultdict(list)
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in {'.svg', '.png', '.tsv'}:
            continue
        parts = path.relative_to(root).parts
        in_data = parts[0] == 'data' or (len(parts) >= 4 and parts[0] == 'batches' and (parts[2] == 'data'))
        if in_data:
            groups[path.suffix, hashlib.sha256(path.read_bytes()).hexdigest()].append(path)
    replacements = {}
    count = saved = 0
    for (suffix, checksum), paths in groups.items():
        if len(paths) < 2:
            continue
        canonical = root / 'data/shared' / (checksum + suffix)
        canonical.parent.mkdir(parents=True, exist_ok=True)
        if canonical.exists():
            if hashlib.sha256(canonical.read_bytes()).hexdigest() != checksum:
                raise ValueError('Shared evidence asset checksum collision')
        else:
            shutil.copy2(paths[0], canonical)
        destination = '/' + canonical.relative_to(root).as_posix()
        for path in paths:
            if path == canonical:
                continue
            replacements['/' + path.relative_to(root).as_posix()] = destination
            saved += path.stat().st_size
            count += 1
            path.unlink()
        if canonical not in paths:
            count -= 1
            saved -= canonical.stat().st_size
    if replacements:
        for page in root.rglob('*.html'):
            content = page.read_text()
            base = 'https://bundle.invalid/' + page.relative_to(root).as_posix()
            tag = re.search('<base\\b[^>]*\\bhref=["\\\']([^"\\\']+)["\\\']', content)
            if tag:
                base = urljoin(base, html.unescape(tag[1]))

            def replace(match):
                url = urlsplit(urljoin(base, html.unescape(match[3])))
                destination = replacements.get(unquote(url.path)) if url.netloc == 'bundle.invalid' else None
                if destination is None:
                    return match[0]
                target = destination + ('?' + url.query if url.query else '') + ('#' + url.fragment if url.fragment else '')
                return match[1] + '=' + match[2] + html.escape(target, quote=True) + match[2]
            segments = re.split('(<script\\b[^>]*>.*?</script>)', content, flags=re.DOTALL | re.IGNORECASE)
            for index in range(0, len(segments), 2):
                segments[index] = re.sub('\\b(href|src)=(["\\\'])(.*?)\\2', replace, segments[index], flags=re.DOTALL)
            page.write_text(''.join(segments))
    return {'shared_asset_groups': len(set(replacements.values())), 'deduplicated_file_count': count, 'deduplicated_file_bytes': saved}

def package_downloads(output):
    """Remove bulk evidence copies and their links from the generated website.

    Scores, visible tables, plots and inline graph models are untouched. The
    complete validated backend bundle and its separate ZIP remain outside output.
    """
    root = Path(output).resolve()
    audit_path = root / 'site-manifest.json'
    (root / 'download-sizes.json').unlink(missing_ok=True)
    before = sum((p.stat().st_size for p in root.rglob('*') if p.is_file() and p != audit_path))
    removed = set()
    removed_bytes = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        in_data = parts[0] == 'data' or (len(parts) >= 4 and parts[0] == 'batches' and (parts[2] == 'data'))
        if not in_data or path.name == 'overview.json':
            continue
        if path.suffix not in {'.json', '.gz', '.zip', '.md'}:
            continue
        removed.add('/' + path.relative_to(root).as_posix())
        removed_bytes += path.stat().st_size
        path.unlink()
    for path in sorted(root.rglob('*.html')):
        content = path.read_text()
        base = 'https://bundle.invalid/' + path.relative_to(root).as_posix()
        base_tag = re.search('<base\\b[^>]*\\bhref=["\\\']([^"\\\']+)["\\\']', content)
        if base_tag:
            base = urljoin(base, html.unescape(base_tag[1]))

        def anchor(match):
            resolved = urlsplit(urljoin(base, html.unescape(match[2])))
            if resolved.netloc == 'bundle.invalid' and unquote(resolved.path) in removed:
                return ''
            return match[0]
        segments = re.split('(<script\\b[^>]*>.*?</script>)', content, flags=re.DOTALL | re.IGNORECASE)
        for index in range(0, len(segments), 2):
            value = re.sub('<a\\b[^>]*\\bhref=(["\\\'])([^"\\\']+)\\1[^>]*>.*?</a>', anchor, segments[index], flags=re.DOTALL)
            value = re.sub('<p>\\s*(?:[·|]\\s*)*</p>', '', value)
            value = re.sub('(<p>)\\s*[·|]\\s*', '\\1', value)
            value = re.sub('\\s*[·|]\\s*(</p>)', '\\1', value)
            segments[index] = value
        path.write_text(''.join(segments))
    for folder in sorted((root / 'batches').glob('*/assets')):
        for path in folder.rglob('*'):
            if path.is_file():
                shared = root / 'assets' / path.relative_to(folder)
                if not shared.is_file() or path.read_bytes() != shared.read_bytes():
                    raise ValueError(f'Batch asset differs from root asset: {path}')
        batch = folder.parent.name
        for page in folder.parent.rglob('*.html'):
            value = page.read_text()
            value = re.sub('((?:href|src)=")(?:(?:\\.\\./)*|/batches/' + re.escape(batch) + '/)assets/', '\\1/assets/', value)
            page.write_text(value)
        import shutil
        shutil.rmtree(folder)
    config_path = root / 'vercel.json'
    config = json.loads(config_path.read_text())
    for key in ('redirects', 'headers'):
        if key in config:
            config[key] = [rule for rule in config[key] if ':scope(' not in rule.get('source', '')]
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    overview = json.loads((root / 'data/overview.json').read_text()) if (root / 'data/overview.json').is_file() else {}
    shared = deduplicate_evidence_assets(root)
    after = sum((p.stat().st_size for p in root.rglob('*') if p.is_file() and p != audit_path))
    manifest = {'schema_version': 2, 'policy': 'presentation-only', 'batch': overview.get('included_batches', [None])[0], 'website_bytes_before': before, 'website_bytes_after': after, 'removed_download_count': len(removed), 'removed_download_bytes': removed_bytes, 'backend_evidence': 'Retained in the separate validated backend bundle; not deployed to Vercel.', **shared}
    audit_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest
