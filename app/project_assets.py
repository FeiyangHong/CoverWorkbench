"""Explicit per-song handoff files. Opening or registering never edits creative files."""
from pathlib import Path
import os
import threading

from core import ROOT, read_json, save_json
import daw

STORE = ROOT / 'config/project-assets.local.json'
LOCK = threading.RLock()
AUDIO = {'.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff'}
TYPES = {'source': AUDIO, 'lead': AUDIO, 'harmony': AUDIO, 'accompaniment': AUDIO,
         'mix': AUDIO, 'svp': {'.svp'}, 'song': {'.song'}}
LABELS = dict(source='原歌曲', lead='分离主声', harmony='和声', accompaniment='伴奏', mix='成品混音', svp='SV 工程', song='Studio One 工程')


def project(ident):
    if ident not in {p['id'] for p in read_json(ROOT / 'config/projects.json')}:
        raise ValueError('请先导入对应的音乐工程')
    return read_json(ROOT / 'data/projects' / (ident + '.json'))['project']


def document():
    return read_json(STORE) if STORE.exists() else {'revision': 0, 'projects': {}}


def overrides(ident):
    with LOCK:
        return document()['projects'].get(ident, {})


def defaults(p):
    paths = {key: p.get('audio', {}).get(key, {}).get('original', '') for key in AUDIO_KEYS}
    paths['svp'] = next((f['original'] for f in p.get('files', []) if str(f.get('original', '')).lower().endswith('.svp')), p.get('working', ''))
    paths['song'] = p.get('dawCopy', {}).get('song', '')
    # Match saved build references, never song titles or guesses about filenames.
    builds = []
    svp = str(Path(paths['svp']).resolve()) if paths['svp'] else ''
    for file in (ROOT / 'projects/studio-one').glob('*/build.json'):
        try:
            b = read_json(file)
            if svp and svp in {str(Path(b[k]).resolve()) for k in ('svp', 'sourceSVP') if b.get(k)}:
                builds.append(b)
        except (OSError, ValueError, KeyError):
            continue
    if builds:
        build = max(builds, key=lambda b: b.get('createdAt', 0))
        paths['song'] = paths['song'] or build.get('song', '')
        paths['accompaniment'] = paths.get('accompaniment') or build.get('sourceAudio', '')
    return paths


AUDIO_KEYS = {'source', 'lead', 'harmony', 'accompaniment', 'mix'}


def status(ident):
    p = project(ident)
    with LOCK:
        doc = document()
        chosen = doc['projects'].get(ident, {})
        paths = {**defaults(p), **{k: v for k, v in chosen.items() if v}}
        items = {}
        for key, suffixes in TYPES.items():
            value = paths.get(key, '')
            exists = bool(value and Path(value).is_file() and Path(value).suffix.lower() in suffixes)
            items[key] = {'label': LABELS[key], 'path': value, 'exists': exists, 'custom': bool(chosen.get(key))}
        return {'id': ident, 'title': p['title'], 'revision': doc['revision'], 'assets': items}


def save(ident, body):
    project(ident)
    fields = body.get('assets')
    if not isinstance(fields, dict) or set(fields) - set(TYPES):
        raise ValueError('未知的工程素材类型')
    values = {key: str(daw.local(value, TYPES[key])) if daw.clean_path(value) else '' for key, value in fields.items()}
    with LOCK:
        doc = document()
        if body.get('revision') != doc['revision']:
            raise ValueError('工程素材已在其他窗口更新，请刷新后重试')
        if STORE.exists():
            save_json(STORE.with_name('project-assets.local.previous.json'), doc)
        doc['projects'][ident] = {**doc['projects'].get(ident, {}), **values}
        doc['revision'] += 1
        save_json(STORE, doc)
    return status(ident)


def open_asset(ident, body):
    key = body.get('asset')
    if key not in TYPES:
        raise ValueError('未知的工程素材类型')
    item = status(ident)['assets'][key]
    if not item['exists']:
        raise ValueError('素材尚未登记或已移动，请重新选择文件')
    path = daw.local(item['path'], TYPES[key])
    if body.get('action') == 'folder':
        return daw.open_local({'path': str(path), 'action': 'folder'})
    if body.get('action') != 'open' or key not in {'song', 'svp'}:
        raise ValueError('仅支持在原生软件中打开 SVP 或 Song')
    if key == 'song':
        return daw.open_local({'path': str(path), 'action': 'song'})
    if os.name != 'nt':
        raise ValueError('本机打开 SV 工程需要 Windows 文件关联')
    os.startfile(str(path))
    return {'opened': True, 'path': str(path)}
