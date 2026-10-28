"""Bounded, cancellable local video jobs. All outputs are immutable private snapshots."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
import copy
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

import settings
import lifecycle
import video_project as project
import video_workflow
import video_audio
import video_storage
import media_names
from core import read_json, save_json, sha

LOCK = threading.RLock()
JOBS = {}
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-studio')
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class Cancelled(Exception):
    pass


def dependencies():
    return {'ffmpeg':bool(settings.executable('ffmpeg',False)), 'ffprobe':bool(settings.executable('ffprobe',False)),
            'download':bool(shutil.which('yt-dlp') or importlib.util.find_spec('yt_dlp')),
            'alignment':all(importlib.util.find_spec(x) for x in ['numpy','scipy']),
            'fonts':fonts(),'fontCatalog':font_catalog()}


def font_catalog():
    installed=fonts();normalized={s.casefold() for s in installed}
    common=[('微软雅黑','Microsoft YaHei','msyh.ttc'),('微软雅黑 UI','Microsoft YaHei UI','msyh.ttc'),
            ('黑体','SimHei','simhei.ttf'),('宋体','SimSun','simsun.ttc'),('新宋体','NSimSun','simsun.ttc'),
            ('楷体','KaiTi','simkai.ttf'),('仿宋','FangSong','simfang.ttf'),('等线','DengXian','Deng.ttf'),
            ('微软正黑体','Microsoft JhengHei','msjh.ttc'),('思源黑体','Source Han Sans SC',''),
            ('思源宋体','Source Han Serif SC',''),('思源黑体 Noto','Noto Sans CJK SC',''),
            ('Arial · 西文','Arial','arial.ttf'),('Segoe UI · 西文','Segoe UI','segoeui.ttf')]
    result=[];seen=set();base=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    for label,family,filename in common:
        available=any(n==family.casefold() or n.startswith(family.casefold()+' ') for n in normalized) or label.casefold() in normalized or bool(filename and (base/filename).is_file())
        result.append({'label':label,'family':family,'available':available,'common':True});seen.add(family.casefold())
    result += [{'label':s,'family':s,'available':True,'common':False} for s in installed if s.casefold() not in seen]
    return result


def fonts():
    if os.name == 'nt':
        import winreg
        names=set()
        for hive in [winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER]:
            try:
                with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        label,_,_=winreg.EnumValue(key,i)
                        names.update(n.strip() for n in re.sub(r'\s*\([^)]*\)$','',label).split(' & '))
            except OSError: pass
        return sorted(names)
    return ['DejaVu Sans','Noto Sans CJK SC','Noto Sans CJK JP']


def public(job):
    return copy.deepcopy({k:v for k,v in job.items() if k not in ['cancel','process','snapshot']})


def update(job, **values):
    with LOCK:
        job.update(values)
        save_json(Path(job['folder'])/'job.json', public(job))


def history(ident):
    locations=project.output_locations(ident)
    rows=[]
    with LOCK:
        live={Path(j['folder']).resolve():public(j) for j in JOBS.values() if j.get('project')==ident}
    for p in [p for dest in locations for section in ['Jobs','Tasks','Exports'] for p in (dest/section).glob('*/job.json')]:
        try:
            # Poll live jobs in memory instead of opening the file being replaced.
            active=p.parent.resolve() in live
            d=live.get(p.parent.resolve())
            if d is None: d=read_json(p)
            d['folder']=str(p.parent.resolve())
            if not active and d['status'] in ['queued','running']:
                d.update(status='interrupted',message='上次服务中断。输入与已完成版本保留，请重新提交。')
            rows.append(d)
        except (OSError,ValueError,KeyError): continue
    return sorted(rows,key=lambda r:r['created'],reverse=True)[:60]


def job(ident):
    with LOCK:
        if ident not in JOBS: raise ValueError('任务不存在；历史结果可从工程列表重新载入')
        return public(JOBS[ident])


def cancel(ident):
    with LOCK:
        if ident not in JOBS: raise ValueError('任务不存在')
        j=JOBS[ident]
        if j['status'] in ['queued','running']: j['cancel'].set()
        return public(j)


def submit(ident, body):
    with lifecycle.operation('提交视频任务'):
        doc=project.validate(project.load(ident))
        kind=body.get('kind')
        if kind not in ['preview','export','analyze','download']: raise ValueError('未知视频任务')
        if kind!='download':
            if (not doc['video'] and not doc.get('composition')) or (not video_audio.original(doc) and not doc['audio']): raise ValueError('请先准备画面并选择视频原声或外部混音，然后保存')
            settings.executable('ffmpeg'); settings.executable('ffprobe')
            if kind=='analyze' and video_audio.original(doc):raise ValueError('视频原声直接跟随画面，无需估计外部混音偏移')
            if kind=='analyze' and doc.get('composition'):raise ValueError('拼接模式以成品混音为时间基准；请直接试听音乐与字幕，不使用整曲 MV 偏移分析')
        if kind in ['preview','export']:
            errors=video_workflow.blockers(doc)
            if errors:raise ValueError('；'.join(errors))
        spec={}
        if kind=='preview':
            start=project.number(body.get('start',0),0,86400,'预览起点')
            end=project.number(body.get('end',start+8),start+.1,min(start+30,86400),'预览终点（最多 30 秒）')
            spec.update(start=start,end=end)
        if kind=='download':
            url=body.get('url','').strip()
            parsed=urlsplit(url)
            # Download sources are deliberately limited to public provider URLs, not local URLs.
            if parsed.scheme!='https' or parsed.hostname not in ['youtube.com','www.youtube.com','m.youtube.com','youtu.be','bilibili.com','www.bilibili.com','b23.tv'] or parsed.username or parsed.password or parsed.port:
                raise ValueError('请输入 YouTube 或 Bilibili 的 HTTPS 视频链接')
            if not dependencies()['download']: raise ValueError('缺少 yt-dlp。请按视频指南安装可选依赖，或导入已下载的视频')
            spec={'url':url,'height':int(project.number(body.get('height',1080),360,2160))}
        with LOCK:
            if sum(j['status'] in ['queued','running'] for j in JOBS.values())>=4: raise ValueError('视频队列已满，请等待或取消任务')
            jid=uuid.uuid4().hex
            minimum=max((int(j.get('version') or 0) for j in history(ident) if j.get('kind')==kind),default=0)+1
            folder,version=video_storage.reserve(project.output_folder(ident,True),kind,minimum)
            save_json(folder/'snapshot.json',doc)
            j=dict(id=jid,project=ident,kind=kind,status='queued',progress=0,stage='等待处理',message='',renderSignature=video_workflow.signature(doc),mediaSignature=video_workflow.media_signature(doc),
                   created=time.time(),folder=str(folder),version=version,spec=spec,files=[],snapshot=doc,cancel=threading.Event())
            if kind=='download':j['outputRoot']=str(folder.parent.parent)
            if kind in ['export','preview']:
                j['outputName']=video_storage.output_name(j,'mp4' if kind=='preview' else doc['format'])
            update(j)
            JOBS[jid]=j
            POOL.submit(run,j)
            return public(j)


def check(j):
    if j['cancel'].is_set(): raise Cancelled()


def command(j, args, progress_duration=None, stage='处理素材', timeout=3600):
    check(j)
    args=list(map(str,args))
    folder=Path(j['folder']); index=len(list(folder.glob('command-*.log')))
    log=folder/f'command-{index:02}.log'
    progress=folder/'progress.txt'
    if progress_duration:
        progress.unlink(missing_ok=True)
        args=[args[0],'-progress',str(progress),'-nostats',*args[1:]]
    update(j,stage=stage)
    with log.open('w',encoding='utf-8') as f:
        f.write(json.dumps(args,ensure_ascii=False)+'\n'); f.flush()
        p=subprocess.Popen(list(map(str,args)),cwd=folder,stdin=subprocess.DEVNULL,stdout=f,stderr=f,creationflags=FLAGS)
        with LOCK: j['process']=p
        began=time.monotonic()
        try:
            while p.poll() is None:
                check(j)
                if time.monotonic()-began>timeout: raise ValueError('任务超时；原文件保留，请缩短区间重试')
                if progress_duration and progress.exists():
                    text=progress.read_text(errors='replace')
                    values=re.findall(r'out_time_us=(\d+)',text)
                    if values: update(j,progress=min(99,round(int(values[-1])/1e6/progress_duration*100,1)))
                elif j['kind']=='download':
                    with log.open(encoding='utf-8',errors='replace') as current:
                        current.seek(max(0,log.stat().st_size-6000))
                        values=re.findall(r'\[download\]\s+(\d+(?:\.\d+)?)%',current.read())
                    if values:update(j,progress=min(99,float(values[-1])),stage='下载当前媒体流（之后会合并音视频）')
                j['cancel'].wait(.25)
            if p.returncode:
                detail=log.read_text(encoding='utf-8',errors='replace')[-1800:]
                raise ValueError(f'{stage}失败，详见本机日志。\n{detail}')
        finally:
            if p.poll() is None:
                if os.name=='nt':
                    # yt-dlp can own a muxing FFmpeg child; cancel that owned tree as well.
                    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=FLAGS)
                else: p.terminate()
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
            with LOCK: j.pop('process',None)
    return log.read_text(encoding='utf-8',errors='replace')


def ff(j,args,**kw):
    return command(j,[settings.executable('ffmpeg'),'-hide_banner','-nostdin','-n',*args],**kw)


def probe(j,path):
    text=command(j,[settings.executable('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',path],stage='读取媒体规格',timeout=60)
    # Log starts with the command line itself.
    info=json.loads(text.split('\n',1)[1]); streams=info.get('streams',[])
    duration=float(info.get('format',{}).get('duration',0))
    if not math.isfinite(duration) or duration<=0 or duration>86400: raise ValueError('媒体时长无效或超过 24 小时')
    return dict(duration=duration,streams=streams)


def measure(j,path,filters='',label='测量综合响度',target=-14,allow_silence=False):
    text=ff(j,['-i',path,'-vn','-af',(filters+',' if filters else '')+f'loudnorm=I={target}:TP=-1:LRA=11:print_format=json','-f','null','-'],stage=label)
    blocks=re.findall(r'\{\s*"input_i".*?\}',text,re.S)
    if not blocks: raise ValueError('未取得响度测量值')
    values=json.loads(blocks[-1])
    metrics={k:float(v) for k,v in values.items() if k!='normalization_type'}
    if not all(math.isfinite(v) for v in metrics.values()):
        if not allow_silence:raise ValueError('音轨过于安静，无法可靠匹配响度')
        return {k:v if math.isfinite(v) else None for k,v in metrics.items()}
    return metrics


def aligned(doc,duration):
    offset=doc['audioOffset']
    shift=f'adelay={offset*1000:.3f}:all=1' if offset>=0 else f'atrim=start={-offset:.6f},asetpts=PTS-STARTPTS'
    return f'aresample=48000,asetpts=PTS-STARTPTS,{shift},apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS'


def correlate(j,doc,duration):
    if not dependencies()['alignment']: return {'available':False,'note':'安装 numpy/scipy 后可分析音频偏移；当前仍可手动设置与试听。'}
    import numpy as np
    from scipy import signal
    folder=Path(j['folder'])
    arrays=[]
    # Bound memory and compare separated windows across the full arrangement.
    windows=[]
    length=min(12,max(2,duration/6))
    for start in [max(0,duration*.12),max(0,duration*.45),max(0,duration*.78)]:
        start=min(start,max(0,duration-length-25))
        arrays=[]
        for index,key in enumerate(['video','audio']):
            lo=max(0,start-20) if key=='video' else start
            n=length+40 if key=='video' else length
            raw=folder/f'align-{len(windows)}-{index}.f32'
            ff(j,['-ss',str(lo),'-i',doc[key],'-t',str(n),'-vn','-ac','1','-ar','6000','-f','f32le',str(raw)],stage='分段估算音频偏移')
            x=np.fromfile(raw,dtype='<f4');raw.unlink(missing_ok=True)
            if len(x)<6000: break
            _,_,z=signal.stft(x,6000,nperseg=512,noverlap=452)
            power=np.abs(z)**2
            bands=np.array([np.log(1e-9+power[a:b].sum(axis=0)) for a,b in [(3,12),(12,25),(25,50),(50,90),(90,160),(160,240)]])
            flux=np.maximum(np.diff(bands,axis=1,prepend=bands[:,:1]),0)
            flux=(flux-flux.mean(axis=1,keepdims=True))/(flux.std(axis=1,keepdims=True)+1e-8)
            arrays.append(flux)
        if len(arrays)!=2 or arrays[0].shape[1]<arrays[1].shape[1]: continue
        a,b=arrays;n=b.shape[1]
        energy=sum(signal.convolve(x*x,np.ones(n),mode='valid',method='fft') for x in a)
        corr=sum(signal.correlate(x,y,mode='valid',method='fft') for x,y in zip(a,b))/np.sqrt(np.maximum(energy*(b*b).sum(),1e-12))
        best=int(np.argmax(corr)); score=float(corr[best]); offset=max(0,start-20)+best*.01-start
        windows.append({'audioStart':round(start,3),'offset':round(offset,3),'correlation':round(score,3)})
        check(j)
    offsets=[w['offset'] for w in windows]; spread=max(offsets)-min(offsets) if offsets else 999
    reliable=len(windows)==3 and min(w['correlation'] for w in windows)>.35 and spread<.08
    return {'available':True,'windows':windows,'suggestedOffset':round(float(np.median(offsets)),3) if offsets else None,
            'spreadSeconds':round(spread,3),'consistent':reliable,
            'note':'仅在编曲相同且多段结果一致时作为固定偏移候选。未自动更改；请试听开头、中段、结尾。重复段落或编曲变化可能误配。'}


def render(j):
    doc=j['snapshot']; folder=Path(j['folder'])
    if video_workflow.signature(doc)!=j['renderSignature']:raise ValueError('排队后素材发生变化，请重新提交任务')
    composition=doc.get('composition')
    source_original=video_audio.original(doc)
    ai=None if source_original else probe(j,doc['audio'])
    if composition:
        vi={'duration':composition['duration'],'streams':[{'codec_type':'video','width':1920,'height':1080}]}
    else:vi=probe(j,doc['video'])
    duration=vi['duration']
    video=next((s for s in vi['streams'] if s['codec_type']=='video'),None)
    if not video: raise ValueError('所选视频没有画面流')
    if not source_original and not any(s['codec_type']=='audio' for s in ai['streams']): raise ValueError('翻唱素材没有音频流')
    warnings=project.warnings(doc,duration)
    project.write_subtitles(doc,folder,duration)
    from video_edit import sources, build_picture
    input_paths=(sources(doc) if composition else [doc['video']])+([] if source_original else [doc['audio']])
    before={p:sha(p) for p in dict.fromkeys(input_paths)}
    if not source_original and doc['audioOffset']+ai['duration']>duration+.1: warnings.append({'id':'audio','messages':['视频以原时长结束，尾部音频可能被裁切，请试听结尾']})
    if j['kind']=='analyze':
        reference=measure(j,doc['video'],label='测量原视频响度')
        cover=measure(j,doc['audio'],aligned(doc,duration),label='测量对齐翻唱响度')
        report={'reference':reference,'cover':cover,'suggestedGainDb':round(reference['input_i']-cover['input_i'],2),'mediaSignature':j['mediaSignature'],
                'suggestedTargetLufs':max(-30,min(-5,reference['input_i'])),'alignment':correlate(j,doc,min(duration,ai['duration'])),
                'warnings':warnings,'inputs':before,'note':'响度匹配可能需要限制峰值；提升响度会改变动态，应用前请试听。'}
        if any(sha(p)!=h for p,h in before.items()):raise ValueError('分析期间素材发生变化，请保存源文件后重试')
        save_json(folder/'analysis.json',report)
        update(j,result=report,files=['analysis.json','captions.ass','captions.srt']); return
    is_preview=j['kind']=='preview'
    start=j['spec'].get('start',0); end=min(duration,j['spec'].get('end',duration))
    if start>=end: raise ValueError('预览区间超出视频长度')
    picture=build_picture(j,start,end,ff,update) if composition else doc['video']
    temporary_audio=[];audio_details=None
    if source_original:
        audio_path,audio_details,temporary_audio=video_audio.build(j,start,end,ff,probe,update)
        ai=probe(j,audio_path);base='aresample=48000,asetpts=PTS-STARTPTS';audio_first=0;audio_last=end-start
    else:
        audio_path=doc['audio'];base=aligned(doc,duration);audio_first=start;audio_last=end
    measured=None
    if source_original: pass
    elif doc['audioMode']=='normalize':
        measured=measure(j,doc['audio'],base,label='响度处理第一遍测量',target=doc['targetLufs'])
        base+=f",loudnorm=I={doc['targetLufs']}:TP=-1:LRA=11:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true"
    else:
        # Oversampled limiter catches intersample peaks; always remeasure encoded output.
        base+=f",aresample=192000,volume={doc['gainDb']}dB,alimiter=limit=0.794328:level=false:latency=true,aresample=48000"
    base+=f',atrim=start={audio_first}:end={audio_last},asetpts=PTS-STARTPTS'
    vfilter=[]
    if composition:vfilter.append(f'setpts=PTS+{start}/TB')
    # Normalize SAR/rotation to a display canvas before positioning ASS subtitles.
    vfilter.append("scale=w='trunc(iw*sar/2)*2':h='trunc(ih/2)*2',setsar=1")
    height=720 if is_preview else int(doc['resolution']) if doc['resolution']!='source' else None
    if height: vfilter.append(f'scale=-2:{height}')
    if doc['burn']: vfilter.append('ass=captions.ass')
    vfilter += [f'trim=start={start}:end={end}','setpts=PTS-STARTPTS']
    if not is_preview and doc['fps']!='source': vfilter.append('fps='+doc['fps'])
    ext='mp4' if is_preview else doc['format']
    partial=folder/('preview.rendering.'+ext if is_preview else 'video.rendering.'+ext)
    output=folder/j.get('outputName',video_storage.output_name(j,ext))
    args=['-i',picture,'-i',audio_path,'-map','0:v:0','-map','1:a:0','-vf',','.join(vfilter),'-af',base,
          '-c:v','libx264','-preset','veryfast' if is_preview else 'medium','-crf',str(21 if is_preview else doc['crf']),
          '-pix_fmt','yuv420p','-fps_mode','cfr' if composition else 'passthrough' if is_preview or doc['fps']=='source' else 'cfr',
          '-c:a','aac','-b:a','320k','-ar','48000','-t',str(end-start),'-map_metadata','-1']
    if composition:
        # trim/setpts can clear the final packet duration; explicit CFR preserves its frame.
        rate=doc['composition']['fps'] if is_preview or doc['fps']=='source' else int(doc['fps'])
        args+=['-r',str(rate)]
    if ext=='mp4': args+=['-movflags','+faststart']
    args+=[str(partial)]
    ff(j,args,progress_duration=end-start,stage='渲染准确区间预览' if is_preview else '合成新版本视频')
    update(j,progress=99)
    ff(j,['-v','error','-err_detect','explode','-i',str(partial),'-map','0:v:0','-map','0:a:0','-f','null','-'],stage='整段解码检查')
    output_info=probe(j,partial)
    if abs(output_info['duration']-(end-start))>.2: raise ValueError('导出时长与预期不符')
    loudness=measure(j,partial,label='复测编码后的响度与真峰值',allow_silence=True)
    if loudness['input_i'] is None:warnings.append({'id':'silence','messages':['该区间静音或太短，无法测得有效综合响度；可以继续检查画面']})
    if loudness['input_tp'] is not None and loudness['input_tp']>-.5: warnings.append({'id':'peak','messages':['编码后真峰值高于 −0.5 dBTP，建议降低增益或目标响度后重导']})
    after={p:sha(p) for p in before}
    if after!=before: raise ValueError('渲染期间源文件发生变化，结果未确认为成片，请保存源文件后重试')
    report=dict(status='complete',revision=doc['revision'],inputs=before,sourceUnchanged=True,sourceVideo=vi,sourceAudio=ai,
                renderSignature=j['renderSignature'],
                output=output_info,loudness=loudness,warnings=warnings,start=start,end=end,
                subtitleClock='video seconds; subtitleShift applied once',audioOffset=0 if source_original else doc['audioOffset'],audioSource=doc.get('audioSource','mix'),sourceAudioPlan=audio_details,
                audioMode='original-level' if source_original else doc['audioMode'],measured=measured,limitations='Decode, duration, hash and loudness checks; final listening/translation review remains manual.')
    check(j); partial.rename(output)
    report['sha256']=sha(output)
    save_json(folder/'report.json',report)
    if composition:
        # These names are created exclusively by this job; keep user media and snapshots.
        for temp in [folder/'picture.mkv', folder/'picture-sequence.txt', *folder.glob('Picture [0-9][0-9][0-9].mkv')]:
            try:
                if temp.is_file():temp.unlink()
            except OSError:pass
    for temp in temporary_audio:
        try:temp.unlink(missing_ok=True)
        except OSError:pass
    update(j,result=report,files=[output.name,'captions.ass','captions.srt','caption-timing.json','snapshot.json','report.json'])


def download(j):
    folder=Path(j['folder']); spec=j['spec']
    root=Path(j.get('outputRoot') or project.output_folder(j['project'])).resolve()
    if not re.fullmatch(r'[0-9a-f]{32}',j['id']):raise ValueError('无效下载任务编号')
    staging=root/'Cache/Downloads'/j['id']
    if not staging.resolve().is_relative_to(root):raise ValueError('下载缓存目录指向工程外部')
    staging.mkdir(parents=True,exist_ok=True)
    command_start=[shutil.which('yt-dlp')] if shutil.which('yt-dlp') else [sys.executable,'-m','yt_dlp']
    args=command_start+['--ignore-config','--no-playlist','--no-overwrites','--no-mtime','--newline','--write-info-json',
          '--socket-timeout','20','--retries','2','--ffmpeg-location',str(Path(settings.executable('ffmpeg')).parent),
          '-f',f"bv*[height<={spec['height']}]+ba/b[height<={spec['height']}]",'--merge-output-format','mkv',
          '-o',str(staging/'source.%(ext)s'),'--',spec['url']]
    command(j,args,stage='yt-dlp 下载视频（耗时取决于网络）',timeout=1800)
    media=[p for p in staging.glob('source.*') if p.suffix in ['.mkv','.mp4','.webm'] and p.is_file()]
    if len(media)!=1: raise ValueError('下载未生成唯一视频，请查看本机日志')
    if not (staging/'source.info.json').is_file():raise ValueError('下载缺少网站标题信息，请查看下载记录')
    details=read_json(staging/'source.info.json')
    if not isinstance(details,dict):raise ValueError('下载标题信息格式无效，请查看下载记录')
    title=details.get('title')
    # Validate the provider's title as data, never interpolate it into a shell command.
    media_names.filename(title,media[0].suffix)
    info=probe(j,media[0])
    if not any(s.get('codec_type')=='video' for s in info['streams']):raise ValueError('下载结果没有视频画面')
    save_json(folder/'info.json',details)
    target,reused=publish_download(j,media[0],root/'Media/Video',title)
    digest=sha(target)
    save_json(folder/'provenance.json',{'url':spec['url'],'title':title,'path':str(target),'sha256':digest,'metadata':info})
    update(j,files=['info.json','provenance.json'],result={'path':str(target),'name':target.name,'title':title,
           'mediaFolder':str(target.parent),'sha256':digest,'reused':reused,
           'note':'下载完成。视频保存在 Media/Video；点击使用此视频后才会更新当前工程。'})
    # Only remove this job's known transient files; never recursively delete a user directory.
    if staging.resolve().parent==(root/'Cache/Downloads').resolve():
        for temp in staging.glob('source.*'):
            try:
                if temp.is_file():temp.unlink()
            except OSError:pass
        try:staging.rmdir()
        except OSError:pass


def publish_download(j,source,directory,title):
    """Exclusive creation prevents concurrent downloads from overwriting user media."""
    root=Path(j.get('outputRoot') or project.output_folder(j['project'])).resolve()
    directory=directory.resolve()
    if not directory.is_relative_to(root):raise ValueError('素材目录指向工程外部')
    directory.mkdir(parents=True,exist_ok=True)
    digest=sha(source);version=1
    while True:
        check(j)
        target=directory/media_names.filename(title,source.suffix,version)
        try:
            stream=target.open('xb')
        except FileExistsError:
            try:
                if target.resolve().is_relative_to(directory) and target.is_file() and sha(target)==digest:return target,True
            except OSError:pass
            version+=1;continue
        try:
            with stream,source.open('rb') as original:
                while block:=original.read(1024*1024):
                    check(j);stream.write(block)
            check(j)
            if sha(target)!=digest or sha(source)!=digest:raise ValueError('视频在归档期间发生变化，请重新下载')
            return target,False
        except BaseException:
            target.unlink(missing_ok=True)
            raise


def run(j):
    try:
        with lifecycle.operation('视频下载或渲染'):
            check(j);update(j,status='running',stage='准备输入')
            (download if j['kind']=='download' else render)(j)
            check(j);update(j,status='completed',progress=100,stage='完成')
    except Cancelled: update(j,status='cancelled',stage='已取消',message='任务已停止，原素材和已完成版本保留。')
    except Exception as e: update(j,status='failed',stage='失败',message=str(e))
    finally:
        for p in Path(j['folder']).glob('*.rendering.*'): p.unlink(missing_ok=True)


def media(ident,jid,name):
    for location in project.output_locations(ident):
        try:
            dest,j=video_storage.locate(location,jid)
            break
        except ValueError:
            continue
    else:
        raise ValueError('任务版本不存在')
    # Canonical old media URLs remain aliases after renaming an existing version.
    aliases={}
    output=j.get('outputName','')
    if output and Path(output).name==output and '/' not in output and '\\' not in output:
        aliases[('preview.' if j['kind']=='preview' else 'video.')+Path(output).suffix.lstrip('.')]=output
    allowed=['preview.mp4','video.mp4','video.mkv','captions.ass','captions.srt','caption-timing.json','report.json','snapshot.json','analysis.json',*aliases.values()]
    if name not in allowed:
        raise ValueError('文件不可下载')
    actual=aliases.get(name,name)
    if j['status']=='completed' and actual in j['files']: return dest/actual
    raise ValueError('文件尚未完成')


def source(ident,role):
    if role not in ['video','audio']: raise ValueError('未知素材')
    doc=project.load(ident)
    return project.local(doc[role],project.MEDIA)
