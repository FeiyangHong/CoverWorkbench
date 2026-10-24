"""Video readiness checks and explicit timing provenance; no writes to source media."""
import copy
import hashlib
import json
import importlib.util
import shutil
from pathlib import Path

import settings
import video_project as project

FIELDS = {'video','audio','audioOffset','subtitleShift','gainDb','targetLufs','audioMode','resolution','fps','format','crf','burn','styles','cues'}


def digest(value):
    def canonical(v):
        if isinstance(v,dict):return {k:canonical(x) for k,x in v.items()}
        if isinstance(v,list):return [canonical(x) for x in v]
        if isinstance(v,(int,float)) and not isinstance(v,bool):return round(float(v),6)
        return v
    return hashlib.sha256(json.dumps(canonical(value),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def file_key(value):
    try:
        text=project.clean_path(value);p=Path(text)
        if not p.is_absolute() or text.startswith(('\\\\','//')):return ''
        p=p.resolve()
        s=p.stat()
        return digest([str(p),s.st_size,s.st_mtime_ns]) if p.is_file() else ''
    except (OSError,ValueError):return ''


def timing(doc,clock,source='confirmed'):
    return {'clock':clock,'source':source,'audioKey':file_key(doc.get('audio')),'videoKey':file_key(doc.get('video')),
            'appliedAudioOffset':doc['audioOffset'] if clock=='audio' else 0}


def reconcile(current,doc):
    """Materialized video timestamps follow the audio by the delta, exactly once."""
    state=copy.deepcopy(current.get('timing',{}))
    if doc.get('cues') and state.get('clock')=='audio':
        linked=(state.get('audioKey')==file_key(doc.get('audio')) and state.get('videoKey')==file_key(doc.get('video')))
        if linked:
            delta=round(doc['audioOffset']-state['appliedAudioOffset'],6)
            if abs(delta)>.000001:
                if any(r['start']+delta<0 for r in doc['cues']):
                    raise ValueError('跟随音频移动后有字幕早于零秒；请先调整首句，或确认字幕改用固定视频时间')
                for row in doc['cues']:
                    row['start']=round(row['start']+delta,6);row['end']=round(row['end']+delta,6)
                state['appliedAudioOffset']=doc['audioOffset']
                state.pop('ackShift',None)
    doc['timing']=state
    return doc


def signature(doc):
    return digest({'document':{k:doc.get(k) for k in FIELDS},'video':file_key(doc.get('video')),'audio':file_key(doc.get('audio'))})


def alignment_signature(doc):
    return digest([file_key(doc.get('video')),file_key(doc.get('audio')),doc.get('audioOffset')])


def media_signature(doc):
    return digest([file_key(doc.get('video')),file_key(doc.get('audio'))])


def blockers(doc):
    errors=[];state=doc.get('timing',{});offset=float(doc.get('audioOffset',0));shift=float(doc.get('subtitleShift',0))
    aligned=doc.get('workflow',{}).get('alignedAudio')
    if aligned and aligned==file_key(doc.get('audio')) and abs(offset)>.000001:
        errors.append('此音轨已标记为对齐视频，音频偏移应为 0；请清零，或取消已对齐标记')
    if not doc.get('cues'):return errors
    if state.get('clock') not in ['audio','video']:
        errors.append('字幕时间基准尚未确认：请选择字幕已是视频时间，或重新导入并指定混音时间')
    elif state.get('audioKey')!=file_key(doc.get('audio')) or state.get('videoKey')!=file_key(doc.get('video')):
        errors.append('素材已更换或被覆盖，请重新确认当前字幕使用的视频时间基准')
    if state.get('clock')=='audio' and abs(state.get('appliedAudioOffset',0))>.02 and abs(shift-state['appliedAudioOffset'])<.02 and state.get('ackShift')!=shift:
        errors.append(f"字幕已包含音频偏移 {state['appliedAudioOffset']:+.3f} 秒；字幕整体移动又是 {shift:+.3f} 秒，可能重复添加。请清零或明确确认这是额外微调")
    return errors


def checks(doc,jobs):
    ready={k:bool(file_key(doc.get(k))) for k in ['video','audio']}
    tools=bool(settings.executable('ffmpeg',False) and settings.executable('ffprobe',False))
    state=doc.get('timing',{});review=doc.get('workflow',{})
    errors=blockers(doc)
    rows=doc.get('cues',[])
    invalid=[]
    for row in rows:
        try:
            a=project.number(row['start'],0,86400);b=project.number(row['end'],0,86400)
            if b<=a:raise ValueError()
        except (ValueError,KeyError):invalid.append(row.get('id','?'))
    has_original=any(r.get('original','').strip() for r in rows)
    has_translation=any(r.get('translation','').strip() for r in rows)
    sig=signature(doc)
    matching=[j for j in jobs if j.get('status')=='completed' and j.get('result',{}).get('renderSignature')==sig]
    previews=[j for j in matching if j.get('kind')=='preview']
    exports=[j for j in matching if j.get('kind')=='export']
    steps=[]
    def add(ident,title,missing,detail):steps.append({'id':ident,'title':title,'done':not missing,'missing':missing,'detail':detail})
    missing_mv=[] if ready['video'] else ['下载并使用 MV，或选择存在的本地视频']
    if not ready['video'] and not (shutil.which('yt-dlp') or importlib.util.find_spec('yt_dlp')):
        missing_mv.append('链接下载需要可选视频工具；也可直接使用本地 MV')
    add('mv','获取 MV',missing_mv,'本地素材也可直接完成这一步')
    add('mix','导入混音',[] if ready['audio'] else ['选择 Studio One 最终混音文件'],'请使用人声与伴奏已混好的版本')
    needs=[]
    if not all(ready.values()):needs.append('先准备 MV 和最终混音')
    if review.get('alignment')!=alignment_signature(doc):needs.append('比较开头、中段、结尾后，确认声音已对齐')
    add('align','对齐声音',needs,'分析提供候选；试听确认记录会在素材或偏移改变后失效')
    needs=[]
    if not has_original:needs.append('导入或填写原文字幕')
    if not has_translation and not review.get('singleLanguage'):needs.append('补充译文，或明确选择只用单语字幕')
    needs+=errors
    if invalid:needs.append('修正无效时间：'+', '.join(invalid[:5]))
    add('captions','双语字幕',needs,'字幕表统一显示视频时间；跟随混音的字幕只移动偏移差值')
    needs=[]
    if not tools:needs.append('在环境设置配置 FFmpeg 与 FFprobe')
    if not previews:needs.append('当前素材、字幕和参数还没有准确预览；旧预览不会自动算作新版')
    elif review.get('preview')!=sig:needs.append('播放本版准确预览后，确认字幕与声音已检查')
    add('preview','预览检查',needs,'修改文字、时间、样式或音频处理后，需重新生成预览')
    add('export','导出成片',[] if exports else ['当前版本尚未完整导出'],'每次导出创建独立目录，保留旧成片')
    pending_delta=0
    if state.get('clock')=='audio' and state.get('audioKey')==file_key(doc.get('audio')) and state.get('videoKey')==file_key(doc.get('video')):
        pending_delta=round(float(doc.get('audioOffset',0))-state.get('appliedAudioOffset',0),6)
    return {'steps':steps,'completed':sum(s['done'] for s in steps),'blockers':errors,'invalid':invalid,
            'analysisIds':[j['id'] for j in jobs if j.get('kind')=='analyze' and j.get('status')=='completed' and j.get('result',{}).get('mediaSignature')==media_signature(doc)],
            'audioAligned':bool(review.get('alignedAudio') and review['alignedAudio']==file_key(doc.get('audio'))),
            'captionClock':state.get('clock','unknown'),'appliedAudioOffset':state.get('appliedAudioOffset',0),
            'pendingDelta':pending_delta,'renderSignature':sig,'previewReady':bool(previews),'exportReady':bool(exports)}


def review(ident,body):
    with project.LOCK:
        doc=project.load(ident)
        if doc['revision']!=body.get('revision'):raise ValueError('工程已更新，请重新载入后检查')
        action=body.get('action');state=copy.deepcopy(doc.get('workflow',{}));clock=copy.deepcopy(doc.get('timing',{}))
        if action=='alignment':
            if not file_key(doc.get('video')) or not file_key(doc.get('audio')):raise ValueError('请先选择有效视频和混音')
            state['alignment']=alignment_signature(doc)
        elif action=='video-clock':clock=timing(doc,'video')
        elif action=='ack-shift':clock['ackShift']=doc['subtitleShift']
        elif action=='single-language':state['singleLanguage']=not state.get('singleLanguage',False)
        elif action=='aligned-audio':
            if not file_key(doc.get('audio')):raise ValueError('请先选择音轨')
            if state.get('alignedAudio')==file_key(doc['audio']):state.pop('alignedAudio')
            else:
                state['alignedAudio']=file_key(doc['audio']);doc['audioOffset']=0
                if clock.get('clock')=='audio':clock={}
        elif action=='preview':
            from video_jobs import history
            if not checks(doc,history(ident))['previewReady']:raise ValueError('请先生成与当前设置一致的准确预览')
            state['preview']=signature(doc)
        else:raise ValueError('未知引导操作')
        return project.save(ident,doc,internal={'workflow':state,'timing':clock})
