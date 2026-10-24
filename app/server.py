from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs
import json, mimetypes, os, re, sys, time, threading
import settings
settings.initialize()
from core import *
import lyrics, live, workflow, daw, desktop, projects, native_audio
live.prepare_manifest()

PORT=int(os.environ.get("COVERWORKBENCH_PORT", "8765"))
STATIC=ROOT/'app/static'
LOCK=threading.RLock()

def get_bundle(pid):
    if pid not in {p['id'] for p in read_json(ROOT/'config/projects.json')}:raise ValueError('Unknown project')
    bundle=read_json(ROOT/'data/projects'/f'{pid}.json')
    state=read_json(Path(bundle['project']['pilot'])/'analysis/review.json')
    bundle['state']=state
    comparison=Path(bundle['project']['pilot'])/'analysis/comparison.json'
    if comparison.exists():bundle['project']['comparison']=read_json(comparison)
    cmp=bundle['project']['comparison'];model=cmp.get('gameSmall',{}).get('notes',[])
    if model:
        primary={'hoshi':['主声','主音_2','主音_3'],'stella':['主声'],'ray':['POPY主声','ROSE主声'],'dependence':['ROSE主声']}.get(pid, [t['name'] for t in bundle['parsed']['tracks']])
        for t in bundle['parsed']['tracks']:
            if t['name'] not in primary:continue
            for n in t['notes']:
                if n['end']-n['start']<.08:continue
                candidates=[(max(0,min(m['end'],n['end'])-max(m['start'],n['start'])),m) for m in model if m['start']<n['end'] and m['end']>n['start']]
                if not candidates:continue
                overlap,m=max(candidates,key=lambda pair:pair[0]);difference=abs(m['pitch']-n['pitch'])
                if overlap/(n['end']-n['start'])>=.6 and difference>=2:
                    bundle['flags'].append({'id':n['id']+':model_pitch','noteId':n['id'],'track':n['track'],'start':n['start'],'end':n['end'],'kind':'model_pitch','label':'模型音高分歧','detail':f"SV 音符 {n['pitch']:g}；GAME {m['pitch']:g}，相差 {difference:g} 半音。只比较基础音符，不含 SV 音高曲线；请试听确认。",'basis':'GAME small','severity':'review'})
        bundle['flags'].sort(key=lambda f:(f['start'],f['track'],f['kind']))
    bundle['subtitleChecks']=subtitle_checks(state['subtitles'],bundle['project']['duration'])
    bundle['live']=live.live_status(pid)
    bundle['liveNotes']=live.mapped(bundle['project'],bundle['parsed'],bundle['live'])
    bundle['project']['sv2Working']=str(Path(bundle['project']['pilot'])/'working/sv2'/f'{pid}.svp')
    bundle['lyricCandidates']=lyrics.cache_candidates(bundle['project'])
    bundle['lyricPackage']=read_json(Path(bundle['project']['pilot'])/'analysis/lyrics-current.json') if (Path(bundle['project']['pilot'])/'analysis/lyrics-current.json').exists() else None
    return bundle

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def handle(self):
        try:super().handle()
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def log_message(self,fmt,*args):
        if '/media/' not in self.path:print(time.strftime('%H:%M:%S'),fmt%args,flush=True)
    def allowed(self):
        return self.headers.get('Host') in {f'127.0.0.1:{PORT}',f'localhost:{PORT}'}
    def respond(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        if self.command!='HEAD':self.wfile.write(raw)
    def file(self,path,download=False):
        p=Path(path)
        if not p.is_file():return self.respond({'error':'File not found'},404)
        size=p.stat().st_size;start=0;end=size-1;partial=False
        if self.headers.get('Range'):
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
            if not m:return self.respond({'error':'Invalid range'},416)
            if not m[1]:start=max(0,size-int(m[2]))
            else:start=int(m[1]);end=min(size-1,int(m[2])) if m[2] else size-1
            if start> end or start>=size:return self.respond({'error':'Range outside file'},416)
            partial=True
        self.send_response(206 if partial else 200)
        mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
        if p.suffix=='.js':mime='text/javascript'
        if p.suffix=='.srt':mime='application/x-subrip'
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-cache')
        if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if download:
            from urllib.parse import quote
            self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(p.name))
        self.end_headers()
        if self.command=='HEAD':return
        try:
            with p.open('rb') as f:
                f.seek(start);left=end-start+1
                while left:
                    data=f.read(min(65536,left))
                    if not data:break
                    self.wfile.write(data);left-=len(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        if not self.allowed():return self.respond({'error':'Local access only'},403)
        try:
            u=urlsplit(self.path);path=unquote(u.path);parts=path.strip('/').split('/')
            if path=='/api/settings':return self.respond(settings.status())
            if path=='/api/mix-native':return self.respond(native_audio.status())
            if parts[:2]==['api','mix-job'] and len(parts)==3:return self.respond(native_audio.job(parts[2]))
            if parts[0]=='mix-audio' and len(parts)==3:return self.file(native_audio.media(parts[1],parts[2]))
            if path=='/api/projects':return self.respond(read_json(ROOT/'config/projects.json'))
            if path=='/api/desktop':return self.respond(desktop.status())
            if len(parts)==2 and parts[0]=='desktop-icons':return self.file(desktop.asset(parts[1]),parts[1].endswith('.ico'))
            if path=='/api/daw/status':return self.respond({'templates':daw.templates(),'builds':daw.history(),'outputOptions':daw.output_options()})
            if path=='/api/health':return self.respond({'ok':True,'version':'0.3.0','root':str(ROOT),'pid':os.getpid()})
            if parts[:2]==['api','workflow'] and len(parts)==3:return self.respond(workflow.status(parts[2]))
            if path=='/report/comparison.md':return self.file(ROOT/'reports/comparison.md',True)
            if parts[:2]==['api','project'] and len(parts)==3:return self.respond(get_bundle(parts[2]))
            if parts[:2]==['api','live'] and len(parts)==3:
                b=get_bundle(parts[2]);return self.respond({'live':b['live'],'notes':b['liveNotes']})
            if parts[0]=='media' and len(parts)==3:
                p=get_bundle(parts[1])['project'];role=parts[2]
                if role not in p['audio']:return self.respond({'error':'Audio not available'},404)
                return self.file(p['audio'][role]['preview'])
            if parts[0]=='download' and len(parts)==3:
                p=get_bundle(parts[1])['project'];base=Path(p['pilot'])/'exports';target=(base/parts[2]).resolve()
                # Export download uses basename lookup only, so URLs cannot read arbitrary paths.
                matches=[f for f in base.rglob('*') if f.is_file() and f.name==parts[2]]
                if len(matches)!=1:return self.respond({'error':'Export not found'},404)
                return self.file(matches[0],True)
            p=(STATIC/(path.lstrip('/') or 'index.html')).resolve()
            if not p.is_relative_to(STATIC.resolve()):return self.respond({'error':'Invalid path'},403)
            return self.file(p)
        except (ValueError,KeyError,IndexError) as e:return self.respond({'error':str(e)},400)
        except Exception as e:return self.respond({'error':str(e)},500)
    def do_POST(self):
        if not self.allowed():return self.respond({'error':'Local access only'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}:return self.respond({'error':'Origin rejected'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.respond({'error':'JSON required'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>2_000_000:return self.respond({'error':'Request too large'},413)
            body=json.loads(self.rfile.read(size));parts=urlsplit(self.path).path.strip('/').split('/')
            if len(parts)!=3 or parts[0]!='api':return self.respond({'error':'Route not found'},404)
            action,pid=parts[1:]
            if action=='mix-inspect':return self.respond(native_audio.inspect(body))
            if action=='mix-render':return self.respond(native_audio.enqueue(body),202)
            if action=='project-import':
                with LOCK:
                    result=projects.create(body);live.prepare_manifest()
                return self.respond(result,201)
            if action=='daw-template':return self.respond(daw.register_template(body),201)
            if action=='daw-host':return self.respond(daw.register_sv2_host(body),201)
            if action=='settings':return self.respond(settings.save(body))
            if action=='desktop-icon':return self.respond(desktop.apply(body))
            if action=='daw-browse':return self.respond(daw.browse(body))
            if action=='daw-open':return self.respond(daw.open_local(body))
            if action=='daw-inspect':return self.respond(daw.inspect(body))
            if action=='daw-build':return self.respond(daw.build(body),201)
            if action=='jobs':return self.respond(workflow.enqueue(pid,body),202)
            if action=='watcher':return self.respond(workflow.watch_config(pid,body.get('enabled')))
            # Network lyric lookup must not block native note audition/review writes.
            if action in ['lyrics-search','lyrics-build','lyrics-revise']:
                p=get_bundle(pid)['project']
                if action=='lyrics-search':return self.respond({'candidates':lyrics.search(p,body.get('query',''))})
                if action=='lyrics-build':return self.respond(lyrics.build(p,body))
                return self.respond(lyrics.revise(p,body))
            with LOCK:
                bundle=get_bundle(pid);p=bundle['project'];state=bundle['state']
                if action=='live':
                    r=live.command(p,bundle['parsed'],body)
                    if body.get('verb','apply')=='apply':
                        nid=body['noteId'];state['edits'][nid]={'noteId':nid,'pitch':int(body['pitch']),'lyrics':str(body['lyrics'])}
                        state['updatedAt']=time.strftime('%Y-%m-%d %H:%M:%S');save_json(Path(p['pilot'])/'analysis/review.json',state)
                    r['state']=state;return self.respond(r)
                if action=='state':
                    if 'decisions' in body:
                        valid={f['id'] for f in bundle['flags']}
                        decisions=body['decisions']
                        if not isinstance(decisions,dict) or any(k not in valid or v not in ['confirmed','ignored','pending'] for k,v in decisions.items()):raise ValueError('Invalid review decision')
                        state['decisions'].update(decisions)
                    if 'edit' in body:
                        e=body['edit'];valid={n['id'] for n in bundle['parsed']['notes']}
                        if e['noteId'] not in valid:raise ValueError('Unknown note')
                        pitch=float(e['pitch'])
                        if not math.isfinite(pitch) or pitch!=int(pitch) or not 0<=pitch<=127:raise ValueError('Invalid pitch')
                        if len(str(e['lyrics']))>200:raise ValueError('Lyric too long')
                        state['edits'][e['noteId']]={'noteId':e['noteId'],'pitch':int(pitch),'lyrics':str(e['lyrics'])}
                    if 'subtitles' in body:
                        if not isinstance(body['subtitles'],list) or len(body['subtitles'])>2000:raise ValueError('Invalid subtitles')
                        rows=[]
                        for r in body['subtitles']:
                            a=float(r['start']);b=float(r['end'])
                            if not math.isfinite(a) or not math.isfinite(b) or a<0 or b<=a:raise ValueError('字幕起止时间无效')
                            rows.append({'start':a,'end':b,'original':str(r.get('original',''))[:2000],'translation':str(r.get('translation',''))[:2000],'reading':str(r.get('reading',''))[:2000],'status':r.get('status','edited')})
                        state['subtitles']=rows;state['subtitleMode']='edited'
                    state['updatedAt']=time.strftime('%Y-%m-%d %H:%M:%S')
                    save_json(Path(p['pilot'])/'analysis/review.json',state)
                    return self.respond({'state':state,'checks':subtitle_checks(state['subtitles'],p['duration'])})
                if action=='export-svp':
                    fallback=dict(p);fallback['working']=str(ROOT/'data/export-base'/f'{pid}.svp')
                    out=export_revision(fallback,list(state['edits'].values()))
                    return self.respond({'file':str(out),'url':f'/download/{pid}/{out.name}','edits':len(state['edits'])})
                if action=='export-subtitles':
                    mode=body.get('mode','bilingual')
                    if mode not in ['bilingual','original','translation']:raise ValueError('Invalid subtitle mode')
                    if not state['subtitles']:raise ValueError('请先生成或填写字幕')
                    out=Path(p['pilot'])/'exports/subtitles'/f'{pid}_{mode}_{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.srt'
                    out.write_text(srt_text(state['subtitles'],mode),encoding='utf-8-sig')
                    save_json(out.with_suffix('.json'),state['subtitles'])
                    return self.respond({'file':str(out),'url':f'/download/{pid}/{out.name}'})
                if action=='export-report':
                    out=Path(p['pilot'])/'exports/reports'/f'{pid}_review_{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.csv'
                    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['time_seconds','track','kind','note_id','status','detail'])
                    for f in bundle['flags']:writer.writerow([f['start'],f['track'],f['label'],f['noteId'],state['decisions'].get(f['id'],'pending'),f['detail']])
                    out.write_text(stream.getvalue(),encoding='utf-8-sig')
                    return self.respond({'file':str(out),'url':f'/download/{pid}/{out.name}'})
            return self.respond({'error':'Unknown action'},404)
        except daw.FolderConflict as e:return self.respond({'error':str(e),'conflict':e.detail},409)
        except (ValueError,KeyError,IndexError,TypeError) as e:return self.respond({'error':str(e)},400)
        except Exception as e:return self.respond({'error':str(e)},500)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
        workflow.start()
        print(f'CoverWorkbench http://127.0.0.1:{PORT}',flush=True)
        server.serve_forever()
    except OSError as e:
        print(f'无法启动：{e}。若已运行，请打开 http://127.0.0.1:{PORT}',flush=True);sys.exit(1)
