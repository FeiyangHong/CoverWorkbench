"""Persistent support tasks and low-frequency handoff/backup scheduling."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy,json,os,re,subprocess,threading,time,uuid
from core import ROOT,read_json,save_json
import project_assets,project_context,project_tasks,project_backup,handoff_watch,audio_qc,asset_impact,lifecycle,settings
LOCK=threading.RLock();POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='production-support');JOBS={}
BASE=ROOT/'runtime/Production Support';CONFIG=ROOT/'config/production-support.local.json';STOP=threading.Event()
KINDS={'audio-check':'音乐交付检查','backup':'增量备份','verify-backup':'备份校验','restore-backup':'恢复为新工程'}

def config():return {'backupDirectory':'','backupEnabled':False,'intervalHours':24,'backupProjects':[],'watchEnabled':True,'lastScheduled':{},'backupFailures':{},**(read_json(CONFIG) if CONFIG.exists() else {})}

def configure(body):
    allowed={'backupDirectory','backupEnabled','intervalHours','backupProjects','watchEnabled'}
    if not isinstance(body,dict) or set(body)-allowed:raise ValueError('未知生产设置')
    d=config();d.update(body)
    if type(d['backupEnabled']) is not bool or type(d['watchEnabled']) is not bool:raise ValueError('自动任务设置必须为开或关')
    if type(d['intervalHours']) is not int or not 1<=d['intervalHours']<=720:raise ValueError('备份间隔为 1–720 小时')
    ids={p['id'] for p in read_json(ROOT/'config/projects.json')}
    if not isinstance(d['backupProjects'],list) or len(d['backupProjects'])>100 or any(p not in ids for p in d['backupProjects']):raise ValueError('请选择已有音乐工程')
    if d['backupDirectory']:d['backupDirectory']=str(project_backup.target(d['backupDirectory']))
    if d['backupEnabled'] and (not d['backupDirectory'] or not d['backupProjects']):raise ValueError('请先选择备份位置和工程')
    with LOCK:
        current=config()
        for key in ('lastScheduled','backupFailures'):d[key]=current[key]
        save_json(CONFIG,d)
    return d

def public(j):return copy.deepcopy({k:v for k,v in j.items() if k not in ('cancel','process')})
def update(j,**fields):
    with LOCK:j.update(fields);save_json(Path(j['folder'])/'Task.json',public(j))
def check(j):
    if j['cancel'].is_set():raise InterruptedError('任务已取消，源工程保留')


def backup_result(j,error=None):
    if j['kind']!='backup':return
    with LOCK:
        d=config()
        if error is None:d['backupFailures'].pop(j['project'],None)
        else:d['backupFailures'][j['project']]={'at':time.time(),'error':str(error),'task':j['id']}
        save_json(CONFIG,d)


def backup_due(d,ident,last,now):
    interval=d['intervalHours']*3600
    return ident not in d.get('backupFailures',{}) and now-last>=interval and now-d['lastScheduled'].get(ident,0)>=interval

def own(ident):
    with LOCK:
        if ident in JOBS:return public(JOBS[ident])
    for file in BASE.glob('Task */Task.json'):
        d=read_json(file)
        if d['id']==ident:
            if d['status'] in ('queued','running'):d.update(status='interrupted',stage='上次后台中断；未完成备份不会列为可恢复版本')
            return d
    raise ValueError('生产任务不存在')

def history():
    rows={}
    for file in BASE.glob('Task */Task.json'):
        try:
            d=read_json(file)
            if d['status'] in ('queued','running') and d['id'] not in JOBS:d.update(status='interrupted',stage='上次后台中断，请按当前保存版本重试')
            rows[d['id']]=d
        except (OSError,ValueError,KeyError):continue
    with LOCK:rows.update({k:public(j) for k,j in JOBS.items()})
    return sorted(rows.values(),key=lambda r:r['created'],reverse=True)[:50]

def cancel(ident):
    with LOCK:
        j=JOBS.get(ident)
        if not j or j['status'] not in ('queued','running'):raise ValueError('任务当前无法取消')
        j['cancel'].set()
        if j['status']=='queued':update(j,status='cancelled',stage='已取消')
    return public(j)

def submit(ident,body):
    kind=body.get('kind')
    if kind not in KINDS:raise ValueError('未知生产任务')
    project_assets.project(ident)
    directory=body.get('backupDirectory') or config()['backupDirectory']
    if kind!='audio-check':
        project_context.get('music',ident);project_backup.project_folder(directory,ident)
        if kind in ('verify-backup','restore-backup') and not body.get('snapshot'):raise ValueError('请选择备份版本')
        if kind=='restore-backup':
            from windows_names import component
            component(body.get('name'),'恢复工程名称')
    with lifecycle.LOCK,LOCK:
        if lifecycle.STOPPING:raise ValueError('工作台正在退出')
        if any(j['project']==ident and j['status'] in ('queued','running') for j in JOBS.values()):raise ValueError('此工程已有生产任务，请完成或取消后继续')
        BASE.mkdir(parents=True,exist_ok=True);number=1
        while (BASE/f'Task {number:03}').exists():number+=1
        folder=BASE/f'Task {number:03}';folder.mkdir()
        request={**body,'backupDirectory':directory}
        j={'id':uuid.uuid4().hex,'kind':kind,'project':ident,'title':project_assets.project(ident)['title'],'name':KINDS[kind],'request':request,'folder':str(folder),'created':time.time(),'status':'queued','progress':0,'stage':'等待处理','cancel':threading.Event()}
        JOBS[j['id']]=j;update(j);POOL.submit(run,j);return public(j)

def command(j,args,label,duration=None):
    check(j);log=Path(j['folder'])/('Command '+str(len(list(Path(j['folder']).glob('Command *.log')))+1).zfill(2)+'.log');progress=log.with_suffix('.progress')
    args=list(map(str,args));args=[args[0],'-progress',str(progress),'-nostats',*args[1:]] if duration else args
    update(j,stage=label)
    with log.open('w',encoding='utf8') as stream:
        stream.write(json.dumps(args,ensure_ascii=False)+'\n');stream.flush()
        child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            began=time.monotonic()
            while child.poll() is None:
                check(j)
                if time.monotonic()-began>7200:raise ValueError('音频检查超时，源文件保留')
                if duration and progress.exists():
                    values=re.findall(r'out_time_us=(\d+)',progress.read_text(encoding='utf8',errors='replace'))
                    if values:update(j,stage=label+' · '+str(min(99,round(int(values[-1])/1e6/duration*100)))+'%')
                j['cancel'].wait(.2)
            if child.returncode:raise ValueError(label+'失败，请查看本次任务日志')
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
    return log.read_text(encoding='utf8',errors='replace')

def run(j):
    import task_resources
    try:
        with task_resources.claim(lambda:check(j),lambda:update(j,stage='等待计算资源')):
            with LOCK:check(j);update(j,status='running')
            kind=j['kind'];request=j['request'];directory=request['backupDirectory']
            if kind=='audio-check':result=audio_qc.analyze(j,lambda args,label,duration=None:command(j,args,label,duration),lambda n,s:update(j,progress=n,stage=s),lambda:check(j))
            elif kind=='backup':result=project_backup.create(j,directory)
            elif kind=='verify-backup':result=project_backup.verify(j,directory,request['snapshot'])
            else:result=project_backup.restore(j,directory,request['snapshot'],request['name'])
            update(j,status='completed',stage='完成',progress=100,result=result)
            backup_result(j)
    except InterruptedError as error:update(j,status='cancelled',stage='已取消',error=str(error))
    except Exception as error:
        backup_result(j,error)
        update(j,status='failed',stage='备份失败，自动重试已暂停' if j['kind']=='backup' else '未完成',error=str(error))

def audio_media(ident):
    j=own(ident)
    if j['kind']!='audio-check' or j['status']!='completed':raise ValueError('没有可用的音乐检查试听')
    result=j['result']
    if result['source']!=asset_impact.fingerprint(result['path']):raise ValueError('音频已更新，请重新检查后试听')
    return Path(result['path'])

def status(ident=None):
    d=config();result={'config':d,'jobs':history()}
    if ident:
        assets=project_assets.status(ident);result.update(assets=assets,audioCheck=audio_qc.latest(ident),backups=[])
        if ident in d['backupFailures']:
            result['backupWarning']='此工程自动备份因失败暂停。请修复后点击「立即备份当前歌曲」；成功后自动恢复计划。原因：'+d['backupFailures'][ident]['error']
        if d['backupDirectory']:
            try:result['backups']=project_backup.listing(d['backupDirectory'],ident)
            except (ValueError,OSError) as error:result['backupWarning']=str(error)
        try:result['watch']=handoff_watch.scan(ident) if d['watchEnabled'] else {'changes':[],'disabled':True}
        except (OSError,ValueError) as error:result['watch']={'changes':[],'error':str(error)}
        try:
            linked=video_links_overview(ident);result['video']={'id':linked['linkedId'],'revision':linked['linked']['revision'] if linked['linked'] else None}
        except (OSError,ValueError,KeyError):result['video']=None
    return result

def video_links_overview(ident):
    import video_links
    return video_links.overview(ident)

def start():
    def service():
        while not STOP.wait(15):
            if lifecycle.STOPPING:return
            try:
                d=config();registry=read_json(ROOT/'config/projects.json')
                if d['watchEnabled']:
                    for p in registry:
                        try:handoff_watch.scan(p['id'])
                        except (OSError,ValueError,KeyError):pass
                if d['backupEnabled']:
                    for ident in d['backupProjects']:
                        try:
                            snapshots=project_backup.listing(d['backupDirectory'],ident);last=snapshots[0]['created'] if snapshots else 0
                            if not backup_due(d,ident,last,time.time()):continue
                            with lifecycle.LOCK,LOCK:
                                latest=config()
                                if not latest['backupEnabled'] or ident not in latest['backupProjects'] or latest['backupDirectory']!=d['backupDirectory']:continue
                                if not backup_due(latest,ident,last,time.time()):continue
                                submit(ident,{'kind':'backup','scheduled':True});latest['lastScheduled'][ident]=time.time();save_json(CONFIG,latest)
                        except (OSError,ValueError):pass
                import app_identity
                app_identity.apply_pending()
            except (OSError,ValueError,KeyError):continue
    thread=threading.Thread(target=service,name='production-watch',daemon=True);thread.start();return thread
