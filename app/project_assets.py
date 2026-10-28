"""Explicit per-song handoff files. Opening or registering never edits creative files."""
from pathlib import Path
import os
import threading

from core import ROOT, read_json, save_json
import daw
import workspaces
import asset_storage
import mix_sources

STORE = ROOT / 'config/project-assets.local.json'
LOCK = threading.RLock()
AUDIO = {'.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff'}
TYPES = {'source': AUDIO, 'vocals': AUDIO, 'lead': AUDIO, 'harmony': AUDIO, 'accompaniment': AUDIO,
         'mix': AUDIO, 'svp': {'.svp'}, 'song': {'.song'}}
LABELS = dict(source='原歌曲', vocals='完整人声（含和声）', lead='分离主声', harmony='和声', accompaniment='伴奏', mix='成品混音', svp='SV 工程', song='Studio One 工程')


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
    paths['svp'] = p.get('managedSVP') or next((f['original'] for f in p.get('files', []) if str(f.get('original', '')).lower().endswith('.svp')), p.get('working', ''))
    paths['song'] = p.get('dawCopy', {}).get('song', '')
    # Match source SVPs and the build index, including per-song/external output roots.
    builds = mix_sources.builds(p,ROOT)
    if builds:
        build = builds[0]
        paths['song'] = paths['song'] or build.get('song', '')
        paths['accompaniment'] = paths.get('accompaniment') or build.get('sourceAudio', '')
    candidate = mix_sources.preferred(mix_sources.collect(p,ROOT))
    if candidate: paths['mix'] = candidate['path']
    return paths


AUDIO_KEYS = {'source', 'vocals', 'lead', 'harmony', 'accompaniment', 'mix'}


def status(ident):
    p = project(ident)
    with LOCK:
        doc = document()
        chosen = doc['projects'].get(ident, {})
        paths = {**defaults(p), **{k: v for k, v in chosen.items() if v}}
        items = {}
        workspace = workspaces.root(p).resolve()
        for key, suffixes in TYPES.items():
            value = paths.get(key, '')
            exists = bool(value and Path(value).is_file() and Path(value).suffix.lower() in suffixes)
            items[key] = {'label': LABELS[key], 'path': value, 'exists': exists, 'custom': bool(chosen.get(key)),
                          'managed': bool(value and Path(value).resolve().is_relative_to(workspace))}
        return {'id': ident, 'title': p['title'], 'revision': doc['revision'], 'assets': items,
                'workspace': str(workspace), 'copyWorkspace': str(workspaces.proposed(p))}


def save(ident, body):
    p = project(ident)
    fields = body.get('assets')
    if not isinstance(fields, dict) or set(fields) - set(TYPES):
        raise ValueError('未知的工程素材类型')
    mode = body.get('storageMode', 'copy')
    if mode not in ('copy', 'reference'):
        raise ValueError('请选择复制到项目或仅引用原路径')
    values = {key: str(daw.local(value, TYPES[key])) if daw.clean_path(value) else '' for key, value in fields.items()}
    with LOCK:
        doc = document()
        if body.get('revision') != doc['revision']:
            raise ValueError('工程素材已在其他窗口更新，请刷新后重试')
        # Allocate only for an actual copy, never when merely browsing or referencing.
        root = workspaces.outputs(p) if mode == 'copy' and any(values.values()) else workspaces.root(p)
        with asset_storage.Import(root) as transfer:
            if mode == 'copy':
                values = {key: str(transfer.asset(Path(value), key)) if value else '' for key, value in values.items()}
                transfer.check()
            if STORE.exists():
                save_json(STORE.with_name('project-assets.local.previous.json'), doc)
            doc['projects'][ident] = {**doc['projects'].get(ident, {}), **values}
            doc['revision'] += 1
            save_json(STORE, doc)
            transfer.done = True
            result = status(ident)
            result['storage'] = {'mode': mode, 'copied': transfer.copied, 'reused': transfer.reused}
            return result


def register_generated(ident, values, baseline):
    """Commit completed outputs together; preserve any path edited during the job."""
    project(ident)
    validated = {k: str(daw.local(v, TYPES[k])) for k, v in values.items()}
    with LOCK:
        current = status(ident)['assets']
        skipped = [k for k in validated if current[k]['path'] != baseline.get(k, '')]
        doc = document()
        chosen = doc['projects'].setdefault(ident, {})
        for key, value in validated.items():
            if key not in skipped:
                chosen[key] = value
        if STORE.exists():
            save_json(STORE.with_name('project-assets.local.previous.json'), document())
        doc['revision'] += 1
        save_json(STORE, doc)
    return skipped


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
