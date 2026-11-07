"""Explainable delivery checks, with bounded real-libass subtitle sampling."""
from pathlib import Path
import copy,math,subprocess,time
from core import save_json,read_json
import settings,video_project as project,video_workflow,video_edit,asset_impact

def structural(doc,duration=None,fonts=None):
    issues=[]
    def add(code,text,at=0,cue=None,level='warning'):issues.append({'code':code,'message':text,'time':max(0,round(at,3)),'cue':cue,'level':level})
    for message in video_workflow.blockers(doc):add('clock',message,level='error')
    tracks={'original':[],'translation':[]};required=set()
    for row in doc.get('cues',[]):
        for key in tracks:
            text=row.get(key,'').strip()
            if not text:continue
            timing=project.caption_times(row,key);a=timing['start']+doc.get('subtitleShift',0);b=timing['end']+doc.get('subtitleShift',0)
            if a<0 or b<=a:add('time','字幕时间无效或早于零秒',a,row['id'],'error');continue
            tracks[key].append((a,b,row['id']));style={**doc['styles'][key],**(row.get(key+'Style') or {})};required.add(style['font'])
            if duration and b>duration+.04:add('tail','字幕超出成片结尾',a,row['id'])
            count=sum(not c.isspace() for c in text);rate=count/max(.01,b-a);limit=16 if any('\u3000'<=c<='\u9fff' for c in text) else 28
            if rate>limit and count>12:add('reading','本句字数较多、显示较短，请确认能读完',a,row['id'])
            if len(text)>100:add('long','本句文字较长，建议检查换行与画面边缘',a,row['id'])
        if row.get('original','').strip() and not row.get('translation','').strip() and not doc.get('workflow',{}).get('singleLanguage'):add('translation','这句没有译文；若有意保留可忽略',row['start'],row['id'])
    for key,rows in tracks.items():
        active=[]
        for a,b,ident in sorted(rows):
            active=[r for r in active if r[1]>a+.02]
            if active:add('overlap',('原文' if key=='original' else '译文')+'存在同时显示的相邻字幕，请检查是否有意叠放',a,ident)
            active.append((a,b,ident))
    if fonts is not None:
        names={n.casefold() for n in fonts}
        for name in sorted(required):
            if name.casefold() not in names:add('font','未检测到字体“'+name+'”，渲染可能使用替代字体',level='warning')
    return issues

def bounds(png,width,height):
    result=subprocess.run([settings.executable('ffmpeg'),'-v','error','-i',str(png),'-vf','alphaextract','-frames:v','1','-f','rawvideo','-pix_fmt','gray','pipe:1'],capture_output=True,timeout=15,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if len(result.stdout)!=width*height:raise ValueError('字幕图层尺寸不匹配')
    xmin=width;ymin=height;xmax=ymax=-1
    for y in range(height):
        row=result.stdout[y*width:(y+1)*width];pixels=[i for i,v in enumerate(row) if v>=64]
        if pixels:xmin=min(xmin,pixels[0]);xmax=max(xmax,pixels[-1]);ymin=min(ymin,y);ymax=y
    return (xmin,ymin,xmax,ymax) if xmax>=0 else None

def run(ident,folder,check=lambda:None,progress=lambda *args:None):
    import video_captions,video_jobs
    doc=project.load(ident);signature=video_workflow.signature(doc);before=asset_impact.video_sources(doc);issues=[];duration=(doc.get('composition') or {}).get('duration')
    if not duration and doc.get('video'):duration=video_edit.inspect(doc['video'])['duration']
    try:fonts=[f['family'] for f in video_jobs.font_catalog() if f['available']]
    except (OSError,ValueError,KeyError):fonts=None
    issues=structural(doc,duration,fonts)
    if doc.get('audio') and doc.get('audioSource')!='video':
        info=video_edit.inspect(doc['audio']);end=doc.get('audioOffset',0)+info['duration']
        if duration and end>duration+.15:issues.append({'code':'audio-tail','message':f'混音比成片末尾长 {end-duration:.2f} 秒，导出会截断这部分，请试听结尾','time':max(0,duration-5),'level':'warning','cue':None})
    # Every cue receives timing/text checks. Rasterize a bounded representative
    # sample: long lines, edge-positioned styles, and each distinct font/style.
    ranked=sorted(doc['cues'],key=lambda r:(-max(len(r.get(k,'')) for k in ['original','translation']),r['start']))
    samples=ranked[:24];seen=set()
    for row in doc['cues']:
        style=repr([doc['styles'],row.get('originalStyle'),row.get('translationStyle')])
        if style not in seen and len(samples)<40:samples.append(row);seen.add(style)
    samples=list({r['id']:r for r in samples}.values());sampled=[]
    for index,row in enumerate(samples):
        check();progress(15+int(75*(index+1)/max(1,len(samples))),'检查字幕字形与画面边缘')
        boxes={}
        for key in ['original','translation']:
            if not row.get(key,'').strip():continue
            isolated=copy.deepcopy(row);isolated['translation' if key=='original' else 'original']=''
            layer=video_captions.render({'width':960,'height':540,'styles':doc['styles'],'cues':[isolated]});box=bounds(video_captions.media(layer['key']+'.png'),960,540);boxes[key]=box
            if box is None:issues.append({'code':'invisible','message':('原文' if key=='original' else '译文')+'未检测到可见字幕像素，请检查字体、位置或文字','time':row['start'],'cue':row['id'],'level':'warning'})
            elif box[0]<=1 or box[1]<=1 or box[2]>=958 or box[3]>=538:issues.append({'code':'edge','message':('原文' if key=='original' else '译文')+'贴近或被画面边缘裁切，请检查位置、字号与换行','time':row['start'],'cue':row['id'],'level':'warning'})
        a,b=boxes.get('original'),boxes.get('translation')
        if a and b and min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1]):issues.append({'code':'layout-overlap','message':'本句原文与译文字形范围重叠，请检查行间距','time':row['start'],'cue':row['id'],'level':'warning'})
        sampled.append(row['id'])
    if signature!=video_workflow.signature(project.load(ident)) or before!=asset_impact.video_sources(doc):raise ValueError('工程或素材在检查期间变化，本次结果未设为当前报告，请重新检查')
    report={'revision':doc['revision'],'signature':signature,'created':time.time(),'issues':issues,'sampledCues':sampled,'checkedCues':len(doc['cues']),'sourceVersions':before,'scope':'所有字幕检查时间与文字；最多 40 句以真实 libass 抽样排版。提示不代表听感、翻译或全片画面已正确。'}
    check();save_json(Path(folder)/'Check Report.json',report);save_json(project.folder(ident)/'ProjectData/Latest Check.json',report);return report

def latest(ident):
    file=project.folder(ident)/'ProjectData/Latest Check.json'
    if not file.is_file():return None
    report=read_json(file);doc=project.load(ident);return {**report,'stale':report['signature']!=video_workflow.signature(doc) or report['sourceVersions']!=asset_impact.video_sources(doc)}
