"""Read-only final-mix discovery within explicitly associated song/output folders."""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import time

from core import read_json
import video_project as video

AUDIO = {'.wav', '.flac', '.mp3', '.m4a', '.aif', '.aiff'}
STEMS = re.compile(r'(^|[\s_.()\[\]-])(vocals?|lead\d*|harmony|instrumental|accompaniment|dry|人声|主声|和声|伴奏)(?=$|[\s_.()\[\]\d-])', re.I)
FINAL = re.compile(r'mixdown|master|final|成品|混音', re.I)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else 0
    except (TypeError, ValueError): return 0


def key(value):
    try: return os.path.normcase(str(Path(video.clean_path(value)).resolve())) if value else ''
    except (OSError, ValueError, TypeError): return ''


def audio_info(value, label, origin='registered'):
    try:
        p = video.local(value, AUDIO); stat = p.stat()
        if not stat.st_size: return None
        signature = hashlib.sha256(json.dumps([str(p),stat.st_size,stat.st_mtime_ns],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return dict(path=str(p),name=p.name,label=label,origin=origin,modified=stat.st_mtime,size=stat.st_size,signature=signature,automatic=True)
    except (OSError, ValueError, TypeError): return None


def read(path, default):
    try: return read_json(path) if path.is_file() else default
    except (OSError, ValueError, TypeError): return default


def registered(root, ident):
    doc = read(root/'config/project-assets.local.json', {})
    return doc.get('projects', {}).get(ident, {}) if isinstance(doc, dict) else {}


def workspace(p, root):
    rows = read(root/'config/workspaces.local.json', {})
    return Path(rows.get(p['id']) or p['pilot'])


def builds(p, root):
    """Indexed/exactly associated builds, including unified and external output roots."""
    custom = registered(root, p['id']); paths = set()
    index = read(root/'data/daw-build-index.json', [])
    if isinstance(index, list): paths.update(Path(v) for v in index[:500] if isinstance(v,str))
    for folder in {root/'projects/studio-one',workspace(p,root)/'studio-one',Path(p['pilot'])/'studio-one'}:
        if folder.is_dir(): paths.update(folder.glob('*/build.json'))
    if custom.get('song'): paths.add(Path(custom['song']).parent/'build.json')
    svps = {key(v) for v in [custom.get('svp'),p.get('managedSVP'),p.get('working'),*(f.get('original') for f in p.get('files',[]) if isinstance(f,dict) and str(f.get('original','')).lower().endswith('.svp'))] if v}
    result=[]
    for path in paths:
        b=read(path,{})
        if not isinstance(b,dict) or b.get('musicId') not in (None,p['id']): continue
        if b.get('musicId')==p['id'] or svps.intersection({key(b.get(k)) for k in ('svp','sourceSVP') if b.get(k)}): result.append(b)
    return sorted(result,key=lambda b:number(b.get('createdAt')),reverse=True)


def collect(p, root):
    custom = registered(root,p['id']); candidates=[]; seen=set(); warnings=[]; searched=[]
    audio=p.get('audio',{});blocked={key(v) for role in ('source','vocals','lead','harmony','accompaniment') for v in [custom.get(role),audio.get(role,{}).get('original')] if v}
    def add(path,label,origin):
        item=audio_info(path,label,origin)
        if item and key(item['path']) not in seen:
            seen.add(key(item['path']));candidates.append(item)
        return item
    # Explicit project registration remains authoritative; per-video choices are handled by the caller.
    if custom.get('mix'):
        if not add(custom['mix'],'项目素材中登记的成品混音','registered'): warnings.append('已登记的成品混音已移动或不可用')
    jobs=[]
    for file in (root/'runtime/workflow').glob('*.json'):
        job=read(file,{})
        if isinstance(job,dict) and job.get('pid')==p['id'] and job.get('kind')=='delivery' and job.get('status')=='completed': jobs.append(job)
    for job in sorted(jobs,key=lambda j:number(j.get('createdAt')),reverse=True):
        data=job.get('input') if isinstance(job.get('input'),dict) else {}
        if key(data.get('audio')) in blocked: continue
        files=job.get('files') if isinstance(job.get('files'),list) else []
        copies=[job.get('masterAudio')]+[f.get('path') for f in files if isinstance(f,dict) and f.get('label')=='原样混音音频']
        if isinstance(job.get('id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,300}',job['id']) and isinstance(job.get('outputDir'),str):
            suffix=Path(str(data.get('audio') or '')).suffix.lower()
            if suffix in AUDIO: copies.append(str(Path(job['outputDir'])/(str(job['id'])+'_master'+suffix)))
        chosen=next((item for path in copies if path for item in [add(path,'已完成交付的混音副本','delivery')] if item),None)
        if not chosen: chosen=add(data.get('audio'),'已完成交付的源混音（副本不可用）','delivery-source')
        confirmed={key(custom.get('mix')),key(audio.get('mix',{}).get('original'))}-{''}
        if chosen and job.get('fromWatcher') and not FINAL.search(Path(str(data.get('audio') or '')).stem) and key(data.get('audio')) not in confirmed:
            chosen['automatic']=False;chosen['label']+='（自动打包，待手动确认）'
    original=audio.get('mix',{}).get('original')
    if original: add(original,'音乐工程登记的成品混音','registered')
    song_paths=[custom.get('song'),p.get('dawCopy',{}).get('song')]
    song_paths += [b.get('song') for b in builds(p,root)]
    song_paths += [f.get('original') for f in p.get('files',[]) if isinstance(f,dict) and str(f.get('original','')).lower().endswith('.song')]
    folders=[]
    for value in song_paths:
        if value:
            try:
                song=Path(video.clean_path(value))
                if song.is_absolute() and not str(song).startswith(('\\\\','//')): folders.append((song.parent/'Mixdown','Studio One 工程的 Mixdown 导出','studio-one'))
            except (OSError, ValueError, TypeError): pass
    for base in {workspace(p,root),Path(p['pilot'])}: folders.append((base/'exports/audio','本曲 exports/audio 导出','exports'))
    known=set(); discovered=[];recent=False
    for folder,label,origin in folders:
        if key(folder) in known: continue
        known.add(key(folder));searched.append(str(folder))
        try:
            if not folder.is_dir(): continue
            for index,file in enumerate(folder.iterdir()):
                if index>=500: warnings.append('导出目录文件较多，只检查前 500 项；可手动选择成品混音');break
                if not file.is_file() or file.suffix.lower() not in AUDIO or key(file) in blocked: continue
                if STEMS.search(file.stem) or re.search(r'(^|[_. -])(temp|tmp|partial|rendering)([_. -]|$)',file.stem,re.I): continue
                stat=file.stat()
                if time.time()-stat.st_mtime<2: recent=True;continue
                discovered.append((bool(FINAL.search(file.stem)),stat.st_mtime,str(file),label,origin))
        except OSError: warnings.append('无法读取导出目录：'+str(folder))
    for marked,_,path,label,origin in sorted(discovered,key=lambda row:(row[0],row[1]),reverse=True):
        item=add(path,label if marked else label+'（待手动确认）',origin)
        if item and not marked:
            for candidate in candidates:
                if candidate is item: candidate['automatic']=False
    if candidates and not any(c['automatic'] for c in candidates): warnings.append('仅找到未标记为 Mixdown / Master / Final 的导出，请从下拉列表确认成品；不会自动把 SV 人声当成混音')
    if recent: warnings.append('有导出文件刚写入，稍候至少 2 秒再点“读取素材”')
    return {'candidates':candidates,'searchedFolders':searched,'warnings':warnings,'completedDeliveries':len(jobs)}


def preferred(discovery):
    return next((c for c in discovery['candidates'] if c.get('automatic',True)),None)
