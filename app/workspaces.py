"""One owned output root per song; legacy creative documents remain in place."""
from pathlib import Path
import re
import threading

from core import ROOT, read_json, save_json

LOCK = threading.RLock()
DIRECTORIES = ['source', 'separation', 'working/sv', 'working/sv2', 'working/lyrics',
               'snapshots/sv', 'analysis', 'studio-one', 'video', 'exports/audio',
               'exports/lyrics', 'exports/subtitles', 'exports/svp', 'exports/reports', 'exports/delivery']


def registry():
    file = ROOT / 'config/workspaces.local.json'
    return read_json(file) if file.exists() else {}


def name(value):
    value = str(value).strip()
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}', value)
            or value.endswith(('.', ' ')) or value.split('.')[0].upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}):
        raise ValueError('目录名请使用英文、数字、空格、连字符或下划线（最多 80 字符）')
    return value


def suggested(p):
    text = ' - '.join(filter(None, [p.get('artist', ''), p['title']]))
    try:
        return name(text)
    except ValueError:
        for value in (p['title'], p['id'] if not re.fullmatch(r'song-[0-9a-f]+', p['id']) else 'New Song'):
            try:
                return name(value)
            except ValueError:
                continue
        return 'New Song'


def root(p):
    """Read only. Before adoption, retain the legacy output root."""
    return Path(registry().get(p['id'], p['pilot']))


def proposed(p):
    """Read-only preview of the copy destination, including legacy adoption."""
    rows = registry()
    if p['id'] in rows:
        return Path(rows[p['id']])
    base, label, number = ROOT / 'projects', suggested(p), 2
    dest = base / label
    while dest.exists():
        dest = base / f'{label}_v{number}'
        number += 1
    return dest


def allocate(p, folder_name=None):
    with LOCK:
        rows = registry()
        if p['id'] in rows:
            return Path(rows[p['id']])
        base = ROOT / 'projects'
        base.mkdir(parents=True, exist_ok=True)
        label = name(folder_name) if folder_name else suggested(p)
        dest = base / label
        number = 2
        while True:
            try:
                dest.mkdir()
                break
            except FileExistsError:
                dest = base / f'{label}_v{number}'
                number += 1
        for directory in DIRECTORIES:
            (dest / directory).mkdir(parents=True, exist_ok=True)
        save_json(dest / 'workspace.json', {'version': 1, 'musicId': p['id'], 'title': p['title'],
                                          'legacyPilot': p.get('pilot', ''), 'directories': DIRECTORIES})
        rows[p['id']] = str(dest)
        save_json(ROOT / 'config/workspaces.local.json', rows)
        return dest


def outputs(p):
    return allocate(p)


def status(ident):
    import project_assets
    p = project_assets.project(ident)
    rows = registry()
    dest = root(p)
    return {'musicId': ident, 'managed': ident in rows, 'root': str(dest), 'suggested': suggested(p),
            'directories': DIRECTORIES,
            'externalAssets': {k: v for k, v in project_assets.status(ident)['assets'].items()
                               if v['path'] and not Path(v['path']).resolve().is_relative_to(dest.resolve())}}


def prepare(ident, body):
    import project_assets
    p = project_assets.project(ident)
    allocate(p, body.get('name'))
    return status(ident)


def video_output(ident):
    """Only explicitly linked songs that adopted a workspace change future output paths."""
    from video_links import STORE
    if STORE.exists():
        for music_id, link in read_json(STORE).get('links', {}).items():
            if link.get('videoId') == ident and music_id in registry():
                return Path(registry()[music_id]) / 'video' / ident
    return None
