"""A shared searchable column picker built with Streamlit's component API."""

from pathlib import Path

import streamlit as st


_ASSETS = Path(__file__).with_name("ui")
_picker = st.components.v2.component(
    "interpolator_column_picker",
    html="""<div class="column-picker">
      <label class="field-label"></label>
      <button class="picker-trigger" type="button" aria-haspopup="dialog" aria-expanded="false">
        <span class="selected-label"></span><span aria-hidden="true">⌄</span>
      </button>
      <div class="picker-popup" popover="auto" role="dialog">
        <div class="search-header"><label class="search-label">Search columns</label>
          <input class="search-input" type="search" autocomplete="off" role="combobox"
                 aria-autocomplete="list" aria-expanded="true" />
        </div>
        <div class="option-list" role="listbox"></div>
        <div class="search-status" role="status" aria-live="polite"></div>
      </div>
    </div>""",
    css=(_ASSETS / "column_picker.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "column_picker.mjs").read_text(encoding="utf-8"),
)


def _commit_selection(key, component_key, options):
    """Apply the component event before a rerun builds dependent role fields."""
    event = st.session_state.get(component_key, {})
    selected = event.get("selected")
    if selected in options:
        st.session_state[key] = selected


def select_column(label, options, key, index=0):
    """Select a required source column, preserving its original name and state."""
    options = list(options)
    if not options:
        raise ValueError("No columns are available for this role.")
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[min(max(index, 0), len(options) - 1)]
    component_key = f"picker_{key}"
    _picker(
        data={"label": label, "options": options, "value": st.session_state[key]},
        key=component_key,
        on_selected_change=lambda: _commit_selection(key, component_key, options),
    )
    # Choices are committed by the callback before rendering. The event itself
    # lasts one run, so it cannot overwrite a repaired or restored mapping later.
    return st.session_state[key]
