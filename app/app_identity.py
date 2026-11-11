"""Separate identities for the running backend, disk source and browser resources."""
from pathlib import Path
import hashlib,json,subprocess,sys,time,threading
from core import ROOT,read_json,save_json,sha
LOCK=threading.RLock();PENDING=ROOT/'runtime/Pending Update.json'

def digest(folder,pattern):
    h=hashlib.sha256()
    for p in sorted(Path(folder).rglob(pattern)):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(p.relative_to(folder).as_posix().encode());h.update(p.read_bytes())
    return h.hexdigest()

def revision():
    if (ROOT/'.git').exists():
        try:return subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,timeout=3,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).decode().strip()
        except (OSError,subprocess.SubprocessError):pass
    try:return read_json(ROOT/'Build Info.json').get('revision','source')
    except (OSError,ValueError):return 'source'

RUNNING_REVISION=revision();STARTED=time.time()
BUILD=Path(sys.executable).parent/'Build Info.json'
INFO=read_json(BUILD) if getattr(sys,'frozen',False) and BUILD.is_file() else {}
RUNNING_BACKEND=INFO.get('backendDigest') or digest(Path(__file__).parent,'*.py')

def status(frontend=None):
    back=digest(ROOT/'app','*.py');front=digest(ROOT/'app/static','*')
    pending=read_json(PENDING) if PENDING.exists() else None
    return {'runningRevision':INFO.get('revision',RUNNING_REVISION),'sourceRevision':revision(),'runningBackend':RUNNING_BACKEND,'diskBackend':back,'frontend':front,'browserFrontend':frontend,'restartRequired':back!=RUNNING_BACKEND,'reloadRequired':bool(frontend and frontend!=front),'startedAt':STARTED,'packaged':bool(getattr(sys,'frozen',False)),'pendingUpdate':pending}

def defer(body):
    import deployment_tools
    if getattr(sys,'frozen',False):raise ValueError('当前是打包后台：请将新版桌面包解压到独立目录，保存退出后启动新版并指向此工作区；不要覆盖运行中的 EXE')
    if body.get('confirm') is not True:raise ValueError('请确认任务结束后应用源码更新；应用后仍需保存草稿并重启')
    from video_project import local
    source=local(body.get('path'),{'.zip'})
    with LOCK:
        if PENDING.exists() and read_json(PENDING).get('status')=='waiting':raise ValueError('已有等待中的更新，请先取消或完成')
        row={'path':str(source),'sha256':sha(source),'status':'waiting','created':time.time()};save_json(PENDING,row);return row

def cancel():
    with LOCK:
        if PENDING.exists():
            row=read_json(PENDING)
            if row['status']!='waiting':raise ValueError('更新已经开始或完成')
            row['status']='cancelled';save_json(PENDING,row)
    return {'cancelled':True}

def apply_pending():
    if not PENDING.exists():return
    import lifecycle,deployment_tools
    with lifecycle.LOCK,LOCK:
        row=read_json(PENDING)
        if row['status']!='waiting' or not lifecycle.status()['canExit']:return
        try:
            if sha(Path(row['path']))!=row['sha256']:raise ValueError('等待期间更新包已改变，请重新选择')
            row['status']='applying';save_json(PENDING,row)
            row['result']=deployment_tools.apply({'path':row['path'],'confirm':True});row['status']='applied';row['message']='源码已更新，请保存草稿并重启后台'
        except Exception as error:row.update(status='failed',message=str(error))
        save_json(PENDING,row)
