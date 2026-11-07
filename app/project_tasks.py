"""Bounded background project transfers; exit remains blocked until they finish."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy,threading,time,uuid
from core import ROOT,save_json,read_json
import lifecycle

LOCK=threading.RLock();JOBS={};POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='project-transfer')
BASE=ROOT/'work/Project Packages'


def public(job):return {k:copy.deepcopy(v) for k,v in job.items() if k!='cancel'}


def update(job,**values):
    with LOCK:
        job.update(values);save_json(Path(job['folder'])/'Task.json',public(job))


def check(job):
    if job['cancel'].is_set():raise InterruptedError('任务已取消，原工程保留')


def submit(scope,ident,body):
    import project_packages
    if body.get('action') not in ('pack','import'):raise ValueError('未知工程传输任务')
    # Validate input and ownership before allocating a job.
    if body['action']=='pack':project_packages.contexts.get(scope,ident)
    else:project_packages.package_path(body.get('path'))
    with lifecycle.LOCK:
        if lifecycle.STOPPING:raise ValueError('工作台正在退出')
        with LOCK:
            if any(j['status'] in ('queued','running') for j in JOBS.values()):raise ValueError('已有工程传输任务，请等待或取消')
            BASE.mkdir(parents=True,exist_ok=True);number=1
            while (BASE/f'Task {number:03}').exists():number+=1
            folder=BASE/f'Task {number:03}';folder.mkdir()
            job={'id':uuid.uuid4().hex,'name':folder.name,'scope':scope,'project':ident,'action':body['action'],'status':'queued','stage':'等待处理','progress':0,'created':time.time(),'folder':str(folder),'cancel':threading.Event()}
            job['request']=copy.deepcopy(body)
            JOBS[job['id']]=job;update(job);POOL.submit(run,job,copy.deepcopy(body))
            return public(job)


def run(job,body):
    import project_packages
    try:
        update(job,status='running',stage='检查工程');check(job)
        result=project_packages.pack(job) if job['action']=='pack' else project_packages.import_package(job,body)
        update(job,status='completed',stage='完成',progress=100,result=result)
    except InterruptedError as error:update(job,status='cancelled',stage='已取消',error=str(error))
    except Exception as error:update(job,status='failed',stage='未完成',error=str(error))


def get(ident):
    with LOCK:
        if ident in JOBS:return public(JOBS[ident])
    if BASE.exists():
        for p in BASE.glob('Task */Task.json'):
            d=read_json(p)
            if d['id']==ident:
                if d['status'] in ('queued','running'):d.update(status='interrupted',stage='服务中断，请按原参数重新提交')
                return d
    raise ValueError('工程传输任务不存在')


def cancel(ident):
    with LOCK:
        if ident not in JOBS:raise ValueError('任务已结束或属于上次会话')
        JOBS[ident]['cancel'].set();return public(JOBS[ident])


def media(ident):
    job=get(ident)
    if job['status']!='completed' or job['action']!='pack':raise ValueError('工程包尚未完成')
    path=Path(job['result']['path']).resolve()
    if path.parent!=Path(job['folder']).resolve() or not path.is_file():raise ValueError('工程包不存在')
    return path
