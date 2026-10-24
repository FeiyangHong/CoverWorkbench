"""MusicLyricApp cache + public provider lookup; no account settings/cookies read."""
from core import *
import os, sys, urllib.request, urllib.parse, unicodedata
sys.path.insert(0,str(ROOT/'runtime/lyrics-packages'))
import settings
def cache_path():
    return Path(settings.load()['lyricCache'] or settings.DEFAULTS['lyricCache'])
def normalize(s):return re.sub(r'\W','',unicodedata.normalize('NFKC',s).lower())
def lrc_rows(text):
    rows=[]
    for line in text.splitlines():
        stamps=re.findall(r'\[(\d+):(\d+(?:[.:]\d+)?)\]',line)
        content=re.sub(r'\[[^\]]*\]','',line).strip()
        for m,s in stamps:rows.append({'start':int(m)*60+float(s.replace(':','.')),'text':content})
    return sorted(rows,key=lambda r:r['start'])
def public_item(d):
    s=d['SongVo'];l=d.get('LyricVo',{})
    return {'key':f"{d.get('Source',0)}:{d['SongId']}",'id':str(d['SongId']),'source':d.get('Source',0),'title':s['Name'],'artist':' / '.join(s.get('Singer',[])),'album':s.get('Album',''),'duration':s.get('Duration',0)/1000,'hasLyrics':bool(l.get('Lyric')),'hasTranslation':bool(l.get('TranslateLyric')),'hasRomaji':bool(l.get('TransliterationLyric')),'cached':True}
def cache_candidates(p):
    rows=[]
    for f in cache_path().glob('*.json'):
        try:
            r=public_item(read_json(f));r['score']=int(normalize(p['title'])==normalize(r['title']))*3+int(normalize(p['artist']) in normalize(r['artist']))*2
            if r['score']>=3:rows.append(r)
        except (ValueError,KeyError,TypeError):continue
    return sorted(rows,key=lambda r:-r['score'])
def search(p,query):
    if not isinstance(query,str) or not 1<=len(query.strip())<=150:raise ValueError('搜索词长度无效')
    d=public_api('search/get/web',{'s':query.strip(),'type':'1','limit':'12','offset':'0'})
    rows=[]
    for s in d.get('result',{}).get('songs',[]):
        rows.append({'key':'0:'+str(s['id']),'source':0,'id':str(s['id']),'title':s['name'],'artist':' / '.join(a['name'] for a in s.get('ar',s.get('artists',[]))),'album':s.get('al',s.get('album',{})).get('name',''),'duration':s.get('dt',s.get('duration',0))/1000,'cached':False})
    save_json(Path(p['pilot'])/'analysis/lyric-search.json',rows)
    return rows
def get_candidate(p,key):
    if not isinstance(key,str) or not re.fullmatch(r'[01]:\d+',key):raise ValueError('歌词来源无效')
    for f in cache_path().glob('*.json'):
        d=read_json(f)
        if public_item(d)['key']==key:return d,'MusicLyricApp cache'
    rows=read_json(Path(p['pilot'])/'analysis/lyric-search.json')
    r=next((r for r in rows if r['key']==key),None)
    if not r or r['source']!=0:raise ValueError('请先搜索并选择歌曲')
    d=public_api('song/lyric',{'id':r['id'],'lv':'-1','tv':'-1','rv':'-1'})
    out={'Source':0,'SongId':r['id'],'SongVo':{'Name':r['title'],'Singer':[r['artist']],'Album':r['album'],'Duration':round(r['duration']*1000)},'LyricVo':{'Lyric':d.get('lrc',{}).get('lyric',''),'TranslateLyric':d.get('tlyric',{}).get('lyric',''),'TransliterationLyric':d.get('romalrc',{}).get('lyric','')}}
    return out,'NetEase public lyrics'
def public_api(route,data):
    req=urllib.request.Request('https://music.163.com/api/'+route+'?'+urllib.parse.urlencode(data),headers={'User-Agent':'Mozilla/5.0','Referer':'https://music.163.com/'})
    with urllib.request.urlopen(req,timeout=20) as r:d=json.loads(r.read())
    if d.get('code')!=200:raise ValueError(f"歌词服务未返回成功（{d.get('code')}）；可使用歌词工具缓存或本地文件")
    return d
def revise(p,body):
    result=read_json(Path(p['pilot'])/'analysis/lyrics-current.json');rows=body.get('rows')
    if not isinstance(rows,list) or len(rows)!=len(result['rows']):raise ValueError('歌词行数已改变，请刷新')
    for i,r in enumerate(rows):
        if not isinstance(r,dict) or any(len(str(r.get(k,'')))>2000 for k in ['romaji','translation']):raise ValueError('歌词字段无效')
        if r.get('original')!=result['rows'][i]['original']:raise ValueError('原文已变化，请刷新')
        if str(r['romaji'])!=result['rows'][i]['romaji']:result['rows'][i]['readingSource']='user'
        result['rows'][i]['romaji']=str(r['romaji']);result['rows'][i]['translation']=str(r.get('translation',''))
    name=f"{p['id']}_reading_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    from workspaces import outputs
    txt=outputs(p)/'exports/lyrics'/(name+'.txt')
    txt.write_text('\n\n'.join('\n'.join(x for x in [r['original'],r['romaji'],r['translation']] if x) for r in result['rows'])+'\n',encoding='utf-8-sig')
    result['exports'][0]={'file':str(txt),'url':f"/download/{p['id']}/{txt.name}"}
    result['generatedReadings']=sum(r['readingSource']=='machine' for r in result['rows'])
    save_json(outputs(p)/'working/lyrics'/(name+'.json'),result);save_json(Path(p['pilot'])/'analysis/lyrics-current.json',result);return result
def build(p,body):
    if body.get('key'):
        d,source=get_candidate(p,body['key']);meta=public_item(d);l=d['LyricVo'];original=l.get('Lyric','');translation=l.get('TranslateLyric','');romaji=l.get('TransliterationLyric','')
    else:
        original=str(body.get('text',''));translation=str(body.get('translation',''));romaji=str(body.get('romaji',''));source='User imported text';meta={'title':p['title'],'artist':p['artist'],'key':None}
    if not original.strip() or len(original)>200000:raise ValueError('请提供原文歌词（TXT / LRC）')
    originals=lrc_rows(original);timed=bool(originals)
    if not originals:originals=[{'start':None,'text':t.strip()} for t in original.splitlines() if t.strip() and not re.fullmatch(r'\[[a-zA-Z]+:.*\]',t.strip())]
    trans=lrc_rows(translation);roman=lrc_rows(romaji)
    plainromaji=[s.strip() for s in romaji.splitlines() if s.strip()] if not roman else []
    k=None
    if p['language']=='ja':
        try:
            from pykakasi import kakasi
            k=kakasi()
        except ImportError:
            raise ValueError('Japanese romaji needs the optional lyric package. Run Setup.ps1 -WithLyrics.')
    rows=[]
    def aligned(stream,start):
        if start is None:return ''
        choices=[r for r in stream if abs(r['start']-start)<=.15 and r['text']]
        return min(choices,key=lambda r:abs(r['start']-start))['text'] if choices else ''
    omitted=[]
    for i,r in enumerate(originals):
        if not r['text']:continue
        if re.match(r'^(?:作[词詞曲]|[编編]曲|制作人|製作|作詞・作曲|Composer|Lyricist)\s*[:：]',r['text'],re.I):omitted.append(r['text']);continue
        reading=aligned(roman,r['start']) or (plainromaji[i] if len(plainromaji)==len(originals) else '')
        kind='provider' if reading and body.get('key') else 'user' if reading else 'none'
        hira=''
        if p['language']=='ja':
            parts=k.convert(r['text']);hira=''.join(x['hira'] for x in parts)
            if not reading:reading=' '.join(x['hepburn'] for x in parts);kind='machine'
        rows.append({'original':r['text'],'romaji':reading,'reading':hira,'translation':aligned(trans,r['start']),'start':r['start'],'readingSource':kind})
    if not rows:raise ValueError('没有有效歌词行，请检查源文件格式')
    for i,r in enumerate(rows):r['end']=rows[i+1]['start'] if timed and i+1<len(rows) else p['duration'] if timed else None
    from workspaces import outputs
    dest=outputs(p)/'working/lyrics';dest.mkdir(parents=True,exist_ok=True)
    rev=f"{p['id']}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    sourcepath=dest/(rev+'_source.json');save_json(sourcepath,{'source':source,'metadata':meta,'original':original,'translation':translation,'romaji':romaji})
    meta['cached']=source=='MusicLyricApp cache'
    result={'source':source,'metadata':meta,'rows':rows,'omittedCredits':omitted,'timed':timed,'generatedReadings':sum(r['readingSource']=='machine' for r in rows),'sourceFile':str(sourcepath),'createdAt':time.strftime('%Y-%m-%d %H:%M:%S'),'notice':'平台罗马音和机器读音均须对照演唱核对；LRC 是来源时间，不是本次声学对齐。此操作不改 SV 音符或旧对齐结果。'}
    from workspaces import outputs
    exp=outputs(p)/'exports/lyrics';exp.mkdir(parents=True,exist_ok=True)
    txt=exp/(rev+'_original_romaji.txt')
    txt.write_text('\n\n'.join('\n'.join(x for x in [r['original'],r['romaji'],r['translation']] if x) for r in rows)+'\n',encoding='utf-8-sig')
    raw=exp/(rev+('_original.lrc' if timed else '_original.txt'));raw.write_text(original,encoding='utf-8-sig')
    result['exports']=[{'file':str(f),'url':f"/download/{p['id']}/{f.name}"} for f in [txt,raw]]
    save_json(dest/(rev+'_lines.json'),result);save_json(Path(p['pilot'])/'analysis/lyrics-current.json',result)
    return result
