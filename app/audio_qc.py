"""Non-destructive music delivery measurements and time-addressable review cues."""
from pathlib import Path
import json,math,re,time
from core import read_json,save_json,sha
import project_assets,settings,daw,asset_impact,workspaces

def number(value):
    try:n=float(value);return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def analyze(job,command,progress,check):
    ident=job['project'];assets=project_assets.status(ident);path=daw.local(job['request'].get('path') or assets['assets']['mix']['path'],project_assets.AUDIO)
    before=asset_impact.fingerprint(str(path));digest=sha(path);info=daw.media_info(path);duration=info['duration'];issues=[]
    if duration>7200:raise ValueError('音乐交付检查支持最长 2 小时音频，请先选择成品歌曲')
    def issue(code,message,at=0,end=None):issues.append({'id':code+'-'+str(round(at,3)),'code':code,'message':message,'time':max(0,round(at,3)),'end':end})
    text=command([settings.executable('ffmpeg'),'-hide_banner','-nostdin','-i',str(path),'-vn','-af','loudnorm=I=-14:TP=-1:LRA=11:print_format=json','-f','null','-'],'测量综合响度与真峰值',duration)
    blocks=re.findall(r'\{\s*"input_i".*?\}',text,re.S)
    if not blocks:raise ValueError('未取得响度读数，请检查音频或 FFmpeg')
    measured={k:number(v) for k,v in json.loads(blocks[-1]).items() if k!='normalization_type'}
    progress(45,'检查静音和声道电平')
    details=command([settings.executable('ffmpeg'),'-hide_banner','-nostdin','-i',str(path),'-vn','-af','silencedetect=noise=-55dB:d=0.5,astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.Peak_level','-f','null','-'],'检查静音、峰值与左右声道',duration)
    starts=[float(x) for x in re.findall(r'silence_start:\s*([\d.]+)',details)];ends=[float(x) for x in re.findall(r'silence_end:\s*([\d.]+)',details)]
    for start in starts:
        end=next((e for e in ends if e>start),duration)
        if start>.2 and end<duration-.1:issue('silence','检测到持续静音，可能是有意的停顿，请试听确认',start,end)
    tp=measured.get('input_tp')
    peak_rows=re.findall(r'pts_time:([\d.]+)[^\n]*\n[^\n]*lavfi\.astats\.Overall\.Peak_level=([-\d.]+)',details)
    peak_at=float(max(peak_rows,key=lambda r:float(r[1]))[0]) if peak_rows else 0
    if tp is not None and tp>-.5:issue('true-peak',f'整曲真峰值 {tp:.2f} dBTP，接近或超过零；定位为最大采样峰值附近，供核对编码余量',peak_at)
    if measured.get('input_i') is None:issue('silent','整段过于安静或太短，综合响度无法可靠测量')
    channel_sections=re.split(r'Channel:\s*\d+',details)[1:];levels=[]
    for section in channel_sections:
        values=re.findall(r'RMS level dB:\s*([-\d.inf]+)',section)
        if values:levels.append(number(values[0]))
    if len(levels)>=2 and all(x is not None for x in levels[:2]) and abs(levels[0]-levels[1])>12:issue('stereo-balance','左右声道整体电平相差超过 12 dB，请确认是否有意声像安排')
    tail=command([settings.executable('ffmpeg'),'-hide_banner','-nostdin','-ss',str(max(0,duration-.08)),'-i',str(path),'-vn','-af','astats=metadata=0:reset=0','-f','null','-'],'检查结尾声音')
    values=re.findall(r'RMS level dB:\s*([-\d.inf]+)',tail);tail_rms=number(values[-1]) if values else None
    if tail_rms is not None and tail_rms>-35:issue('tail','文件末端仍有明显声音，请确认尾音未被截断；有意硬切可忽略',max(0,duration-3),duration)
    accompaniment=assets['assets']['accompaniment']
    if accompaniment.get('exists'):
        reference=daw.media_info(Path(accompaniment['path']))['duration']
        if abs(reference-duration)>2:issue('duration',f'成品与登记伴奏时长相差 {abs(reference-duration):.2f} 秒，请确认片头或尾音安排',max(0,min(reference,duration)-3))
    check()
    if before!=asset_impact.fingerprint(str(path)) or digest!=sha(path):raise ValueError('检查期间混音发生变化，请在导出完成后重新检查')
    result={'path':str(path),'source':before,'sha256':digest,'duration':duration,'measured':measured,'issues':issues,'created':time.time(),'scope':'仅分析原文件；不改变增益、不压缩、不切除静音。提示为待试听疑点，不代表混音有错。'}
    save_json(Path(job['folder'])/'Audio Check.json',result)
    root=workspaces.root(project_assets.project(ident));save_json(root/'analysis/Workbench/Latest Audio Check.json',{'job':job['id'],**result})
    return result

def latest(ident):
    root=workspaces.root(project_assets.project(ident));file=root/'analysis/Workbench/Latest Audio Check.json'
    if not file.exists():return None
    doc=read_json(file);doc['stale']=doc['source']!=asset_impact.fingerprint(doc['path'])
    decisions=root/'analysis/Workbench/Audio Check Decisions.json';saved=read_json(decisions) if decisions.exists() else {}
    doc['ignored']=saved.get('ignored',[]) if saved.get('sha256')==doc['sha256'] else []
    return doc

def ignore(ident,body):
    doc=latest(ident)
    if not doc or doc['stale'] or body.get('sha256')!=doc['sha256']:raise ValueError('检查结果已过期，请重新检查')
    ids=body.get('ignored');known={r['id'] for r in doc['issues']}
    if not isinstance(ids,list) or any(v not in known for v in ids):raise ValueError('请选择当前报告中的提示')
    root=workspaces.root(project_assets.project(ident));save_json(root/'analysis/Workbench/Audio Check Decisions.json',{'sha256':doc['sha256'],'ignored':ids});return latest(ident)
