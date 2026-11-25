"""Shared Streamlit fixtures and assertions, without inherited test methods."""

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.runtime.media_file_manager import MediaFileManager
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "main.py"


class ColumnPickerState:
    """Exercise picker-backed workflow state without simulating browser keys.

    AppTest does not execute custom-component JavaScript. Browser checks cover
    the search popup and its keyboard behavior; this adapter covers the same
    scalar mapping state used by the calculation workflow.
    """

    def __init__(self, app, key, options):
        self.app, self.key, self.options = app, key, options

    @property
    def value(self):
        return self.app.session_state[self.key]

    def set_value(self, value):
        if value not in self.options:
            raise ValueError(f"{value!r} is not an available column.")
        self.app.session_state[self.key] = value
        return self.app


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
        return self.column_picker(lambda key: key.startswith(f"input_column_{dimension}_")
                                  and key.endswith(f"_{index}"))

    def query_column(self, axis):
        return self.column_picker(lambda key: key.startswith(f"input_query_{axis}_2d"))

    def column_picker(self, matches):
        for element in self.app.get("bidi_component"):
            key = element.proto.id.partition("-picker_")[2]
            if key and matches(key):
                return ColumnPickerState(self.app, key, json.loads(element.proto.json)["options"])
        # Retain compatibility with native controls while component integration
        # is tested against supported Streamlit versions.
        return next(element for element in self.app.selectbox if matches(element.key))

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
