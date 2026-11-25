"""Streamlit interface for exploring one- and two-dimensional interpolation."""

import hashlib
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coffee_widget import add_buy_me_a_coffee
from column_picker import select_column
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


def read_table_cached(content, options, context, *, uploaded=False):
    """Retain only the latest parsed table per workflow, within this session."""
    payload = content if isinstance(content, bytes) else content.encode("utf-8")
    identity = hashlib.sha256(payload + repr(options).encode("utf-8")).hexdigest()
    cache_key = f"_parsed_{context}"
    cached = st.session_state.get(cache_key)
    if cached is not None and cached[0] == identity:
        return cached[1]
    frame = (read_csv_smart(io.BytesIO(payload), **options) if uploaded
             else read_pasted_table(content, **options))
    frame.attrs["input_identity"] = identity
    st.session_state[cache_key] = (identity, frame)
    return frame


def prepare_reference_cached(raw, selected, dimension):
    identity = (raw.attrs.get("input_identity", "example"), tuple(selected))
    cache_key = f"_prepared_reference_{dimension}"
    cached = st.session_state.get(cache_key)
    if cached is None or cached[0] != identity:
        clean, stats = prepare_reference(raw, selected)
        st.session_state[cache_key] = (identity, clean, stats)
    else:
        _, clean, stats = cached
    clean.attrs["input_identity"] = identity
    clean.attrs["source_label"] = raw.attrs.get("source_label", "Example data")
    return clean, stats


def numeric_query_cached(raw, selected):
    identity = (raw.attrs["input_identity"], tuple(selected))
    cached = st.session_state.get("_prepared_queries_2d")
    if cached is None or cached[0] != identity:
        query = numeric_columns(raw, selected)
        valid = np.isfinite(query.to_numpy(dtype=float)).all(axis=1)
        query.columns = ["xi", "yi"]
        query = query.reset_index(drop=True)
        st.session_state["_prepared_queries_2d"] = (identity, query, valid)
    else:
        _, query, valid = cached
    query.attrs["source_label"] = raw.attrs.get("source_label", "Pasted query table")
    query.attrs["column_roles"] = tuple(selected)
    return query, valid


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
    st.write(f"Read as: {delimiter} columns · decimal {decimal} · {header} · {thousands}. "
               f"{len(frame):,} data rows, {len(frame.columns):,} columns.")
    for warning in info.get("warnings", []):
        st.warning(warning)


def numeric_preview(frame, columns):
    if "import_format" not in frame.attrs:
        return
    numeric = numeric_columns(frame.head(5), columns)
    preview = pd.DataFrame(index=frame.index[:5])
    config = {}
    for column in columns:
        preview[f"{column} (original)"] = frame[column].head(5).astype(str)
        preview[f"{column} (number)"] = numeric[column].head(5)
        config[f"{column} (number)"] = st.column_config.NumberColumn(format="%.12g")
    with st.expander("Check how your numbers are read", expanded=False):
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


def clear_upload(key):
    st.session_state.pop(f"cached_{key}", None)
    context = "queries_2d" if key == "upload_queries_2d" else key.removeprefix("upload_")
    st.session_state.pop(f"_parsed_{context}", None)
    st.session_state.pop(f"_prepared_{context}", None)
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
    frame = read_table_cached(content, options, key.removeprefix("upload_"), uploaded=True)
    # Filename is part of source identity, even if the numerical cells are identical.
    frame.attrs["source_label"] = f"Uploaded CSV · {name}"
    return frame


def load_table(dimension):
    source = st.radio("Reference data", SOURCES, horizontal=True,
                      key=f"input_source_{dimension}")
    frame = pd.DataFrame()
    try:
        if source == "Example data":
            frame = example_data(dimension)
            frame.attrs["input_identity"] = f"example_{dimension}"
            frame.attrs["source_label"] = "Example data"
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
                frame = read_table_cached(text, options, f"reference_{dimension}")
                frame.attrs["source_label"] = "Pasted reference table"
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
        clean, stats = prepare_reference_cached(raw, selected, dimension)
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
            identity = (text, decimal_comma)
            cached = st.session_state.get("_prepared_queries_1d")
            if cached is None or cached[0] != identity:
                queries = parse_float_list(text, decimal_comma=decimal_comma)
                query = pd.DataFrame({"xi": queries})
                query.attrs["input_identity"] = hashlib.sha256(repr(identity).encode("utf-8")).hexdigest()
                query.attrs["source_label"] = "Entered X values"
                st.session_state["_prepared_queries_1d"] = (identity, query)
            else:
                query = cached[1]
            if query.empty:
                return None, "Enter one or more numeric X values."
            return query, None
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
            raw = read_table_cached(text, options, "queries_2d")
            raw.attrs["source_label"] = "Pasted query table"
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
        left, right = st.columns(2)
        with left:
            qx = select_column("Query X column", columns, f"input_query_x_2d_{source}_{mode}")
        with right:
            qy = select_column("Query Y column", [c for c in columns if c != qx],
                               f"input_query_y_2d_{source}_{mode}")
        # Queries keep their order and duplicates; reject invalid rows as a batch.
        numeric_preview(raw, [qx, qy])
        query, valid = numeric_query_cached(raw, [qx, qy])
        if not valid.all():
            rows = ", ".join(str(i + 1) for i in np.flatnonzero(~valid)[:8])
            return None, (f"Fix query data row(s) {rows}: both coordinates must be finite numbers. "
                          "Check the decimal and thousands settings. No query rows were removed.")
        return query, None
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
    summary = {
        "auto": "Uses bilinear interpolation for a complete grid; linear for scattered points.",
        "linear": ("Straight lines between neighboring samples." if dimension == "1d" else
                   "A piecewise linear surface between scattered samples."),
        "nearest": "Returns the closest known sample; values change in steps.",
        "regular": "Bilinear interpolation requires a complete rectangular X/Y grid.",
        "rbf": "Fits a smooth surface. Distances use scaled coordinate axes.",
    }
    st.caption(summary[method])
    return method, outside


def signature(source, data, selected, queries, method, outside):
    if data is None or queries is None:
        return None
    digest = hashlib.sha256(repr((source, selected, method, outside,
                                data.attrs.get("input_identity"),
                                data.attrs.get("source_label"),
                                queries.attrs.get("input_identity"),
                                queries.attrs.get("source_label"),
                                queries.attrs.get("column_roles"))).encode("utf-8"))
    for frame in (data, queries):
        digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return digest.hexdigest()


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
    from html import escape

    # Keep the same visual roles across methods and modes. Marker shapes also
    # identify measured samples, queries, and outside-data estimates.
    colors = {"estimate": "#6251c6", "sample": "#252b3b",
              "query": "#087e8b", "outside": "#9a4b05", "grid": "#e5e7ee"}
    labels = [escape(str(column)) for column in selected]
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
                                 name="Interpolation", line=dict(color=colors["estimate"], width=2,
                                                                 shape="hv" if method == "nearest" else "linear"),
                                 hovertemplate=f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}"
                                               "<extra>Estimated curve</extra>"))
        fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="Reference samples",
                                 marker=dict(size=8, symbol="square", color=colors["sample"],
                                             line=dict(color="white", width=1)),
                                 hovertemplate=f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}"
                                               "<extra>Known sample</extra>"))
        y_title = selected[1]
    else:
        xcol, ycol, zcol = selected
        gx = np.linspace(data[xcol].min(), data[xcol].max(), 55)
        gy = np.linspace(data[ycol].min(), data[ycol].max(), 55)
        mx, my = np.meshgrid(gx, gy)
        z = interpolator(mx.ravel(), my.ravel()).reshape(mx.shape)
        fig.add_trace(go.Heatmap(
            x=gx, y=gy, z=z, name="Estimated display grid (55 × 55)", zsmooth=False,
            colorscale=[[0, "#f0edff"], [0.5, "#a99bde"], [1, "#49378f"]],
            colorbar=dict(title=dict(text=zcol, side="top"), orientation="h",
                          y=1.08, yanchor="bottom", x=0, xanchor="left", len=1, thickness=12),
            hovertemplate=f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}<br>{labels[2]}: %{{z}}"
                          "<extra>Estimated display grid</extra>"))
        fig.add_trace(go.Scatter(x=data[xcol], y=data[ycol], mode="markers", name="Reference samples",
                                 customdata=data[[zcol]].to_numpy(),
                                 marker=dict(size=8, symbol="square", color=colors["sample"],
                                             line=dict(color="white", width=1)),
                                 hovertemplate=f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}"
                                               f"<br>{labels[2]}: %{{customdata[0]}}"
                                               "<extra>Known sample</extra>"))
        y_title = ycol
    output_col = "yi" if dimension == "1d" else "zi"
    for is_outside, name, color, symbol in [(False, "Interpolated queries", colors["query"], "circle"),
                                            (True, "Outside known data", colors["outside"], "diamond")]:
        points = out[out["status"].str.startswith("Outside") == is_outside]
        if dimension == "1d":
            # Blank results have no Y position, so their status remains in the table.
            points = points[np.isfinite(points[output_col])]
        if not points.empty:
            hover = (f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}" if dimension == "1d" else
                     f"{labels[0]}: %{{x}}<br>{labels[1]}: %{{y}}<br>{labels[2]}: %{{customdata[0]}}")
            fig.add_trace(go.Scatter(x=points["xi"], y=points["yi"], mode="markers", name=name,
                                     customdata=points[[output_col, "status"]].to_numpy(),
                                     hovertemplate=hover + "<br>%{customdata[1]}<extra></extra>",
                                     marker=dict(size=10, color=color, symbol=symbol,
                                                 line=dict(width=1, color="white"))))
    fig.update_layout(xaxis_title=selected[0], yaxis_title=y_title,
                      height=480 if dimension == "2d" else 420,
                      margin=dict(l=45, r=15, t=90 if dimension == "2d" else 15, b=125),
                      # A single column of legend entries fits narrow screens and
                      # cannot overlap the chart tools or query controls.
                      legend=dict(orientation="v", y=-0.18, yanchor="top", x=0,
                                  font=dict(size=12)),
                      font=dict(family="Inter, system-ui, sans-serif", size=12, color=colors["sample"]),
                      hoverlabel=dict(bgcolor="white", font_color=colors["sample"]),
                      uirevision=f"{dimension}|{'|'.join(map(str, selected))}",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(automargin=True, gridcolor=colors["grid"], zerolinecolor=colors["grid"])
    fig.update_yaxes(automargin=True, gridcolor=colors["grid"], zerolinecolor=colors["grid"])
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
    record["chart_note"] = (
        "Squares are known samples; circles are queries within known data; diamonds mark outside-data queries. "
        + ("The estimated surface is drawn on a 55 × 55 display grid, not additional measured data. "
           "Query results are calculated at their exact coordinates."
           if dimension == "2d" else
           "The line shows nearest-sample steps." if method == "nearest" else
           "The line joins known samples using linear interpolation.")
    )
    if dimension == "1d" and np.any(~np.isfinite(values)):
        record["chart_note"] += " Blank results remain in the table and have no chart marker."
    try:
        record["chart"] = make_chart(dimension, data, selected, out, method, outside, interpolator)
    except (ValueError, RuntimeError):
        record["chart_error"] = "The chart could not be drawn. Your calculated table is still available."
    return record


def render_results(dimension, fingerprint):
    st.subheader("3. Inspect results")
    saved = st.session_state.get(f"result_{dimension}")
    if saved is None:
        st.info("Ready when you are. Add your query points and select Calculate values.",
                icon=":material/auto_graph:")
        st.write("Your chart and calculated table will appear here.")
        st.caption("Try the loaded example first. Then check each query's status and download all results.")
        return
    stale = saved["fingerprint"] != fingerprint
    if stale:
        st.warning("Inputs have changed. These are your previous results. Calculate again to update them.")
    else:
        st.success(f"Calculated {len(saved['data']):,} query point(s). Results are current.")
    st.write(f"Source: {saved.get('source_label', 'Previous reference data')}")
    if saved.get("query_source"):
        st.caption(f"Queries: {saved['query_source']}")
    st.caption(f"{saved['method']} · Outside known data: {saved['outside'].lower()}")
    st.caption(" · ".join(f"{role}: {name}" for role, name in
                          zip(["X", "Y", "Z"], saved["columns"])))
    if saved["outside_count"]:
        st.info(f"{saved['outside_count']:,} query point(s) outside the known data region. "
                "Check the status column before using these results.")
    if saved["chart"] is not None:
        st.plotly_chart(saved["chart"], width="stretch", key=f"plot_{dimension}",
                        config={"scrollZoom": False, "displaylogo": False})
        if saved.get("chart_note"):
            st.caption(saved["chart_note"])
    if saved["chart_error"]:
        st.info(saved["chart_error"])
    columns = saved["columns"]
    column_config = {"xi": st.column_config.NumberColumn(f"X · {columns[0]}", format="%.6g"),
                     "yi": st.column_config.NumberColumn(f"Y · {columns[1]}", format="%.6g"),
                     "status": st.column_config.TextColumn("Status")}
    if dimension == "2d":
        column_config["zi"] = st.column_config.NumberColumn(f"Z · {columns[2]}", format="%.6g")
    st.markdown("**Calculated queries**")
    st.caption(f"All {len(saved['data']):,} queries, in your original order. "
               "The table displays six significant digits; downloads keep full numeric precision.")
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
        st.caption("Format preview · first three queries only")
        st.code(preview.decode("utf-8-sig"), language="text")
    # One export buffer per result: cosmetic reruns do not repeatedly serialize a large table.
    export_key = (delimiter, decimal)
    if saved.get("export_format") != export_key:
        saved["export_bytes"] = result_csv(saved["data"], delimiter=delimiter, decimal=decimal)
        saved["export_format"] = export_key
    csv_data = saved["export_bytes"]
    extension = "tsv" if delimiter == "\t" else "csv"
    st.download_button("Download results as CSV" if extension == "csv" else "Download results as TSV", csv_data,
                       file_name=f"interpolated_{dimension}.{extension}",
                       mime="text/tab-separated-values" if extension == "tsv" else "text/csv",
                       disabled=stale, key=f"download_{dimension}", width="stretch",
                       icon=":material/download:", on_click="ignore")
    if stale:
        st.caption("Recalculate to enable the download for your current inputs.")
    else:
        st.caption("CSV includes every query in its original order, full numeric precision, and a status column.")


def render_workflow(dimension):
    controls, results = st.columns([1, 1.65], gap="large")
    with controls:
        with st.container(border=True, key=f"controls_{dimension}"):
            source, data, selected = reference_inputs(dimension)
            st.divider()
            st.subheader("2. Choose what to estimate")
            query, query_error = query_inputs(dimension, source)
            method, outside = settings_inputs(dimension)
            fingerprint = signature(source, data, selected, query, method, outside)
            if query_error:
                if query_error.startswith(("Enter ", "Choose ")):
                    st.info(query_error)
                else:
                    st.error(query_error)
            elif query is not None:
                st.caption(f"{len(query):,} query point(s) ready. Query order and duplicates are preserved.")
            if data is None:
                st.info("Add valid reference data in step 1 to enable calculation.")
            if st.button("Calculate values", type="primary", key=f"calculate_{dimension}",
                         disabled=fingerprint is None, width="stretch", icon=":material/calculate:"):
                try:
                    with st.spinner("Calculating values and preparing the chart…"):
                        result = calculate(dimension, data, selected, query, method, outside, fingerprint)
                    result["source_label"] = data.attrs.get("source_label", source)
                    result["query_source"] = query.attrs.get("source_label", "Entered query points")
                    result["reference_count"] = len(data)
                    st.session_state[f"result_{dimension}"] = result
                except (ValueError, RuntimeError) as error:
                    st.error(f"Could not calculate values. {error} Your inputs are kept; correct them and try again.")
    with results:
        with st.container(border=True, key=f"results_{dimension}"):
            render_results(dimension, fingerprint)


def main():
    st.set_page_config(page_title="Interpolator", page_icon="📈", layout="wide")
    remember_inputs()
    st.markdown("""<style>
        :root { --workspace-surface: #fff; --workspace-muted: #626b80;
                --workspace-focus: #6251c6; }
        .block-container { max-width: 1440px; padding-top: 2rem; padding-bottom: 2rem; }
        h1 { letter-spacing: -0.035em; }
        .st-key-controls_1d, .st-key-controls_2d,
        .st-key-results_1d, .st-key-results_2d { background: var(--workspace-surface); }
        [data-testid="stCaptionContainer"] { color: var(--workspace-muted); font-size: 0.94rem; }
        :focus-visible { outline: 2px solid var(--workspace-focus); outline-offset: 3px; }
        @media (max-width: 640px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            h1 { font-size: 2rem; }
            button { min-height: 44px; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { scroll-behavior: auto !important;
                animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
        }
    </style>""", unsafe_allow_html=True)
    st.title("Interpolator")
    st.write("Estimate values between known data points.")
    st.caption("Add known data → Choose query points → Inspect and download results")
    tab1, tab2 = st.tabs(["1D · Find Y from X", "2D · Find Z from X and Y"])
    with tab1:
        render_workflow("1d")
    with tab2:
        render_workflow("2d")
    st.divider()
    st.caption("Inputs, settings, and results are kept in this server session. Download results to keep them.")
    with st.expander("Session & privacy"):
        st.write("Uploaded files and pasted data are sent to the Streamlit server for processing. "
                 "They are retained in the active session, including when you switch sources or modes. "
                 "Use Clear uploaded file to remove a retained upload. Previous calculated results stay "
                 "visible and are marked as needing an update.")
        st.write("Settings are not saved as a portable setup. A browser refresh, disconnection, or server "
                 "restart may reset the session. Download any results you want to keep.")
    add_buy_me_a_coffee()


if __name__ == "__main__":
    main()
