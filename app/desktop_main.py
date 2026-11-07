"""Windows WebView2 shell; one workspace and the same localhost service."""
from pathlib import Path
import argparse,json,os,runpy,socket,subprocess,sys,threading,time,urllib.request,urllib.error,webbrowser

def request(base,path,body=None,timeout=3):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'} if data else {})
    return json.load(urllib.request.urlopen(req,timeout=timeout))

def root_path(value=None):
    root=Path(value or os.environ.get('COVERWORKBENCH_ROOT') or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])).resolve()
    if not (root/'app/static/index.html').is_file():raise ValueError('请选择完整 CoverWorkbench 工作区目录，需含 app/static/index.html')
    return root

def ensure_service(root,port):
    base=f'http://127.0.0.1:{port}'
    try:
        health=request(base,'/api/health')
        if Path(health['root']).resolve()!=root:raise ValueError('端口已被另一工作区使用，请更换端口')
        try:request(base,'/api/task-center')
        except urllib.error.HTTPError as error:raise ValueError('后台仍是旧版本。请先保存网页编辑、彻底退出后台，再启动桌面版。') from error
        return base,request(base,'/api/lifecycle')['instance'],False
    except (urllib.error.URLError,TimeoutError,ConnectionError):pass
    (root/'logs').mkdir(exist_ok=True);(root/'runtime').mkdir(exist_ok=True)
    command=[sys.executable,'--server','--workspace',str(root),'--port',str(port)] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve()),'--server','--workspace',str(root),'--port',str(port)]
    # An existing source workspace retains its optional native/lyrics packages.
    source_python=root/'.venv/Scripts/python.exe'
    if source_python.is_file():command=[str(source_python),str(root/'app/server.py')]
    with (root/'logs/desktop-service.log').open('ab') as log:
        process=subprocess.Popen(command,cwd=root,env={**os.environ,'COVERWORKBENCH_ROOT':str(root),'COVERWORKBENCH_PORT':str(port),'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(120):
        if process.poll() is not None:raise ValueError('后台启动失败，请查看 logs/desktop-service.log')
        try:
            health=request(base,'/api/health',timeout=1)
            if Path(health['root']).resolve()!=root:raise ValueError('端口正在被其他工作区使用')
            if health['pid']!=process.pid:
                owner=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',f'(Get-CimInstance Win32_Process -Filter "ProcessId = {int(health["pid"])}").ParentProcessId'],capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) if os.name=='nt' else None
                if not owner or owner.stdout.strip()!=str(process.pid):raise ValueError('后台进程身份不匹配，已保留现有服务')
            (root/'runtime/server.pid').write_text(str(health['pid']),encoding='ascii')
            return base,request(base,'/api/lifecycle')['instance'],True
        except (urllib.error.URLError,TimeoutError,ConnectionError):time.sleep(.1)
    raise ValueError('后台启动超时；请查看 logs/desktop-service.log')

class Bridge:
    def __init__(self,base,instance,owned):self._base=base;self._instance=instance;self._owned=owned;self._window=None;self._allow_close=False
    def info(self):return {'desktop':True,'serviceOwned':self._owned,'url':self._base,'engine':'WebView2','sharedWorkspace':True}
    def open_browser(self):webbrowser.open(self._base);return True
    def close_window(self):
        self._allow_close=True
        threading.Thread(target=self._window.destroy,daemon=True).start();return True
    def finish_exit(self):
        try:
            state=request(self._base,'/api/lifecycle')
            if state['instance']==self._instance:raise ValueError('后台仍在运行，请等待完成退出')
        except (urllib.error.URLError,TimeoutError,ConnectionError):pass
        return self.close_window()
    def closing(self):
        if self._allow_close:return True
        try:
            if self._window.evaluate_js('Boolean(window.CWDesktop)'):
                self._window.run_js('window.CWDesktop.requestClose()');return False
        except Exception:pass
        return True

def smoke(window,bridge,path):
    # Exercises the actual WebView2 document and close event in a disposable workspace.
    report={'engine':'WebView2'}
    try:
        for _ in range(160):
            try:
                if window.evaluate_js('Boolean(window.CWDesktop && document.querySelector("#taskCenterButton"))'):break
            except Exception:pass
            time.sleep(.2)
        else:raise RuntimeError('Desktop document did not become ready')
        window.run_js('window.CWDesktop.requestClose()');time.sleep(.3)
        report['closeDialog']=window.evaluate_js('document.querySelector("#desktopCloseDialog").open')
        window.run_js('document.querySelector("#desktopCloseCancel").click()')
        report['cancelKeptWindow']=not window.evaluate_js('document.querySelector("#desktopCloseDialog").open')
        report['taskButton']=window.evaluate_js('document.querySelector("#taskCenterButton").textContent')
        report['userAgent']=window.evaluate_js('navigator.userAgent')
        state=request(bridge._base,'/api/lifecycle')
        if not bridge._owned or not state['canExit']:raise ValueError('Smoke test requires its own idle backend')
        request(bridge._base,'/api/shutdown/local',{'confirm':True,'instance':bridge._instance});time.sleep(1)
        for _ in range(30):
            try:request(bridge._base,'/api/health');time.sleep(.1)
            except (urllib.error.URLError,TimeoutError,ConnectionError):break
        else:raise ValueError('Backend did not exit')
        report['backendExited']=True;report['ok']=bool(report['closeDialog'] and report['cancelKeptWindow'])
    except Exception as error:report.update(ok=False,error=str(error))
    finally:
        Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');bridge.close_window()

def main():
    if '--module' in sys.argv:
        index=sys.argv.index('--module');name=sys.argv[index+1]
        if name!='yt_dlp':raise ValueError('Unknown module')
        sys.argv=[name,*sys.argv[index+2:]];runpy.run_module(name,run_name='__main__');return
    parser=argparse.ArgumentParser();parser.add_argument('--workspace');parser.add_argument('--port',type=int,default=int(os.environ.get('COVERWORKBENCH_PORT','8765')));parser.add_argument('--server',action='store_true');parser.add_argument('--worker');parser.add_argument('--module');parser.add_argument('--smoke-test');parser.add_argument('arguments',nargs='*');args=parser.parse_args()
    if not 1<=args.port<=65535:raise ValueError('端口应在 1 至 65535 之间')
    root=root_path(args.workspace);os.environ['COVERWORKBENCH_ROOT']=str(root);os.environ['COVERWORKBENCH_PORT']=str(args.port);sys.path.insert(0,str(root/'app'))
    if args.worker:
        if args.worker not in ('native_audio_worker.py','song_mix_worker.py'):raise ValueError('Unknown worker')
        sys.argv=[str(root/'app'/args.worker),*args.arguments];runpy.run_path(sys.argv[0],run_name='__main__');return
    if args.module:
        if args.module!='yt_dlp':raise ValueError('Unknown module')
        sys.argv=[args.module,*args.arguments];runpy.run_module(args.module,run_name='__main__');return
    if args.server:
        (root/'logs').mkdir(parents=True,exist_ok=True)
        if sys.stdout is None:sys.stdout=(root/'logs/desktop-service.log').open('a',encoding='utf-8')
        if sys.stderr is None:sys.stderr=sys.stdout
        runpy.run_path(str(root/'app/server.py'),run_name='__main__');return
    (root/'logs').mkdir(exist_ok=True)
    if sys.stdout is None:sys.stdout=(root/'logs/desktop-window.log').open('a',encoding='utf-8')
    if sys.stderr is None:sys.stderr=sys.stdout
    import webview
    base,instance,owned=ensure_service(root,args.port);bridge=Bridge(base,instance,owned)
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=True
    window=webview.create_window('CoverWorkbench',base+'/?desktop=1',js_api=bridge,width=1440,height=960,min_size=(900,650),background_color='#f6f4fb',text_select=True,zoomable=True)
    bridge._window=window;window.events.closing+=bridge.closing
    profile=root/'runtime/Desktop Profile';profile.mkdir(parents=True,exist_ok=True)
    try:
        webview.start(smoke if args.smoke_test else None,(window,bridge,args.smoke_test) if args.smoke_test else None,gui='edgechromium',private_mode=False,storage_path=str(profile),icon=str(root/'assets/icons/cw-signature.ico'))
    except Exception:
        if owned:
            try:
                state=request(base,'/api/lifecycle')
                if state['instance']==instance and state['canExit']:request(base,'/api/shutdown/local',{'confirm':True,'instance':instance})
            except (OSError,ValueError):pass
        raise

if __name__=='__main__':
    try:main()
    except Exception as error:
        if '--server' in sys.argv or '--worker' in sys.argv or '--module' in sys.argv:raise
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(error)+'\n\n源码启动需先运行 Setup.ps1 -WithDesktop；桌面窗口需要 WebView2 Runtime。','CoverWorkbench',0x10)
        else:raise
