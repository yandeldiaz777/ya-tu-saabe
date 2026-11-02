import contextlib
import ctypes
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('portable_backend', Path(__file__).resolve().parent.parent / 'backend.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class WindowsOS:
    name='nt'
    def __getattr__(self,key): return getattr(os,key)

class PortTests(unittest.TestCase):
    def setUp(self):
        b.cancelled=False
        b.staging_low.clear()
    def tearDown(self):
        b.cancelled=False
        b.staging_low.clear()
    def test_windows_lock_uses_msvcrt_and_releases(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            msvcrt=SimpleNamespace(LK_NBLCK=1,LK_UNLCK=2,locking=lambda fd,mode,n:calls.append((mode,n)))
            with patch.object(b,'os',WindowsOS()),patch.object(b,'msvcrt',msvcrt,create=True):
                with b.destination_lock(Path(d)): self.assertEqual(calls,[(1,1)])
            self.assertEqual(calls,[(1,1),(2,1)])
    def test_windows_detects_volume_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'os',WindowsOS()),patch.object(b,'ROOT',Path(d)),patch.object(b,'MOUNT_ROOT',Path(Path(d).anchor)),patch.object(b,'initial_dev',None),patch.object(b,'initial_inode',None),patch.object(b,'initial_windows_serial',None),patch.object(b,'windows_volume_serial',side_effect=[100,101]):
                b.validate_volume()
                with self.assertRaisesRegex(RuntimeError,'unidad de destino cambió'):
                    b.validate_volume()
    def test_windows_removable_drive_limit_is_not_applied_to_fixed_disk(self):
        class DriveType:
            def __init__(self, value): self.value=value
            def __call__(self, root): return self.value
        with patch.object(b,'os',WindowsOS()),patch.object(b,'MOUNT_ROOT',Path('/')):
            with patch.object(ctypes,'WinDLL',return_value=SimpleNamespace(GetDriveTypeW=DriveType(2)),create=True):
                self.assertTrue(b.is_removable_volume())
            with patch.object(ctypes,'WinDLL',return_value=SimpleNamespace(GetDriveTypeW=DriveType(3)),create=True):
                self.assertFalse(b.is_removable_volume())

    def test_windows_cancel_terminates_child_tree(self):
        stopped=threading.Event(); calls=[]
        class Output:
            def __iter__(self):
                b.cancelled=True
                stopped.wait(3)
                return iter(())
            def close(self): pass
        child=SimpleNamespace(pid=4242,stdout=Output(),wait=lambda: 1,terminate=lambda: None)
        def taskkill(args,**kwargs):
            calls.append(args); stopped.set()
        with patch.object(b,'os',WindowsOS()),patch.object(b,'volume_present',return_value=True),patch.object(b,'check_local_space'),patch.object(b.subprocess,'CREATE_NO_WINDOW',0,create=True),patch.object(b.subprocess,'Popen',return_value=child),patch.object(b.subprocess,'run',side_effect=taskkill):
            with self.assertRaisesRegex(RuntimeError,'cancelada'): b.run(['dummy'])
        self.assertEqual(calls,[['taskkill','/PID','4242','/T','/F']])
    def test_cancel_file_reaches_backend_without_console_signals(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'cancel'
            argv=['backend.py','--url','https://youtube.com/watch?v=abcdefghijk','--mode','single','--destination',d,'--cancel-file',str(marker)]
            @contextlib.contextmanager
            def fake_lock(_): yield
            def body(a,root):
                marker.touch()
                for _ in range(30):
                    if b.cancelled: return 0
                    time.sleep(.05)
                self.fail('No se detectó el marcador de cancelación')
            with patch.object(sys,'argv',argv),patch.object(b,'verify_url',side_effect=lambda x,_:x),patch.object(b,'set_destination'),patch.object(b,'destination_lock',fake_lock),patch.object(b,'execute_in_destination',side_effect=body):
                self.assertEqual(b.execute(),0)

if __name__ == '__main__': unittest.main()
