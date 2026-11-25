"""Reusable Streamlit helper for a quiet, inline project-support link."""

from __future__ import annotations

from html import escape

import streamlit as st

DEFAULT_COFFEE_URL = "https://paypal.me/jgoncalocouto/1"

_INLINE_SUPPORT_HTML = """
<style>
  .interpolator-support {{
    margin: 1rem 0 .25rem;
  }}
  .interpolator-support a {{
    display: inline-flex;
    align-items: center;
    gap: .5rem;
    min-height: 44px;
    border-radius: 7px;
    color: inherit;
    font-size: 14px;
    line-height: 1.5;
    text-decoration: underline;
    text-underline-offset: 3px;
  }}
  .interpolator-support a:focus-visible {{
    outline: 2px solid currentColor;
    outline-offset: 3px;
  }}
</style>

<div class="interpolator-support">
  <a href="{url}" target="_blank" rel="noopener" title="{title}"><span aria-hidden="true">☕</span>{title}</a>
</div>
"""


def add_buy_me_a_coffee(url: str = DEFAULT_COFFEE_URL, *, title: str = "Buy me a coffee") -> None:
    """Render an inline support link in the current Streamlit container."""
    st.markdown(_INLINE_SUPPORT_HTML.format(url=escape(url, quote=True), title=escape(title, quote=True)),
                unsafe_allow_html=True)
