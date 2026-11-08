"""Create raw/RMS-matched SV1 audition projects and measured CSV from a benchmark."""
from pathlib import Path
import argparse,csv,json,sys,math,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import read_json,save_json,sha
from sv_starter import track

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',required=True);args=parser.parse_args();base=Path(args.folder).resolve()
    if not base.is_relative_to((ROOT/'projects').resolve()):raise ValueError('Auditions must stay inside a workbench comparison project')
    if list((base/'working/sv').glob('*.svp')):raise ValueError('已有试听工程，拒绝覆盖；请先选择新的对比工程副本目录')
    import numpy as np,soundfile as sf
    doc=read_json(base/'analysis/Benchmark.json');songs=doc['songs'];results=doc['results'];rate=44100
    # A measured capacity limit is an experiment result, not missing promised audio.
    # Keep it in the report; only successfully rendered stems enter the auditions.
    required_failures=[f for f in doc.get('failures',[]) if f.get('modelId')!='unmixx' and f.get('category')!='capacity']
    if required_failures:raise ValueError('常规模型仍有失败，请先重新运行缺少的模型再生成试听工程；已有文件保持不变')
    plan=read_json(base/'analysis/Plan.json') if (base/'analysis/Plan.json').is_file() else {'songs':[]}
    for song in songs:
        source=next((s for s in plan['songs'] if s['id']==song['id']),{})
        song['displayName']=source.get('displayName',song['label'])
    for row in results:
        if row.get('inputAudio'):continue
        if row.get('kind')=='song':row['inputAudio']=next(s['original'] for s in songs if s['id']==row['song'])
        elif row.get('kind') in ('harmony','singers'):
            baseline=next((r for r in results if r['song']==row['song'] and r['modelId']=='big7'),None)
            if baseline:row['inputAudio']=baseline['outputs']['vocals']
    for s in plan['songs']:
        if not s.get('archived') or any(r['song']==s['id'] and r['modelId']=='archived-msst' for r in results):continue
        outputs={};records={}
        for role,value in s['archived'].items():
            source=Path(value);before=sha(source);target=base/'separation'/s['label']/'Archived MSST'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(source,target)
            if sha(target)!=before or sha(source)!=before:raise ValueError('Archived reference changed during copy')
            outputs[role]=str(target.relative_to(base));records[role]={'source':str(source),'sha256':before}
        results.append({'song':s['id'],'modelId':'archived-msst','name':'Archived MSST - Existing Results','kind':'pipeline','engine':'archived','outputs':outputs,'metrics':{},'wallSeconds':None,'audioSeconds':next(x['duration'] for x in songs if x['id']==s['id']),'inputRole':'Archived original-project stems; historical timing/parameters unknown','modelSHA256':'','provenance':records})
    def stats(path):
        total=0.;count=0;peak=0.
        for block in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):
            if not np.isfinite(block).all():raise ValueError('Non-finite samples: '+str(path))
            total+=float(np.sum(block.astype('float64')**2));count+=block.size;peak=max(peak,float(np.max(np.abs(block))))
        return {'rms':math.sqrt(total/count) if count else 0.,'samplePeak':peak}
    for row in results:
        row['levels']={};row['matched']={}
        expected=sf.info(base/next(s['original'] for s in songs if s['id']==row['song']))
        for role,file in row['outputs'].items():
            info=sf.info(base/file)
            if info.samplerate!=rate or info.channels!=2 or abs(info.frames-expected.frames)>1:raise ValueError('Output format/duration differs: '+file)
            row['levels'][role]=stats(base/file)
    for song in songs:
        for role in dict.fromkeys(role for r in results if r['song']==song['id'] for role in r['outputs']):
            group=[r for r in results if r['song']==song['id'] and role in r['outputs']]
            if not group:continue
            reference=next((r for r in group if r['modelId']==('big7' if role in ['vocals','accompaniment'] else 'mel-karaoke')),group[0]);target=reference['levels'][role]['rms']
            max_peak=max((r['levels'][role]['samplePeak']*target/r['levels'][role]['rms'] for r in group if r['levels'][role]['rms']>1e-10),default=0)
            if max_peak>10**(-3/20):target*=10**(-3/20)/max_peak
            for row in group:
                level=row['levels'][role];gain=target/level['rms'] if level['rms']>1e-10 else 1.
                source=(base/row['outputs'][role]).resolve()
                if not source.is_relative_to(base):raise ValueError('Model output is outside the owned comparison folder')
                dest=base/'separation'/song['label']/row['modelId']/'Matched'/source.name;dest.parent.mkdir(parents=True,exist_ok=True)
                # Derivatives only; raw model outputs are never normalized in place.
                with sf.SoundFile(source) as original,sf.SoundFile(dest,'w',samplerate=rate,channels=2,subtype='PCM_24') as output:
                    for block in original.blocks(blocksize=65536,dtype='float32',always_2d=True):output.write(block*gain)
                row['matched'][role]=str(dest.relative_to(base));level.update(matchedGainDb=20*math.log10(gain) if gain else 0,targetRMS=target,matchedSamplePeak=level['samplePeak']*gain)
    folder=base/'working/sv';folder.mkdir(parents=True,exist_ok=True);media=folder/'Media';media.mkdir(exist_ok=True)
    labels={'vocals':'完整人声','accompaniment':'伴奏','lead':'主声','harmony':'和声 / 其余人声','singer1':'实验人声 A','singer2':'实验人声 B'}
    colors={None:'ff54a5af','vocals':'ff8c71ce','accompaniment':'ff5996cd','lead':'ffe48bb5','harmony':'ffe6a25f','singer1':'ff6faa91','singer2':'ffd6b45c'}
    offset=0;timeline=[]
    for song in songs:
        info=sf.info(base/song['original']);timeline.append({'song':song['id'],'name':song['displayName'],'start':offset/rate,'end':(offset+info.frames)/rate});offset+=info.frames+rate*6
    total_frames=offset-rate*6
    families=[('original','Original Songs',None)];seen=set()
    for row in results:
        for role in row['outputs']:
            key=(row['modelId'],role)
            if key not in seen:families.append((row['modelId'],row['name']+' - '+role,role));seen.add(key)
    def document(tracks,bpm=120):return {'version':153,'time':{'tempo':[{'position':0,'bpm':bpm}],'meter':[{'index':0,'numerator':4,'denominator':4}]},'library':[],'tracks':tracks,'renderConfig':{'destination':str(base/'exports/audio'),'filename':'Comparison','numChannels':2,'sampleRate':44100,'bitDepth':24,'exportMixDown':True,'aspirationFormat':'noAspiration'}}
    for matched in [False,True]:
        tracks=[]
        for number,(model,label,role) in enumerate(families):
            dest=media/(str(number).zfill(2)+' - '+model+(' - '+role if role else '')+(' - Matched' if matched else ' - Raw')+'.wav')
            with sf.SoundFile(dest,'w',samplerate=rate,channels=2,subtype='PCM_24' if matched and model!='original' else 'FLOAT') as output:
                for index,song in enumerate(songs):
                    row=next((r for r in results if r['song']==song['id'] and r['modelId']==model and role in r['outputs']),None)
                    path=base/song['original'] if model=='original' else base/row['matched' if matched else 'outputs'][role] if row else None
                    if path:
                        for block in sf.blocks(path,blocksize=65536,dtype='float32',always_2d=True):output.write(block)
                    else:
                        remaining=sf.info(base/song['original']).frames
                        while remaining:
                            n=min(remaining,65536);output.write(np.zeros((n,2),dtype='float32'));remaining-=n
                    if index<len(songs)-1:output.write(np.zeros((rate*6,2),dtype='float32'))
            assert sf.info(dest).frames==total_frames
            display='原曲（按歌曲顺序）' if role is None else labels.get(role,role)+' · '+label.rsplit(' - ',1)[0]
            tracks.append(track(str(number).zfill(2)+' '+display,number,'sv1',dest,total_frames/rate,muted=number!=0));tracks[-1]['dispColor']=colors.get(role,'ff8c71ce')
        save_json(folder/('Model Comparison.svp' if matched else 'Model Comparison - Raw.svp'),document(tracks))
        for song in songs:
            tracks=[track('00 原曲',0,'sv1',base/song['original'],song['duration'])];tracks[0]['dispColor']=colors[None]
            for row in [r for r in results if r['song']==song['id']]:
                for role,file in row['matched' if matched else 'outputs'].items():
                    tracks.append(track(labels.get(role,role)+' · '+row['name'],len(tracks),'sv1',base/file,song['duration'],muted=True));tracks[-1]['dispColor']=colors.get(role,'ff8c71ce')
            save_json(folder/(song['label']+(' - Matched.svp' if matched else ' - Raw.svp')),document(tracks,song['bpm']))
    reports=base/'exports/reports';reports.mkdir(parents=True,exist_ok=True)
    fields=['song','model','engine','input','batchSize','tta','audioSeconds','wallSeconds','modelLoadSeconds','inferenceAndWriteSeconds','cudaPeakAllocatedMiB','cudaPeakReservedMiB','devicePeakMemoryMiB','deviceMemoryStartMiB']
    with (base/'exports/reports/Performance.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['歌曲','模型','引擎','输入','Batch size','TTA','音频时长 (s)','整任务耗时 (s)','模型加载 (s)','推理和写盘 (s)','CUDA 分配峰值 (MiB)','CUDA 保留峰值 (MiB)','设备总峰值 (MiB)','设备起始 (MiB)'])
        for row in results:
            record={k:row['metrics'].get(k,'') for k in fields};record.update(song=next(s['displayName'] for s in songs if s['id']==row['song']),model=row['name'],engine=row['engine'],input=row['inputRole'],audioSeconds=row['audioSeconds'],wallSeconds=row['wallSeconds']);writer.writerow([round(record[k],2) if isinstance(record[k],(float,int)) else record[k] for k in fields])
    if doc.get('failures'):
        with (reports/'Failures.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['歌曲','模型 / 设置','失败类型','日志'])
            for row in doc['failures']:writer.writerow([row['song'],row.get('name',row['modelId']),row.get('category','runtime'),row.get('error','')])
    protected=read_json(base/'analysis/Protected Sources.json');changed=[p for p,h in protected.items() if not Path(p).is_file() or sha(Path(p))!=h]
    if changed:raise ValueError('Protected source changed outside this comparison: '+str(changed))
    doc['sourceValidation']=read_json(base/'analysis/Source Validation.json') if (base/'analysis/Source Validation.json').is_file() else {}
    doc.update(status='completed',current='',svp=str(folder/'Model Comparison.svp'),timeline=timeline,levelMatching='Whole-song RMS per same-role group, same target per song; shared sample-peak ceiling -3 dBFS. PCM24 audition derivatives; original float stems retained.',verified={'protectedFiles':len(protected),'changed':0,'results':len(results),'frames':total_frames,'sampleRate':rate})
    save_json(base/'analysis/Benchmark.json',doc)
    lines=['# 模型对比试听','', '打开 `working/sv/Model Comparison.svp`：歌曲依次排列，模型轨道严格对齐。','', '默认只打开原曲轨。先将原曲 M 静音，再取消需要试听轨的 M；需要用 S 独听时，请先取消该轨的 M。每次只听一条，避免重复叠加。','', '配平版按每首歌、同类声部的整体 RMS 匹配，保留公共 -3 dBFS 样本峰值余量；不是 EBU 响度标准化。Raw 工程保留模型原始电平。','', doc.get('method','具体 batch、TTA、重叠和输入以 Benchmark.json 各条测量记录为准。'),'', '耗时为单次本机实测，不是多轮平均；设备显存包含其他软件。失败项留在报告中，不生成虚假的试听轨道。','', '主声/和声表示声部分离，不等于按歌手身份分轨。没有真实干净分轨参考，不计算 SDR 或自动排名。','', '## 时间导航','']
    lines += [f"- {x['name']}：{int(x['start']//60):02}:{x['start']%60:06.3f} — {int(x['end']//60):02}:{x['end']%60:06.3f}" for x in timeline]
    lines += ['', '也可打开同目录下每首歌单独的 Matched / Raw 工程；所有引用均指向此对比目录，不引用或更改原音乐工程。', '', '网页入口：工作台 → 素材分离 → 模型对比试听。', '', '测量表：`exports/reports/Performance.csv`；详细配置、显存与原文件校验：`analysis/Benchmark.json`、`analysis/Protected Sources.json`。']
    (base/'Read Me.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(doc['verified']),str(folder/'Model Comparison.svp'))

if __name__=='__main__':main()
