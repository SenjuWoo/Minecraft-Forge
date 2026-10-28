"""Exercise bounded directory publication retries without weakening no-overwrite behavior."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from mcforge import workbench


def denied(winerror=None):
    error = PermissionError(13, "Directory publication denied")
    if winerror is not None:
        error.winerror = winerror
    return error


class PublishTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(scratch.resolve()))
        self.stage = self.root / "stage"
        self.stage.mkdir()
        (self.stage / "STATE.md").write_text("staged source", encoding="utf-8")
        self.destination = self.root / "published"

    def test_transient_windows_denial_retries_then_performs_real_rename(self):
        original = Path.rename
        for winerror in (5, 32):
            with self.subTest(winerror=winerror):
                first = denied(winerror)
                attempts = []

                def flaky(source, destination):
                    attempts.append((source, destination))
                    if len(attempts) == 1:
                        raise first
                    return original(source, destination)

                with patch.object(workbench, "os", SimpleNamespace(name="nt")), \
                        patch.object(workbench.time, "sleep") as sleep, \
                        patch.object(Path, "rename", autospec=True, side_effect=flaky):
                    workbench.publish_project(self.stage, self.destination)
                self.assertEqual(attempts, [(self.stage, self.destination)] * 2)
                sleep.assert_called_once_with(0.02)
                self.assertFalse(self.stage.exists())
                self.assertEqual((self.destination / "STATE.md").read_text(), "staged source")
                original(self.destination, self.stage)

    def test_persistent_windows_denial_exhausts_four_attempts_and_preserves_last_error(self):
        errors = [denied(5) for _ in range(4)]
        with patch.object(workbench, "os", SimpleNamespace(name="nt")), \
                patch.object(workbench.time, "sleep") as sleep, \
                patch.object(Path, "rename", autospec=True, side_effect=errors) as rename:
            with self.assertRaises(PermissionError) as caught:
                workbench.publish_project(self.stage, self.destination)
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual(rename.call_count, 4)
        self.assertEqual(sleep.call_args_list, [call(0.02), call(0.05), call(0.1)])
        self.assertEqual((self.stage / "STATE.md").read_text(), "staged source")
        self.assertFalse(self.destination.exists())

    def test_destination_created_during_denied_rename_is_not_retried_or_overwritten(self):
        error = denied(5)

        def concurrent_destination(source, destination):
            destination.mkdir()
            (destination / "personal.txt").write_text("keep", encoding="utf-8")
            raise error

        with patch.object(workbench, "os", SimpleNamespace(name="nt")), \
                patch.object(workbench.time, "sleep") as sleep, \
                patch.object(Path, "rename", autospec=True, side_effect=concurrent_destination) as rename:
            with self.assertRaises(PermissionError) as caught:
                workbench.publish_project(self.stage, self.destination)
        self.assertIs(caught.exception, error)
        rename.assert_called_once_with(self.stage, self.destination)
        sleep.assert_not_called()
        self.assertEqual((self.destination / "personal.txt").read_text(), "keep")
        self.assertEqual((self.stage / "STATE.md").read_text(), "staged source")

    def test_missing_source_is_not_retried(self):
        missing = self.root / "missing"
        error = denied(5)
        with patch.object(workbench, "os", SimpleNamespace(name="nt")), \
                patch.object(workbench.time, "sleep") as sleep, \
                patch.object(Path, "rename", autospec=True, side_effect=error) as rename:
            with self.assertRaises(PermissionError) as caught:
                workbench.publish_project(missing, self.destination)
        self.assertIs(caught.exception, error)
        rename.assert_called_once_with(missing, self.destination)
        sleep.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_other_platforms_and_unrelated_errors_are_not_retried(self):
        cases = (("posix", denied(5)), ("nt", denied(1234)),
                 ("nt", denied()), ("nt", FileExistsError(17, "Already exists")))
        for platform, error in cases:
            with self.subTest(platform=platform, error=repr(error)), \
                    patch.object(workbench, "os", SimpleNamespace(name=platform)), \
                    patch.object(workbench.time, "sleep") as sleep, \
                    patch.object(Path, "rename", autospec=True, side_effect=error) as rename:
                with self.assertRaises(type(error)) as caught:
                    workbench.publish_project(self.stage, self.destination)
                self.assertIs(caught.exception, error)
                rename.assert_called_once_with(self.stage, self.destination)
                sleep.assert_not_called()
        self.assertTrue(self.stage.is_dir())
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(os.name == "nt", "Windows file-sharing boundary")
    def test_real_windows_child_handle_blocks_publish_until_retry_releases_it(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        # READ|WRITE sharing deliberately omits FILE_SHARE_DELETE, reproducing WinError5.
        handle = kernel.CreateFileW(str(self.stage / "STATE.md"), 0x80000000, 3, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())

        def release_on_retry(delay):
            nonlocal handle
            self.assertEqual(delay, 0.02)
            self.assertTrue(self.stage.is_dir())
            self.assertFalse(self.destination.exists())
            self.assertTrue(kernel.CloseHandle(handle))
            handle = None

        try:
            with patch.object(workbench.time, "sleep", side_effect=release_on_retry) as sleep:
                workbench.publish_project(self.stage, self.destination)
            sleep.assert_called_once_with(0.02)
            self.assertFalse(self.stage.exists())
            self.assertEqual((self.destination / "STATE.md").read_text(), "staged source")
        finally:
            if handle is not None:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
