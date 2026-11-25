"""State contracts at the supported custom-component boundary."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import column_picker


class ColumnPickerTests(unittest.TestCase):
    def mount(self, state, options, selected=None, index=0):
        component = Mock(return_value=SimpleNamespace(selected=selected))
        with patch.object(column_picker, "st", SimpleNamespace(session_state=state)), \
                patch.object(column_picker, "_picker", component):
            if selected is not None:
                state["picker_input_x"] = {"selected": selected}
                column_picker._commit_selection("input_x", "picker_input_x", options)
            value = column_picker.select_column("X · input", options, "input_x", index=index)
        return value, component

    def test_valid_choice_updates_scalar_mapping_without_changing_names(self):
        names = ["Énergie totale (J)", "Time (s)"]
        state = {"input_x": names[1]}
        value, component = self.mount(state, names, names[0])
        self.assertEqual(value, names[0])
        self.assertEqual(state["input_x"], names[0])
        self.assertEqual(component.call_args.kwargs["data"], {
            "label": "X · input", "options": names, "value": names[0]})
        self.assertEqual(component.call_args.kwargs["key"], "picker_input_x")

    def test_registered_callback_commits_choice_before_next_mount(self):
        names = ["Énergie totale (J)", "Time (s)"]
        state = {"input_x": names[1]}
        component = Mock()
        with patch.object(column_picker, "st", SimpleNamespace(session_state=state)), \
                patch.object(column_picker, "_picker", component):
            column_picker.select_column("X · input", names, "input_x")
            callback = component.call_args.kwargs["on_selected_change"]
            # Streamlit updates the event state and invokes the registered
            # callback before rerunning the script and dependent role controls.
            state["picker_input_x"] = {"selected": names[0]}
            callback()
            column_picker.select_column("X · input", names, "input_x")
            self.assertEqual(state["input_x"], names[0])
            self.assertEqual(component.call_args.kwargs["data"]["value"], names[0])

    def test_search_or_dismissal_preserves_required_selection(self):
        state = {"input_x": "X"}
        value, _ = self.mount(state, ["X", "Y"])
        self.assertEqual(value, "X")
        self.assertEqual(state, {"input_x": "X"})

    def test_upstream_role_changes_repair_invalid_choice_and_ignore_stale_event(self):
        state = {"input_x": "old column"}
        value, component = self.mount(state, ["Position", "Reading"], "old column", index=1)
        self.assertEqual(value, "Reading")
        self.assertEqual(component.call_args.kwargs["data"]["value"], "Reading")

    def test_programmatic_choice_is_not_overwritten_by_old_component_state(self):
        state = {"input_x": "Position"}
        first, _ = self.mount(state, ["Position", "Reading"], "Reading")
        self.assertEqual(first, "Reading")
        state["input_x"] = "Position"
        second, _ = self.mount(state, ["Position", "Reading"])
        self.assertEqual(second, "Position")

    def test_empty_options_explain_the_missing_role(self):
        with self.assertRaisesRegex(ValueError, "No columns"):
            self.mount({}, [])


if __name__ == "__main__":
    unittest.main()
