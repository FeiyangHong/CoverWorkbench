"""Readable version allocation, immutable media names and legacy download aliases."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import video_storage as storage
import video_project as project
import video_jobs as jobs
from core import save_json, sha


def main():
    with tempfile.TemporaryDirectory(prefix='video versions ') as tmp:
        project.BASE = Path(tmp)
        doc = project.create({'name': 'My Cover Video'})
        parent = project.folder(doc['id'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            allocated = list(pool.map(lambda _: storage.reserve(parent, 'export'), range(12)))
        assert sorted(n for _, n in allocated) == list(range(1, 13))
        assert {p.name for p, _ in allocated} == {f'Export {i:03}' for i in range(1, 13)}
        for kind, prefix in [('preview', 'Preview'), ('analyze', 'Analysis'), ('download', 'Download')]:
            assert storage.reserve(parent, kind)[0].name == prefix + ' 001'
        (parent / 'Exports/Export 013').write_text('An existing file must not be overwritten')
        assert storage.reserve(parent, 'export')[1] == 14
        jid = 'a' * 32
        legacy = parent / 'Exports' / jid
        legacy.mkdir()
        video = legacy / 'video.mp4'
        video.write_bytes(b'unchanged synthetic encoded bytes')
        before = sha(video)
        record = {'id': jid, 'kind': 'export', 'project': doc['id'], 'status': 'completed',
                  'folder': str(legacy), 'files': ['video.mp4'], 'created': 1}
        save_json(legacy / 'job.json', record)
        assert jobs.media(doc['id'], jid, 'video.mp4') == video
        renamed = parent / 'Exports/Export 015'
        legacy.rename(renamed)
        record.update(folder=str(renamed), version=15)
        record['outputName'] = storage.output_name(record, 'mp4')
        assert record['outputName'] == 'My Cover Video - v015.mp4'
        (renamed / 'video.mp4').rename(renamed / record['outputName'])
        record['files'] = [record['outputName']]
        save_json(renamed / 'job.json', record)
        assert jobs.media(doc['id'], jid, 'video.mp4') == renamed / record['outputName']
        assert jobs.media(doc['id'], jid, record['outputName']) == renamed / record['outputName']
        assert sha(jobs.media(doc['id'], jid, 'video.mp4')) == before
        assert jobs.history(doc['id'])[0]['folder'] == str(renamed)
        for invalid in ['../project.json', 'job.json', 'unlisted.mp4']:
            try: jobs.media(doc['id'], jid, invalid)
            except ValueError: pass
            else: raise AssertionError('An unapproved output was served')
        try: storage.locate(parent, '../escape')
        except ValueError: pass
        else: raise AssertionError('Invalid task ID accepted')
        record['status'] = 'failed'
        save_json(renamed / 'job.json', record)
        try: jobs.media(doc['id'], jid, 'video.mp4')
        except ValueError: pass
        else: raise AssertionError('Incomplete result was served')
    print('PASS: concurrent readable versions, collision preservation, readable filenames, legacy folders/URLs and download boundaries')


if __name__ == '__main__':
    main()
