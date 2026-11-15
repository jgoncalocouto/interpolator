"""Shared Streamlit fixtures and assertions, without inherited test methods."""

from contextlib import contextmanager
import logging
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.runtime.media_file_manager import MediaFileManager
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "main.py"


class AppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("streamlit.runtime.scriptrunner_utils.script_run_context",
                     "streamlit.elements.lib.policies", "streamlit.deprecation_util"):
            logging.getLogger(name).setLevel(logging.ERROR)

    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assert_no_exception()

    def assert_no_exception(self):
        self.assertFalse(list(self.app.exception))

    def download(self, dimension):
        return next(element for element in self.app.get("download_button")
                    if element.proto.id.endswith(f"-download_{dimension}"))

    def reference_column(self, dimension, index):
        return next(element for element in self.app.selectbox
                    if element.key.startswith(f"input_column_{dimension}_")
                    and element.key.endswith(f"_{index}"))

    def query_column(self, axis):
        return next(element for element in self.app.selectbox
                    if element.key.startswith(f"input_query_{axis}_2d"))

    def import_setting(self, context, name):
        return self.app.selectbox(key=f"input_format_{context}_{name}")

    def number_preview(self, column, first_original=None):
        for element in self.app.dataframe:
            frame = element.value
            if f"{column} (number)" not in frame.columns:
                continue
            if first_original is not None and str(frame[f"{column} (original)"].iloc[0]) != first_original:
                continue
            return frame
        self.fail(f"No numeric preview found for {column!r}")

    @contextmanager
    def capture_downloads(self):
        """Capture real download bytes while preserving Streamlit registration."""
        captured = {}
        original_add = MediaFileManager.add

        def capture(manager, path_or_data, mimetype, coordinates, file_name=None,
                    is_for_static_download=False):
            url = original_add(manager, path_or_data, mimetype, coordinates, file_name,
                               is_for_static_download)
            if is_for_static_download:
                captured[file_name] = {"data": path_or_data, "mime": mimetype, "url": url}
            return url

        with patch.object(MediaFileManager, "add", new=capture):
            yield captured
