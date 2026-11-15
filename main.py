"""Streamlit interface for exploring one- and two-dimensional interpolation."""

import hashlib
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coffee_widget import add_buy_me_a_coffee
from interpolation import (
    build_forward_interpolator,
    interp_linear,
    interp_nearest,
    numeric_columns,
    parse_float_list,
    prepare_reference,
    read_csv_smart,
    read_pasted_table,
    result_csv,
)


SOURCES = ["Example data", "Upload CSV", "Paste table"]
METHODS = {
    "auto": "Automatic (recommended)",
    "linear": "Linear",
    "nearest": "Nearest sample",
    "regular": "Bilinear · complete grid",
    "rbf": "Smooth surface (RBF)",
}
OUTSIDE = {
    "nan": "Leave blank",
    "clamp": "Keep boundary value",
    "linear": "Extend end slopes",
    "nearest": "Use nearest sample",
}
DELIMITERS = {"auto": "Auto detect", ",": "Comma (,)", ";": "Semicolon (;)",
              "\t": "Tab", "whitespace": "Whitespace", "|": "Pipe (|)"}
DECIMALS = {"auto": "Auto detect", ".": "Point (1.25)", ",": "Comma (1,25)"}
THOUSANDS = {None: "None", ",": "Comma (1,000)", ".": "Point (1.000)",
             " ": "Space (1 000)", "'": "Apostrophe (1'000)"}


def import_settings(context):
    with st.expander("Import settings"):
        st.caption("Check the preview below. Override automatic detection if your data is read incorrectly.")
        left, right = st.columns(2)
        with left:
            delimiter = st.selectbox("Column separator", list(DELIMITERS),
                                      format_func=DELIMITERS.get,
                                      key=f"input_format_{context}_delimiter")
            header = st.selectbox("First row contains column names", ["auto", True, False],
                                   format_func={"auto": "Auto detect", True: "Yes", False: "No"}.get,
                                   key=f"input_format_{context}_header")
        with right:
            decimal = st.selectbox("Decimal separator", list(DECIMALS), format_func=DECIMALS.get,
                                    key=f"input_format_{context}_decimal")
            thousands = st.selectbox("Thousands separator (optional)", list(THOUSANDS),
                                      format_func=THOUSANDS.get,
                                      key=f"input_format_{context}_thousands",
                                      help="Choose a grouping separator only if your numbers use one. It is never guessed.")
        st.caption("Decimal commas and comma-separated columns can be combined when the decimal values are quoted. "
                   "For unquoted decimal commas, use semicolons or tabs between columns.")
    return {"delimiter": delimiter, "decimal": decimal, "thousands": thousands, "header": header}


def import_summary(frame):
    info = frame.attrs.get("import_format")
    if not info:
        return
    delimiter = {",": "comma", ";": "semicolon", "\t": "tab", "whitespace": "whitespace", "|": "pipe"}.get(
        info["delimiter"], str(info["delimiter"]))
    decimal = "comma" if info["decimal"] == "," else "point"
    header = "header row" if info["header"] else "no header row"
    thousands = ("no thousands separator" if info["thousands"] is None else
                 f"thousands: {THOUSANDS[info['thousands']].lower()}")
    st.caption(f"Read as: {delimiter} columns · decimal {decimal} · {header} · {thousands}. "
               f"{len(frame):,} data rows, {len(frame.columns):,} columns.")
    for warning in info.get("warnings", []):
        st.warning(warning)


def numeric_preview(frame, columns):
    if "import_format" not in frame.attrs:
        return
    numeric = numeric_columns(frame, columns)
    preview = pd.DataFrame(index=frame.index[:5])
    config = {}
    for column in columns:
        preview[f"{column} (original)"] = frame[column].head(5).astype(str)
        preview[f"{column} (number)"] = numeric[column].head(5)
        config[f"{column} (number)"] = st.column_config.NumberColumn(format="%.12g")
    with st.expander("Check how your numbers are read", expanded=True):
        st.caption("First five data rows, before excluding invalid values or averaging duplicates. "
                   "Numeric previews use decimal points. A blank numeric cell means the value could not be read.")
        st.dataframe(preview, hide_index=True, width="stretch", column_config=config)


def example_data(dimension):
    if dimension == "1d":
        return pd.DataFrame({"Time (s)": [0, 2, 4, 6, 8, 10],
                             "Temperature (°C)": [18, 22, 28, 35, 39, 42]})
    x, y = np.meshgrid([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
    return pd.DataFrame({"X": x.ravel(), "Y": y.ravel(),
                         "Value": (10 + 2 * x + 3 * y + x * y).ravel()})


def remember_inputs():
    # Keep text and settings when their source-specific widgets are hidden.
    # File uploads have separate keys and are never assigned programmatically.
    for key in list(st.session_state):
        if key.startswith("input_"):
            st.session_state[key] = st.session_state[key]


def select_column(label, options, key, index=0):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[min(index, len(options) - 1)]
    return st.selectbox(label, options, key=key)


def clear_upload(key):
    st.session_state.pop(f"cached_{key}", None)
    st.session_state[f"generation_{key}"] = st.session_state.get(f"generation_{key}", 0) + 1


def uploaded_table(label, key, context):
    generation = st.session_state.get(f"generation_{key}", 0)
    upload = st.file_uploader(label, type=["csv"], key=f"{key}_{generation}")
    if upload is not None:
        st.session_state[f"cached_{key}"] = (upload.name, upload.getvalue())
    cached = st.session_state.get(f"cached_{key}")
    options = import_settings(context)
    if cached is None:
        return None
    name, content = cached
    st.caption(f"Loaded: {name}. This file stays available when you switch input sources.")
    st.button("Clear uploaded file", key=f"clear_{key}", on_click=clear_upload, args=(key,))
    return read_csv_smart(io.BytesIO(content), **options)


def load_table(dimension):
    source = st.radio("Reference data", SOURCES, horizontal=True,
                      key=f"input_source_{dimension}")
    frame = pd.DataFrame()
    try:
        if source == "Example data":
            frame = example_data(dimension)
            st.caption("A small example is loaded. Calculate below, or switch to your own data.")
        elif source == "Upload CSV":
            uploaded = uploaded_table("Choose a reference CSV", f"upload_reference_{dimension}",
                                       f"reference_{dimension}_{source}")
            if uploaded is not None:
                frame = uploaded
            else:
                st.info("Choose a CSV with at least two columns." if dimension == "1d"
                        else "Choose a CSV with at least three columns.")
        else:
            text = st.text_area("Paste reference data", height=130,
                                placeholder="X,Y\n0,10\n1,20\n2,30" if dimension == "1d"
                                else "X,Y,Value\n0,0,10\n1,0,12\n0,1,13\n1,1,16",
                                key=f"input_reference_{dimension}",
                                help="Paste cells from a spreadsheet, or a comma- or semicolon-separated table. Headers are optional.")
            options = import_settings(f"reference_{dimension}_{source}")
            if text.strip():
                frame = read_pasted_table(text, **options)
            else:
                st.info("Paste your known data points to get started.")
    except (ValueError, pd.errors.ParserError, UnicodeError) as error:
        st.error(f"Could not read this table. {error}")

    if "import_format" in frame.attrs:
        import_summary(frame)

    with st.expander("Input formats and example CSV"):
        st.write("Use a CSV or paste spreadsheet cells. A header row is optional. "
                 "Use Import settings to choose column, decimal, and optional thousands separators. "
                 "Each row must have the same number of columns. The preview shows how your selected values are read.")
        st.download_button("Download example CSV", result_csv(example_data(dimension)),
                           file_name=f"example_{dimension}.csv", mime="text/csv",
                           key=f"example_download_{dimension}")
    return source, frame


def reference_inputs(dimension):
    st.subheader("1. Add known data")
    source, raw = load_table(dimension)
    required = 2 if dimension == "1d" else 3
    if raw.empty:
        if "import_format" in raw.attrs:
            st.info("No data rows were found. Add your known points, or check whether the first row contains column names.")
        return source, None, None
    if len(raw.columns) < required:
        st.error(f"This table has {len(raw.columns)} column(s). Add at least {required} columns.")
        return source, None, None

    choices, selected = list(raw.columns), []
    labels = ["X · input", "Y · value to estimate"] if dimension == "1d" else [
        "X · first input", "Y · second input", "Z · value to estimate"]
    for index, (column, label) in enumerate(zip(st.columns(required), labels)):
        with column:
            available = [name for name in choices if name not in selected]
            selected.append(select_column(label, available, f"input_column_{dimension}_{source}_{index}"))
    try:
        numeric_preview(raw, selected)
        clean, stats = prepare_reference(raw, selected)
    except ValueError as error:
        st.error(str(error))
        return source, None, selected

    if stats["invalid_rows"]:
        st.warning(f"{stats['invalid_rows']:,} of {stats['input_rows']:,} reference rows excluded: "
                   "a selected cell is empty, invalid for the chosen number format, or infinite. "
                   "Check Import settings and the original table below.")
    if stats["duplicates_merged"]:
        coordinates = "X values" if dimension == "1d" else "X/Y pairs"
        st.info(f"{stats['duplicates_merged']:,} duplicate {coordinates} merged by averaging "
                "their output values.")
    with st.expander("Review reference data", expanded=False):
        st.caption("Prepared data used for calculation")
        st.dataframe(clean, hide_index=True, width="stretch")
        if stats["invalid_rows"] or stats["duplicates_merged"]:
            st.caption("Original table")
            st.dataframe(raw, hide_index=True, width="stretch")
    if dimension == "1d" and len(clean) < 2:
        st.error("Choose columns with at least two different numeric X values.")
        return source, None, selected
    if dimension == "2d" and len(clean) < 3:
        st.error("Add at least three different numeric coordinate pairs.")
        return source, None, selected
    ranges = " · ".join(f"{name}: {clean[name].min():g} to {clean[name].max():g}"
                         for name in selected[:-1])
    st.caption(f"{len(clean):,} reference points ready · {ranges}")
    return source, clean, selected


def query_inputs(dimension, source):
    if dimension == "1d":
        query_key = f"input_queries_1d_{source}"
        if query_key not in st.session_state:
            st.session_state[query_key] = "1\n3\n7\n12" if source == "Example data" else ""
        text = st.text_area("X values to estimate", height=140,
                            key=query_key, placeholder="1\n2.5\n3.75",
                            help="Separate values with newlines, commas, spaces, or semicolons. "
                            "Commas separate values unless you enable decimal commas below.")
        decimal_comma = st.checkbox("Use decimal commas (2,5 → 2.5)",
                                    key=f"input_decimal_1d_{source}",
                                    help="Separate decimal-comma values with newlines, spaces, tabs, or semicolons.")
        if not text.strip():
            return None, "Enter one or more X values."
        try:
            queries = parse_float_list(text, decimal_comma=decimal_comma)
            if queries.size == 0:
                return None, "Enter one or more numeric X values."
            return pd.DataFrame({"xi": queries}), None
        except ValueError as error:
            return None, str(error)

    mode = st.radio("Query points", ["Paste table", "Upload CSV"], horizontal=True,
                    key="input_query_source_2d")
    try:
        if mode == "Paste table":
            query_key = f"input_queries_2d_{source}"
            if query_key not in st.session_state:
                st.session_state[query_key] = "X,Y\n0.5,0.5\n1.5,1\n3,1" if source == "Example data" else ""
            text = st.text_area("X and Y coordinates to estimate", height=140,
                                key=query_key, placeholder="X,Y\n0.5,0.5\n1.5,1",
                                help="One coordinate pair per row. Headers are optional.")
            options = import_settings(f"queries_2d_{source}_{mode}")
            if not text.strip():
                return None, "Enter X and Y coordinates, one pair per row."
            raw = read_pasted_table(text, **options)
        else:
            uploaded = uploaded_table("Choose a query CSV", "upload_queries_2d",
                                       f"queries_2d_{source}_{mode}")
            if uploaded is None:
                return None, "Choose a CSV containing X and Y query coordinates."
            raw = uploaded
        import_summary(raw)
        if raw.empty:
            return None, "No query data rows were found. Add coordinate pairs or check the column-name setting."
        if len(raw.columns) < 2:
            return None, "Query points need at least two columns: X and Y."
        columns = list(raw.columns)
        if len(columns) > 2 or mode == "Upload CSV":
            left, right = st.columns(2)
            with left:
                qx = select_column("Query X column", columns, f"input_query_x_2d_{source}_{mode}")
            with right:
                qy = select_column("Query Y column", [c for c in columns if c != qx],
                                   f"input_query_y_2d_{source}_{mode}")
        else:
            qx, qy = columns[:2]
        # Queries keep their order and duplicates; reject invalid rows as a batch.
        numeric_preview(raw, [qx, qy])
        query = numeric_columns(raw, [qx, qy])
        valid = np.isfinite(query.to_numpy(dtype=float)).all(axis=1)
        if not valid.all():
            rows = ", ".join(str(i + 1) for i in np.flatnonzero(~valid)[:8])
            return None, (f"Fix query data row(s) {rows}: both coordinates must be finite numbers. "
                          "Check the decimal and thousands settings. No query rows were removed.")
        query.columns = ["xi", "yi"]
        return query.reset_index(drop=True), None
    except (ValueError, pd.errors.ParserError, UnicodeError) as error:
        return None, f"Could not read query points. {error}"


def settings_inputs(dimension):
    left, right = st.columns(2)
    with left:
        methods = ["linear", "nearest"] if dimension == "1d" else list(METHODS)
        method = st.selectbox("Interpolation method", methods, format_func=METHODS.get,
                              key=f"input_method_{dimension}")
    with right:
        outside_options = ["nan", "clamp", "linear"] if dimension == "1d" and method == "linear" else (
            ["nan", "clamp"] if dimension == "1d" else ["nan", "nearest"])
        outside_key = f"input_outside_{dimension}"
        if st.session_state.get(outside_key) not in outside_options:
            st.session_state[outside_key] = "nan"
        outside = st.selectbox("Outside known data", outside_options, format_func=OUTSIDE.get,
                               key=outside_key,
                               help="Outside values depend on an assumption. Leave blank avoids estimating beyond your data.")
    with st.expander("Choosing a method"):
        if dimension == "1d":
            st.write("**Linear** joins neighboring samples with straight lines. "
                     "**Nearest sample** returns the closest measured value. "
                     "The known range runs from the smallest to the largest X.")
        else:
            st.write("**Automatic** uses bilinear interpolation for a complete grid, and linear "
                     "interpolation for scattered points. **Nearest sample** keeps measured values. "
                     "**Smooth surface (RBF)** fits a smooth surface through the samples. "
                     "**Bilinear** requires every combination of X and Y to be present.")
            st.write("The known region is the area enclosed by the outermost reference points "
                     "(their convex hull). A query can be outside that area even if its X and Y "
                     "are individually within range.")
    return method, outside


def signature(source, data, selected, queries, method, outside):
    if data is None or queries is None:
        return None
    content = "|".join([source, repr(selected), data.to_csv(index=False),
                        queries.to_csv(index=False), method, outside])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def result_status(inside, values, outside):
    result = np.where(inside, "Interpolated", "Outside · left blank").astype(object)
    result[~inside & np.isfinite(values)] = {
        "clamp": "Outside · boundary value",
        "linear": "Outside · extended slope",
        "nearest": "Outside · nearest sample",
    }.get(outside, "Outside · left blank")
    result[inside & ~np.isfinite(values)] = "Unavailable"
    return result


def make_chart(dimension, data, selected, out, method, outside, interpolator=None):
    fig = go.Figure()
    if dimension == "1d":
        x, y = (data[c].to_numpy() for c in selected)
        # Evaluate the actual method so nearest-neighbor charts show their steps.
        if method == "nearest":
            midpoints = (x[:-1] + x[1:]) / 2
            gx = np.unique(np.r_[x, midpoints, np.nextafter(midpoints, np.inf)])
        else:
            gx = np.unique(np.r_[np.linspace(x.min(), x.max(), 400), x])
        fn = interp_linear if method == "linear" else interp_nearest
        fig.add_trace(go.Scatter(x=gx, y=fn(x, y, gx, outside), mode="lines",
                                 name="Interpolation", line=dict(color="#0f766e", width=2,
                                                                 shape="hv" if method == "nearest" else "linear")))
        fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="Reference samples",
                                 marker=dict(size=7, color="#0f766e")))
        y_title = selected[1]
    else:
        xcol, ycol, zcol = selected
        gx = np.linspace(data[xcol].min(), data[xcol].max(), 55)
        gy = np.linspace(data[ycol].min(), data[ycol].max(), 55)
        mx, my = np.meshgrid(gx, gy)
        z = interpolator(mx.ravel(), my.ravel()).reshape(mx.shape)
        fig.add_trace(go.Heatmap(x=gx, y=gy, z=z, colorscale="Teal", colorbar=dict(title=zcol),
                                 hovertemplate="X: %{x}<br>Y: %{y}<br>Value: %{z}<extra></extra>"))
        fig.add_trace(go.Scatter(x=data[xcol], y=data[ycol], mode="markers", name="Reference samples",
                                 marker=dict(size=6, color="#172b4d", line=dict(color="white", width=1))))
        y_title = ycol
    output_col = "yi" if dimension == "1d" else "zi"
    for is_outside, name, color, symbol in [(False, "Interpolated queries", "#2563eb", "circle"),
                                            (True, "Outside known data", "#b45309", "diamond")]:
        points = out[out["status"].str.startswith("Outside") == is_outside]
        if dimension == "1d":
            # Blank results have no Y position, so their status remains in the table.
            points = points[np.isfinite(points[output_col])]
        if not points.empty:
            fig.add_trace(go.Scatter(x=points["xi"], y=points["yi"], mode="markers", name=name,
                                     customdata=points[[output_col, "status"]].to_numpy(),
                                     hovertemplate="X: %{x}<br>Y: %{y}<br>Value: %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
                                     marker=dict(size=10, color=color, symbol=symbol,
                                                 line=dict(width=1, color="white"))))
    fig.update_layout(xaxis_title=selected[0], yaxis_title=y_title, height=390,
                      margin=dict(l=10, r=10, t=15, b=10),
                      legend=dict(orientation="h", y=-0.23, x=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def calculate(dimension, data, selected, query, method, outside, fingerprint):
    out = query.copy()
    interpolator = None
    if dimension == "1d":
        x, y = (data[c].to_numpy() for c in selected)
        values = (interp_linear if method == "linear" else interp_nearest)(
            x, y, query["xi"].to_numpy(), outside)
        inside = query["xi"].between(x.min(), x.max()).to_numpy()
        actual_method = METHODS[method]
    else:
        interpolator, meta = build_forward_interpolator(data, *selected, method=method, extrap=outside)
        xq, yq = query["xi"].to_numpy(), query["yi"].to_numpy()
        values = interpolator(xq, yq)
        inside = meta["inside_domain"](xq, yq)
        actual_method = {"regular": "Bilinear · complete grid", "linearnd": "Linear · scattered points",
                         "linear": "Linear · scattered points", "nearest": "Nearest sample",
                         "rbf": "Smooth surface (RBF)"}.get(meta["type"], meta["type"])
    out["yi" if dimension == "1d" else "zi"] = values
    out["status"] = result_status(inside, values, outside)
    record = {"fingerprint": fingerprint, "data": out, "columns": selected,
              "method": actual_method, "outside": OUTSIDE[outside],
              "outside_count": int((~inside).sum()), "chart": None, "chart_error": None}
    try:
        record["chart"] = make_chart(dimension, data, selected, out, method, outside, interpolator)
    except (ValueError, RuntimeError):
        record["chart_error"] = "The chart could not be drawn. Your calculated table is still available."
    return record


def render_results(dimension, fingerprint):
    st.subheader("3. Inspect results")
    saved = st.session_state.get(f"result_{dimension}")
    if saved is None:
        st.info("Ready when you are. Add your query points and select Calculate values.")
        st.caption("Your results will include a chart, a table, and a CSV download.")
        return
    stale = saved["fingerprint"] != fingerprint
    if stale:
        st.warning("Inputs have changed. These are your previous results. Calculate again to update them.")
    else:
        st.success(f"Calculated {len(saved['data']):,} query point(s).")
    st.caption(f"{saved['method']} · Outside known data: {saved['outside'].lower()}")
    if saved["outside_count"]:
        st.info(f"{saved['outside_count']:,} query point(s) outside the known data region. "
                "Check the status column before using these results.")
    if saved["chart"] is not None:
        st.plotly_chart(saved["chart"], width="stretch", key=f"plot_{dimension}",
                        config={"scrollZoom": False, "displaylogo": False})
    if saved["chart_error"]:
        st.info(saved["chart_error"])
    columns = saved["columns"]
    column_config = {"xi": st.column_config.NumberColumn(f"X · {columns[0]}", format="%.6g"),
                     "yi": st.column_config.NumberColumn(f"Y · {columns[1]}", format="%.6g"),
                     "status": st.column_config.TextColumn("Status")}
    if dimension == "2d":
        column_config["zi"] = st.column_config.NumberColumn(f"Z · {columns[2]}", format="%.6g")
    st.dataframe(saved["data"], hide_index=True, width="stretch", column_config=column_config)
    with st.expander("CSV download format"):
        left, right = st.columns(2)
        with left:
            delimiter = st.selectbox("CSV column separator", [",", ";", "\t", "|"],
                                      format_func=DELIMITERS.get, key=f"input_export_delimiter_{dimension}")
        with right:
            decimal = st.selectbox("CSV decimal separator", [".", ","], format_func=DECIMALS.get,
                                    key=f"input_export_decimal_{dimension}")
        st.caption("Export settings change the downloaded file. Your calculated values stay the same. "
                   "UTF-8 encoding preserves column names and symbols in spreadsheets.")
        preview = result_csv(saved["data"].head(3), delimiter=delimiter, decimal=decimal)
        st.code(preview.decode("utf-8-sig"), language="text")
    csv_data = result_csv(saved["data"], delimiter=delimiter, decimal=decimal)
    extension = "tsv" if delimiter == "\t" else "csv"
    st.download_button("Download results as CSV" if extension == "csv" else "Download results as TSV", csv_data,
                       file_name=f"interpolated_{dimension}.{extension}",
                       mime="text/tab-separated-values" if extension == "tsv" else "text/csv",
                       disabled=stale, key=f"download_{dimension}", width="stretch")
    if stale:
        st.caption("Recalculate to enable the download for your current inputs.")
    else:
        st.caption("CSV includes every query in its original order, full numeric precision, and a status column.")


def render_workflow(dimension):
    with st.container(border=True):
        source, data, selected = reference_inputs(dimension)
    controls, results = st.columns([1, 1.5], gap="large")
    with controls:
        st.subheader("2. Choose what to estimate")
        query, query_error = query_inputs(dimension, source)
        method, outside = settings_inputs(dimension)
        fingerprint = signature(source, data, selected, query, method, outside)
        if query_error:
            if query_error.startswith(("Enter ", "Choose ")):
                st.caption(query_error)
            else:
                st.error(query_error)
        elif query is not None:
            st.caption(f"{len(query):,} query point(s) ready. Query order and duplicates are preserved.")
        if data is None:
            st.caption("Add valid reference data in step 1 to enable calculation.")
        if st.button("Calculate values", type="primary", key=f"calculate_{dimension}",
                     disabled=fingerprint is None, width="stretch"):
            try:
                with st.spinner("Calculating values…"):
                    result = calculate(dimension, data, selected, query, method, outside, fingerprint)
                st.session_state[f"result_{dimension}"] = result
            except (ValueError, RuntimeError) as error:
                st.error(f"Could not calculate values. {error}")
    with results:
        render_results(dimension, fingerprint)


def main():
    st.set_page_config(page_title="Interpolator", page_icon="📈", layout="wide")
    add_buy_me_a_coffee()
    remember_inputs()
    st.markdown("""<style>
        .block-container { max-width: 1440px; padding-top: 2rem; }
        h1 { letter-spacing: -0.035em; }
    </style>""", unsafe_allow_html=True)
    st.title("Interpolator")
    st.write("Estimate values between known data points.")
    st.caption("Add known data → Choose query points → Inspect and download results")
    tab1, tab2 = st.tabs(["1D · Find Y from X", "2D · Find Z from X and Y"])
    with tab1:
        render_workflow("1d")
    with tab2:
        render_workflow("2d")


if __name__ == "__main__":
    main()
