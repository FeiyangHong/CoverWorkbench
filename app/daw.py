"""Build a separate Studio One song from a user's SVP and an existing mix template.

No source project is rewritten. Effect DSP payloads are copied without approximation;
public starter metadata is sanitized and the SV external-project state is retargeted.
"""
from pathlib import Path
import copy, hashlib, html, json, math, os, re, shutil, struct, subprocess, threading, time, uuid, zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit
from core import ROOT, read_json, save_json, sha, parse_svp, seconds_converter, BLICK

BASE=ROOT/'projects/studio-one'
import settings
import starter_templates
BUILD_INDEX=ROOT/'data/daw-build-index.json'
BUILD_LOCK=threading.Lock()
ROLES={'lead1':'主声 1','lead2':'主声 2','lead3':'主声 3','harmony':'和声'}


class FolderConflict(ValueError):
    def __init__(self,folder):
        super().__init__('同名工程位置已存在，请打开已有工程或另存新版本。')
        self.detail={'folder':str(folder),'songs':[str(p) for p in sorted(folder.glob('*.song')) if p.is_file()] if folder.is_dir() else []}

def open_local(body):
    action=body.get('action');text=clean_path(body.get('path'));p=Path(text)
    if not p.is_absolute() or text.startswith(('\\\\','//')) or not p.exists():raise ValueError('请选择存在的本机路径')
    p=p.resolve()
    if action=='song':
        if not p.is_file() or p.suffix.lower()!='.song':raise ValueError('请选择 Studio One 的 .song 工程')
        exe=Path(settings.executable('studioOne'))
        if not exe.is_file():raise ValueError('找不到 Studio One 程序')
        subprocess.Popen([str(exe),str(p)])
    elif action=='folder':
        exe=Path(os.environ.get('WINDIR','C:/Windows'))/'explorer.exe'
        subprocess.Popen([str(exe),str(p)] if p.is_dir() else [str(exe),'/select,',str(p)])
    else:raise ValueError('无效的打开操作')
    return {'opened':True,'path':str(p),'action':action}

def xml(raw):return ET.fromstring(raw.decode('utf-8-sig').replace('x:id','x_id'))
def xmlbytes(node):return ('<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(node,encoding='unicode').replace('x_id=','x:id=')).encode('utf-8')
def uid():return '{'+str(uuid.uuid4()).upper()+'}'
def child(node,tag,key):return node.find(f'./{tag}[@x_id="{key}"]')
def external(url):return Path(unquote(urlsplit(url).path).lstrip('/'))
def fileurl(path):return 'file:///'+Path(path).as_posix()

def clean_path(value):
    text=str(value or '').strip()
    pairs={'"':'"',"'":"'",'“':'”','‘':'’'}
    while len(text)>1 and text[0] in pairs and text[-1]==pairs[text[0]]:
        text=text[1:-1].strip()
    if any(c in text for c in ['\x00','\r','\n']):raise ValueError('路径中不能包含换行或空字符')
    return text

def local(value,suffixes):
    p=Path(clean_path(value))
    if not p.is_absolute() or str(p).startswith(('\\\\','//')) or not p.is_file() or p.suffix.lower() not in suffixes:
        raise ValueError('请选择存在的本地文件：'+', '.join(sorted(suffixes)))
    return p.resolve()

def output_options():
    return [{'id':'workbench','name':'CoverWorkbench · 工作台工程','path':str(BASE)},
            {'id':'songs','name':'Studio One · Songs','path':settings.load()['songsDirectory'] or str(Path.home()/'Documents/Studio One/Songs')}]

def output_base(value):
    text=clean_path(value) or str(BASE)
    p=Path(text)
    if not p.is_absolute() or text.startswith(('\\\\','//')) or any(c in text for c in '<>"|?*') or ':' in text[2:]:
        raise ValueError('请选择本机绝对文件夹路径')
    if p.exists() and not p.is_dir():raise ValueError('输出位置必须是文件夹，不能是文件')
    return p.resolve()

def browse(body):
    kind=body.get('kind')
    if kind not in ['project','audio','folder']:raise ValueError('无效的文件选择类型')
    sort=body.get('sort','modified-desc');folders_first=body.get('foldersFirst',True)
    if sort not in ['modified-desc','modified-asc','created-desc','name-asc','name-desc','size-desc','size-asc']:raise ValueError('无效的排序方式')
    text=clean_path(body.get('path'))
    candidate=Path(text or str(ROOT.parent))
    p=output_base(str(candidate.parent) if candidate.is_file() else str(candidate))
    # A typed not-yet-created output folder starts browsing at its nearest parent.
    while not p.exists() and p!=p.parent:p=p.parent
    if not p.is_dir():raise ValueError('找不到可浏览的文件夹')
    extensions={'.svp','.song'} if kind=='project' else {'.wav','.flac','.aif','.aiff'}
    entries=[]
    try:
        for f in p.iterdir():
            try:
                directory=f.is_dir()
                if directory or (kind!='folder' and f.suffix.lower() in extensions):
                    st=f.stat()
                    entries.append({'name':f.name,'path':str(f),'directory':directory,'modified':st.st_mtime,'created':st.st_ctime,'size':None if directory else st.st_size})
            except OSError:continue
    except OSError:raise ValueError('这个文件夹无法读取，请选择其他位置')
    field,direction=sort.split('-')
    entries.sort(key=lambda f:f['name'].casefold())
    entries.sort(key=lambda f:f['name'].casefold() if field=='name' else f[field] or 0,reverse=direction=='desc')
    if folders_first:entries.sort(key=lambda f:not f['directory'])
    return {'path':str(p),'parent':str(p.parent) if p.parent!=p else None,
            'roots':[f'{c}:\\' for c in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{c}:/').is_dir()],
            'entries':entries[:1500],'truncated':len(entries)>1500,'sort':sort,'foldersFirst':bool(folders_first)}

def project_source(value):
    path=local(value,{'.svp','.song'})
    if path.suffix.lower()=='.svp':return path,None
    candidates=[]
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.endswith('.vstpreset'):continue
            blob=z.read(name)
            if blob[:4]!=b'VST3' or blob[8:40] not in [b'ABCDEF019182FAEB44746E6353565232',b'ABCDEF019182FAEB44746E6353565332']:continue
            for tag,data in chunks(blob):
                if tag!=b'Comp':continue
                state,_=json.JSONDecoder().raw_decode(data.decode('utf-8'))
                linked=state.get('projectPath','').replace('\\\\','\\')
                if linked:candidates.append(local(linked,{'.svp'}))
    candidates=list(dict.fromkeys(candidates))
    if len(candidates)!=1:raise ValueError('Song 未找到唯一的外部 SVP 链接，请直接选择需要的人声 SVP 文件')
    return candidates[0],str(path)

TEMPLATE_INDEX=ROOT/'config/daw-templates.local.json'

def template(pid):
    bundled=starter_templates.resolve(pid)
    if bundled:return bundled
    entries=read_json(TEMPLATE_INDEX) if TEMPLATE_INDEX.exists() else []
    match=next((d for d in entries if d['id']==pid),None)
    if match:return match
    if pid in ['hoshi','stella']:
        path=ROOT/'data/projects'/f'{pid}.json'
        if path.exists():
            return read_json(path)['project']['dawCopy']
    raise ValueError('Template is unavailable. Register your own Song in Environment settings.')

def validate_template(path):
    with zipfile.ZipFile(path) as z:
        required=['Devices/audiomixer.xml','Devices/audiosynthfolder.xml','Devices/musictrackdevice.xml',
                  'Devices/transportdevice.xml','Song/song.xml','Song/mediapool.xml','metainfo.xml','settings.xml']
        if any(n not in z.namelist() for n in required):raise ValueError('Unsupported Song structure; see docs/Deployment.md')
        mix=xml(z.read('Devices/audiomixer.xml'));group=mix.find('./Attributes/ChannelGroup[@name="AudioSynth"]')
        if group is None:raise ValueError('Template needs Synthesizer V instrument outputs')
        if not any(re.search(r'主声|lead',c.get('label',''),re.I) for c in group):raise ValueError('Name at least one vocal mixer channel Lead or 主声')
        if not any(re.search(r'和声|harmony',c.get('label',''),re.I) for c in group):raise ValueError('Name one vocal mixer channel Harmony or 和声')
        synth=xml(z.read('Devices/audiosynthfolder.xml'))
        if len(synth.findall('./Attributes[@name="Inst01"]'))!=1:raise ValueError('Template needs an Inst01 instrument')
        names=[n for n in z.namelist() if n.endswith('.vstpreset') and 'Synthesizer V' in n]
        if len(names)!=1:raise ValueError('Template needs exactly one Synthesizer V preset')
        if z.read(names[0])[8:40]!=b'ABCDEF019182FAEB44746E6353565232':raise ValueError('The base template must use the supported SV1 plugin; SV2 needs a separate host preset')
        song=xml(z.read('Song/song.xml'))
        if len(list(song.iter('AudioEvent')))!=1:raise ValueError('Template needs exactly one backing audio event')
        pool=xml(z.read('Song/mediapool.xml'))
        if len(list(pool.iter('AudioClip')))!=1:raise ValueError('Template needs exactly one audio clip')
        instrument_channels=[c for c in channels(mix) if c.tag=='AudioTrackChannel']
        if len(instrument_channels)!=1:raise ValueError('Template needs exactly one backing audio channel')
    return True

def register_template(body):
    path=local(body.get('song'),{'.song'})
    name=str(body.get('name','')).strip()
    if not name or len(name)>80:raise ValueError('Enter a template name of 1-80 characters')
    validate_template(path)
    with BUILD_LOCK:
        entries=read_json(TEMPLATE_INDEX) if TEMPLATE_INDEX.exists() else []
        if any(Path(d['originalSong']).resolve()==path for d in entries):raise ValueError('This template is already registered')
        entry={'id':'template-'+uuid.uuid4().hex[:12],'name':name,'originalSong':str(path)}
        entries.append(entry);save_json(TEMPLATE_INDEX,entries)
    return entry

def register_sv2_host(body):
    """Capture a user's saved native SV2 host state; never ship that state."""
    source=local(body.get('song'),{'.song'})
    source_hash=sha(source)
    with zipfile.ZipFile(source) as archive:
        candidates=[]
        for name in archive.namelist():
            if not name.endswith('.vstpreset'):continue
            blob=archive.read(name)
            if blob[:4]==b'VST3' and blob[8:40]==b'ABCDEF019182FAEB44746E6353565332':
                if not any(tag==b'Comp' for tag,data in chunks(blob)):
                    raise ValueError('SV2 preset has no component state')
                candidates.append(blob)
    if len(candidates)!=1:raise ValueError('Save a Song containing exactly one supported Synthesizer V Studio 2 VST3 instance')
    if sha(source)!=source_hash:raise ValueError('Source Song changed during capture; save it and try again')
    with BUILD_LOCK:
        folder=ROOT/'integrations/studio-one';folder.mkdir(parents=True,exist_ok=True)
        preset=folder/('sv2-host-'+uuid.uuid4().hex[:12]+'.vstpreset')
        preset.write_bytes(candidates[0])
        entry={'classID':'{ABCDEF01-9182-FAEB-4474-6E6353565332}',
               'preset':preset.relative_to(ROOT).as_posix(),'nativeSong':str(source),'sourceSHA256':source_hash}
        old=folder/'sv2-host.json'
        if old.exists():
            backup=ROOT/'runtime/sv2-host-backups'/str(time.time_ns())/'sv2-host.json'
            backup.parent.mkdir(parents=True);shutil.copy2(old,backup)
        save_json(old,entry)
    return {'ready':True,'source':str(source),'preset':str(preset)}

def channels(mixer):return [n for n in mixer.iter() if n.tag in ['AudioSynthChannel','AudioTrackChannel','AudioEffectChannel','AudioGroupChannel','AudioOutputChannel']]
def recipe(c):
    inserts=child(c,'Attributes','Inserts');sends=child(c,'Attributes','Sends')
    return {'name':c.get('label'),'type':c.tag,'output':int(c.get('synthPort','-1'))+1,
      'gainDB':round(20*math.log10(float(c.get('gain',1))),2) if float(c.get('gain',1))>0 else None,
      'muted':c.get('mute')=='1','effects':[] if inserts is None else [v.get('name') for v in inserts.findall('./Attributes/Attributes[@x_id="deviceData"]')],
      'destination':(child(c,'Connection','destination').get('friendlyName') if child(c,'Connection','destination') is not None else ''),
      'sends':[] if sends is None else [{'to':v.find('Connection').get('friendlyName'),'levelDB':round(20*math.log10(float(v.get('level',1))),2) if float(v.get('level',1))>0 else None,'bypassed':v.get('bypass')=='1'} for v in sends if v.find('Connection') is not None]}

def templates():
    out=[]
    custom=read_json(TEMPLATE_INDEX) if TEMPLATE_INDEX.exists() else []
    for pid in [d['id'] for d in starter_templates.entries()]+['hoshi','stella']+[d['id'] for d in custom]:
        try:
            d=template(pid)
            with zipfile.ZipFile(d['originalSong']) as z:
                mix=xml(z.read('Devices/audiomixer.xml'))
            out.append({'id':pid,'name':d.get('name', 'Local Vocal Plate' if pid=='hoshi' else 'Local Vocal Delay'),
                        'source':d['originalSong'],'bundled':d.get('bundled',False),
                        'requiredPlugins':d.get('requiredPlugins',[]),'warnings':d.get('warnings',[]),
                        'channels':[recipe(c) for c in channels(mix)]})
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):
            continue
    return out


def inspect(body):
    path,source_song=project_source(body.get('svp',''));raw=read_json(path)
    if not isinstance(raw.get('tracks'),list) or not raw['tracks']:raise ValueError('SVP 没有音轨')
    parsed=parse_svp(path);trackmap={t['id']:t for t in parsed['tracks']};rows=[];lead=0
    for index,t in sorted(enumerate(raw['tracks']),key=lambda pair:pair[1].get('dispOrder',pair[0])):
        ref=t.get('mainRef',{});instrumental=ref.get('isInstrumental',False)
        n=trackmap.get(index,{}).get('count',0)
        if not instrumental:lead+=1
        role='harmony' if re.search(r'和声|和音|harm|back',t.get('name',''),re.I) else 'lead'+str(min(lead,3))
        rows.append({'index':index,'name':t.get('name',f'Track {index+1}'),'notes':n,'instrumental':bool(instrumental),
                     'muted':bool(t.get('mixer',{}).get('mute')), 'solo':bool(t.get('mixer',{}).get('solo')), 'selected':not instrumental and n>0 and not t.get('mixer',{}).get('mute'),
                     'role':role,'voice':ref.get('database',{}).get('name','')})
    version=int(raw.get('version',0));engine='sv2' if version>=180 else 'sv1'
    requested=body.get('engine','auto')
    if requested not in ['auto','sv1','sv2']:raise ValueError('请选择有效的 SV 插件版本')
    if requested=='sv1' and version>=180:raise ValueError('此 SV2 格式不能交给 SV1 插件')
    if requested!='auto':engine=requested
    warnings=['只读取磁盘上已保存的 SVP；SV 内尚未保存的修改不会被导入。',
              '新工程会移除 SV 副本里的参考音频轨，伴奏只在 Studio One 播放一次。',
              '效果器与发送沿用所选歌曲的真实设置；压缩阈值、齿音和音量需对新歌试听调整。']
    if any(t['solo'] for t in rows):warnings.append('源工程存在 Solo 独奏轨；副本保留此状态，其他声部可能无声。请先在 SV 确认 Solo 设置。')
    if engine=='sv2' and not (ROOT/'integrations/studio-one/sv2-host.json').exists():
        warnings.append('当前已验证模板使用 SV1 插件；SV2 工程需要 SV2 宿主模板，不能静默交给 SV1。')
    complex_time=len(raw.get('time',{}).get('tempo',[]))>1 or len(raw.get('time',{}).get('meter',[]))>1
    if complex_time:warnings.append('此工程存在变速或变拍：当前生成器仅验证恒定速度 / 单一拍号，暂不自动生成。')
    if source_song:warnings.insert(0,'已从 Song 读取外部 SVP：'+str(path)+'。效果器仍使用下方所选模板。')
    return {'svp':str(path),'sourceSong':source_song,'sha256':sha(path),'version':version,'engine':engine,'tracks':rows,
            'duration':parsed['duration'],'tempo':raw.get('time',{}).get('tempo',[]),'warnings':warnings,
            'canBuild':not complex_time and (engine=='sv1' or (ROOT/'integrations/studio-one/sv2-host.json').exists())}

def chunks(blob):
    if blob[:4]!=b'VST3':raise ValueError('无效 VST3 预设')
    off=struct.unpack_from('<Q',blob,40)[0]
    if blob[off:off+4]!=b'List':raise ValueError('无效 VST3 索引')
    rows=[]
    for i in range(struct.unpack_from('<I',blob,off+4)[0]):
        tag,a,n=struct.unpack_from('<4sQQ',blob,off+8+i*20)
        if a+n>len(blob):raise ValueError('VST3 区块越界')
        rows.append((tag,blob[a:a+n]))
    return rows

def vst_external(blob,path):
    result=[];found=False
    for tag,data in chunks(blob):
        if tag==b'Comp':
            text=data.decode('utf-8');state,end=json.JSONDecoder().raw_decode(text)
            if 'projectPath' not in state:raise ValueError('宿主模板没有外部 SVP 字段')
            state['projectPath']=str(path).replace('\\','\\\\') if '\\\\' in state['projectPath'] else str(path)
            state.setdefault('sessionConfiguration',{})['channelLayout']=536870930
            # ARA bridge is not required for host transport/multi-out playback.
            state['araBridgeEnabled']=False
            data=(json.dumps(state,ensure_ascii=True)+text[end:]).encode();found=True
        result.append((tag,data))
    if not found:raise ValueError('缺少 SV 插件组件状态')
    payload=b'';records=[]
    for tag,data in result:records.append((tag,48+len(payload),len(data)));payload+=data
    return blob[:40]+struct.pack('<Q',48+len(payload))+payload+b'List'+struct.pack('<I',len(records))+b''.join(struct.pack('<4sQQ',*r) for r in records)

def media_info(path):
    cp=subprocess.run([settings.executable('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,encoding='utf-8',errors='replace',timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if cp.returncode:raise ValueError('无法读取伴奏：'+cp.stderr[-250:])
    info=json.loads(cp.stdout);s=next((s for s in info['streams'] if s.get('codec_type')=='audio'),None)
    if s is None:raise ValueError('伴奏没有音频流')
    sr=int(s['sample_rate']);duration=float(info['format']['duration'])
    return {'duration':duration,'rate':sr,'frames':round(duration*sr),'channels':int(s['channels']),
            'bits':int(s.get('bits_per_raw_sample') or s.get('bits_per_sample') or 16),
            'float':str(s.get('sample_fmt','')).startswith(('flt','dbl'))}

def history():
    records=[];paths=set()
    if BUILD_INDEX.exists():
        for value in read_json(BUILD_INDEX):paths.add(Path(value))
    if BASE.exists():
        paths.update(BASE.glob('*/build.json'))
    for f in paths:
        try:records.append(read_json(f))
        except (ValueError,OSError):pass
    return sorted(records,key=lambda r:r.get('createdAt',0),reverse=True)[:30]

def build(body):
    with BUILD_LOCK:return _build(body)

def _build(body):
    preview=inspect(body)
    if preview['engine']=='sv2' and not (ROOT/'integrations/studio-one/sv2-host.json').exists():raise ValueError('这是 SV2 格式，尚未建立 SV2 宿主模板。请勿改扩展名或强制用 SV1 打开。')
    if body.get('sourceSHA256')!=preview['sha256']:raise ValueError('SVP 已改变或尚未扫描；请重新读取并确认音轨')
    original=read_json(preview['svp'])
    # Only constant-tempo/meter songs have been verified against Studio One's time map format.
    if len(original.get('time',{}).get('tempo',[]))>1 or len(original.get('time',{}).get('meter',[]))>1:
        raise ValueError('当前自动建工程仅验证了恒定速度与拍号；变速 / 变拍工程请先单独处理速度图，避免错位')
    slug=str(body.get('name','')).strip()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,63}',slug):raise ValueError('工程名称使用 1–64 位英文字母、数字、空格、下划线或连字符，以字母开头')
    supplied=body.get('tracks',[])
    if not isinstance(supplied,list) or not 1<=len(supplied)<=16:raise ValueError('选择 1–16 条人声音轨')
    tracks={r['index']:r for r in preview['tracks']};selected=[];seen=set()
    for choice in supplied:
        i=choice.get('index');role=choice.get('role')
        if type(i) is not int or i not in tracks or i in seen or tracks[i]['instrumental'] or not tracks[i]['notes'] or role not in ROLES:raise ValueError('音轨选择或效果角色无效')
        if tracks[i]['muted']:raise ValueError('选中的 SV 音轨处于静音，请先在 SV 确认并保存后重新读取')
        seen.add(i);selected.append(dict(tracks[i],role=role))
    audio=local(body.get('accompaniment',''),{'.wav','.flac','.aif','.aiff'})
    info=media_info(audio);d=template(body.get('template'));validate_template(d['originalSong'])
    naming=body.get('folderNaming','plain')
    if naming not in ['plain','timestamp','unique']:raise ValueError('请选择有效的文件夹命名方式')
    conflict_action=body.get('conflictAction')
    if conflict_action not in [None,'version']:raise ValueError('无效的同名处理方式')
    # The record ID stays unique independently of the visible folder name.
    stamp=slug+'_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    folder_name=slug if naming=='plain' else stamp.rsplit('_',1)[0] if naming=='timestamp' else stamp
    base=output_base(body.get('outputDir'))
    dest=base/folder_name
    if conflict_action=='version':
        version=2
        while True:
            dest=base/(slug+f'_v{version}')
            try:dest.mkdir(parents=True,exist_ok=False);break
            except FileExistsError:version+=1
    else:
        try:dest.mkdir(parents=True,exist_ok=False)
        except FileExistsError:raise FolderConflict(dest)
    for sub in ['SV','Media','Presets','Mixdown']:(dest/sub).mkdir()
    song=dest/f'{slug}.song';svp=dest/'SV/project.svp';accompaniment=dest/'Media'/('instrumental'+audio.suffix.lower())
    raw=copy.deepcopy(original)
    raw['tracks']=[copy.deepcopy(original['tracks'][r['index']]) for r in selected]
    for index,t in enumerate(raw['tracks']):t['dispOrder']=index
    raw.setdefault('renderConfig',{})['destination']=str(dest/'Mixdown');save_json(svp,raw)
    audio_hash=sha(audio);shutil.copy2(audio,accompaniment)
    if sha(accompaniment)!=audio_hash:raise ValueError('伴奏在复制时发生变化，请完成渲染后重试')
    with zipfile.ZipFile(d['originalSong']) as z:archive={n:z.read(n) for n in z.namelist()}
    # Workspace uses Studio One's non-XML FrameItem::ViewState tags; preserve it byte-for-byte.
    docs={n:xml(v) for n,v in archive.items() if n.endswith('.xml') and not n.startswith('Workspace/')}
    mix=docs['Devices/audiomixer.xml'];allch=channels(mix);synthgroup=mix.find('./Attributes/ChannelGroup[@name="AudioSynth"]')
    synthnodes=list(synthgroup);leadnodes=[c for c in synthnodes if re.search(r'主声|lead',c.get('label',''),re.I)];harmony=next(c for c in synthnodes if re.search(r'和声|harmony',c.get('label',''),re.I))
    for c in list(synthgroup):synthgroup.remove(c)
    outputids=[];mapping=[]
    for i,row in enumerate(selected):
        proto=harmony if row['role']=='harmony' else leadnodes[min(int(row['role'][-1])-1,len(leadnodes)-1)]
        c=copy.deepcopy(proto)
        for item in c.findall('.//UID[@x_id="uniqueID"]'):item.set('uid',uid())
        c.set('synthPort',str(i));c.set('name',f'Channel{i+1:02}');c.set('label',row['name']);c.set('mute','0');c.set('solo','0')
        outputids.append(child(c,'UID','uniqueID').get('uid'));synthgroup.append(c)
        mapping.append({'svpTrack':row['name'],'sourceIndex':row['index'],'output':i+1,'role':row['role'],**recipe(c)})
    synth=docs['Devices/audiosynthfolder.xml'].find('./Attributes[@name="Inst01"]')
    listing=child(synth,'List','synthChannels');listing.clear();listing.set('x_id','synthChannels')
    for value in outputids:ET.SubElement(listing,'UID',{'uid':value})
    ports=synth.find('./Attributes[@x_id="ghostData"]/Attributes[@x_id="IO"]/List[@x_id="audioOutputs"]')
    for i,p in enumerate(ports):p.set('flags','3' if i==0 else '1' if i<len(selected) else '0')
    # One DAW instrument track controls the plugin; the separate mixer channels carry the audio.
    music=docs['Devices/musictrackdevice.xml'];instrument=next(n for n in music.iter('MusicTrackChannel') if child(n,'Connection','instrumentOut') is not None)
    instrument.set('label','SV Vocals');child(instrument,'Connection','instrumentOut').set('objectID',outputids[0]+'/Input');child(instrument,'Connection','instrumentOut').set('friendlyName',selected[0]['name'])
    for n in instrument.findall('.//Attributes[@recordArmed]'):n.set('recordArmed','0');n.set('monitorActive','0')
    vocaltrack=next(n for n in docs['Song/song.xml'].iter('MediaTrack') if n.get('mediaType')=='Music');vocaltrack.set('name','SV Vocals')
    # Do not inherit song-specific backing-track volume/pan automation.
    audiochannel=next(c for c in allch if c.tag=='AudioTrackChannel');audiochannel.set('label','Instrumental')
    songroot=docs['Song/song.xml'];audiotrack=next(n for n in songroot.iter('MediaTrack') if n.get('mediaType')=='Audio');audiotrack.set('name','Instrumental')
    automation=child(audiotrack,'Attributes','AutomationRegionList')
    if automation is not None:automation.clear();automation.set('x_id','AutomationRegionList');automation.set('visible','0')
    event=next(audiotrack.iter('AudioEvent'));event.set('name','Instrumental');event.set('start','0');event.set('length',str(info['duration']));event.set('speed','1')
    clip=next(docs['Song/mediapool.xml'].iter('AudioClip'));clip.set('peak','1');fmt=child(clip,'Attributes','format')
    fmt.attrib.update(frameCount=str(info['frames']),sampleRate=str(info['rate']),numChannels=str(info['channels']),bitDepth=str(info['bits']),sampleType='1' if info['float'] else '0')
    poolurl=child(clip,'Url','path');old_audio=external(poolurl.get('url'));poolurl.set('url',fileurl(accompaniment))
    for node in clip.findall('.//AudioTempoMap'):
        node.clear();node.set('x_id','tempoMap');node.set('tempoApproved','0')
    duration=max(preview['duration'],info['duration']);axis=seconds_converter(original)
    tempos=original.get('time',{}).get('tempo') or [{'position':0,'bpm':120}]
    if any(not math.isfinite(float(t['bpm'])) or float(t['bpm'])<=0 for t in tempos):raise ValueError('SV 速度图无效')
    tempos=copy.deepcopy(sorted(tempos,key=lambda t:t['position']));tempos[0]['position']=0
    context=child(songroot.find('Attributes'),'Attributes','timeContext');tm=child(context,'TempoMap','tempoMap');tm.clear();tm.set('x_id','tempoMap')
    for i,t in enumerate(tempos):ET.SubElement(tm,'TempoMapSegment',{'curveType':'0','start':str(axis(t['position'])),'end':str(axis(tempos[i+1]['position'])) if i+1<len(tempos) else '1.7976931348623156e+200','tempo':str(60/float(t['bpm']))})
    meters=original.get('time',{}).get('meter') or [{'index':0,'numerator':4,'denominator':4}]
    # SV meter positions are bar indexes; S1 map positions are quarter-note beats.
    sm=child(context,'TimeSignatureMap','timeSignatureMap');sm.clear();sm.set('x_id','timeSignatureMap');beat=0;last=0;num=4;den=4
    for m in sorted(meters,key=lambda m:m['index']):
        beat+=(m['index']-last)*num*4/den;num=m['numerator'];den=m['denominator'];last=m['index']
        ET.SubElement(sm,'TimeSignatureMapSegment',{'start':str(beat),'numerator':str(num),'denominator':str(den)})
    songroot.find('Attributes').set('length',str(max(duration+5,60)))
    zone=next(context.iter('TimeZone'));zone.set('end',str(duration+10))
    end=next(n for n in songroot.iter('MarkerEvent') if n.get('markerType')=='3')
    # timeFormat 2 markers are in quarter-note beats, not seconds.
    lasttempo=tempos[-1];endbeat=lasttempo['position']/BLICK+(duration-axis(lasttempo['position']))*float(lasttempo['bpm'])/60
    end.set('start',str(endbeat))
    transport=docs['Devices/transportdevice.xml'];transport.set('position','0');transport.set('loopStart','0');transport.set('loopEnd',str(duration));transport.set('loopActive','0')
    for attr in docs['metainfo.xml'].iter('Attribute'):
        values={'Document:Title':slug,'Media:Tempo':str(tempos[0]['bpm']),'Media:Length':str(duration),'Media:TimeSignatureNumerator':str(meters[0]['numerator']),'Media:TimeSignatureDenominator':str(meters[0]['denominator'])}
        if attr.get('id') in values:attr.set('value',values[attr.get('id')])
    for n in docs['settings.xml'].iter('Attributes'):
        if 'fileName' in n.attrib:n.set('fileName',slug+'_Mixdown')
    assetmap={str(old_audio.resolve()):accompaniment,str(Path(d['originalSong']).resolve()):song}
    for name,node in docs.items():
        for n in node.iter():
            url=n.get('url','')
            if not url.startswith('file:///'):continue
            source=external(url);key=str(source.resolve())
            if source.resolve().is_relative_to(dest.resolve()):target=source
            elif 'mixdown' in n.get('x_id','').lower() or source.name=='Mixdown':target=dest/'Mixdown'
            elif key in assetmap:target=assetmap[key]
            elif source.is_file():
                # Existing plugin presets use their real state blobs; external preset URLs are copied for completeness.
                target=dest/'Presets'/(hashlib.sha256(key.encode()).hexdigest()[:12]+source.suffix)
                if not target.exists():shutil.copy2(source,target)
                assetmap[key]=target
            else:raise ValueError('模板依赖丢失：'+str(source))
            n.set('url',fileurl(target)+('/' if url.endswith('/') else ''))
    svpreset=next(n for n in archive if n.endswith('.vstpreset') and 'Synthesizer V' in n)
    archive[svpreset]=vst_external(archive[svpreset],svp)
    if preview['engine']=='sv2':
        host=read_json(ROOT/'integrations/studio-one/sv2-host.json');preset=(ROOT/host['preset']).read_bytes()
        archive[svpreset]=vst_external(preset,svp)
        oldid='{ABCDEF01-9182-FAEB-4474-6E6353565232}'
        for node in docs.values():
            for n in node.iter():
                for k,v in list(n.attrib.items()):
                    if v==oldid:n.set(k,host['classID'])
                    if v=='Synthesizer V Studio Plugin':n.set(k,'Synthesizer V Studio 2 Plugin')
    archive.update({name:xmlbytes(node) for name,node in docs.items()})
    # All generated physical directories and archive directory segments use ASCII.
    renames={};newarchive={}
    for name,value in archive.items():
        if name.startswith('Envelopes/'):continue
        parts=name.split('/');mapped='/'.join(part if part.isascii() else 'asset_'+hashlib.sha256(part.encode()).hexdigest()[:10]+(Path(part).suffix if '.' in part else '') for part in parts)
        renames[name]=mapped;newarchive[mapped]=value
    for name,value in list(newarchive.items()):
        if name.endswith('.xml'):
            text=value.decode('utf-8-sig')
            for old,new in renames.items():text=text.replace(html.escape(old,quote=True),html.escape(new,quote=True))
            newarchive[name]=text.encode('utf-8')
    with zipfile.ZipFile(song,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in newarchive.items():z.writestr(name,value)
    with zipfile.ZipFile(song) as z:
        if z.testzip() is not None:raise ValueError('生成的 Song 压缩包校验失败')
    unchanged=[]
    for name,value in archive.items():
        if name.endswith('.vstpreset') and name!=svpreset:
            if newarchive[renames[name]]!=value:raise ValueError('效果器状态未完整保留')
            unchanged.append(name)
    warnings=preview['warnings']+d.get('warnings',[])+(['Vocal Delay 返回默认为静音，本模板保留此状态。'] if body['template']=='stella' else [])
    result={'id':stamp,'name':slug,'folderNaming':naming,'conflictAction':conflict_action,'template':body['template'],'engine':preview['engine'],'createdAt':time.time(),'outputDir':str(base),'folder':str(dest),'song':str(song),'svp':str(svp),
            'sourceSVP':preview['svp'],'sourceSHA256':preview['sha256'],'sourceAudio':str(audio),'audioSHA256':audio_hash,
            'mapping':mapping,'duration':duration,'effectPresetsPreserved':len(unchanged),'warnings':warnings,
            'validation':'文件结构、引用、音轨映射和效果器状态已校验；打开后需确认声库、插件加载及播放。'}
    save_json(dest/'build.json',result)
    (dest/'README.txt').write_text('在 Studio One 打开 '+str(song)+'\n外部 SVP 为生成副本；请在插件中确认声库与各输出发声。\n'+ '\n'.join(warnings),encoding='utf-8-sig')
    if sha(preview['svp'])!=preview['sha256']:raise ValueError('源工程在生成期间发生变化，请重新读取后再建工程')
    if sha(audio)!=audio_hash:raise ValueError('源伴奏在生成期间发生变化，请完成渲染后重新生成')
    index=read_json(BUILD_INDEX) if BUILD_INDEX.exists() else []
    save_json(BUILD_INDEX,[str(dest/'build.json')]+[v for v in index if Path(v).is_file()][:499])
    return result
