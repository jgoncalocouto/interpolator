"""Practical interpolation guidance and the first Excel formula workflow."""

import pandas as pd
import streamlit as st

from excel_formulas import build_linear_formula, parse_vector_reference


EXCEL_OUTSIDE = {"nan": "Leave blank", "clamp": "Keep boundary value", "linear": "Extend end slopes"}


def render_tips():
    for key, default in {"input_excel_x_range": "$A$2:$A$7", "input_excel_y_range": "$B$2:$B$7",
                         "input_excel_query_range": "D2:D5"}.items():
        if key not in st.session_state:
            st.session_state[key] = default
    st.subheader("Linear interpolation in Excel")
    st.write("Enter your worksheet references to generate a formula that calculates Yi from Xi. "
             "The calculation runs in your Excel workbook; this page does not read its cells.")
    st.info("Requires Microsoft 365 or Excel 2024 with English function names. "
            "Use at least two paired numeric samples with unique X values.")

    controls, output = st.columns([1, 1.65], gap="large")
    with controls:
        with st.container(border=True, key="excel_controls"):
            st.markdown("**1. Set your ranges**")
            x_range = st.text_input(
                "Known X range", key="input_excel_x_range",
                help="One row or column of known X values. Exclude headers and empty cells. "
                     "Sheet references work too, for example 'My data'!$A$2:$A$7.",
            )
            y_range = st.text_input(
                "Known Y range", key="input_excel_y_range",
                help="Matching Y values, in the same order as X. X and Y can be horizontal or vertical vectors.",
            )
            query_range = st.text_input(
                "Xi cell or range", key="input_excel_query_range",
                help="Use one query cell, such as D2, or one row or column of query values. "
                     "Results spill in the same shape and order as this reference.",
            )
            st.markdown("**2. Choose the behavior**")
            outside = st.selectbox("Outside the known X range", list(EXCEL_OUTSIDE),
                                   format_func=EXCEL_OUTSIDE.get, key="input_excel_outside")
            separator = st.selectbox(
                "Formula argument separator", [",", ";"],
                format_func={",": "Comma (,)", ";": "Semicolon (;)"}.get,
                key="input_excel_separator",
                help="Match the separator your Excel uses between function arguments. "
                     "Function names remain in English.",
            )
            st.caption("The formula sorts X and Y together. Every X must be unique: "
                       "average repeated measurements first. Empty query cells stay blank; "
                       "text, logical values, and other invalid queries return #N/A.")

    with output:
        with st.container(border=True, key="excel_formula"):
            st.markdown("**3. Copy your Yi formula**")
            try:
                formula = build_linear_formula(x_range, y_range, query_range,
                                               separator=separator, outside=outside)
            except ValueError as error:
                st.error(str(error))
                st.write("Correct the references to generate a formula.")
            else:
                x = parse_vector_reference(x_range)
                query = parse_vector_reference(query_range)
                st.caption(f"{x.length:,} known X/Y pairs · {query.length:,} query cell(s). "
                           "Excel checks the cell contents when the formula runs.")
                st.write("Use the copy icon, then paste into an empty cell outside your X, Y, and Xi ranges. "
                         "For the default layout, paste into **E2** and leave E2:E5 clear.")
                st.code(formula, language=None, wrap_lines=True)
                st.caption("A single Xi cell returns one Yi. A query range spills all Yi values in the same "
                           "shape and order. Changing these settings does not alter your calculated results "
                           "in the 1D or 2D tabs.")

    with st.expander("Try a worked example"):
        st.write("On a blank worksheet, put these headers in row 1 and the data below them. "
                 "Use X = $A$2:$A$7, Y = $B$2:$B$7, and Xi = D2:D5. Paste the generated formula into E2.")
        expected_outside = {"nan": "Blank", "clamp": "42", "linear": "45"}[outside]
        example = pd.DataFrame({
            "A · X": [0, 2, 4, 6, 8, 10],
            "B · Y": [18, 22, 28, 35, 39, 42],
            "C · unused": [""] * 6,
            "D · Xi": ["1", "3", "7", "12", "", ""],
            "E · expected Yi": ["20", "25", "37", expected_outside, "", ""],
        })
        st.dataframe(example, hide_index=True, width="stretch")
        st.caption(f"The query at X = 12 is outside the known range. With {EXCEL_OUTSIDE[outside].lower()}, "
                   f"its result is {expected_outside.lower()}.")

    with st.expander("How the Excel formula works"):
        st.write("The formula sorts the paired samples by X and finds the two neighbors around each Xi. "
                 "An exact known X returns its measured Y. Between samples, it uses:")
        st.latex(r"y_i = y_0 + \frac{x_i - x_0}{x_1 - x_0}(y_1-y_0)")
        st.write("Outside the known X range, Leave blank returns an empty string, Keep boundary value "
                 "returns the nearest endpoint's Y, and Extend end slopes uses the first or last segment. "
                 "The formula requires numeric source cells with unique X values. It returns #N/A when "
                 "those requirements are not met.")
        st.write("FORECAST.LINEAR applied to the full dataset fits one regression line. "
                 "Piecewise interpolation uses the neighboring samples for each query.")
        st.markdown("Microsoft documentation: [MAP and supported Excel versions]"
                    "(https://support.microsoft.com/en-us/excel/functions/map-function), "
                    "[XMATCH](https://support.microsoft.com/en-us/excel/functions/xmatch-function), "
                    "[FORECAST.LINEAR](https://support.microsoft.com/en-us/excel/functions/forecast-and-forecast-linear-functions).")

    with st.expander("Fix common Excel problems"):
        st.markdown(
            "- **#SPILL!** Clear the cells needed for the results. Put the formula outside an Excel table.\n"
            "- **#NAME? or an unrecognized function.** Check the Excel version and function language. "
            "This generator uses English MAP, TOCOL, and other modern functions.\n"
            "- **Excel will not accept the formula.** Try the other argument separator. "
            "Localized function names may also need translation.\n"
            "- **#N/A.** Check both known ranges for headers, blanks, text, errors, and repeated X values. "
            "An individual nonnumeric query also returns #N/A. Convert numbers stored as text to numbers.\n"
            "- **Circular reference.** Put Yi in separate cells; the formula must not replace X, Y, or Xi.\n"
            "- **Copying a single-query formula down.** Anchor known ranges with $, such as $A$2:$A$7, "
            "and keep the Xi cell relative, such as D2."
        )

    with st.expander("Get dependable interpolation results"):
        st.markdown(
            "- Use the same units for known X values and query Xi values.\n"
            "- Start with **Leave blank** outside your known data. Extending an end slope adds an assumption.\n"
            "- Check the original-versus-numeric preview when importing decimal commas or grouped numbers.\n"
            "- Use **Nearest sample** in the calculation tab when you need the closest measured value. "
            "The Excel generator currently produces 1D linear interpolation.\n"
            "- Download results to retain every query, its status, and full numeric precision. "
            "The result table's displayed rounding does not change the download."
        )
