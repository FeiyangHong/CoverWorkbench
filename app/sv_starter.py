"""Create a new, unvoiced SV session with explicitly selected audio reference tracks."""
from pathlib import Path
import math
import shutil
import threading
import uuid

from core import save_json, sha
import daw
import project_assets
import workspaces

LOCK = threading.Lock()
ROLES = {'source': 'Original', 'vocals': 'Vocals', 'lead': 'Lead', 'harmony': 'Harmony', 'accompaniment': 'Instrumental'}


def track(label, index, engine, audio=None, duration=0, muted=False):
    group = str(uuid.uuid4())
    reference = {'groupID': group, 'blickAbsoluteBegin': 0, 'blickAbsoluteEnd': -1,
                 'blickOffset': 0, 'pitchOffset': 0, 'isInstrumental': bool(audio),
                 'database': {'name': '', 'language': '', 'phoneset': '', 'languageOverride': '',
                              'phonesetOverride': '', 'backendType': '', 'version': '-2'},
                 'dictionary': '', 'voice': {'vocalModeInherited': True, 'vocalModePreset': '', 'vocalModeParams': {}}}
    if engine == 'sv2':
        reference.update(uuid=str(uuid.uuid4()), mute=False, voicePresetName='',
                         takes={'activeTakeId': 0, 'takes': [{'id': 0, 'seedDuration': 0, 'seedPitch': 0, 'seedTimbre': 0, 'liked': False}]})
    else:
        reference.update(systemPitchDelta={'mode': 'cubic', 'points': []},
                         pitchTakes={'activeTakeId': 0, 'takes': [{'id': 0, 'expr': 0., 'liked': False}]},
                         timbreTakes={'activeTakeId': 0, 'takes': [{'id': 0, 'expr': 0., 'liked': False}]})
    if audio:
        reference['audio'] = {'filename': str(audio), 'duration': duration}
    return {'name': label, 'dispColor': 'ff8c71ce', 'dispOrder': index, 'renderEnabled': not bool(audio),
            'mixer': {'gainDecibel': 0., 'pan': 0., 'mute': muted, 'solo': False, 'display': True},
            'mainGroup': {'name': 'main', 'uuid': group, 'parameters': {
                key: {'mode': 'cubic', 'points': []} for key in
                ['pitchDelta', 'vibratoEnv', 'loudness', 'tension', 'breathiness', 'voicing', 'gender', 'toneShift']},
                'vocalModes': {}, 'notes': []}, 'mainRef': reference, 'groups': []}


def create(ident, body):
    engine = body.get('engine', 'sv2')
    if engine not in ['sv1', 'sv2']:
        raise ValueError('请选择 SV1 或 SV2')
    roles = body.get('roles', [])
    if not isinstance(roles, list) or not roles or any(r not in ROLES for r in roles) or len(set(roles)) != len(roles):
        raise ValueError('请选择至少一种音频素材，每种只选一次')
    bpm = float(body.get('bpm', 120))
    if not math.isfinite(bpm) or not 20 <= bpm <= 400:
        raise ValueError('BPM 应在 20–400 之间；不确定时可在 SV 中设置')
    p = project_assets.project(ident)
    current = project_assets.status(ident)['assets']
    sources = []
    for role in roles:
        source = daw.local(current[role]['path'], {'.wav', '.flac'})
        sources.append((role, source, daw.media_info(source)))
    with LOCK:
        parent = workspaces.outputs(p) / 'working' / ('sv2' if engine == 'sv2' else 'sv')
        number = 1
        while True:
            folder = parent / f'Session {number:02}'
            try:
                folder.mkdir()
                break
            except FileExistsError:
                number += 1
        (folder / 'Media').mkdir()
        records, tracks = [], []
        for role, source, info in sources:
            dest = folder / 'Media' / (ROLES[role] + source.suffix.lower())
            before = sha(source)
            shutil.copy2(source, dest)
            if sha(dest) != before or sha(source) != before:
                raise ValueError('音频在复制期间发生改变，请保存后重试；原文件未改动')
            # Keep references muted to avoid adding together multiple versions of the same voice.
            tracks.append(track(ROLES[role], len(tracks), engine, dest, info['duration'], muted=True))
            records.append({'role': role, 'source': str(source), 'copy': str(dest), 'sha256': before})
        tracks.append(track('Lead Vocal', len(tracks), engine))
        doc = {'version': 196 if engine == 'sv2' else 153,
               'time': {'tempo': [{'position': 0, 'bpm': bpm}], 'meter': [{'index': 0, 'numerator': 4, 'denominator': 4}]},
               'library': [], 'tracks': tracks, 'renderConfig': {'destination': str(workspaces.root(p) / 'exports/audio'),
               'filename': 'Vocal', 'numChannels': 1, 'aspirationFormat': 'noAspiration', 'bitDepth': 24,
               'sampleRate': 48000, 'exportMixDown': False, 'exportPitch': False}}
        if engine == 'sv2':
            doc['uuid'] = str(uuid.uuid4())
        output = folder / 'project.svp'
        save_json(output, doc)
        skipped = project_assets.register_generated(ident, {'svp': str(output)}, {'svp': current['svp']['path']}) if body.get('register') is True else []
        save_json(folder / 'session.json', {'engine': engine, 'bpm': bpm, 'sources': records,
                 'svp': str(output), 'registered': body.get('register') is True and not skipped})
    return {'svp': str(output), 'folder': str(folder), 'engine': engine, 'skipped': skipped,
            'message': '新 SVP 已生成。参考音频默认静音；在 SV 中选择人声轨提取音符，并选择自己的声库。'}
