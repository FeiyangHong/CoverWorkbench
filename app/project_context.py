"""Resolve explicit music/video ownership without creating a project."""
from pathlib import Path
import project_assets,workspaces,video_project


def get(scope,ident):
    if scope=='music':
        project=project_assets.project(ident)
        if ident not in workspaces.registry():raise ValueError('请先在项目主页启用统一项目目录')
        root=workspaces.root(project)
        videos=[v for v in video_project.listing() if video_project.folder(v['id']).is_relative_to(root.resolve())]
        from video_links import STORE
        if STORE.exists():
            from core import read_json
            linked=read_json(STORE).get('links',{}).get(ident,{}).get('videoId')
            if linked and not any(v['id']==linked for v in videos):
                match=next((v for v in video_project.listing() if v['id']==linked),None)
                if match:videos.append(match)
        return {'scope':scope,'id':ident,'title':project['title'],'root':root.resolve(),'project':project,'videos':videos}
    if scope=='video':
        doc=video_project.load(ident)
        return {'scope':scope,'id':ident,'title':doc['name'],'root':video_project.folder(ident),'project':doc,'videos':[{'id':ident,'name':doc['name']}]}
    raise ValueError('未知工程类型')


def metadata(context):
    return context['root']/('analysis/Workbench' if context['scope']=='music' else 'ProjectData')
