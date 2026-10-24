"""Private video documents, subtitle interchange, and read-only SV timing anchors."""
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
import copy
import math
import re
import threading
import tomllib
import unicodedata
import uuid

from core import ROOT, read_json, save_json, sha, parse_svp, read_srt, srt_text
from daw import clean_path, local

BASE = ROOT / 'projects/video'
LOCK = threading.RLock()
MEDIA = {'.mp4', '.webm', '.mkv', '.mov', '.avi', '.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff'}
STYLE = dict(font='Microsoft YaHei', size=38, spacing=0, x=960, y=964, outline=2.5, shadow=1.2, color='#ffffff', bold=False)


def number(value, lo, hi, label='数值'):
    if isinstance(value, bool):
        raise ValueError(label + ' 必须是数字')
    try: value = float(value)
    except (TypeError, ValueError): raise ValueError(label + ' 必须是数字')
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{label} 应在 {lo} 至 {hi} 之间')
    return value


def stamp(value):
    if isinstance(value, str) and ':' in value:
        parts = value.replace(',', '.').split(':')
        if len(parts) not in (2, 3): raise ValueError('时间格式为 分:秒.毫秒')
        number(parts[-1],0,59.999999,'秒数')
        if len(parts)==3:number(parts[-2],0,59,'分钟')
        seconds = 0
        for part in parts: seconds = seconds * 60 + number(part, 0, 9999, '时间')
        return number(seconds,0,86400,'时间')
    return number(value, 0, 86400, '时间')


def folder(ident):
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9 _.-]{1,90}', ident) or ident in {'.', '..'}:
        raise ValueError('无效的视频工程编号')
    p = (BASE / ident).resolve()
    if p.parent != BASE.resolve() or not (p / 'project.json').is_file():
        raise ValueError('视频工程不存在')
    return p


def load(ident):
    with LOCK: return read_json(folder(ident) / 'project.json')


def listing():
    if not BASE.exists(): return []
    items = []
    for path in BASE.glob('*/project.json'):
        try:
            p = read_json(path)
            items.append({k: p[k] for k in ['id', 'name', 'revision', 'updated']})
        except (OSError, ValueError, KeyError): continue
    return sorted(items, key=lambda p: p['updated'], reverse=True)


def style(value):
    if not isinstance(value, dict) or set(value) - set(STYLE): raise ValueError('未知字幕样式参数')
    out = {**STYLE, **value}
    if not isinstance(out['font'], str) or not out['font'].strip() or len(out['font']) > 100 or any(c in out['font'] for c in ',\r\n{}\\'):
        raise ValueError('请填写字体家族名，不要填写路径或 ASS 标签')
    for key, lo, hi in [('size', 8, 200), ('spacing', -5, 30), ('x', 0, 1920), ('y', 0, 1080), ('outline', 0, 15), ('shadow', 0, 15)]:
        out[key] = number(out[key], lo, hi, key)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', out['color']): raise ValueError('字幕颜色应为 #RRGGBB')
    out['bold'] = bool(out['bold'])
    return out


def validate(doc):
    if not isinstance(doc, dict): raise ValueError('无效的视频工程')
    for key in ['video', 'audio']:
        if doc.get(key): doc[key] = str(local(doc[key], MEDIA))
    doc['audioOffset'] = number(doc.get('audioOffset', 0), -600, 600, '音频偏移')
    doc['subtitleShift'] = number(doc.get('subtitleShift', 0), -600, 600, '字幕整体偏移')
    doc['gainDb'] = number(doc.get('gainDb', 0), -60, 24, '音频增益')
    doc['targetLufs'] = number(doc.get('targetLufs', -14), -30, -5, '目标响度')
    if doc.get('audioMode') not in ['gain', 'normalize']: raise ValueError('无效的响度模式')
    if doc.get('resolution') not in ['source', '1080', '720']: raise ValueError('无效的分辨率')
    if doc.get('fps') not in ['source', '24', '25', '30', '60']: raise ValueError('无效帧率')
    if doc.get('format') not in ['mp4', 'mkv']: raise ValueError('无效导出格式')
    if not isinstance(doc.get('burn'),bool): raise ValueError('字幕烧录选项应为布尔值')
    doc['crf'] = int(number(doc.get('crf', 18), 14, 28, 'CRF'))
    doc['styles'] = {k: style(doc.get('styles', {}).get(k, {})) for k in ['original', 'translation']}
    rows = doc.get('cues', [])
    if not isinstance(rows, list) or len(rows) > 5000: raise ValueError('字幕最多 5000 组')
    ids = set()
    for row in rows:
        ident = row.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', ident) or ident in ids: raise ValueError('字幕编号应唯一')
        ids.add(ident)
        row['start'], row['end'] = stamp(row['start']), stamp(row['end'])
        if row['end'] <= row['start']: raise ValueError(f'{ident} 结束时间须晚于开始时间')
        for key in ['original', 'translation']:
            value = row.get(key, '')
            if not isinstance(value, str) or len(value) > 2000 or '\x00' in value: raise ValueError('字幕文字过长或无效')
            row[key] = value
            overrides = row.get(key + 'Style', {})
            if overrides: style({**doc['styles'][key], **overrides})
    return doc


def warnings(doc, duration=None):
    result = []
    rows = sorted(doc['cues'], key=lambda r: r['start'])
    for i, row in enumerate(rows):
        notes = []
        if row['start'] + doc['subtitleShift'] < 0: notes.append('移动后开始时间小于零，将裁切')
        if i and row['start'] < rows[i-1]['end'] - .005: notes.append('与上一句重叠，请确认是否为对唱')
        if duration and row['end'] + doc['subtitleShift'] > duration: notes.append('超过视频结尾，将裁切')
        if max(len(row['original']), len(row['translation'])) / (row['end'] - row['start']) > 18: notes.append('阅读速度偏快')
        if max(len(row['original']), len(row['translation'])) > 55: notes.append('长句，请用准确预览检查宽度')
        if notes: result.append({'id': row['id'], 'messages': notes})
    return result


def create(body):
    name = str(body.get('name', 'New Video')).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}', name) or name.endswith(('.', ' ')) or name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('工程名请使用英文、数字、空格、下划线或连字符')
    doc = dict(name=name, video='', audio='', audioOffset=0, subtitleShift=0, gainDb=0, targetLufs=-14,
               audioMode='gain', resolution='source', fps='source', format='mp4', crf=18, burn=True,
               styles={'original': dict(STYLE), 'translation': {**STYLE, 'size':44, 'y':1026}}, cues=[], provenance=[])
    with LOCK:
        BASE.mkdir(parents=True, exist_ok=True)
        dest = BASE / name
        version = 2
        while dest.exists(): dest = BASE / f'{name}_v{version}'; version += 1
        dest.mkdir()
        for child in ['Sources', 'History', 'Jobs', 'Exports']: (dest / child).mkdir()
        doc.update(id=dest.name, revision=1, updated=datetime.now().isoformat(timespec='seconds'))
        save_json(dest / 'project.json', doc)
    return doc


def save(ident, body, internal=None):
    with LOCK:
        current = load(ident)
        if body.get('revision') != current['revision']: raise ValueError('工程已在另一窗口更新；请重新载入，避免覆盖其修改')
        keys = {'video','audio','audioOffset','subtitleShift','gainDb','targetLufs','audioMode','resolution','fps','format','crf','burn','styles','cues'}
        doc = validate({**current, **{k: copy.deepcopy(v) for k,v in body.items() if k in keys}})
        if internal is None:
            from video_workflow import reconcile
            doc=reconcile(current,doc)
            validate(doc)
        else:
            doc.update(copy.deepcopy(internal))
        save_json(folder(ident) / 'History' / f"r{current['revision']:06}.json", current)
        doc['revision'] += 1
        doc['updated'] = datetime.now().isoformat(timespec='seconds')
        save_json(folder(ident) / 'project.json', doc)
        return doc


def read_captions(path):
    path = local(path, {'.lrc', '.srt', '.vtt'})
    if path.stat().st_size > 2_000_000: raise ValueError('字幕文件过大')
    try:path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:raise ValueError('请先把字幕保存为 UTF-8 编码')
    if path.suffix.lower() == '.lrc':
        text = path.read_text(encoding='utf-8-sig')
        offset = re.search(r'\[offset:([+-]?\d+)\]', text, re.I)
        offset = int(offset[1])/1000 if offset else 0
        rows = []
        for line in text.splitlines():
            stamps = list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]', line))
            if stamps:
                words = line[stamps[-1].end():].strip()
                for m in stamps: rows.append({'start':int(m[1])*60+float(m[2])+offset, 'text':words})
        rows.sort(key=lambda r:r['start'])
        for i,r in enumerate(rows): r['end'] = rows[i+1]['start'] if i+1<len(rows) else r['start']+4
        return rows
    if path.suffix.lower()=='.vtt':
        rows=[]
        for block in re.split(r'\n\s*\n',path.read_text(encoding='utf-8-sig').replace('\r\n','\n')):
            lines=block.splitlines()
            i=next((i for i,line in enumerate(lines) if '-->' in line),None)
            if i is None: continue
            start,end=lines[i].split('-->',1)
            rows.append({'start':stamp(start.strip()),'end':stamp(end.strip().split()[0]),'text':re.sub(r'<[^>]*>','','\n'.join(lines[i+1:]))})
        return rows
    return read_srt(path)


def import_captions(ident, body):
    doc = load(ident)
    a = local(body['original'], {'.lrc','.srt','.vtt'})
    b = local(body['translation'], {'.lrc','.srt','.vtt'}) if clean_path(body.get('translation')) else None
    if body.get('clock') not in ['audio','video']:raise ValueError('请明确选择字幕是混音时间还是视频时间')
    for source in [a,b]:
        if source and (source.parent/'caption-timing.json').is_file():
            sidecar=read_json(source.parent/'caption-timing.json')
            if sidecar.get('files',{}).get(source.name)==sha(source) and body['clock']=='audio':
                raise ValueError('这是工作台导出的字幕，已经使用视频时间；请选择「已经对齐视频」，避免再次加音频偏移')
    original = read_captions(a)
    translation = read_captions(b) if b else []
    if not original or not any(r['text'].strip() for r in original):raise ValueError('原文文件没有有效字幕，当前字幕表保留')
    if b and not translation:raise ValueError('译文文件没有有效字幕，当前字幕表保留')
    if any(r['end']<=r['start'] for r in original+translation):raise ValueError('字幕来源有时间倒置或重复时间戳，请检查后导入')
    shift = doc['audioOffset'] if body.get('clock') == 'audio' else 0
    # Independent timelines are joined by time, never by row number.
    boundaries = sorted({max(0, round(r[k]+shift, 4)) for r in original+translation for k in ['start','end']})
    cues = []
    for start,end in zip(boundaries,boundaries[1:]):
        if end <= start: continue
        texts = ['\n'.join(r['text'] for r in stream if r['start']+shift <= (start+end)/2 < r['end']+shift) for stream in [original,translation]]
        if not any(texts): continue
        if cues and [cues[-1]['original'],cues[-1]['translation']] == texts and abs(cues[-1]['end']-start)<.001:
            cues[-1]['end'] = end
        else: cues.append(dict(id=f'L{len(cues)+1:04}',start=start,end=end,original=texts[0],translation=texts[1]))
    doc['cues'] = cues
    doc['subtitleShift']=0
    for path in [a,b]:
        if path:
            target = folder(ident) / 'Sources' / (uuid.uuid4().hex[:8] + path.suffix.lower())
            target.write_bytes(path.read_bytes())
    from video_workflow import timing
    return save(ident, doc,internal={'timing':timing(doc,body['clock'],'import')})


def import_legacy(body):
    path = local(body['path'], {'.toml'})
    cfg = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    meta = read_json(path.parent / '01_Project/project.json')
    doc = create({'name':body.get('name') or 'Imported Video'})
    # Reuse the verified aligned PCM, avoiding a second application of its offset/gain.
    audio = Path(meta['audio'])
    doc.update(video=meta['source_video'], audio=str(audio) if audio.is_file() else meta['source_mix'],
               audioOffset=0 if audio.is_file() else meta['delay_seconds'],
               gainDb=0 if audio.is_file() else meta.get('gain_db',0), subtitleShift=cfg.get('global',{}).get('time_shift_seconds',0))
    mapping = {'font_name':'font','font_size':'size','spacing':'spacing','x':'x','y':'y','outline':'outline','shadow':'shadow'}
    for old,new in [('english','original'),('chinese','translation')]:
        doc['styles'][new] = {**doc['styles'][new], **{v:cfg[old][k] for k,v in mapping.items() if k in cfg[old]}}
    for row in cfg['subtitles']:
        cue = dict(id=row['id'], start=stamp(row['start']), end=stamp(row['end']), original=row.get('english',''), translation=row.get('chinese',''))
        for old,new in [('english_style','originalStyle'),('chinese_style','translationStyle')]:
            if row.get(old): cue[new] = {mapping[k]:v for k,v in row[old].items() if k in mapping}
        doc['cues'].append(cue)
    snapshot = folder(doc['id']) / 'Sources/legacy_config.toml'
    snapshot.write_bytes(path.read_bytes())
    from video_workflow import timing,file_key
    state={}
    if audio.is_file():state['alignedAudio']=file_key(doc['audio'])
    result = save(doc['id'], doc,internal={'timing':timing(doc,'video','legacy'),'workflow':state})
    result['importNote'] = '已复制配置与全部字幕。沿用已对齐音轨时偏移为 0，避免重复移动；原工程保留。长句适配请以准确预览为准。'
    return result


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())


def sv_anchors(body):
    path = local(body['path'], {'.svp'})
    parsed = parse_svp(path)
    if 'track' not in body: return {'tracks':[{k:t[k] for k in ['id','name','count']} for t in parsed['tracks']], 'sha256':sha(path)}
    track = next((t for t in parsed['tracks'] if t['id'] == int(body['track'])), None)
    if not track: raise ValueError('请选择 SV 中实际演唱的音轨')
    chars, anchors = '', []
    for note in track['notes']:
        token = normalize(note['lyrics'])
        if note['muted'] or not token: continue
        chars += token
        anchors += [note] * len(token)
    results, cursor = [], 0
    for cue in body.get('cues', []):
        text = normalize(cue.get('original',''))
        if not text: continue
        match = chars.find(text, cursor)
        if match >= 0:
            a,b = match,match+len(text); score=1.0
        else:
            # Best contiguous matching block only proposes anchors; no silent fuzzy rewrite.
            hit = SequenceMatcher(None, text, chars[cursor:], autojunk=False).find_longest_match()
            score = hit.size / max(1,len(text)); a=cursor+hit.b; b=a+hit.size
        if score < .75 or b <= a:
            results.append({'id':cue['id'],'score':round(score,3),'matched':False}); continue
        offset=number(body.get('offset',0),-600,600)
        results.append({'id':cue['id'],'matched':True,'score':round(score,3),'start':max(0,anchors[a]['start']+offset),
                        'end':max(.01,anchors[b-1]['end']+offset),'noteIds':list(dict.fromkeys(n['id'] for n in anchors[a:b]))})
        cursor=b
    return {'rows':results,'sha256':sha(path),'note':'按已保存 SVP 的歌词匹配音符起止；不包含辅音提前量，翻译与原句一起移动。重复句、延音和读音差异需试听确认。'}


def ass_stamp(t):
    n=round(max(0,t)*100); h,n=divmod(n,360000); m,n=divmod(n,6000); s,f=divmod(n,100)
    return f'{h}:{m:02}:{s:02}.{f:02}'


def ass_text(text):
    # Neutralize tags rather than allowing user text to become ASS drawing/file commands.
    return text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r','').replace('\n',r'\N')


def write_subtitles(doc, dest, duration):
    header='[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    def style_line(name,s):
        rgb=s['color'][1:]; color='&H00'+rgb[4:6]+rgb[2:4]+rgb[:2]
        return f"Style: {name},{s['font']},{s['size']},{color},{color},&H00151515,&H80000000,{-1 if s['bold'] else 0},0,0,0,100,100,{s['spacing']},0,1,{s['outline']},{s['shadow']},2,80,80,54,1\n"
    events=[]; output=[]
    for i,row in enumerate(doc['cues']):
        start=max(0,row['start']+doc['subtitleShift']); end=min(duration,row['end']+doc['subtitleShift'])
        if end<=start: continue
        output.append({**row,'start':start,'end':end})
        for key in ['original','translation']:
            if not row[key]: continue
            name=f'S{i}_{key}'; s=style({**doc['styles'][key],**row.get(key+'Style',{})})
            header+=style_line(name,s)
            events.append(f"Dialogue: 0,{ass_stamp(start)},{ass_stamp(end)},{name},,0,0,0,,{{\\an2\\pos({s['x']},{s['y']})}}{ass_text(row[key])}")
    header+='\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    (dest/'captions.ass').write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
    (dest/'captions.srt').write_text(srt_text(output),encoding='utf-8-sig')
    save_json(dest/'caption-timing.json',{'clock':'video','audioOffset':doc['audioOffset'],
             'subtitleShift':doc['subtitleShift'],'files':{name:sha(dest/name) for name in ['captions.ass','captions.srt']}})
    return output
