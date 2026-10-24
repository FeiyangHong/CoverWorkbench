"""Local-only project parsing and copy-on-export editing. No writes to source files."""
from pathlib import Path
import bisect, csv, hashlib, io, json, math, re, time, uuid
import os
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
BLICK = 705600000
# Bounded lock storage; readers must close their Windows handles before replace.
_JSON_LOCKS = tuple(threading.RLock() for _ in range(64))


def _json_lock(path):
    return _JSON_LOCKS[hash(os.path.normcase(os.path.abspath(path))) % len(_JSON_LOCKS)]


def _replace_json(source, destination):
    deadline = time.monotonic() + 2
    delay = .025
    while True:
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            # Other processes (e.g. scanners) can briefly deny delete sharing.
            remaining = deadline - time.monotonic()
            if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33) or remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, .2)

def read_json(path):
    with _json_lock(path):
        text = Path(path).read_text(encoding='utf-8-sig').rstrip('\x00')
    return json.loads(text)

def save_json(path, value):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2)
    with _json_lock(p):
        # Unique names also isolate writers in separate workbench processes.
        fd, name = tempfile.mkstemp(prefix='.' + p.name + '.', suffix='.tmp', dir=p.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(text)
            _replace_json(name, p)
        finally:
            try:
                Path(name).unlink(missing_ok=True)
            except OSError:
                pass

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def seconds_converter(d):
    tempos = sorted(d.get('time', {}).get('tempo') or [{'position':0,'bpm':120}], key=lambda t:t['position'])
    if tempos[0]['position'] > 0: tempos.insert(0, {'position':0,'bpm':tempos[0]['bpm']})
    positions = [x['position'] for x in tempos]; elapsed = [0.0]
    for i in range(1,len(tempos)):
        elapsed.append(elapsed[-1] + (positions[i]-positions[i-1])/BLICK * 60/tempos[i-1]['bpm'])
    def convert(b):
        i = max(0, bisect.bisect_right(positions,b)-1)
        return elapsed[i]+(b-positions[i])/BLICK*60/tempos[i]['bpm']
    return convert

def parse_svp(path):
    d = read_json(path); sec=seconds_converter(d)
    library = {g['uuid']:g for g in d.get('library',[])}
    tracks=[]; all_notes=[]
    for ti,t in enumerate(d.get('tracks',[])):
        notes=[]; refs=[('main',t.get('mainGroup',{}),t.get('mainRef',{}))]
        refs += [(str(ri),library.get(r.get('groupID'),{}),r) for ri,r in enumerate(t.get('groups',[]))]
        for ri,g,r in refs:
            offset=r.get('blickOffset',0); shift=r.get('pitchOffset',0)
            for ni,n in enumerate(g.get('notes',[])):
                onset=n.get('onset',0)+offset; end=onset+n.get('duration',0)
                # Absolute begin/end can trim a referenced group without deleting its notes.
                begin=r.get('blickAbsoluteBegin',-1); finish=r.get('blickAbsoluteEnd',-1)
                if begin>=0 and end<=begin: continue
                if finish>=0 and onset>=finish: continue
                start=sec(max(onset,begin) if begin>=0 else onset)
                stop=sec(min(end,finish) if finish>=0 else end)
                if stop<=start: continue
                note={'id':f'{ti}:{ri}:{ni}','track':ti,'group':ri,'index':ni,
                      'groupName':g.get('name',''),'start':round(start,6),'end':round(stop,6),
                      'pitch':n.get('pitch',60)+shift,'lyrics':n.get('lyrics',''),
                      'phonemes':n.get('phonemes',''),'muted':bool(r.get('muted',False))}
                notes.append(note)
        notes.sort(key=lambda n:(n['start'],n['end']))
        muted=bool(t.get('mixer',{}).get('mute',False))
        tr={'id':ti,'name':t.get('name',f'Track {ti+1}'),'voice':t.get('mainRef',{}).get('database',{}).get('name',''),
            'muted':muted,'groups':len(t.get('groups',[])),'notes':notes,'count':len(notes)}
        if notes: tracks.append(tr); all_notes.extend(notes)
    return {'version':d.get('version'),'tempo':d.get('time',{}).get('tempo',[]),'tracks':tracks,
            'notes':all_notes,'render':d.get('renderConfig',{}),'duration':max((n['end'] for n in all_notes),default=0)}

RULES={'short':'短音符','overlap':'音符重叠','octave':'八度跳进','leap':'较大跳进','lyric':'空白歌词','fragment':'同音碎片'}
def audit(parsed):
    flags=[]
    def add(n,kind,detail):
        flags.append({'id':n['id']+':'+kind,'noteId':n['id'],'track':n['track'],'start':n['start'],
                      'end':n['end'],'kind':kind,'label':RULES[kind],'detail':detail,'basis':'rule','severity':'review'})
    for t in parsed['tracks']:
        ns=t['notes']
        for i,n in enumerate(ns):
            if n['end']-n['start']<0.065: add(n,'short','短于 65 ms；检查是否为碎片、辅音或有意的短音。')
            if not n['lyrics'].strip(): add(n,'lyric','歌词字段为空；确认是否为延音或待填写音节。')
            if not i: continue
            prev=ns[i-1]; gap=n['start']-prev['end']; jump=abs(n['pitch']-prev['pitch'])
            if gap < -0.02: add(n,'overlap',f'与前一个音符重叠 {-gap*1000:.0f} ms；叠唱可能是有意的。')
            if gap<0.3 and jump>=11: add(n,'octave',f'相邻音符相差 {jump:g} 半音；检查八度或真实跳进。')
            elif gap<0.2 and jump>=8: add(n,'leap',f'相邻音符相差 {jump:g} 半音。')
            if abs(gap)<0.045 and jump==0 and n['end']-n['start']<0.1 and prev['end']-prev['start']<0.1:
                add(n,'fragment','连续同音短音符；检查重复字、断音或提取碎片。')
    return sorted(flags,key=lambda x:(x['start'],x['track'],x['kind']))

def read_srt(path):
    text=Path(path).read_text(encoding='utf-8-sig',errors='replace').replace('\r\n','\n')
    rows=[]
    def stamp(v):
        h,m,s=re.split('[:]',v.replace(',','.')); return int(h)*3600+int(m)*60+float(s)
    for block in re.split(r'\n\s*\n',text.strip()):
        lines=block.splitlines(); idx=next((i for i,l in enumerate(lines) if '-->' in l),None)
        if idx is None: continue
        a,b=lines[idx].split('-->'); b=b.strip().split()[0]
        try: rows.append({'start':stamp(a.strip()),'end':stamp(b),'text':'\n'.join(lines[idx+1:])})
        except ValueError: continue
    return rows

def read_lrc(path):
    rows=[]
    for line in Path(path).read_text(encoding='utf-8-sig',errors='replace').splitlines():
        times=re.findall(r'\[(\d+):(\d+(?:\.\d+)?)\]',line)
        text=re.sub(r'\[[^\]]*\]','',line).strip()
        if text:
            for m,s in times:rows.append({'start':int(m)*60+float(s),'text':text})
    rows.sort(key=lambda r:r['start'])
    for i,r in enumerate(rows):r['end']=rows[i+1]['start'] if i+1<len(rows) else r['start']+4
    return rows

def subtitle_checks(rows,duration):
    problems=[]
    for i,r in enumerate(rows):
        a=float(r['start']);b=float(r['end']);text=r.get('original','')+'\n'+r.get('translation','')
        reasons=[]
        if not math.isfinite(a) or not math.isfinite(b) or a<0 or b<=a:reasons.append('时间范围无效')
        if b>duration+2:reasons.append('超出音频时长')
        if i and a<float(rows[i-1]['end'])-0.02:reasons.append('与上一句重叠（对唱需人工确认）')
        if b>a and len(re.sub(r'\s','',text))/(b-a)>18:reasons.append('阅读速度偏快')
        if any(len(line)>40 for line in text.splitlines()):reasons.append('单行偏长')
        if not r.get('original','').strip():reasons.append('原文为空')
        if reasons:problems.append({'row':i,'reasons':reasons})
    return problems

def srt_text(rows,mode='bilingual'):
    def stamp(s):
        ms=round(float(s)*1000); h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    chunks=[]
    for r in rows:
        lines=[]
        if mode in ['bilingual','original'] and r.get('original','').strip():lines.append(r['original'].strip())
        if mode in ['bilingual','translation'] and r.get('translation','').strip():lines.append(r['translation'].strip())
        if lines:chunks.append(f"{len(chunks)+1}\n{stamp(r['start'])} --> {stamp(r['end'])}\n"+'\n'.join(lines))
    return '\n\n'.join(chunks)+'\n'

def export_revision(project,edits):
    """Write a new SVP in the pilot folder; never overwrite snapshot/source."""
    d=read_json(project['working']); lib={g['uuid']:g for g in d.get('library',[])}
    for e in edits:
        ti,ri,ni=e['noteId'].split(':'); t=d['tracks'][int(ti)]
        # Detach shared referenced groups so editing one instance does not change others.
        if ri=='main':g=t['mainGroup'];shift=t.get('mainRef',{}).get('pitchOffset',0)
        else:
            r=t['groups'][int(ri)]; old_id=r['groupID']
            if sum(rr.get('groupID')==old_id for tt in d['tracks'] for rr in tt.get('groups',[]))>1:
                g=json.loads(json.dumps(lib[old_id]));g['uuid']=str(uuid.uuid4());d['library'].append(g);lib[g['uuid']]=g;r['groupID']=g['uuid']
            else:g=lib[old_id]
            shift=r.get('pitchOffset',0)
        n=g['notes'][int(ni)]
        if 'lyrics' in e:
            if str(e['lyrics'])!=n.get('lyrics','') and n.get('phonemes'):n['phonemes']=''
            n['lyrics']=str(e['lyrics'])
        if 'pitch' in e:
            p=float(e['pitch'])
            if not math.isfinite(p) or p!=int(p) or not 0<=p<=127:raise ValueError('音高必须为 0–127 的整数')
            n['pitch']=int(p)-shift
    from workspaces import outputs
    dest=outputs(project)/'exports'/'svp';dest.mkdir(parents=True,exist_ok=True)
    d.setdefault('renderConfig',{})['destination']=str(outputs(project)/'exports'/'audio')
    out=dest/f"{project['id']}_review_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.svp"
    save_json(out,d)
    return out
