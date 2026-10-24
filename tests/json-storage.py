"""Atomic state persistence under polling, concurrent writers and Windows sharing locks."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import core
import video_jobs


def writer(path, count=30):
    for i in range(count):
        core.save_json(path, {'sequence': i, 'payload': str(i) * 4096})


def hold_windows_reader(path):
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Share read/write, deliberately omit FILE_SHARE_DELETE as normal readers do.
    handle = kernel.CreateFileW(str(path), 0x80000000, 1 | 2, None, 3, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return lambda: kernel.CloseHandle(handle)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'job.json'
        core.save_json(self.path, {'sequence': -1, 'payload': 'original'})

    def assert_no_temps(self):
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_concurrent_pollers_and_writers(self):
        stop = threading.Event()
        def poll():
            while not stop.is_set():
                value = core.read_json(self.path)
                if value['sequence'] >= 0:
                    self.assertEqual(value['payload'], str(value['sequence']) * 4096)
        with ThreadPoolExecutor(max_workers=8) as pool:
            readers = [pool.submit(poll) for _ in range(4)]
            try:
                for task in [pool.submit(writer, self.path) for _ in range(4)]:
                    task.result(timeout=20)
            finally:
                stop.set()
            for task in readers:
                task.result(timeout=5)
        self.assert_no_temps()

    def test_separate_process_writers(self):
        children = [subprocess.Popen([sys.executable, __file__, '--writer', str(self.path)]) for _ in range(3)]
        try:
            for child in children:
                self.assertEqual(child.wait(timeout=30), 0)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        value = core.read_json(self.path)
        self.assertEqual(value, {'sequence': 29, 'payload': '29' * 4096})
        self.assert_no_temps()

    def test_failed_replace_preserves_previous_state(self):
        before = self.path.read_bytes()
        with patch.object(core.os, 'replace', side_effect=OSError('Disk unavailable')):
            with self.assertRaisesRegex(OSError, 'Disk unavailable'):
                core.save_json(self.path, {'sequence': 50})
        self.assertEqual(self.path.read_bytes(), before)
        self.assert_no_temps()

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_short_windows_sharing_lock_recovers(self):
        close = hold_windows_reader(self.path)
        released = threading.Event()
        def release():
            close()
            released.set()
        timer = threading.Timer(.2, release)
        timer.start()
        try:
            core.save_json(self.path, {'status': 'completed'})
        finally:
            timer.join(5)
        self.assertTrue(released.is_set())
        self.assertEqual(core.read_json(self.path), {'status': 'completed'})
        self.assert_no_temps()

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_permanent_windows_sharing_lock_is_bounded(self):
        before = self.path.read_bytes()
        close = hold_windows_reader(self.path)
        started = time.monotonic()
        try:
            with self.assertRaises(PermissionError):
                core.save_json(self.path, {'status': 'completed'})
        finally:
            close()
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(self.path.read_bytes(), before)
        self.assert_no_temps()

    def test_live_history_never_opens_status_file(self):
        ident = 'a' * 32
        folder = self.path.parent / 'Exports' / ident
        folder.mkdir(parents=True)
        core.save_json(folder / 'job.json', {'id': ident, 'status': 'queued', 'created': 1})
        live = {'id': ident, 'status': 'running', 'progress': 42, 'created': 1}
        with patch.object(video_jobs.project, 'folder', return_value=self.path.parent), \
             patch.dict(video_jobs.JOBS, {ident: live}), \
             patch.object(video_jobs, 'read_json', side_effect=AssertionError('Live disk read')):
            result = video_jobs.history('Synthetic')
        self.assertEqual(result, [live])
        self.assertIsNot(result[0], live)
        with patch.object(video_jobs.project, 'folder', return_value=self.path.parent):
            self.assertEqual(video_jobs.history('Synthetic')[0]['status'], 'interrupted')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--writer':
        writer(sys.argv[2])
    else:
        unittest.main()
