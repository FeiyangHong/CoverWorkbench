"""Private associations, non-destructive material handoff and exactly-once offsets."""
from pathlib import Path
import copy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import video_links as links
import video_project as video
import video_workflow as workflow
from core import read_json, save_json, sha


def rejects(fn, message):
    try:
        fn()
    except ValueError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError('Expected rejection: ' + message)


def main():
    with tempfile.TemporaryDirectory(prefix='music video handoff ') as tmp:
        root = Path(tmp)
        links.ROOT = root
        links.STORE = root / 'config/video-links.local.json'
        video.BASE = root / 'projects/video'
        pilot = root / 'pilot'
        mix, lead, latest, mv = [root / n for n in ['mix.wav', 'lead.wav', 'latest.flac', 'mv.mp4']]
        for path in [mix, lead, latest, mv]:
            path.write_bytes(b'synthetic local fixture')
        save_json(root / 'config/projects.json', [{'id': 'song', 'title': 'Test Song'}, {'id': 'other', 'title': 'Other'}])
        project = dict(id='song', title='Test Song', artist='Test Artist', pilot=str(pilot),
                       audio={'mix': {'original': str(mix), 'preview': str(lead)}, 'lead': {'original': str(lead)}})
        save_json(root / 'data/projects/song.json', {'project': project})
        save_json(root / 'data/projects/other.json', {'project': {**project, 'id': 'other', 'title': 'Other'}})
        cues = [{'start': 1, 'end': 3, 'original': 'Hello', 'translation': '你好'}]
        review = pilot / 'analysis/review.json'
        save_json(review, {'subtitles': cues})
        originals = {p: sha(p) for p in [mix, lead, latest, mv, review]}
        source = links.overview('song')
        assert source['audio']['path'] == str(mix) and source['captions']['translation'] == 1
        assert not source['linked'] and source['defaultName'] == 'Test Song Video'
        for name, job in [('failed', dict(pid='song', status='failed')), ('other', dict(pid='other', status='completed')),
                          ('missing', dict(pid='song', status='completed'))]:
            save_json(root / f'runtime/workflow/{name}.json', {**job, 'kind': 'delivery', 'createdAt': 4, 'input': {'audio': None if name == 'missing' else str(lead)}})
        assert links.overview('song')['audio']['path'] == str(mix), 'Failed, unrelated and missing deliveries must not replace the final mix'
        save_json(root / 'runtime/workflow/done.json', dict(pid='song', kind='delivery', status='completed', createdAt=5, input={'audio': str(latest)}))
        source = links.overview('song')
        assert source['audio']['path'] == str(latest)
        rejects(lambda: links.perform('song', {'action': 'create', 'name': 'Invalid/Name', 'sourceSignature': source['signature']}), '工程名')
        assert not video.BASE.exists(), 'Invalid creation left an orphan project'
        first = links.perform('song', {'action': 'create', 'name': 'Song Video', 'sourceSignature': source['signature']})
        ident = first['videoId']
        doc = video.load(ident)
        assert doc['audio'] == str(latest) and doc['cues'][0]['translation'] == '你好' and doc['revision'] == 1
        assert doc['timing']['clock'] == 'audio'
        saved = sha(video.folder(ident) / 'project.json')
        assert links.perform('song', {'action': 'create'})['existing']
        assert sha(video.folder(ident) / 'project.json') == saved, 'Reentry modified the video'
        doc.update(video=str(mv), audioOffset=2)
        doc = video.save(ident, doc)
        assert doc['cues'][0]['start'] == 3 and not workflow.blockers(doc)
        doc = video.save(ident, doc)
        assert doc['cues'][0]['start'] == 3, 'First MV offset applied twice'
        doc['audioOffset'] = 3
        doc = video.save(ident, doc)
        assert doc['cues'][0]['start'] == 4
        # Bind a carefully edited video; linking must not touch its document at all.
        existing = video.create({'name': 'Existing Edited Video'})
        existing.update(audio=str(mix), video=str(mv), audioOffset=5, subtitleShift=.3,
                        cues=[{'id': 'A', 'start': 11, 'end': 14, 'original': 'Edited', 'translation': '保留',
                               'translationTiming': {'start': 12, 'end': 13}}])
        existing['styles']['translation']['size'] = 53
        existing = video.save(existing['id'], existing, internal={'timing': workflow.timing(existing, 'video')})
        path = video.folder(existing['id']) / 'project.json'
        preserved = sha(path)
        rejects(lambda: links.perform('song', {'action': 'bind', 'videoId': existing['id'], 'expectedVideoId': None}), '其他窗口变化')
        links.perform('song', {'action': 'bind', 'videoId': existing['id'], 'expectedVideoId': ident})
        assert sha(path) == preserved
        rejects(lambda: links.perform('other', {'action': 'bind', 'videoId': existing['id'], 'expectedVideoId': None}), '另一首歌')
        assert links.for_video(existing['id'])['music']['id'] == 'song'
        source = links.overview('song')
        update = dict(action='update', videoId=existing['id'], revision=existing['revision'],
                      sourceSignature=source['signature'], captions=True)
        rejects(lambda: links.perform('song', update), '同时带入混音')
        rejects(lambda: links.perform('song', {**update, 'revision': 0}), '视频工程已更新')
        rejects(lambda: links.perform('song', {**update, 'sourceSignature': 'stale'}), '音乐侧素材已更新')
        links.perform('song', {**update, 'audio': True, 'captions': False})
        changed = video.load(existing['id'])
        assert changed['audio'] == str(latest) and changed['cues'] == existing['cues']
        assert changed['styles'] == existing['styles'] and changed['subtitleShift'] == .3
        assert changed['timing']['clock'] == 'video'
        assert read_json(video.folder(existing['id']) / f"History/r{existing['revision']:06}.json") == existing
        source = links.overview('song')
        links.perform('song', {**update, 'revision': changed['revision'], 'sourceSignature': source['signature']})
        changed = video.load(existing['id'])
        assert changed['cues'][0]['start'] == 6 and changed['subtitleShift'] == 0
        assert changed['styles'] == existing['styles'] and changed['audioOffset'] == 5
        changed = video.save(changed['id'], changed)
        assert changed['cues'][0]['start'] == 6 and not workflow.blockers(changed)
        # Custom quoted paths and stale content signatures are checked by the server.
        source = links.overview('song', '"' + str(mix) + '"')
        assert source['audio']['path'] == str(mix)
        latest.write_bytes(b'replaced final mix')
        rejects(lambda: links.perform('song', {**update, 'revision': changed['revision']}), '音乐侧素材已更新')
        latest.write_bytes(b'synthetic local fixture')
        links.perform('song', {'action': 'unlink', 'expectedVideoId': existing['id']})
        assert not links.overview('song')['linked'] and path.exists() and video.folder(ident).exists()
        assert links.STORE.with_name('video-links.local.previous.json').exists()
        assert all(sha(p) == h for p, h in originals.items())
        # Saved subtitles win. A timed downloaded lyric package is clearly a draft fallback.
        save_json(review, {'subtitles': []})
        package = pilot / 'analysis/lyrics-current.json'
        save_json(package, {'rows': cues})
        source = links.overview('song')
        assert source['captions']['count'] == 1 and '待校对' in source['captions']['label']
        save_json(package, {'rows': [{'original': 'Untimed', 'start': None, 'end': None}]})
        assert links.overview('song')['captions']['count'] == 0
        save_json(review, {'subtitles': [{**cues[0], 'end': 0}]})
        source = links.overview('song')
        assert source['captions']['count'] == 0 and source['captions']['issue']
        source_path = root / 'data/projects/song.json'
        project['title'] = '星'
        project['audio'] = {'lead': {'original': str(lead)}}
        save_json(source_path, {'project': project})
        (root / 'runtime/workflow/done.json').unlink()
        source = links.overview('song')
        assert source['audio'] is None and source['defaultName'] == 'song Video'
        empty = links.perform('song', dict(action='create', sourceSignature=source['signature']))
        assert set(empty['missing']) == {'混音', '字幕'}
        assert not video.load(empty['videoId'])['audio']
        project['audio'] = {'mix': {'original': str(mix)}}
        save_json(source_path, {'project': project})
        assert links.overview('song')['changed']['audio'], 'A newly available mix should be offered'
        source = links.overview('song', str(latest))
        links.perform('song', dict(action='update', videoId=empty['videoId'], revision=1, audio=True,
                                   audioPath=str(latest), sourceSignature=source['signature']))
        assert links.overview('song')['audioSelection'] == str(latest)
        assert links.overview('song')['audio']['path'] == str(latest) and not links.overview('song')['changed']['audio']
        source = links.overview('song', '')
        assert source['audio']['path'] == str(mix), 'Explicit automatic selection should bypass the remembered path'
        links.perform('song', dict(action='update', videoId=empty['videoId'], revision=2, audio=True,
                                   audioPath='', sourceSignature=source['signature']))
        assert links.overview('song')['audioSelection'] == ''
        rejects(lambda: links.overview('../unknown'), '音乐工程不存在')
    print('PASS: final-mix precedence, subtitle sources, seeded creation, read-only reentry/binding, one-to-one links, stale guards, selective updates, exactly-once offsets, History and original hashes')


if __name__ == '__main__':
    main()
