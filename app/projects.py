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

LOCK = threading.Lock()


def create(body):
    source = local(body.get('svp'), {'.svp'})
    original_hash = sha(source)
    raw = read_json(source)
    parsed = parse_svp(source)
    if not parsed['notes']:
        raise ValueError('The SVP must contain at least one note')
    language = body.get('language', 'ja')
    if language not in ['ja', 'zh', 'en']:
        raise ValueError('Unsupported language')
    title = str(body.get('title', '')).strip() or source.stem
    artist = str(body.get('artist', '')).strip()
    if len(title) > 150 or len(artist) > 150:
        raise ValueError('Title / artist is too long')
    # Validate all external files before creating the destination.
    media = []
    for role in ['lead', 'vocals', 'mix']:
        if body.get(role):
            path = local(body[role], {'.wav', '.flac', '.mp3', '.aif', '.aiff', '.m4a'})
            media.append((role, path, media_info(path)))
    with LOCK:
        ident = 'song-' + uuid.uuid4().hex[:12]
        pilot = ROOT / 'projects' / ident
        pilot.mkdir(exist_ok=False)
        for folder in ['snapshots/sv', 'working/sv', 'working/sv2', 'working/lyrics', 'media', 'analysis',
                       'exports/svp', 'exports/subtitles', 'exports/audio', 'exports/reports', 'exports/lyrics']:
            (pilot / folder).mkdir(parents=True, exist_ok=True)
        snapshot = pilot / 'snapshots/sv/source.svp'
        shutil.copy2(source, snapshot)
        if sha(source) != original_hash or sha(snapshot) != original_hash:
            raise ValueError('Source changed during import; retry after saving in SV')
        working = pilot / 'working/sv/project.svp'
        doc = copy.deepcopy(raw)
        doc.setdefault('renderConfig', {})['destination'] = str(pilot / 'exports/audio')
        def resolve_media(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['filename', 'filePath', 'path'] and isinstance(value, str) and value.lower().endswith(('.wav', '.flac', '.mp3')):
                        obj[key] = str((source.parent / value).resolve())
                    else:
                        resolve_media(value)
            elif isinstance(obj, list):
                for value in obj:
                    resolve_media(value)
        resolve_media(doc)
        save_json(working, doc)
        audio = {}
        for role, path, info in media:
            audio[role] = {'original': str(path), 'preview': str(path), 'duration': info['duration'],
                           'format': {'sample_rate': info['rate'], 'channels': info['channels'], 'bits_per_raw_sample': info['bits']}}
        project = {'id': ident, 'title': title, 'artist': artist, 'source': str(source.parent), 'pilot': str(pilot),
                   'working': str(working), 'snapshot': str(snapshot), 'language': language,
                   'files': [{'original': str(source), 'snapshot': str(snapshot), 'sha256': original_hash, 'snapshot_sha256': original_hash}],
                   'audio': audio, 'duration': max([parsed['duration']] + [i[2]['duration'] for i in media]),
                   'metrics': {}, 'versions': ['source.svp'], 'selectedVersion': 'source.svp', 'waveform': [],
                   'lyricsRaw': '', 'subtitleSource': None, 'comparison': {}, 'builtAt': time.strftime('%Y-%m-%d %H:%M:%S')}
        save_json(ROOT / 'data/projects' / (ident + '.json'), {'project': project, 'parsed': parse_svp(working), 'flags': audit(parsed)})
        save_json(pilot / 'analysis/review.json', {'decisions': {}, 'edits': {}, 'subtitles': [], 'subtitleMode': 'none'})
        rows = read_json(ROOT / 'config/projects.json')
        rows.append({k: project[k] for k in ['id', 'title', 'artist', 'language', 'duration', 'pilot', 'selectedVersion']})
        save_json(ROOT / 'config/projects.json', rows)
        return project
