from core import *
LIVE=ROOT/'runtime/sv-live'
def prepare_manifest():
    LIVE.mkdir(parents=True,exist_ok=True)
    rows=[]
    for p in read_json(ROOT/'config/projects.json'):
        d=read_json(ROOT/'data/projects'/f"{p['id']}.json")['project']
        rows.append(p['id']+'\t'+d['working'].encode().hex())
        alternate=Path(d.get('sv2Working') or Path(p['pilot'])/'working/sv2'/f"{p['id']}.svp")
        alternate.parent.mkdir(parents=True,exist_ok=True)
        if not alternate.exists():alternate.write_bytes(Path(d['working']).read_bytes())
        rows.append(p['id']+'\t'+str(alternate).encode().hex())
        baseline=ROOT/'data/live-addresses'/f"{p['id']}.json"
        if not baseline.exists():save_json(baseline,address_map(d,read_json(ROOT/'data/projects'/f"{p['id']}.json")['parsed'],initial=True))
        exportbase=ROOT/'data/export-base'/f"{p['id']}.svp"
        exportbase.parent.mkdir(parents=True,exist_ok=True)
        if not exportbase.exists():exportbase.write_bytes(Path(d['working']).read_bytes())
    (LIVE/'manifest.tsv').write_text('\n'.join(rows),encoding='ascii')
def live_status(pid):
    # Windows Lua replace uses remove+rename; retry the very short missing-file window.
    for attempt in range(4):
        try:
            s=read_json(LIVE/'status.json');s['connected']=time.time()-s['updatedAt']<4 and s['status']!='disconnected';s['selected']=s['connected'] and s['pid']==pid
            if not isinstance(s.get('notes'),list):s['notes']=[]
            return s
        except (OSError,ValueError,KeyError):
            if attempt<3:time.sleep(.01)
    return {'connected':False,'selected':False,'notes':[]}

def address_map(p,parsed,initial=False):
    if not initial:return read_json(ROOT/'data/live-addresses'/f"{p['id']}.json")
    d=read_json(p['working']);lib={g['uuid']:g for g in d.get('library',[])};result={}
    for n in parsed['notes']:
        t=d['tracks'][n['track']]
        if n['group']=='main':g=t['mainGroup'];r=t['mainRef']
        else:r=t['groups'][int(n['group'])];g=lib[r['groupID']]
        original=g['notes'][n['index']]
        result[n['id']]={'track':n['track'],'uuid':g['uuid'],'offset':r.get('blickOffset',0),'onset':original['onset'],'duration':original['duration']}
    return result
def key(n):return tuple(n.get(k) for k in ['track','uuid','offset','onset','duration'])
def mapped(p,parsed,s):
    if not s['selected']:return {}
    addresses=address_map(p,parsed);bykey={};duplicates=set()
    for n in s['notes']:
        k=key(n)
        if k in bykey:duplicates.add(k)
        bykey[k]=n
    return {nid:{**bykey[key(a)],'noteId':nid} for nid,a in addresses.items() if key(a) in bykey and key(a) not in duplicates}
def command(p,parsed,body):
    s=live_status(p['id'])
    if not s['selected']:raise ValueError('SV 未连接到本曲试点副本；请打开工作副本并启动 CoverWorkbench Live 脚本')
    verb=body.get('verb','apply');seq=uuid.uuid4().hex
    if verb not in ['apply','play','pause','disconnect','seek','gain']:raise ValueError('Invalid bridge command')
    fields=[seq,s['session'],p['id'].encode().hex(),verb]+['']*15
    if verb in ['apply','play','seek','gain'] and s.get('protocol')!=3:raise ValueError('SV 桥接脚本需要更新：先断开连接，再重新扫描并启动 CoverWorkbench Live')
    if verb in ['apply','play','seek']:
        a=float(body.get('start',0));b=float(body.get('end',a+3))
        if not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=p['duration']+2 or b-a>60:raise ValueError('试听范围无效')
        fields[13:15]=[str(a),str(b)]
        loop=body.get('loop',True)
        if not isinstance(loop,bool):raise ValueError('Invalid loop mode')
        pos=float(body.get('position',a))
        if not math.isfinite(pos) or not a<=pos<=b:raise ValueError('试听位置无效')
        fields[15:17]=['1' if loop else '0',str(pos)]
    if verb=='gain':
        ti=body.get('track');gain=float(body.get('gain',0))
        if not isinstance(ti,int) or not any(t.get('track')==ti and t.get('gainSupported') for t in s.get('tracks',[])) or not math.isfinite(gain) or not -30<=gain<=6:raise ValueError('音轨增益无效')
        fields[4]=str(ti);fields[17]=str(gain)
    if verb=='apply':
        nid=body.get('noteId');n=mapped(p,parsed,s).get(nid)
        if n is None:raise ValueError('当前音符已移位或改变分组，请在 SV 中修改或重新打开基准副本')
        expected=body.get('expected',{})
        if expected.get('pitch')!=n['pitch'] or expected.get('lyrics')!=n['lyrics']:raise ValueError('SV 中音符已经变化，网页已刷新；请检查后再次应用')
        pitch=float(body['pitch']);text=str(body['lyrics'])
        if not math.isfinite(pitch) or pitch!=int(pitch) or not 0<=pitch<=127 or len(text)>200:raise ValueError('音符值无效')
        fields[4:13]=[str(n['track']),n['uuid'].encode().hex(),str(n['offset']),str(n['onset']),str(n['duration']),str(n['pitch']),n['lyrics'].encode().hex(),str(int(pitch)),text.encode().hex()]
    tmp=LIVE/'command.tmp';tmp.write_text('\t'.join(fields),encoding='ascii');tmp.replace(LIVE/'command.tsv')
    for _ in range(30):
        time.sleep(.1);r=live_status(p['id'])
        if r.get('sequence')==seq:
            if r['status']=='error':raise ValueError(r['message'])
            return {'sequence':seq,'status':r['status'],'live':r,'notes':mapped(p,parsed,r)}
    raise ValueError('SV 未及时确认；请检查脚本和连接状态，不要重复盲目提交')
