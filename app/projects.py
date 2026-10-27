"""Import a saved SVP into an isolated workbench project; originals stay read-only."""
from pathlib import Path
import copy
import re
import shutil
import threading
import time
import uuid
from core import ROOT, read_json, save_json, sha, parse_svp, audit
from daw import local, media_info
import workspaces
import asset_storage

LOCK = threading.Lock()


def create(body):
    source = local(body.get('svp'), {'.svp'}) if body.get('svp', '').strip() else None
    audio_source = local(body.get('source'), {'.wav', '.flac'}) if not source and body.get('source', '').strip() else None
    original_hash = sha(source) if source else None
    raw = read_json(source) if source else {'version': 147, 'time': {'tempo': [{'position': 0, 'bpm': 120}],
          'meter': [{'index': 0, 'numerator': 4, 'denominator': 4}]}, 'tracks': [], 'library': []}
    parsed = parse_svp(source) if source else {'duration': 0, 'notes': [], 'tracks': []}
    if source and not parsed['notes']:
        raise ValueError('The SVP must contain at least one note')
    if source:
        for path in asset_storage.sv_references(raw, source.parent):
            if not path.is_file():
                raise ValueError('SVP 参考音频缺失：' + str(path))
    language = body.get('language', 'ja')
    if language not in ['ja', 'zh', 'en']:
        raise ValueError('Unsupported language')
    title = str(body.get('title', '')).strip() or ((source or audio_source).stem if source or audio_source else '')
    if not title:
        raise ValueError('请填写歌曲名称，或选择原歌曲 / SVP')
    artist = str(body.get('artist', '')).strip()
    if len(artist) > 150:
        raise ValueError('Artist is too long')
    # Validate all external files before creating the destination.
    media = []
    if audio_source:
        media.append(('source', audio_source, media_info(audio_source)))
    for role in ['lead', 'vocals', 'mix']:
        if body.get(role):
            path = local(body[role], {'.wav', '.flac', '.mp3', '.aif', '.aiff', '.m4a'})
            media.append((role, path, media_info(path)))
    with LOCK:
        ident = 'song-' + uuid.uuid4().hex[:12]
        pilot = workspaces.allocate({'id': ident, 'title': title, 'artist': artist}, body.get('folderName') or None)
        for folder in ['snapshots/sv', 'working/sv', 'working/sv2', 'working/lyrics', 'media', 'analysis',
                       'exports/svp', 'exports/subtitles', 'exports/audio', 'exports/reports', 'exports/lyrics']:
            (pilot / folder).mkdir(parents=True, exist_ok=True)
        snapshot = pilot / 'snapshots/sv/source.svp'
        if source:
            shutil.copy2(source, snapshot)
            if sha(source) != original_hash or sha(snapshot) != original_hash:
                raise ValueError('Source changed during import; retry after saving in SV')
        else:
            save_json(snapshot, raw)
        working = pilot / 'working/sv/project.svp'
        doc = copy.deepcopy(raw)
        doc.setdefault('renderConfig', {})['destination'] = str(pilot / 'exports/audio')
        with asset_storage.Import(pilot) as transfer:
            if source:
                transfer.remember(source)
                doc = transfer.sv_document(source, doc, working.parent / 'Media')
            save_json(working, doc)
            audio = {}
            for role, path, info in media:
                path = transfer.asset(path, role)
                audio[role] = {'original': str(path), 'preview': str(path), 'duration': info['duration'],
                               'format': {'sample_rate': info['rate'], 'channels': info['channels'], 'bits_per_raw_sample': info['bits']}}
            transfer.check()
            if source and sha(source) != original_hash:
                raise ValueError('Source changed during import; retry after saving in SV')
            transfer.done = True
        project = {'id': ident, 'title': title, 'artist': artist, 'source': str((source or audio_source).parent) if source or audio_source else str(pilot / 'source'), 'pilot': str(pilot),
                   'working': str(working), 'managedSVP': str(working), 'sv2Working': str(pilot / 'working/sv2/project.svp'), 'snapshot': str(snapshot), 'language': language,
                   'files': [{'original': str(source), 'snapshot': str(snapshot), 'sha256': original_hash, 'snapshot_sha256': original_hash}] if source else [],
                   'audio': audio, 'duration': max([parsed['duration']] + [i[2]['duration'] for i in media]),
                   'metrics': {}, 'versions': ['source.svp'], 'selectedVersion': 'source.svp', 'waveform': [],
                   'lyricsRaw': '', 'subtitleSource': None, 'comparison': {}, 'builtAt': time.strftime('%Y-%m-%d %H:%M:%S')}
        save_json(ROOT / 'data/projects' / (ident + '.json'), {'project': project, 'parsed': parse_svp(working), 'flags': audit(parsed)})
        save_json(pilot / 'analysis/review.json', {'decisions': {}, 'edits': {}, 'subtitles': [], 'subtitleMode': 'none'})
        rows = read_json(ROOT / 'config/projects.json')
        rows.append({k: project[k] for k in ['id', 'title', 'artist', 'language', 'duration', 'pilot', 'selectedVersion']})
        save_json(ROOT / 'config/projects.json', rows)
        return project
