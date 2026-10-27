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
import media_names

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
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    return {'kind': 'image' if image else 'video' if video else 'audio', 'duration': duration,
            'hasAudio': audio is not None, 'audioCodec': audio.get('codec_name', '') if audio else '',
            'videoCodec': video.get('codec_name', '') if video else '',
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
        owned=any(source.is_relative_to((base/'Media').resolve()) for base in project.output_locations(ident))
        # An already-owned titled file gets its own library entry; keep older aliases/clips intact.
        existing = next((a for a in library(ident) if a['sha256'] == before and Path(a['path']).is_file()
                         and (not owned or Path(a['path']).resolve()==source)), None)
        if existing:
            return existing
        metadata = inspect(source)
        root = project.folder(ident) / 'Media' / {'video': 'Video', 'image': 'Images', 'audio': 'Audio'}[metadata['kind']]
        root.mkdir(parents=True, exist_ok=True)
        dest=source
        if not owned:
            number=1
            while True:
                dest=root/media_names.filename(source.stem,source.suffix,number)
                try:stream=dest.open('xb')
                except FileExistsError:number+=1;continue
                try:
                    with stream,source.open('rb') as original:shutil.copyfileobj(original,stream)
                    break
                except BaseException:
                    dest.unlink(missing_ok=True);raise
        if sha(dest) != before or sha(source) != before:
            if not owned:dest.unlink(missing_ok=True)
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
        output = project.folder(ident) / 'Cache/Proxies' / (item['id'] + '-av.mp4')
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            partial = output.with_name(item['id'] + '.rendering.mp4')
            command([settings.executable('ffmpeg'), '-v', 'error', '-nostdin', '-i', item['path'], '-map', '0:v:0', '-map', '0:a:0?',
                     '-vf', 'scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1',
                     '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p',
                     '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-y', partial], timeout=900)
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
        if row.get('transition') is not None:
            tr = row['transition']
            if not isinstance(tr, dict) or tr.get('type') not in ['dissolve', 'fade']:
                raise ValueError('请选择交叉溶解或淡出淡入转场')
            frames = round(project.number(tr.get('duration'), 2/fps, 10, '转场时长') * fps / 2) * 2
            out['clips'][-1]['transition'] = {'type': tr['type'], 'duration': frames/fps, 'from': str(tr.get('from', ''))}
    out['clips'].sort(key=lambda c: c['start'])
    for left, right in zip(out['clips'], out['clips'][1:]):
        if right['start'] < left['start'] + left['duration'] - .5/fps:
            raise ValueError('画面片段重叠；第一版单轨请将片段接在前一段之后')
    for i, right in enumerate(out['clips']):
        tr = right.get('transition')
        if not tr: continue
        left = out['clips'][i-1] if i else None
        if not left or tr['from'] != left['id'] or abs(right['start']-left['start']-left['duration']) > .5/fps:
            raise ValueError('转场需要两个相邻且无空隙的画面片段')
        if tr['duration'] > min(left['duration'], right['duration']) + .001:
            raise ValueError('转场时长不能超过相邻较短片段的时长')
    if value.get('fades') is not None:
        fades = value['fades']
        if not isinstance(fades, dict): raise ValueError('片头片尾淡化设置无效')
        normalized = {}
        for key in ['in', 'out']:
            seconds = project.number(fades.get(key, 0), 0, 10, '画面淡入淡出时长')
            frames = round(seconds*fps)
            if seconds and frames < 2: raise ValueError('画面淡入淡出至少需要两帧')
            normalized[key] = frames/fps
        if sum(round(t*fps) for t in normalized.values()) > round(out['duration']*fps):
            raise ValueError('片头淡入与片尾淡出总时长不能超过成片时长')
        if any(normalized.values()): out['fades'] = normalized
    return out


def transitions(comp):
    result = []
    for i, right in enumerate(comp['clips']):
        if right.get('transition'):
            tr = right['transition']; half = round(tr['duration']*comp['fps']/2)
            cut = round(right['start']*comp['fps'])
            result.append({'start': cut-half, 'end': cut+half, 'left': comp['clips'][i-1], 'right': right, **tr})
    return result


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


def enable(ident, body):
    """Explicitly enable editing on the same project, preserving its independent clocks."""
    original = project.load(ident)
    if original['revision'] != body.get('revision'):
        raise ValueError('工程已更新，请重新读取后再启用剪辑')
    if original.get('composition'):
        return {'project': original, 'warnings': []}
    fps, assets, clips, lengths, warnings = 25, [], [], [.1], []
    if original.get('video'):
        item = import_media(ident, {'path': original['video']})
        lengths.append(item['duration'])
        if item['kind'] == 'video':
            if body.get('autoProxy', True) and (Path(item['path']).suffix.lower() in ('.mkv', '.avi') or item.get('videoCodec', 'h264') not in ('h264', 'vp8', 'vp9', 'av1')):
                try: item = proxy(ident, {'asset': item['id']})
                except (ValueError, OSError, subprocess.SubprocessError):
                    warnings.append('原视频已保留；网页代理未就绪，可在媒体库重试生成')
            assets.append(item)
            clips.append({'id': 'Clip1', 'asset': item['id'], 'start': 0, 'in': 0,
                          'duration': max(1/fps, math.floor(item['duration']*fps)/fps), 'fit': 'contain', 'x': 0, 'y': 0})
    if original.get('audio'):
        lengths.append(inspect(original['audio'])['duration'] + original['audioOffset'])
    lengths += [project.caption_times(row, language)['end'] + original['subtitleShift']
                for row in original.get('cues', []) for language in ('original', 'translation')]
    composition = {'version': 1, 'duration': math.ceil(max(lengths)*fps)/fps if len(lengths)>1 else 30,
                   'fps': fps, 'width': 1920, 'height': 1080, 'allowGaps': False, 'assets': assets, 'clips': clips}
    # save() keeps the previous document in History and checks the revision again after media work.
    result = project.save(ident, {**original, 'composition': composition})
    return {'project': result, 'warnings': warnings}


def picture_segments(comp, first, last):
    """One frame grid for cuts, transition envelopes and preview slices."""
    fps = comp['fps']; effects = transitions(comp)
    boundaries = {first, last}
    for clip in comp['clips']:
        boundaries.update([round(clip['start']*fps), round((clip['start']+clip['duration'])*fps)])
    for tr in effects: boundaries.update([tr['start'], tr['end']])
    points = sorted(p for p in boundaries if first <= p <= last)
    result = []
    for a, b in zip(points, points[1:]):
        tr = next((tr for tr in effects if tr['start'] <= a < tr['end']), None)
        clip = next((c for c in comp['clips'] if round(c['start']*fps) <= a < round((c['start']+c['duration'])*fps)), None)
        result.append((a, b, tr, clip))
    return result


def picture_input(comp, clip, a, b):
    fps = comp['fps']; count = b-a
    if not clip:
        return ['-f', 'lavfi', '-i', f'color=c=black:s=1920x1080:r={fps}'], 'setsar=1'
    source = next(x for x in comp['assets'] if x['id'] == clip['asset'])
    if source['kind'] == 'image':
        args = ['-loop', '1', '-framerate', str(fps), '-i', source['path']]
        envelope = ''
    else:
        first = round(clip['start']*fps); last = first + round(clip['duration']*fps)
        # Never reveal trimmed-away material. Extend first/last allowed frames instead.
        local = max(0, min(a-first, last-first-1))
        args = ['-ss', str(clip['in'] + local/fps), '-i', source['path']]
        read = max(1, min(count, last-max(a, first)))
        pre = max(0, first-a)
        envelope = f',trim=end_frame={read},tpad=start_mode=clone:start={pre}:stop_mode=clone:stop={count},trim=end_frame={count}'
    normal = "scale=w='trunc(iw*sar/2)*2':h='trunc(ih/2)*2',setsar=1,"
    if clip['fit'] == 'cover':
        fit = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)*{(clip['x']+1)/2}:(ih-oh)*{(clip['y']+1)/2}"
    else:
        fit = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)*{(clip['x']+1)/2}:(oh-ih)*{(clip['y']+1)/2}:black"
    return args, normal + fit + f',fps={fps},format=yuv420p,settb=1/{fps},setpts=PTS-STARTPTS' + envelope + f',settb=AVTB,setpts=N/({fps}*TB)'


def picture_fades(comp, first):
    """Apply picture-only fades on the absolute frame clock, including partial previews."""
    fades = comp.get('fades', {}); fps = comp['fps']; effects = []
    for key in ['in', 'out']:
        frames = round(fades.get(key, 0)*fps)
        if not frames: continue
        start = 0 if key == 'in' else (round(comp['duration']*fps)-frames)/fps
        effects.append(f'fade=t={key}:st={start}:d={(frames-1)/fps}')
    # Frame-index timestamps avoid fractional PTS truncation at segment joins.
    if not effects: return f',settb=AVTB,setpts=N/({fps}*TB)'
    return f',settb=AVTB,setpts=(N+{first})/({fps}*TB),' + ','.join(effects) + f',setpts=N/({fps}*TB)'


def build_picture(job, start, end, execute, update):
    """Render the requested interval using absolute transition times, independent of audio/captions."""
    comp = validate(job['snapshot']['composition']); fps = comp['fps']; folder = Path(job['folder'])
    first, last = round(start*fps), round(end*fps)
    if last <= first: raise ValueError('预览区间短于一帧')
    segments = picture_segments(comp, first, last); entries = []
    for index, (a, b, tr, clip) in enumerate(segments):
        update(job, stage=f'拼接画面 {index+1} / {len(segments)}', progress=5+int(50*index/max(1,len(segments))))
        if tr:
            left_args, left_filter = picture_input(comp, tr['left'], a, b)
            right_args, right_filter = picture_input(comp, tr['right'], a, b)
            phase = f'min(1,max(0,(T*{fps}+{a-tr["start"]})/{tr["end"]-tr["start"]}))'
            # Fade through legal-range black (Y=16, U/V=128), matching the browser black canvas.
            if tr['type'] == 'dissolve':
                blend = f"all_expr='A*(1-({phase}))+B*({phase})'"
            else:
                blend = ':'.join(f"c{i}_expr='(A-{black})*max(0,1-2*({phase}))+(B-{black})*max(0,2*({phase})-1)+{black}'" for i, black in enumerate([16, 128, 128]))
            graph = f"[0:v]{left_filter}[l];[1:v]{right_filter}[r];[l][r]blend={blend}{picture_fades(comp, a)}[v]"
            args = left_args + right_args + ['-filter_complex_threads', '1', '-filter_complex', graph, '-map', '[v]']
        else:
            args, filters = picture_input(comp, clip, a, b)
            args += ['-vf', filters+f',tpad=stop_mode=clone:stop_duration={1/fps},fps={fps},setpts=PTS-STARTPTS'+picture_fades(comp, a)]
        name = f'Picture {index+1:03}.mkv'; output = folder/name
        execute(job, args + ['-an', '-frames:v', str(b-a), '-r', str(fps), '-fps_mode', 'cfr', '-c:v', 'ffv1', '-level', '3', '-threads', '2', '-pix_fmt', 'yuv420p', output], stage='渲染画面转场' if tr else '拼接画面片段')
        entries.extend(["file '" + name + "'", f"duration {(b-a)/fps:.9f}"])
    sequence = folder/'picture-sequence.txt'; sequence.write_text('\n'.join(entries), encoding='utf-8')
    output = folder/'picture.mkv'
    execute(job, ['-f', 'concat', '-safe', '0', '-i', sequence, '-c', 'copy', output], stage='组装画面时间轴')
    return output
