"""Unified task views and validated retries across existing local services."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy,threading,time,uuid,os,subprocess
from contextlib import nullcontext
from core import ROOT,read_json,save_json
import lifecycle,video_project,video_jobs,separation_jobs,project_tasks,native_audio,workflow,task_resources

LOCK=threading.RLock();JOBS={};POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='studio-tools')
BASE=ROOT/'runtime/studio-tasks'
NAMES={'download':'视频下载','export':'完整导出','preview':'准确预览','analyze':'音频分析','pipeline':'两步素材分离','song':'人声与伴奏分离','harmony':'主声与和声分离','pack':'工程打包','import':'工程导入','preflight':'成片检查','proxy':'网页代理','diagnostic':'环境诊断','delivery':'音频交付','video':'视频交付','native':'插件试听','pymss-models':'PyMSS 模型准备'}

def public(j):return copy.deepcopy({k:v for k,v in j.items() if k!='cancel'})
def update(j,**values):
    with LOCK:j.update(values);save_json(Path(j['folder'])/'Task.json',public(j))
def check(j):
    if j['cancel'].is_set():raise InterruptedError('任务已取消；已有文件保留')
def own(ident):
    with LOCK:
        if ident in JOBS:return public(JOBS[ident])
    for file in BASE.glob('Task */Task.json'):
        try:
            d=read_json(file)
            if d['id']==ident:
                if d['status'] in ('running','queued'):d.update(status='interrupted',stage='后台重启，任务未自动重跑')
                return d
        except (OSError,ValueError,KeyError):continue
    raise ValueError('任务不存在')

def submit(body):
    kind=body.get('kind');ident=body.get('project')
    if kind not in ('preflight','proxy','diagnostic','pymss-models'):raise ValueError('未知后台工具')
    if kind=='pymss-models':
        import pymss_backend
        pymss_backend.installation()
        if not isinstance(body.get('models'),list) or not body['models'] or len(body['models'])>len(pymss_backend.PRESETS) or any(k not in pymss_backend.PRESETS for k in body['models']):raise ValueError('请选择已知模型')
    if kind not in ('diagnostic','pymss-models'):
        doc=video_project.load(ident)
        if body.get('revision')!=doc['revision']:raise ValueError('请先保存视频工程并重新提交检查')
        if kind=='proxy' and not body.get('asset'):raise ValueError('请选择媒体素材')
    with lifecycle.LOCK,LOCK:
        if lifecycle.STOPPING:raise ValueError('工作台正在退出')
        if sum(j['status'] in ('queued','running') for j in JOBS.values())>=4:raise ValueError('后台工具队列已满')
        BASE.mkdir(parents=True,exist_ok=True);number=1
        while (BASE/f'Task {number:03}').exists():number+=1
        folder=BASE/f'Task {number:03}';folder.mkdir()
        job={'id':uuid.uuid4().hex,'kind':kind,'project':ident,'created':time.time(),'status':'queued','stage':'等待处理','progress':0,'folder':str(folder),'request':body,'cancel':threading.Event()};JOBS[job['id']]=job;update(job);POOL.submit(run,job);return public(job)

def run(j):
    try:
        with (nullcontext() if j['kind']=='pymss-models' else task_resources.claim(lambda:check(j),lambda:update(j,stage='等待计算资源'))):
            check(j);update(j,status='running',stage='处理输入')
            if j['kind']=='preflight':
                import publish_checks
                result=publish_checks.run(j['project'],j['folder'],lambda:check(j),lambda p,s:update(j,progress=p,stage=s))
            elif j['kind']=='proxy':
                import video_edit
                result=video_edit.proxy(j['project'],j['request'],check=lambda:check(j))
            elif j['kind']=='pymss-models':
                import pymss_backend
                python,models=pymss_backend.paths();folder=Path(j['folder']);flag=folder/'Cancel.requested'
                update(j,stage='下载并登记缺少的模型；已有文件和 App 环境保留')
                with (folder/'Model Preparation.log').open('wb') as log:
                    child=subprocess.Popen([str(python),str(ROOT/'tools/PreparePyMSS.py'),'--cancel-file',str(flag),'--parent-pid',str(os.getpid()),'--models',*j['request']['models']],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    try:
                        while child.poll() is None:
                            if j['cancel'].wait(.2):flag.write_text('cancel',encoding='ascii');raise InterruptedError('已取消模型准备；下载片段保留，可再次继续')
                    finally:
                        if child.poll() is None:
                            try:child.wait(timeout=3)
                            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
                if child.returncode:raise ValueError('模型准备失败，请查看 Model Preparation.log；App 的 Python 环境未修改')
                result={'modelDirectory':str(models),'models':j['request']['models']}
            else:
                import deployment_tools
                result=deployment_tools.diagnostic(j['folder'])
            check(j);update(j,status='completed',progress=100,stage='完成',result=result)
    except InterruptedError as e:update(j,status='cancelled',stage='已取消',error=str(e))
    except Exception as e:update(j,status='failed',stage='未完成',error=str(e))

def error_help(message):
    value=str(message or '').lower()
    if any(x in value for x in ['winerror 5','permission','拒绝访问','being used']):return '文件可能被占用或目录不可写。关闭占用文件的程序后重试；任务记录和源文件保留。'
    if any(x in value for x in ['missing','not found','不存在','未找到','缺少']):return '检查环境设置或素材路径。重新定位文件后，以当前已保存工程重试。'
    if any(x in value for x in ['cuda','memory','显存']):return '可关闭其他占用显存的工具后重试。已完成的分离步骤可以复用。'
    return '查看任务详情与输出目录；修正输入或设置后重试。重试会新建任务，不覆盖旧结果。'

def all_jobs():
    rows=[]
    music=read_json(ROOT/'config/projects.json') if (ROOT/'config/projects.json').exists() else [];titles={p['id']:p['title'] for p in music}
    def add(origin,job,title='',project=None):
        j=copy.deepcopy(job);status={'ready':'completed','error':'failed'}.get(j['status'],j['status']);kind=j.get('kind') or j.get('mode') or j.get('action') or 'native'
        rows.append({'key':origin+':'+j['id'],'origin':origin,'id':j['id'],'name':NAMES.get(kind,kind),'kind':kind,'project':project or j.get('project') or j.get('musicId') or j.get('pid'),'title':title,'status':status,'created':j.get('created',j.get('createdAt',0)),'progress':j.get('progress',100 if status=='completed' else 0),'stage':j.get('stage') or j.get('message') or status,'error':j.get('error') or (j.get('message') if status in ('failed','interrupted') else ''),'help':error_help(j.get('error') or j.get('message')),'folder':j.get('folder') or j.get('outputDir'),'cancelable':status in ('queued','running'),'retryable':status in ('failed','cancelled','interrupted'),'resultSummary':{'issueCount':len((j.get('result') or {}).get('issues',[]))},'spec':j.get('spec')})
    for v in video_project.listing():
        for j in video_jobs.history(v['id']):add('video',j,v['name'])
    for p in music:
        for j in separation_jobs.history(p['id']):add('separation',j,p['title'])
    for f in project_tasks.BASE.glob('Task */Task.json'):
        try:j=read_json(f);add('package',project_tasks.get(j['id']),titles.get(j.get('project'),j.get('project') if not str(j.get('project','')).startswith('song-') else '工程'))
        except (OSError,ValueError,KeyError):continue
    ids={j['id'] for j in JOBS.values()}
    for f in BASE.glob('Task */Task.json'):
        try:
            j=read_json(f)
            if j['id'] not in ids:add('studio',own(j['id']),j.get('project') or '本机环境')
        except (OSError,ValueError,KeyError):continue
    with LOCK:
        for j in JOBS.values():add('studio',public(j),j.get('project') or '本机环境')
    with native_audio.LOCK:
        native=[dict(j,folder=str(native_audio.CACHE/key)) for key,j in native_audio.JOBS.items()]
    native_ids={j['id'] for j in native}
    for file in native_audio.CACHE.glob('*/Job.json'):
        try:
            j=read_json(file)
            if j['id'] not in native_ids:
                if j['status'] in ('queued','running'):j['status']='interrupted'
                native.append(dict(j,folder=str(file.parent)))
        except (ValueError,OSError,KeyError):continue
    for j in native:add('native',j,'插件试听')
    with workflow.GUARD:deliveries=[workflow.public(j) for j in workflow.JOBS.values()]
    for j in deliveries:add('delivery',j,titles.get(j.get('pid'),''))
    return sorted(rows,key=lambda r:(r['status'] not in ('queued','running'),-r['created']))[:200]

def action(key,body):
    selected=next((j for j in all_jobs() if j['key']==key),None)
    if not selected:raise ValueError('任务记录不存在')
    origin=selected['origin'];ident=selected['id'];operation=body.get('action')
    if operation=='cancel':
        if not selected['cancelable']:raise ValueError('任务已结束')
        if origin=='video':return video_jobs.cancel(ident)
        if origin=='separation':return separation_jobs.cancel(selected['project'],{'id':ident})
        if origin=='package':return project_tasks.cancel(ident)
        if origin=='native':return native_audio.cancel(ident)
        if origin=='delivery':return workflow.cancel(ident)
        with LOCK:
            if ident not in JOBS:raise ValueError('任务属于上次会话')
            JOBS[ident]['cancel'].set();return public(JOBS[ident])
    if operation!='retry' or not selected['retryable'] or body.get('confirmCurrent') is not True:raise ValueError('请明确确认以当前已保存素材重试')
    if origin=='video':
        old=video_jobs.job(ident);return video_jobs.submit(selected['project'],{'kind':old['kind'],**old.get('spec',{})})
    if origin=='separation':
        old=next(j for j in separation_jobs.history(selected['project']) if j['id']==ident)
        return separation_jobs.submit(selected['project'],{'mode':old['mode'],'harmonyInput':old['harmonyInput'],'input':old['input'],'resumeFrom':ident,'engine':old.get('engine','msst'),'quality':old.get('quality','high'),'songModel':old.get('songModel','big7'),'harmonyModel':old.get('harmonyModel','bs-frazer'),'batchSize':old.get('batchSize') or 1,'tta':bool(old.get('tta',False))})
    if origin=='package':
        old=project_tasks.get(ident);request=old.get('request')
        if not request:raise ValueError('旧任务未保存参数，请在工程管理中重新选择')
        return project_tasks.submit(old['scope'],old['project'],request)
    if origin=='native':
        import shutil
        old=native_audio.CACHE/ident
        def prepare(target):
            for file in old.rglob('*'):
                if file.is_file() and file.suffix.lower() in ('.json','.vstpreset') and file.name not in ('result.json','Job.json','error.json'):
                    dest=target/file.relative_to(old);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
        return native_audio.submit(read_json(old/'request.json'),prepare=prepare)
    if origin=='delivery':
        old=workflow.JOBS[ident];return workflow.enqueue(old['pid'],{'kind':old['kind'],**old['input']})
    old=own(ident);request=copy.deepcopy(old['request'])
    if request.get('project'):request['revision']=video_project.load(request['project'])['revision']
    return submit(request)

def report_file(ident):
    j=own(ident);file=Path(j['folder'])/'Diagnostic Report.zip'
    if j['kind']!='diagnostic' or j['status']!='completed' or not file.is_file():raise ValueError('诊断报告未完成')
    return file
