import importlib.util
import errno
import os
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backend_staging', Path(__file__).resolve().parent.parent / 'backend.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class LocalStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'source.mp3'
        self.source.write_bytes(b'abc123' * 300_000)
        self.dest = self.root/'song.mp3'
        b.cancelled = False
        b.staging_low.clear()

    def tearDown(self):
        b.cancelled = False
        b.staging_low.clear()
        self.temp.cleanup()

    def hidden_partials(self):
        return list(self.root.glob('.musica-subaru-*.part'))

    def test_verified_copy_published(self):
        with patch.object(b, 'volume_present', return_value=True), patch.object(b, 'validate_volume'):
            b.publish_audio(self.source, self.dest)
        self.assertEqual(self.source.read_bytes(), self.dest.read_bytes())
        self.assertFalse(self.hidden_partials())

    def test_corrupted_copy_is_not_published(self):
        def corrupt(fd):
            os.pwrite(fd, b'BAD', 0)
        with patch.object(b, 'volume_present', return_value=True), patch.object(b, 'validate_volume'), patch.object(b.os, 'fsync', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'integridad'):
                b.publish_audio(self.source, self.dest)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.hidden_partials())

    def test_cancel_preserves_existing_song(self):
        self.dest.write_bytes(b'original')
        def presence():
            b.cancelled = True
            return True
        with patch.object(b, 'volume_present', side_effect=presence), patch.object(b, 'validate_volume'):
            with self.assertRaisesRegex(RuntimeError, 'cancelada'):
                b.publish_audio(self.source, self.dest)
        self.assertEqual(self.dest.read_bytes(), b'original')
        self.assertFalse(self.hidden_partials())

    def test_disconnect_never_publishes(self):
        with patch.object(b, 'volume_present', return_value=False), patch.object(b, 'validate_volume'):
            with self.assertRaisesRegex(RuntimeError, 'disponible'):
                b.publish_audio(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_disconnect_during_copy_never_publishes(self):
        # Connected initially and for the first block, disconnected for the
        # second block, then available for best-effort partial-file cleanup.
        with patch.object(b, 'volume_present', side_effect=[True, True, False, True]), patch.object(b, 'validate_volume'):
            with self.assertRaisesRegex(RuntimeError, 'disponible'):
                b.publish_audio(self.source, self.dest)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.hidden_partials())

    def test_full_destination_never_publishes_or_replaces(self):
        self.dest.write_bytes(b'original')
        with patch.object(b, 'volume_present', return_value=True), patch.object(b, 'validate_volume'), patch.object(b.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'sin espacio')):
            with self.assertRaises(OSError):
                b.publish_audio(self.source, self.dest)
        self.assertEqual(self.dest.read_bytes(), b'original')
        self.assertFalse(self.hidden_partials())

    def test_low_space_stops_and_is_sticky(self):
        usage = namedtuple('usage', 'total used free')
        with patch.object(b.shutil, 'disk_usage', return_value=usage(4_000_000_000,3_500_000_000,500_000_000)):
            with self.assertRaisesRegex(RuntimeError, 'espacio libre'):
                b.check_local_space(start=True)
        with patch.object(b.shutil, 'disk_usage', return_value=usage(4_000_000_000,0,4_000_000_000)):
            with self.assertRaisesRegex(RuntimeError, 'espacio libre'):
                b.check_local_space()


if __name__ == '__main__':
    unittest.main()
