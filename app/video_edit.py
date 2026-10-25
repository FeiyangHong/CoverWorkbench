"""Owned media library and a non-destructive, single-picture-track composition."""
from pathlib import Path
import copy
import json
import math
import re
import shutil
import subprocess
import threading
import uuid

from core import read_json, save_json, sha
import settings
import video_project as project

LOCK = threading.RLock()
EXTENSIONS = project.MEDIA | {'.png', '.jpg', '.jpeg', '.webp'}


def command(args, timeout=120):
    result = subprocess.run(list(map(str, args)), capture_output=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('媒体处理失败：' + result.stderr.decode('utf-8', errors='replace')[-700:])
    return result.stdout


def inspect(path):
    info = json.loads(command([settings.executable('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path]))
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    image = Path(path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}
    duration = 5. if image else float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('无法读取有效的素材时长')
    return {'kind': 'image' if image else 'video' if video else 'audio', 'duration': duration,
            'width': video.get('width', 0) if video else 0, 'height': video.get('height', 0) if video else 0}


def library(ident):
    path = project.folder(ident) / 'media-library.json'
    return read_json(path) if path.exists() else []


def asset(ident, key):
    return next((a for a in library(ident) if a['id'] == key), None)


def import_media(ident, body):
    source = project.local(body.get('path'), EXTENSIONS)
    before = sha(source)
    with LOCK:
        existing = next((a for a in library(ident) if a['sha256'] == before), None)
        if existing and Path(existing['path']).is_file():
            return existing
        metadata = inspect(source)
        root = project.folder(ident) / 'Media' / {'video': 'Video', 'image': 'Images', 'audio': 'Audio'}[metadata['kind']]
        root.mkdir(parents=True, exist_ok=True)
        label = re.sub(r'[^A-Za-z0-9 _.-]', '', source.stem).strip(' .')[:70] or metadata['kind'].title()
        if label.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}:
            label = 'Media ' + label
        dest = root / (label + source.suffix.lower())
        number = 2
        while dest.exists():
            dest = root / (label + f' v{number}' + source.suffix.lower()); number += 1
        shutil.copy2(source, dest)
        if sha(dest) != before or sha(source) != before:
            raise ValueError('素材在复制期间发生改变，请保存后重新导入')
        item = {'id': uuid.uuid4().hex, 'name': source.name, 'path': str(dest), 'source': str(source),
                'sha256': before, **metadata}
        if item['kind'] != 'audio':
            thumb = project.folder(ident) / 'Cache/Thumbnails' / (item['id'] + '.jpg')
            thumb.parent.mkdir(parents=True, exist_ok=True)
            try:
                command([settings.executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', dest, '-frames:v', '1', '-vf', 'scale=320:-2', '-y', thumb])
                item['thumbnail'] = str(thumb)
            except (ValueError, OSError, subprocess.SubprocessError):
                pass
        rows = library(ident); rows.append(item)
        save_json(project.folder(ident) / 'media-library.json', rows)
        return item


def media(ident, key, kind):
    item = asset(ident, key)
    field = {'original': 'path', 'thumb': 'thumbnail', 'proxy': 'proxy'}.get(kind)
    if not item or not field or not item.get(field) or not Path(item[field]).is_file():
        raise ValueError('媒体文件不存在，请重新导入或生成代理')
    return Path(item[field])


def proxy(ident, body):
    with LOCK:
        item = asset(ident, body.get('asset'))
        if not item or item['kind'] != 'video':
            raise ValueError('请选择视频素材')
        output = project.folder(ident) / 'Cache/Proxies' / (item['id'] + '.mp4')
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            partial = output.with_name(item['id'] + '.rendering.mp4')
            command([settings.executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', item['path'], '-an',
                     '-vf', 'scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1',
                     '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p',
                     '-movflags', '+faststart', '-y', partial], timeout=900)
            partial.replace(output)
        rows = library(ident)
        for row in rows:
            if row['id'] == item['id']: row['proxy'] = str(output)
        save_json(project.folder(ident) / 'media-library.json', rows)
        return next(row for row in rows if row['id'] == item['id'])


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('不支持的画面剪辑版本')
    out = {'version': 1, 'duration': project.number(value.get('duration'), .1, 21600, '成片时长'),
           'fps': value.get('fps', 25), 'width': 1920, 'height': 1080,
           'allowGaps': value.get('allowGaps') is True, 'clips': [], 'assets': []}
    if out['fps'] not in [24, 25, 30, 60]: raise ValueError('请选择 24、25、30 或 60 fps')
    rows = value.get('assets', [])
    if not isinstance(rows, list) or len(rows) > 300: raise ValueError('媒体库最多引用 300 个素材')
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(row.get('id', ''))) or row['id'] in ids:
            raise ValueError('无效或重复的媒体引用')
        if row.get('kind') not in ['video', 'image', 'audio']: raise ValueError('无效的媒体类型')
        # Missing files remain editable/relinkable; rendering does its own existence checks.
        path = Path(project.clean_path(row.get('path')))
        if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or path.suffix.lower() not in EXTENSIONS:
            raise ValueError('素材必须引用本机媒体文件')
        duration = project.number(row.get('duration'), .001, 86400, '素材时长')
        ids.add(row['id']); out['assets'].append({**row, 'path': str(path), 'duration': duration})
    clips = value.get('clips', [])
    if not isinstance(clips, list) or len(clips) > 200: raise ValueError('第一版最多使用 200 个画面片段')
    keys = set(); fps = out['fps']
    for row in clips:
        if not isinstance(row, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(row.get('id', ''))) or row['id'] in keys:
            raise ValueError('画面片段编号无效或重复')
        source = next((a for a in out['assets'] if a['id'] == row.get('asset')), None)
        if not source or source['kind'] == 'audio': raise ValueError('画面片段需要视频或图片素材')
        start = round(project.number(row.get('start'), 0, 21600, '片段位置') * fps) / fps
        length = round(project.number(row.get('duration'), 1/fps, 21600, '片段时长') * fps) / fps
        begin = project.number(row.get('in', 0), 0, 86400, '素材入点')
        if source['kind'] == 'video' and begin + length > source['duration'] + 1/fps + .001:
            raise ValueError('片段超出素材长度，请缩短出点')
        if start + length > out['duration'] + 1/fps + .001: raise ValueError('片段超出成片终点，请先增加成片时长')
        if row.get('fit', 'contain') not in ['contain', 'cover']: raise ValueError('请选择完整显示或裁切填满')
        keys.add(row['id']); out['clips'].append({'id': row['id'], 'asset': row['asset'], 'start': start,
            'duration': length, 'in': begin, 'fit': row.get('fit', 'contain'),
            'x': project.number(row.get('x', 0), -1, 1, '水平取景'), 'y': project.number(row.get('y', 0), -1, 1, '垂直取景')})
    out['clips'].sort(key=lambda c: c['start'])
    for left, right in zip(out['clips'], out['clips'][1:]):
        if right['start'] < left['start'] + left['duration'] - .5/fps:
            raise ValueError('画面片段重叠；第一版单轨请将片段接在前一段之后')
    return out


def gaps(comp):
    end = 0.; result = []
    for clip in sorted(comp['clips'], key=lambda c: c['start']):
        if clip['start'] > end + .5/comp['fps']: result.append([end, clip['start']])
        end = clip['start'] + clip['duration']
    if end < comp['duration'] - .5/comp['fps']: result.append([end, comp['duration']])
    return result


def sources(doc):
    comp = doc.get('composition')
    if not comp: return []
    used = {c['asset'] for c in comp['clips']}
    return [a['path'] for a in comp['assets'] if a['id'] in used]


def blockers(doc):
    if not doc.get('composition'): return []
    comp = validate(doc['composition']); result = []
    if not comp['clips']: result.append('请先把素材加入画面时间轴')
    if gaps(comp) and not comp['allowGaps']: result.append('画面仍有空白，请补齐，或明确选择允许黑底空白')
    if any(not Path(p).is_file() for p in sources(doc)): result.append('时间轴素材缺失，请在媒体库重新定位')
    return result


def edit_copy(ident, body):
    original = project.load(ident)
    if original['revision'] != body.get('revision'): raise ValueError('工程已更新，请重新读取后再创建副本')
    seed = {k: copy.deepcopy(v) for k, v in original.items() if k not in ['id', 'name', 'revision', 'updated', 'composition']}
    duration = original['composition']['duration'] if original.get('composition') else inspect(original['video'])['duration'] if original.get('video') else max(.1, inspect(original['audio'])['duration'] + original['audioOffset']) if original.get('audio') else 30
    seed['composition'] = copy.deepcopy(original['composition']) if original.get('composition') else {'version': 1, 'duration': duration, 'fps': 25, 'width': 1920, 'height': 1080, 'allowGaps': False, 'assets': [], 'clips': []}
    from workspaces import video_output
    parent = video_output(ident)
    target = project.create({'name': body.get('name') or (original['name'][:55] + ' Edit')}, internal=seed,
                            directory=parent.parent if parent else project.folder(ident).parent)
    if original.get('composition'):
        replacements = {}
        for old in original['composition']['assets']:
            replacements[old['id']] = import_media(target['id'], {'path': old['path']})
        target['composition']['assets'] = list({a['id']:a for a in replacements.values()}.values())
        for clip in target['composition']['clips']: clip['asset'] = replacements[clip['asset']]['id']
    elif original.get('video'):
        item = import_media(target['id'], {'path': original['video']})
        target['composition']['assets'] = [item]
        target['composition']['clips'] = [{'id': 'Clip1', 'asset': item['id'], 'start': 0, 'in': 0, 'duration': duration, 'fit': 'contain', 'x': 0, 'y': 0}]
    target['video'] = ''
    from video_workflow import timing
    target['timing'] = {**original.get('timing', {}), **timing(target, original.get('timing', {}).get('clock', 'video'), 'edit-copy')}
    save_json(project.folder(target['id']) / 'project.json', target)
    return target


def build_picture(job, start, end, execute, update):
    """Render only the requested interval. Segment boundaries share one output-frame grid."""
    comp = validate(job['snapshot']['composition']); fps = comp['fps']; folder = Path(job['folder'])
    first, last = round(start*fps), round(end*fps)
    if last <= first: raise ValueError('预览区间短于一帧')
    segments = []; cursor = 0
    for clip in comp['clips']:
        a, b = round(clip['start']*fps), round((clip['start']+clip['duration'])*fps)
        if a > cursor: segments.append((cursor, a, None))
        segments.append((a, b, clip)); cursor = b
    if cursor < round(comp['duration']*fps): segments.append((cursor, round(comp['duration']*fps), None))
    segments = [(max(a, first), min(b, last), clip) for a,b,clip in segments if min(b,last)>max(a,first)]
    entries = []
    for index, (a, b, clip) in enumerate(segments):
        update(job, stage=f'拼接画面 {index+1} / {len(segments)}', progress=5+int(50*index/max(1,len(segments))))
        args = []
        if clip:
            source = next(x for x in comp['assets'] if x['id'] == clip['asset'])
            if source['kind'] == 'image': args += ['-loop', '1', '-framerate', str(fps), '-i', source['path']]
            else: args += ['-ss', str(clip['in'] + a/fps - clip['start']), '-i', source['path']]
            normal = "scale=w='trunc(iw*sar/2)*2':h='trunc(ih/2)*2',setsar=1,"
            if clip['fit'] == 'cover':
                fit = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)*{(clip['x']+1)/2}:(ih-oh)*{(clip['y']+1)/2}"
            else: fit = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)*{(clip['x']+1)/2}:(oh-ih)*{(clip['y']+1)/2}:black"
            filters = normal + fit
        else:
            args += ['-f', 'lavfi', '-i', f'color=c=black:s=1920x1080:r={fps}']; filters = 'setsar=1'
        name = f'Picture {index+1:03}.mkv'; output = folder/name
        # Lossless intermediates avoid an extra lossy encode before final export.
        execute(job, args + ['-an', '-vf', filters+f',tpad=stop_mode=clone:stop_duration={1/fps},fps={fps},setpts=PTS-STARTPTS', '-frames:v', str(b-a),
                 '-c:v', 'ffv1', '-level', '3', '-threads', '2', '-pix_fmt', 'yuv420p', output], stage='拼接画面片段')
        entries.append("file '" + name + "'")
    sequence = folder/'picture-sequence.txt'; sequence.write_text('\n'.join(entries), encoding='utf-8')
    output = folder/'picture.mkv'
    execute(job, ['-f', 'concat', '-safe', '0', '-i', sequence, '-c', 'copy', output], stage='组装画面时间轴')
    return output
