"""Private music/video associations and explicit, snapshot-based material transfer."""
from pathlib import Path
import copy
import hashlib
import json
import re
import threading
import time

from core import ROOT, read_json, save_json
import video_project as video
from video_workflow import timing

STORE = ROOT / 'config/video-links.local.json'
LOCK = threading.RLock()
AUDIO = {'.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def registry():
    return read_json(ROOT / 'config/projects.json')


def music(ident):
    if ident not in {p['id'] for p in registry()}:
        raise ValueError('音乐工程不存在，请先在音乐工作台导入 SVP')
    return read_json(ROOT / 'data/projects' / (ident + '.json'))['project']


def links():
    data = read_json(STORE) if STORE.exists() else {'version': 1, 'links': {}}
    if data.get('version') != 1 or not isinstance(data.get('links'), dict):
        raise ValueError('视频关联配置格式无效，请保留文件并检查配置')
    if any(not isinstance(v, dict) or not isinstance(v.get('videoId'), str) for v in data['links'].values()):
        raise ValueError('视频关联记录无效，请保留文件并检查配置')
    return data['links']


def persist(rows):
    if STORE.exists():
        save_json(STORE.with_name('video-links.local.previous.json'), read_json(STORE))
    save_json(STORE, {'version': 1, 'links': rows})


def audio_info(path, label):
    try:
        p = video.local(path, AUDIO)
        stat = p.stat()
        return {'path': str(p), 'name': p.name, 'label': label,
                'signature': digest([str(p), stat.st_size, stat.st_mtime_ns])}
    except (OSError, ValueError, TypeError):
        return None


def caption_rows(rows):
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError('字幕应为最多 5000 行的列表')
    result = []
    for i, row in enumerate(rows):
        out = {'id': f'L{i+1:04}', 'start': video.stamp(row['start']), 'end': video.stamp(row['end'])}
        if out['end'] <= out['start']:
            raise ValueError('音乐侧存在结束早于开始的字幕，请先修正')
        for key in ('original', 'translation'):
            text = row.get(key, '')
            if not isinstance(text, str) or len(text) > 2000 or '\x00' in text:
                raise ValueError('音乐侧字幕文字无效或过长')
            out[key] = text
        if out['original'] or out['translation']:
            result.append(out)
    return result


def materials(ident, override=None):
    p = music(ident)
    pilot = Path(p['pilot'])
    candidates = []
    assets = ROOT / 'config/project-assets.local.json'
    registered_mix = read_json(assets).get('projects', {}).get(ident, {}).get('mix') if assets.exists() else None
    item = audio_info(registered_mix, '项目素材中登记的成品混音') if registered_mix else None
    if item:
        candidates.append(item)
    # Use explicit, completed delivery records, never filename guesses or separated vocals.
    deliveries = []
    for path in (ROOT / 'runtime/workflow').glob('*.json'):
        try:
            job = read_json(path)
            if job.get('pid') == ident and job.get('kind') == 'delivery' and job.get('status') == 'completed':
                deliveries.append(job)
        except (OSError, ValueError):
            continue
    for job in sorted(deliveries, key=lambda j: j.get('createdAt', 0), reverse=True)[:10]:
        item = audio_info(job.get('input', {}).get('audio'), '已完成交付的混音')
        if item and not any(c['path'] == item['path'] for c in candidates):
            candidates.append(item)
    registered = p.get('audio', {}).get('mix', {}).get('original')
    item = audio_info(registered, '音乐工程登记的成品混音') if registered else None
    if item and not any(c['path'] == item['path'] for c in candidates):
        candidates.append(item)
    selected = links().get(ident, {}).get('audioPath', '') if override is None else override
    chosen = None
    if selected:
        chosen = audio_info(selected, '本曲手动选择的混音')
        if not chosen and override is not None:
            raise ValueError('所选混音不存在或格式不支持，请重新选择')
        if chosen and not any(c['path'] == chosen['path'] for c in candidates):
            candidates.insert(0, chosen)
    else:
        chosen = candidates[0] if candidates else None
    review = pilot / 'analysis/review.json'
    state = read_json(review) if review.exists() else {}
    raw = state.get('subtitles', [])
    label = '音乐工程已保存字幕'
    package = pilot / 'analysis/lyrics-current.json'
    if not raw and package.exists():
        source = read_json(package)
        rows = source.get('rows', [])
        # Untimed lyrics are not converted into invented timestamps.
        if rows and all(isinstance(r.get('start'), (float, int)) and isinstance(r.get('end'), (float, int)) for r in rows):
            raw = rows
            label = '歌词素材 LRC 时间草稿（待校对）'
    issue = ''
    try:
        cues = caption_rows(raw)
    except (ValueError, KeyError, TypeError) as e:
        cues = []
        issue = str(e)
    subtitle = {'label': label, 'count': len(cues), 'original': sum(bool(r['original'].strip()) for r in cues),
                'translation': sum(bool(r['translation'].strip()) for r in cues), 'issue': issue,
                'signature': digest(cues) if cues else None}
    signature = digest([chosen['signature'] if chosen else None, subtitle['signature'], label, issue])
    return {'music': {'id': ident, 'title': p['title'], 'artist': p.get('artist', '')}, 'audio': chosen,
            'audioCandidates': candidates, 'audioSelection': str(chosen['path']) if selected and chosen else str(selected or ''),
            'captions': subtitle, 'signature': signature, '_cues': cues}


def public_materials(source):
    return {k: v for k, v in source.items() if k != '_cues'}


def overview(ident, override=None):
    with LOCK:
        rows = links()
        source = materials(ident, override)
        link = rows.get(ident)
        target = None
        if link:
            try:
                d = video.load(link['videoId'])
                target = {'id': d['id'], 'name': d['name'], 'revision': d['revision'], 'audio': d['audio'],
                          'cueCount': len(d['cues']), 'audioOffset': d['audioOffset']}
            except (OSError, ValueError, KeyError):
                pass
        title = re.sub(r'[^A-Za-z0-9 _.-]+', ' ', source['music']['title']).strip(' ._-') or ident
        names = {p['id']: p['title'] for p in registry()}
        videos = []
        for item in video.listing():
            owner = next((pid for pid, r in rows.items() if r['videoId'] == item['id']), None)
            videos.append({**item, 'musicId': owner, 'musicTitle': names.get(owner, owner)})
        changed = {'audio': bool(link and 'audioSignature' in link and link['audioSignature'] != (source['audio']['signature'] if source['audio'] else None)),
                   'captions': bool(link and 'captionSignature' in link and link['captionSignature'] != source['captions']['signature'])}
        return {**public_materials(source), 'linked': target, 'linkedId': link['videoId'] if link else None, 'missingLink': bool(link and not target),
                'videos': videos, 'changed': changed, 'defaultName': title[:54] + ' Video',
                'captionCompatible': bool(target and source['audio'] and target['audio'] and Path(target['audio']).resolve() == Path(source['audio']['path']).resolve())}


def for_video(ident):
    video.folder(ident)
    with LOCK:
        choices = [{'id': p['id'], 'title': p['title'], 'artist': p.get('artist', '')} for p in registry()]
        owner = next((pid for pid, item in links().items() if item['videoId'] == ident), None)
        return {'videoId': ident, 'music': next((p for p in choices if p['id'] == owner), None), 'choices': choices}


def checked_source(ident, body):
    source = materials(ident, body.get('audioPath'))
    if body.get('sourceSignature') != source['signature']:
        raise ValueError('音乐侧素材已更新，请刷新关联窗口后再操作')
    return source


def perform(ident, body):
    with LOCK, video.LOCK:
        action = body.get('action')
        if action == 'preview':
            return overview(ident, body.get('audioPath'))
        music(ident)
        rows = links()
        link = rows.get(ident)
        if action in {'bind', 'unlink'}:
            if body.get('expectedVideoId') != (link['videoId'] if link else None):
                raise ValueError('关联已在其他窗口变化，请刷新后重试')
            if action == 'unlink':
                rows.pop(ident, None)
                persist(rows)
                return {'videoId': None}
            target = video.load(body.get('videoId'))
            if any(pid != ident and r['videoId'] == target['id'] for pid, r in rows.items()):
                raise ValueError('这个视频已关联另一首歌，请先解除原关联')
            if link and link['videoId'] == target['id']:
                return {'videoId': target['id']}
            rows[ident] = {'videoId': target['id'], 'updatedAt': time.time()}
            persist(rows)
            return {'videoId': target['id']}
        if action == 'create':
            if link:
                try:
                    video.folder(link['videoId'])
                    return {'videoId': link['videoId'], 'existing': True}
                except (OSError, ValueError):
                    pass
            source = checked_source(ident, body)
            seed = {'audio': source['audio']['path'] if source['audio'] else '', 'cues': copy.deepcopy(source['_cues'])}
            clock = {**seed, 'video': '', 'audioOffset': 0}
            seed['timing'] = timing(clock, 'audio' if seed['audio'] else 'unknown', 'music-project')
            seed['musicImport'] = {'musicId': ident, 'captionSource': source['captions']['label']}
            target = video.create({'name': body.get('name') or overview(ident)['defaultName']}, internal=seed)
            rows[ident] = {'videoId': target['id'], 'audioSignature': source['audio']['signature'] if source['audio'] else None,
                           'captionSignature': source['captions']['signature'], 'audioPath': source['audioSelection'], 'updatedAt': time.time()}
            persist(rows)
            return {'videoId': target['id'], 'existing': False, 'missing': [k for k, ok in [('混音', bool(seed['audio'])), ('字幕', bool(seed['cues']))] if not ok]}
        if action == 'update':
            if not link or body.get('videoId') != link['videoId']:
                raise ValueError('视频关联已变化，请刷新后重试')
            target = video.load(link['videoId'])
            if target['revision'] != body.get('revision'):
                raise ValueError('视频工程已更新，请保存草稿并刷新关联窗口')
            source = checked_source(ident, body)
            audio = body.get('audio') is True
            captions = body.get('captions') is True
            if not audio and not captions:
                raise ValueError('请选择需要带入的混音或字幕')
            if audio and not source['audio']:
                raise ValueError('音乐工程尚无可用的成品混音')
            if captions and not source['_cues']:
                raise ValueError(source['captions']['issue'] or '音乐工程尚无有效时间字幕')
            if captions and not audio and (not source['audio'] or not target['audio'] or Path(target['audio']).resolve() != Path(source['audio']['path']).resolve()):
                raise ValueError('当前视频音轨与音乐侧混音不同，请同时带入混音，避免套用错误的字幕时间基准')
            if audio:
                target['audio'] = source['audio']['path']
            if captions:
                target['cues'] = copy.deepcopy(source['_cues'])
                for row in target['cues']:
                    video.shift_caption(row, target['audioOffset'])
                target['subtitleShift'] = 0
                ledger = timing(target, 'audio', 'music-project')
            else:
                # Keep all existing video-time edits when replacing just the audio.
                known = target.get('timing', {}).get('clock') in {'audio', 'video'}
                ledger = timing(target, 'video' if known else 'unknown', 'music-audio-update')
            video.save(target['id'], target, internal={'timing': ledger})
            if audio:
                link['audioSignature'] = source['audio']['signature']
                link['audioPath'] = source['audioSelection']
            if captions:
                link['captionSignature'] = source['captions']['signature']
            link['updatedAt'] = time.time()
            persist(rows)
            return {'videoId': target['id']}
        raise ValueError('未知的音乐与视频关联操作')
