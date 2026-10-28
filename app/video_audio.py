"""Selected output audio: a separate mix, or the visible video clips on the picture clock."""
from pathlib import Path
import video_tracks as tracks


def original(doc):
    return doc.get('audioSource', 'mix') == 'video'


def segments(doc, duration=None):
    comp = doc.get('composition')
    if not comp:
        return [{'start':0,'end':duration or 0,'path':doc.get('video'),'in':0,'asset':None}]
    fps=comp['fps'];visible=tracks.visible_clips(comp)
    points=sorted({0,round(comp['duration']*fps),*(round(t*fps) for c in visible for t in (c['start'],c['start']+c['duration']))})
    rows=[]
    for first,last in zip(points,points[1:]):
        # Audio hard-cuts at actual clip boundaries; picture dissolves/fades stay picture-only.
        clip=None
        for track in reversed(tracks.tracks(comp)):
            if track.get('hidden'): continue
            clip=next((c for c in tracks.clips_on(comp,track['id']) if round(c['start']*fps)<=first<round((c['start']+c['duration'])*fps)),None)
            if clip: break
        asset=next((a for a in comp['assets'] if clip and a['id']==clip['asset']),None)
        rows.append({'start':first/fps,'end':last/fps,'path':asset['path'] if asset and asset['kind']=='video' else None,
                     'in':clip['in']+(first/fps-clip['start']) if asset and asset['kind']=='video' else 0,'asset':asset})
    return rows


def paths(doc):
    return list(dict.fromkeys(row['path'] for row in segments(doc) if row['path']))


def available(doc):
    """Cheap readiness without launching decoders on every UI edit; render probes authoritative streams."""
    if not original(doc): return bool(doc.get('audio') and Path(doc['audio']).is_file())
    return any(row['path'] and Path(row['path']).is_file() and (row['asset'] or {}).get('hasAudio') is not False for row in segments(doc))


def build(job, start, end, execute, probe, update):
    doc=job['snapshot'];folder=Path(job['folder']);rows=segments(doc,end);metadata={}
    for path in dict.fromkeys(row['path'] for row in rows if row['path']):
        metadata[path]=probe(job,path)
    if not any(any(s['codec_type']=='audio' for s in info['streams']) for info in metadata.values()):
        raise ValueError('当前可见视频都没有音轨，请选择含音轨的视频或使用外部混音')
    entries=[];rendered=[];silent=[]
    for row in rows:
        a,b=max(start,row['start']),min(end,row['end'])
        if b<=a: continue
        count=round(b*48000)-round(a*48000);length=count/48000
        info=metadata.get(row['path']);has_audio=bool(info and any(s['codec_type']=='audio' for s in info['streams']))
        name=f'Original Audio {len(rendered)+1:03}.wav';target=folder/name
        if has_audio:
            begin=max(0,row['in']+a-row['start'])
            args=['-ss',f'{begin:.9f}','-i',row['path'],'-map','0:a:0','-vn']
        else:
            args=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo'];silent.append([a,b])
        args+=['-af',f'aresample=48000:async=1:first_pts=0,apad,atrim=end_sample={count},asetpts=PTS-STARTPTS',
               '-ac','2','-ar','48000','-c:a','pcm_f32le','-t',f'{length:.9f}',target]
        execute(job,args,stage='组装可见视频的原声');rendered.append(target)
        entries.append("file '"+name+"'")
        update(job,stage=f'组装视频原声 {len(rendered)} 段')
    listing=folder/'original-audio-sequence.txt';listing.write_text('\n'.join(entries),encoding='utf-8')
    output=folder/'original-audio.wav'
    execute(job,['-f','concat','-safe','0','-i',listing,'-c:a','copy',output],stage='连接视频原声音轨')
    return output,{'mode':'video','segments':rows,'silentRanges':silent,'start':start,'end':end,
                   'timing':'Visible clips, source in-points and trims; no external mix offset or gain; picture-only transitions'},[*rendered,listing,output]
