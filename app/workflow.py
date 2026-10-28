"""Queued local delivery tasks. Source media is read only; outputs stay in pilots."""
from pathlib import Path
import copy, json, math, os, queue, re, shutil, subprocess, threading, time, uuid, zipfile
from core import ROOT, read_json, save_json, sha, srt_text, subtitle_checks

import settings
import lifecycle
STORE = ROOT / 'runtime/workflow'
STORE.mkdir(parents=True, exist_ok=True)
GUARD = threading.RLock()
PENDING = queue.Queue()
JOBS = {}
WATCH = {}
SEEN = {}
STARTED = False

def project(pid):
    if pid not in {p['id'] for p in read_json(ROOT/'config/projects.json')}:
        raise ValueError('Unknown pilot')
    return read_json(ROOT/'data/projects'/f'{pid}.json')['project']

def local_media(value, suffixes):
    p = Path(str(value).strip())
    if not p.is_absolute() or str(p).startswith(('\\\\', '//')) or not p.is_file() or p.suffix.lower() not in suffixes:
        raise ValueError('请填写存在的本机音频 / 视频绝对路径')
    return p.resolve()

def persist(j):
    save_json(STORE/f"{j['id']}.json", j)

def update(j, **kw):
    with GUARD:
        j.update(kw); j['updatedAt'] = time.time(); persist(j)

def command(j, args, cwd=None):
    # Argument lists, no shell; each invocation and diagnostic retained locally.
    cp = subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True,
                        encoding='utf-8', errors='replace', timeout=900,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    log = Path(j['outputDir'])/'task.log'
    with log.open('a', encoding='utf-8') as f:
        f.write(json.dumps([str(x) for x in args], ensure_ascii=False)+'\n'+cp.stdout+'\n'+cp.stderr+'\n')
    if cp.returncode:
        raise ValueError('媒体工具执行失败；详情见任务日志：'+cp.stderr[-700:])
    return cp

def probe(j, path):
    return json.loads(command(j, [settings.executable('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',path]).stdout)

def duration(metadata):
    return float(metadata['format']['duration'])

def add_file(j, p, label):
    with GUARD:
        j['files'].append({'label':label,'path':str(p),'url':f"/download/{j['pid']}/{p.name}"}); persist(j)

def delivery(j):
    source = Path(j['input']['audio']); out = Path(j['outputDir']); prefix = j['id']
    update(j, progress=15, message='检查音频格式与响度')
    info = probe(j, source)
    if not any(s['codec_type']=='audio' for s in info['streams']): raise ValueError('输入没有音频流')
    measured = command(j,[settings.executable('ffmpeg'),'-hide_banner','-nostdin','-i',source,'-vn','-af','ebur128=peak=true','-f','null','-']).stderr
    summaries = measured.rsplit('Summary:',1)[-1]
    def metric(pattern):
        m = re.search(pattern,summaries); value = float(m.group(1)) if m else None
        return value if value is not None and math.isfinite(value) else None
    lufs = metric(r'I:\s*([-+\d.]+)\s*LUFS'); peak = metric(r'Peak:\s*([-+\d.]+)\s*dBFS')
    h = sha(source); warnings=[]
    if peak is not None and peak>=0: warnings.append('真峰值达到或超过 0 dBFS，请回 DAW 检查失真。')
    if peak is not None and peak>-1: warnings.append('真峰值余量不足 1 dB；压缩编码后建议复查。')
    if lufs is None: warnings.append('未获得有限响度值，可能是静音文件。')
    state=j['snapshot']['state']; cues=state.get('subtitles',[])
    if cues:
        if any(float(r['end'])>duration(info)+.1 for r in cues): warnings.append('字幕超出音频时长，请检查结束时间。')
        warnings.append('字幕仍需人工确认；打包不代表歌词或时间已准确。')
    else: warnings.append('没有字幕，交付包未生成 SRT。')
    report={'source':str(source),'sha256':h,'metadata':info,'integratedLUFS':lufs,'truePeakDBFS':peak,
            'warnings':warnings,'subtitleChecks':subtitle_checks(cues,duration(info)),
            'processing':'音频原样复制，不归一化、不调整混音','project':j['pid']}
    update(j,qc={'lufs':lufs,'truePeakDBTP':peak,'duration':duration(info)})
    qc=out/f'{prefix}_qc.json'; save_json(qc,report); add_file(j,qc,'音频检查报告')
    update(j,progress=55,message='整理音频、歌词与字幕')
    audio=out/f'{prefix}_master{source.suffix.lower()}'; shutil.copy2(source,audio)
    if sha(audio)!=h: raise ValueError('交付音频校验失败')
    add_file(j,audio,'原样混音音频');update(j,masterAudio=str(audio))
    if cues:
        sub=out/f'{prefix}_bilingual.srt';sub.write_text(srt_text(cues,'bilingual'),encoding='utf-8-sig');add_file(j,sub,'双语字幕（待人工确认）')
    package=j['snapshot'].get('lyrics') or {}; rows=package.get('rows',[])
    if rows:
        lyric=out/f'{prefix}_lyrics_romaji.txt'
        lyric.write_text('\n\n'.join('\n'.join(str(r.get(k,'')) for k in ['original','reading','romaji','translation']) for r in rows),encoding='utf-8-sig')
        add_file(j,lyric,'原文 / 假名 / 罗马音 / 译文')
        provenance=out/f'{prefix}_lyrics_source.json';save_json(provenance,package);add_file(j,provenance,'歌词来源与读音修订记录')
    manifest=out/f'{prefix}_manifest.json'
    save_json(manifest,{'task':j['id'],'pilot':j['snapshot']['pilot'],'createdAt':j['createdAt'],
                       'sourceAudio':str(source),'audioSHA256':h,'warnings':warnings,
                       'files':[{'name':Path(f['path']).name,'sha256':sha(f['path'])} for f in j['files']]})
    add_file(j,manifest,'交付清单')
    update(j,progress=85,message='生成交付 ZIP')
    archive=out/f'{prefix}_delivery.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:
        for f in list(j['files']): z.write(f['path'],Path(f['path']).name)
    add_file(j,archive,'完整交付包');add_file(j,out/'task.log','任务日志')
    # Log basename must be unique for downloads.
    renamed=out/f'{prefix}_task.log';(out/'task.log').rename(renamed)
    with GUARD:
        j['files'][-1]={'label':'任务日志','path':str(renamed),'url':f"/download/{j['pid']}/{renamed.name}"}
        j['warnings']=warnings;persist(j)

def video(j):
    args=j['input']; out=Path(j['outputDir']); prefix=j['id']
    update(j,progress=10,message='检查视频与替换音轨时长')
    vi=probe(j,args['video']);ai=probe(j,args['audio']); vd=duration(vi); ad=duration(ai);offset=args['offset']
    if not any(s['codec_type']=='video' for s in vi['streams']): raise ValueError('视频没有画面流')
    if not any(s['codec_type']=='audio' for s in ai['streams']): raise ValueError('音频没有音频流')
    if abs(vd-(ad+offset))>2 and not args['allowDurationMismatch']:
        raise ValueError(f'视频 {vd:.2f}s / 音频 {ad:.2f}s，偏移 {offset:.2f}s；请检查或勾选允许裁切 / 补静音后重新提交。')
    target=out/f'{prefix}_cover.mp4'
    cmd=[settings.executable('ffmpeg'),'-hide_banner','-nostdin','-y','-i',args['video'],'-i',args['audio']]
    filt=f'atrim=start={max(0,-offset):.6f},asetpts=PTS-STARTPTS,adelay={max(0,offset)*1000:.3f}:all=1,apad'
    cmd+=['-map','0:v:0','-map','1:a:0','-af',filt,'-t',str(vd),'-c:a','aac','-b:a','320k']
    cues=j['snapshot']['state'].get('subtitles',[])
    if args['burnSubtitles']:
        if not cues: raise ValueError('没有字幕；请先到歌词与字幕页保存字幕')
        shifted=[]
        for r in cues:
            a=max(0,float(r['start'])+offset);b=min(vd,float(r['end'])+offset)
            if b>a:shifted.append(dict(r,start=a,end=b))
        sub=out/'subtitles.srt';sub.write_text(srt_text(shifted,'bilingual'),encoding='utf-8-sig')
        cmd+=['-vf',"subtitles=subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize=20,Outline=1.5,MarginV=28'",'-c:v','libx264','-preset','medium','-crf','18']
    else:cmd+=['-c:v','copy']
    cmd+=['-movflags','+faststart',target]
    update(j,progress=35,message='替换音轨'+('并烧录字幕' if args['burnSubtitles'] else '，保留视频编码'))
    command(j,cmd,cwd=out)
    result=probe(j,target);save_json(out/f'{prefix}_video.json',{'videoInput':args['video'],'audioInput':args['audio'],
           'offsetSeconds':offset,'durationPolicy':'保留视频时长；音频按偏移裁切 / 补静音','subtitleOffsetSeconds':offset,
           'burnSubtitles':args['burnSubtitles'],'output':result})
    add_file(j,target,'换音轨视频');add_file(j,out/f'{prefix}_video.json','视频任务说明')
    if args['burnSubtitles']:
        sub.rename(out/f'{prefix}_bilingual.srt');add_file(j,out/f'{prefix}_bilingual.srt','已偏移字幕')
    log=out/f'{prefix}_task.log';(out/'task.log').rename(log);add_file(j,log,'任务日志')

def enqueue(pid, body, watcher=False):
    with lifecycle.operation('提交交付任务'):
        return _enqueue(pid,body,watcher)

def _enqueue(pid, body, watcher=False):
    p=project(pid); kind=body.get('kind')
    if kind not in ['delivery','video']:raise ValueError('Unknown task')
    import mix_sources
    choice=mix_sources.preferred(mix_sources.collect(p,ROOT))
    default=choice['path'] if choice else ''
    audio=local_media(body.get('audio') or default,{'.wav','.flac','.mp3','.m4a','.aiff','.aif'})
    data={'audio':str(audio)}
    if kind=='video':
        data['video']=str(local_media(body.get('video',''),{'.mp4','.mkv','.mov','.webm','.avi'}))
        offset=float(body.get('offset',0))
        if not math.isfinite(offset) or abs(offset)>600:raise ValueError('音频偏移需要在 ±600 秒内')
        data.update(offset=offset,burnSubtitles=body.get('burnSubtitles') is True,
                    allowDurationMismatch=body.get('allowDurationMismatch') is True)
    if not (settings.executable('ffmpeg')).is_file():raise ValueError('FFmpeg 未找到')
    stamp=f"{pid}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    from workspaces import outputs
    out=outputs(p)/'exports'/('delivery' if kind=='delivery' else 'video')/stamp
    out.mkdir(parents=True,exist_ok=False)
    lp=Path(p['pilot'])/'analysis/lyrics-current.json'
    j={'id':stamp,'pid':pid,'kind':kind,'status':'queued','progress':0,'message':'等待执行','createdAt':time.time(),
       'outputDir':str(out),'input':data,'files':[],'fromWatcher':watcher,
       'snapshot':{'pilot':p['pilot'],'state':read_json(Path(p['pilot'])/'analysis/review.json'),
                   'lyrics':read_json(lp) if lp.exists() else None}}
    with GUARD:JOBS[stamp]=j;persist(j)
    PENDING.put(stamp);return public(j)

def public(j):return copy.deepcopy({k:v for k,v in j.items() if k!='snapshot'})

def status(pid):
    from workspaces import root
    p=project(pid)
    import mix_sources
    discovery=mix_sources.collect(p,ROOT)
    with GUARD:
        for j in JOBS.values():
            if j['pid']==pid and j['kind']=='delivery' and j['status']=='completed' and not j.get('qc'):
                try:
                    r=read_json(Path(j['outputDir'])/(j['id']+'_qc.json'))
                    j['qc']={'lufs':r['integratedLUFS'],'truePeakDBTP':r['truePeakDBFS'],'duration':duration(r['metadata'])}
                except (OSError,KeyError,ValueError):pass
        jobs=[public(j) for j in JOBS.values() if j['pid']==pid]
        return {'jobs':sorted(jobs,key=lambda j:j['createdAt'],reverse=True)[:40],
                'watcher':copy.deepcopy(WATCH.get(pid,{'enabled':False})),
                'renderFolder':str(root(p)/'exports/audio'),
                'defaultAudio':mix_sources.preferred(discovery)['path'] if mix_sources.preferred(discovery) else '',
                'audioDiscovery':discovery,
                'nativeScripts':['CW Phrase Lyrics','CW Phrase Reuse','CW Voice Presets'],
                'presets': [{'id':f.stem.split('_',1)[1], 'svMajor':f.stem.split('_',1)[0]}
                            for f in sorted((ROOT/'data/sv-presets').glob('*.tsv'))],
                'phrases':[f.stem[len(pid)+1:] for f in sorted((ROOT/'data/sv-phrases').glob(pid+'_*.tsv'))]}

def watch_config(pid, enabled):
    from workspaces import outputs
    p=project(pid); folder=outputs(p)/'exports/audio';folder.mkdir(parents=True,exist_ok=True)
    with GUARD:
        # Explicit enable starts after the existing inventory; old renders are never submitted.
        WATCH[pid]={'enabled':enabled is True,'folder':str(folder),'enabledAt':time.time(),'message':'只检查启用后新增或更新的音频'}
        SEEN[pid]={str(f):(f.stat().st_size,f.stat().st_mtime_ns,0,True) for f in folder.iterdir() if f.is_file()}
        save_json(STORE/'watchers.json',WATCH)
    return status(pid)

def watch_tick(now=None):
    now=time.monotonic() if now is None else now
    with GUARD: configs=copy.deepcopy(WATCH)
    for pid,c in configs.items():
        if not c.get('enabled'):continue
        try:
            for f in Path(c['folder']).iterdir():
                if not f.is_file() or f.suffix.lower() not in ['.wav','.flac','.mp3','.aiff','.aif','.m4a']:continue
                s=f.stat();key=str(f); sig=(s.st_size,s.st_mtime_ns)
                with GUARD:
                    prior=SEEN.setdefault(pid,{}).get(key)
                    if not prior or prior[:2]!=sig:SEEN[pid][key]=(*sig,now,False);continue
                    if prior[3] or now-prior[2]<10:continue
                    SEEN[pid][key]=(*sig,prior[2],True)
                try:enqueue(pid,{'kind':'delivery','audio':key},watcher=True)
                except Exception as e:
                    with GUARD:WATCH[pid]['message']='文件处理失败：'+str(e)
        except Exception as e:
            with GUARD:WATCH[pid]['message']='文件夹检查失败：'+str(e)

def worker():
    while True:
        ident=PENDING.get(); j=JOBS[ident]
        with lifecycle.operation('交付任务'):
            try:
                update(j,status='running',message='任务开始')
                (delivery if j['kind']=='delivery' else video)(j)
                update(j,status='completed',progress=100,message='完成；可下载结果')
            except Exception as e:
                update(j,status='failed',message=str(e))
                log=Path(j['outputDir'])/'task.log'
                if log.exists():
                    dest=log.with_name(j['id']+'_task.log');log.rename(dest);add_file(j,dest,'失败日志')
            finally:PENDING.task_done()

def start():
    global STARTED
    if STARTED:return
    STARTED=True
    for f in STORE.glob('*.json'):
        if f.name=='watchers.json':continue
        try:
            j=read_json(f)
            if j['status'] in ['queued','running']:j.update(status='interrupted',message='上次服务退出中断，请重新提交');persist(j)
            JOBS[j['id']]=j
        except (ValueError,KeyError):pass
    # Watchers are paused after restart to avoid silently claiming files written while offline.
    if (STORE/'watchers.json').exists():
        for pid,c in read_json(STORE/'watchers.json').items():
            WATCH[pid]=dict(c,enabled=False,message='服务重启后已暂停，重新启用将跳过现有文件')
    threading.Thread(target=worker,daemon=True,name='delivery-worker').start()
    def loop():
        while True:
            watch_tick();time.sleep(3)
    threading.Thread(target=loop,daemon=True,name='render-watch').start()
