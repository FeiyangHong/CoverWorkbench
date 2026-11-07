"""Exercise the frozen app against a disposable workspace, never the owner's songs."""
from pathlib import Path
import argparse,json,os,shutil,socket,subprocess,tempfile,time,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[1]

def request(base,path,body=None):
    raw=None if body is None else json.dumps(body).encode();req=urllib.request.Request(base+path,data=raw,headers={'Content-Type':'application/json'} if raw else {});return json.load(urllib.request.urlopen(req,timeout=3))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',default=str(ROOT/'dist/desktop/CoverWorkbench/CoverWorkbench.exe'));parser.add_argument('--backend-only',action='store_true');args=parser.parse_args();exe=Path(args.exe).resolve();assert exe.is_file()
    version=subprocess.run([str(exe),'--module','yt_dlp','--version'],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert version.returncode==0 and version.stdout.strip(),('Frozen download helper did not return CLI output',version.stderr.decode('utf-8',errors='replace'))
    (ROOT/'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='Desktop Smoke ',dir=ROOT/'work') as td:
        root=Path(td)
        for name in ['app','assets','integrations','tools']:
            shutil.copytree(exe.parent/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        base=f'http://127.0.0.1:{port}';report=root/'Desktop Test.json';command=[str(exe),'--workspace',str(root),'--port',str(port)]+(['--server'] if args.backend_only else ['--smoke-test',str(report)])
        process=subprocess.Popen(command,cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if report.exists():break
                if args.backend_only:
                    try:
                        health=request(base,'/api/health');assert Path(health['root'])==root
                        assert request(base,'/api/projects')==[] and request(base,'/api/task-center')['jobs']==[]
                        state=request(base,'/api/lifecycle');request(base,'/api/shutdown/local',{'confirm':True,'instance':state['instance']});break
                    except urllib.error.URLError:pass
                if process.poll() is not None:raise AssertionError('Desktop process exited before verification: '+str(process.returncode))
                time.sleep(.2)
            else:raise AssertionError('Desktop smoke timed out')
            assert process.wait(timeout=20)==0
            if not args.backend_only:
                evidence=json.loads(report.read_text(encoding='utf-8'));assert evidence['ok'] and evidence['backendExited'],evidence
                (ROOT/'reports').mkdir(exist_ok=True);(ROOT/'reports/desktop-smoke.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PASS: frozen desktop '+('backend isolation, routes and clean exit' if args.backend_only else 'WebView2 UI, task entry, close/cancel dialog and owned backend shutdown'))
        finally:
            try:
                if Path(request(base,'/api/health')['root'])==root:
                    state=request(base,'/api/lifecycle')
                    if state['canExit']:request(base,'/api/shutdown/local',{'confirm':True,'instance':state['instance']})
            except (OSError,ValueError,KeyError):pass
            if process.poll() is None:process.terminate();process.wait(timeout=10)
            # WebView2 may release its profile handles a little after window exit.
            time.sleep(1)

if __name__=='__main__':main()
