"""Readable video version folders; opaque job IDs stay stable for old links."""
from pathlib import Path
import re

from core import read_json
from windows_names import generated

PREFIXES = {'export': 'Export', 'preview': 'Preview', 'analyze': 'Analysis', 'download': 'Download'}


def reserve(project_folder, kind, minimum=1):
    prefix = PREFIXES[kind]
    parent = Path(project_folder) / ('Exports' if kind == 'export' else 'Jobs')
    parent.mkdir(exist_ok=True)
    numbers = [int(match[1]) for child in parent.iterdir()
               if (match := re.fullmatch(re.escape(prefix) + r' (\d+)', child.name))]
    version = max(minimum, max(numbers, default=0) + 1)
    while True:
        target = parent / f'{prefix} {version:03}'
        try:
            target.mkdir()
            return target, version
        except FileExistsError:
            version += 1


def output_name(job, extension):
    if not job.get('version'):
        return ('preview.' if job['kind'] == 'preview' else 'video.') + extension
    label = f"v{job['version']:03}" if job['kind'] == 'export' else f"Preview {job['version']:03}"
    return generated(job['project'], f' - {label}.{extension}')


def locate(project_folder, ident):
    if not re.fullmatch(r'[0-9a-f]{32}', ident):
        raise ValueError('无效任务编号')
    for section in ('Exports', 'Jobs'):
        parent = Path(project_folder) / section
        legacy = parent / ident
        candidates = [legacy] + [p for p in parent.iterdir() if p != legacy] if parent.exists() else []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.parent != parent.resolve() or not (resolved / 'job.json').is_file():
                continue
            try:
                record = read_json(resolved / 'job.json')
                if record.get('id') == ident:
                    return resolved, record
            except (OSError, ValueError):
                continue
    raise ValueError('任务版本不存在')
