# interpolator_app.py
import io
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.interpolate import RegularGridInterpolator, LinearNDInterpolator, NearestNDInterpolator, griddata, RBFInterpolator

from coffee_widget import add_buy_me_a_coffee

# ---------------------------
# Page setup
# ---------------------------
st.set_page_config(page_title="Interpolator", page_icon="☄", layout="wide")
st.title("☄ Interpolator")
st.caption("1-D and 2-D interpolation online tool")
add_buy_me_a_coffee()

# ---------------------------
# Helpers
# ---------------------------
def _make_unique(names):
    seen, out = {}, []
    for n in names:
        base = str(n).strip() or "col"
        k = seen.get(base, 0)
        out.append(base if k == 0 else f"{base}.{k}")
        seen[base] = k + 1
    return out

def _looks_numeric(s: str) -> bool:
    s = str(s).strip()
    if s == "": return False
    s = s.replace(",", ".")
    try: float(s); return True
    except ValueError: return False

def read_csv_smart(file) -> pd.DataFrame:
    """
    Smart CSV reader:
    - If first row looks like headers (non-numeric), use as columns.
    - Else, keep all rows as data and auto-name columns col1, col2, ...
    - Auto-detect delimiter (engine='python', sep=None).
    - Coerce EU-decimal commas when converting later.
    """
    raw = pd.read_csv(file, header=None, sep=None, engine="python", dtype=str)
    if raw.empty: return pd.DataFrame()
    first_row = raw.iloc[0].tolist()
    header_like = not any(_looks_numeric(v) for v in first_row)
    if header_like:
        cols = _make_unique([str(v).strip() or f"col{i+1}" for i, v in enumerate(first_row)])
        df = raw.iloc[1:].reset_index(drop=True); df.columns = cols
    else:
        df = raw.copy(); df.columns = [f"col{i+1}" for i in range(df.shape[1])]
    # best-effort numeric (defer strict conversion to where needed)
    for c in df.columns:
        try:
            df[c] = pd.to_numeric(df[c].str.replace(",", ".", regex=False), errors="ignore")
        except Exception:
            pass
    return df

def read_pasted_table(text: str) -> pd.DataFrame:
    """
    Parse pasted table robustly:
    - Accepts comma, semicolon, or any whitespace as column separators.
    - Avoids splitting decimal commas (e.g., '3,14').
    - Promotes first row to header if it looks non-numeric.
    """
    text = (text or "").strip()
    if not text:
        return pd.DataFrame()

    # Remove carriage returns and strip empty lines
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        return pd.DataFrame()

    # Regex: split on ; or on , (only if not digit,digit), or whitespace
    # We do it by first protecting decimal commas
    safe = []
    for ln in lines:
        safe.append(re.sub(r"(\d),(\d)", r"\1§\2", ln))  # temporarily replace decimal commas
    safe_text = "\n".join(safe)

    try:
        df = pd.read_csv(
            io.StringIO(safe_text),
            sep=r"[;,\s]+",  # split on ; , or whitespace
            engine="python",
            header=None
        )
    except Exception:
        return pd.DataFrame({0: lines})

    # Restore decimal commas
    df = df.applymap(lambda v: str(v).replace("§", ",") if isinstance(v, str) else v)

    if df.empty:
        return df

    # Smart header detection
    def _looks_numeric_cell(v) -> bool:
        s = str(v).strip()
        if s == "":
            return False
        s = s.replace(",", ".")  # allow decimal comma
        try:
            float(s)
            return True
        except ValueError:
            return False

    first_row = df.iloc[0].tolist()
    header_like = not any(_looks_numeric_cell(v) for v in first_row)

    if header_like:
        cols = [str(v).strip() or f"col{i+1}" for i, v in enumerate(first_row)]
        # Ensure unique
        seen, uniq = {}, []
        for c in cols:
            k = seen.get(c, 0)
            uniq.append(c if k == 0 else f"{c}.{k}")
            seen[c] = k + 1
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = uniq
    else:
        df.columns = [f"col{i+1}" for i in range(df.shape[1])]

    return df



# --- 1D helpers ---
def parse_float_list(text: str) -> np.ndarray:
    text = text.strip()
    if not text: return np.array([], dtype=float)
    parts = re.split(r"[,\t;\s]+", text)
    vals = []
    for p in parts:
        if not p: continue
        try: vals.append(float(p.replace(",", ".")))
        except ValueError: pass
    return np.asarray(vals, dtype=float)

def prepare_xy(df: pd.DataFrame, x_col: str, y_col: str):
    d = df[[x_col, y_col]].copy()
    d = d.dropna()
    d[x_col] = pd.to_numeric(d[x_col], errors="coerce")
    d[y_col] = pd.to_numeric(d[y_col], errors="coerce")
    d = d.dropna()
    d = d.groupby(x_col, as_index=False)[y_col].mean()
    d = d.sort_values(x_col).reset_index(drop=True)
    return d

def interp_linear(x: np.ndarray, y: np.ndarray, xi: np.ndarray, extrap: str):
    if len(x) < 2:
        return np.full_like(xi, np.nan, dtype=float)
    yi = np.interp(xi, x, y, left=np.nan, right=np.nan)
    x_min, x_max = x[0], x[-1]
    y_min, y_max = y[0], y[-1]
    left_mask = xi < x_min
    right_mask = xi > x_max
    if extrap == "clamp":
        yi[left_mask] = y_min
        yi[right_mask] = y_max
    else:
        m_left = (y[1] - y[0]) / (x[1] - x[0])
        yi[left_mask] = y_min + m_left * (xi[left_mask] - x_min)
        m_right = (y[-1] - y[-2]) / (x[-1] - x[-2])
        yi[right_mask] = y_max + m_right * (xi[right_mask] - x_max)
    return yi

def interp_nearest(x: np.ndarray, y: np.ndarray, xi: np.ndarray, extrap: str):
    if len(x) == 0: return np.full_like(xi, np.nan, dtype=float)
    if len(x) == 1: return np.full_like(xi, y[0], dtype=float)
    idx = np.searchsorted(x, xi)
    left_idx = np.clip(idx - 1, 0, len(x) - 1)
    right_idx = np.clip(idx, 0, len(x) - 1)
    left_dist = np.abs(xi - x[left_idx])
    right_dist = np.abs(xi - x[right_idx])
    choose_right = right_dist < left_dist
    nearest_idx = np.where(choose_right, right_idx, left_idx)
    yi = y[nearest_idx]
    return yi  # extrap behaves like clamp

# --- 2D helpers ---
def dedupe_xy_mean(df, xcol, ycol, zcol):
    d = df[[xcol, ycol, zcol]].copy().dropna()
    d[xcol] = pd.to_numeric(d[xcol], errors="coerce")
    d[ycol] = pd.to_numeric(d[ycol], errors="coerce")
    d[zcol] = pd.to_numeric(d[zcol], errors="coerce")
    d = d.dropna()
    return d.groupby([xcol, ycol], as_index=False)[zcol].mean()

def is_full_grid(x, y):
    xu, yu = np.unique(x), np.unique(y)
    return x.size == xu.size * yu.size

def build_forward_interpolator(df, xcol, ycol, zcol, method="auto", extrap="nan"):
    d = dedupe_xy_mean(df, xcol, ycol, zcol)
    x, y, z = d[xcol].to_numpy(), d[ycol].to_numpy(), d[zcol].to_numpy()
    grid = is_full_grid(x, y)
    if method == "auto":
        method = "regular" if grid else "linearnd"

    if method == "regular" and grid:
        X = np.unique(x); Y = np.unique(y)
        xi = {v:i for i, v in enumerate(X)}; yi = {v:i for i, v in enumerate(Y)}
        Z = np.full((X.size, Y.size), np.nan)
        for xv, yv, zv in zip(x, y, z):
            Z[xi[xv], yi[yv]] = zv
        bounds_error = (extrap != "nan")
        fill_value = None if extrap != "nan" else np.nan
        rgi = RegularGridInterpolator((X, Y), Z, method="linear",
                                      bounds_error=bounds_error, fill_value=fill_value)
        def f(XQ, YQ): return rgi(np.column_stack([XQ, YQ]))
        return f, {"type":"regular", "X":X, "Y":Y, "Z":Z}

    if method in ("linearnd", "linear"):
        pts = np.column_stack([x, y])
        f_lin = LinearNDInterpolator(pts, z, fill_value=np.nan if extrap=="nan" else None)
        f_near = NearestNDInterpolator(pts, z) if extrap == "nearest" else None
        def f(XQ, YQ):
            out = f_lin(XQ, YQ)
            if extrap == "nearest":
                mask = np.isnan(out)
                if np.any(mask): out[mask] = f_near(XQ[mask], YQ[mask])
            return out
        return f, {"type":"linearnd"}

    if method == "nearest":
        pts = np.column_stack([x, y])
        f_near = NearestNDInterpolator(pts, z)
        def f(XQ, YQ): return f_near(XQ, YQ)
        return f, {"type":"nearest"}

    if method == "rbf":
        xmu, xsd = x.mean(), (x.std() or 1.0)
        ymu, ysd = y.mean(), (y.std() or 1.0)
        P = np.column_stack([(x - xmu)/xsd, (y - ymu)/ysd])
        rbf = RBFInterpolator(P, z, kernel="thin_plate_spline")
        def f(XQ, YQ):
            PQ = np.column_stack([(XQ - xmu)/xsd, (YQ - ymu)/ysd])
            return rbf(PQ)
        return f, {"type":"rbf"}

    pts = np.column_stack([x, y])
    def f(XQ, YQ):
        out = griddata(pts, z, (XQ, YQ), method="linear")
        if extrap == "nearest":
            near = griddata(pts, z, (XQ, YQ), method="nearest")
            mask = np.isnan(out)
            if np.any(mask): out[mask] = near[mask]
        return out
    return f, {"type":"griddata"}

# ---------------------------
# Tabs
# ---------------------------
tab1, tab2 = st.tabs(["1-D Interpolation", "2-D Interpolation (forward)"])

def render_tab1():
    st.subheader("1-D Interpolation: x → y")
    
    with st.expander("Upload",expanded=True):

        # --- Base data (x,y) ---
        left, _ = st.columns(2)
        with left:
            mode = st.radio("Provide base (x,y) data via:", ["Upload CSV", "Paste table"], index=0, key="mode1d")
    
        base_df = pd.DataFrame()
        if mode == "Upload CSV":
            file = st.file_uploader("Upload CSV (1st row = headers; select columns below)", type=["csv"], key="csv1d")
            if file:
                base_df = read_csv_smart(file)
        elif mode == "Paste table":
            paste = st.text_area("Paste table. Header row recommended.", height=160, key="paste1d")
            if paste.strip():
                base_df = read_pasted_table(paste)
    
        if base_df.empty:
            st.info("Load base (x,y) data to continue.")
            return

    # Column selection
    with st.expander("Select columns",expanded=True):
        col_x = st.selectbox("Select X column", options=list(base_df.columns), index=0, key="x1d")
        col_y = st.selectbox("Select Y column", options=list(base_df.columns), index=1 if base_df.shape[1] > 1 else 0, key="y1d")

        # Clean & prepare
        clean_df = base_df[[col_x, col_y]].copy()
        clean_df[col_x] = pd.to_numeric(clean_df[col_x], errors="coerce")
        clean_df[col_y] = pd.to_numeric(clean_df[col_y], errors="coerce")
        clean_df = clean_df.dropna(subset=[col_x, col_y])

        if clean_df.empty or clean_df[col_x].nunique() < 2:
            st.error("Not enough valid numeric data after cleaning. Check your X/Y columns.")
            return

        clean_df = clean_df.groupby(col_x, as_index=False)[col_y].mean().sort_values(col_x).reset_index(drop=True)
        st.caption("Reference Data for the interpolation")
        st.dataframe(clean_df, width="stretch")
        st.info("Duplicated `x` values are averaged before interpolation")

        x = clean_df[col_x].to_numpy()
        y = clean_df[col_y].to_numpy()
        
    with st.expander("Calculation",expanded=True):

        st.markdown("#### Select Method & Extrapolation options")

        st.markdown(
            """
            **How the methods work**

            * `linear` performs piecewise-linear interpolation between consecutive
              data points. Inside the data range it solves the line equation for
              each segment so the result always travels straight from one
              sample to the next.
            * `nearest` picks the Y value whose X is closest to the query point.
              It produces a step-like curve that never invents intermediate
              values.

            **Extrapolation choices**

            * `clamp` keeps the nearest boundary value whenever the query lies
              outside the sampled X range. This is often used to avoid
              extrapolating beyond measured data.
            * `linear` extends the slope of the first and last line segments to
              continue the trend outside the known data.
            """
        )

        # Interpolation settings (inside the tab)
        c1, c2 = st.columns(2)
        with c1:
            method = st.selectbox("Method", ["linear", "nearest"], index=0, key="m1d")
        with c2:
            extrap = st.selectbox("Extrapolation", ["clamp", "linear"], index=0, key="e1d",
                                  help="- **clamp**: outside X range, use boundary Y\n- **linear**: extend end slopes")

        # xi input
        st.markdown("#### Paste xi values")
        xi_text = st.text_area("Paste xi values (newlines/commas/tabs/semicolons OK).",
                               height=140, placeholder="e.g.\n1.0\n2.5\n3.75\n5\n...", key="xi1d")
        xi = parse_float_list(xi_text)
        if xi.size == 0:
            st.info("Paste some xi values to compute interpolated yi.")
            return
    
        # --- Compute button ---
        compute_1d = st.button("Compute yi", type="primary", key="compute1d")
        if not compute_1d:
            st.stop()  # or `return` if you're inside the tab function
    
        yi = interp_linear(x, y, xi, extrap=extrap) if method == "linear" else interp_nearest(x, y, xi, extrap=extrap)
        res = pd.DataFrame({"xi": xi, "yi": yi})

    with st.expander("Results",expanded=True):
        
        c3,c4=st.columns(2)
        
        with c3:
            # Results + export
            st.markdown("#### Results (xi, yi)")
            st.dataframe(res, use_container_width=True)
            csv_buf = io.StringIO(); res.to_csv(csv_buf, index=False)
            st.download_button("⬇️ Download CSV (xi, yi)", data=csv_buf.getvalue().encode("utf-8"),
                               file_name="interpolated_values.csv", mime="text/csv", key="dl1d")
        with c4:
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Base (x,y)", line=dict(width=3)))
            fig.add_trace(go.Scatter(x=res["xi"], y=res["yi"], mode="markers", name="Interpolated (xi, yi)", marker=dict(size=9, color="red")))
            fig.update_layout(xaxis_title=str(col_x), yaxis_title=str(col_y),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                              margin=dict(l=10, r=10, t=10, b=10), height=520)
            st.plotly_chart(fig, use_container_width=True)

def render_tab2():
    st.subheader("2-D Interpolation: (x, y) ➜ z")

    with st.expander("Upload",expanded=True):
        # --- Base data (x,y,z) ---
        left, _ = st.columns(2)
        with left:
            mode = st.radio("Provide base (x,y,z) data via:", ["Upload CSV", "Paste table"], index=0, key="mode2d")
        base2d = pd.DataFrame()
    
        if mode == "Upload CSV":
            f = st.file_uploader("Upload CSV with columns x, y, z (any names; select below)", type=["csv"], key="csv2d")
            if f: base2d = read_csv_smart(f)
        elif mode == "Paste table":
            txt = st.text_area("Paste table (Excel cells OK). Header row recommended.", height=160, key="paste2d")
            if txt.strip(): base2d = read_pasted_table(txt)
    
        if base2d.empty:
            st.info("Load base (x,y,z) data to continue.")
            return
        
    with st.expander("Select columns",expanded=True):
        cols = list(base2d.columns)
        col_x = st.selectbox("X column", cols, index=0, key="x2d")
        col_y = st.selectbox("Y column", cols, index=1 if len(cols) > 1 else 0, key="y2d")
        col_z = st.selectbox("Z column", cols, index=2 if len(cols) > 2 else 0, key="z2d")
        
    with st.expander("Calculation",expanded=True):

        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            method = st.selectbox("Method", ["auto", "linear", "nearest", "regular", "rbf"], index=0,
                                  help="auto: RegularGrid if full grid; else LinearND", key="m2d")
        with c2:
            extrap = st.selectbox("Extrapolation", ["nan", "nearest"], index=0,
                                  help="Outside domain: NaN or nearest value", key="e2d")
        with c3:
            grid_res = st.slider("Plot grid resolution", 30, 150, 60, 10,
                                 help="Higher = slower but smoother heatmap", key="g2d")

        st.markdown(
            """
            **Method overview**

            * `auto` chooses `regular` when the input data form a complete grid
              of X/Y combinations; otherwise it falls back to `linear`.
            * `regular` feeds the data into SciPy's `RegularGridInterpolator`
              for bilinear interpolation on structured grids.
            * `linear` uses `LinearNDInterpolator` which builds simplices
              (triangles) over scattered data and performs linear interpolation
              inside each simplex.
            * `nearest` relies on `NearestNDInterpolator`, returning the value
              from the closest known sample point.
            * `rbf` fits a smooth radial basis function surface (thin plate
              spline kernel) that passes through all sample points and is often
              helpful for smoothly varying data.

            **Extrapolation options**

            * `nan` leaves results outside the convex hull undefined (NaN).
            * `nearest` fills any undefined locations with the value from the
              nearest known sample.
            """
        )

        try:
            f2d, meta = build_forward_interpolator(base2d, col_x, col_y, col_z, method=method, extrap=extrap)
        except Exception as e:
            st.error(f"Could not build interpolator: {e}")
            return
    
        # --- Query points (xi, yi) ---
        st.markdown(f"#### Paste points ({col_x}, {col_y})")
        
        qmode = st.radio("Provide queries via:", ["Paste table", "Upload CSV"], horizontal=True, key="qmode2d")
        qdf = pd.DataFrame()
        
        if qmode == "Paste table":
            qtxt = st.text_area(
                f"Paste two columns ({col_x}, {col_y}). Headers optional.",
                height=140,
                placeholder=f"{col_x}\t{col_y}\n0.0\t0.0\n1.2\t-0.5\n...",
                key="qtxt2d"
            )
            if qtxt.strip():
                qdf = read_pasted_table(qtxt)
        else:
            qfile = st.file_uploader(
                f"Upload CSV with {col_x}, {col_y} (any names; select below)",
                type=["csv"],
                key="qcsv2d"
            )
            if qfile:
                qdf = read_csv_smart(qfile)
    
        if qdf.empty or qdf.shape[1] < 2:
            st.info(f"Provide at least two columns to interpret as {col_x}, {col_y}.")
            return
        
        q_x, q_y = qdf.columns[0], qdf.columns[1]
        # Coerce numeric & drop NA
        Q = qdf[[q_x, q_y]].copy()
        Q[q_x] = pd.to_numeric(Q[q_x], errors="coerce")
        Q[q_y] = pd.to_numeric(Q[q_y], errors="coerce")
        Q = Q.dropna().reset_index(drop=True)
        if Q.empty:
            st.error(f"No valid numeric {col_x}, {col_y} after cleaning.")
            return
        
        XQ = Q[q_x].to_numpy()
        YQ = Q[q_y].to_numpy()
        
        # --- Compute button ---
        compute_2d = st.button("Compute zi", type="primary", key="compute2d")
        if not compute_2d:
            st.stop()  # or `return` if inside the tab function
        
        try:
            ZQ = f2d(XQ, YQ)
        except Exception as e:
            st.error(f"Interpolation failed: {e}")
            return


        out = pd.DataFrame({"xi": XQ, "yi": YQ, "zi": ZQ})

    # Results + export
    with st.expander("Results",expanded=True):
        c6,c7=st.columns(2)
        with c6:
            st.dataframe(out, use_container_width=True)
            buf = io.StringIO(); out.to_csv(buf, index=False)
            st.download_button("⬇️ Download CSV (xi, yi, zi)", data=buf.getvalue().encode("utf-8"),
                               file_name="interpolated_2d.csv", mime="text/csv", key="dl2d")
        with c7:

            # Plot surface heatmap + points
            dclean = dedupe_xy_mean(base2d, col_x, col_y, col_z)
            if dclean.empty:
                st.info("No valid base points to plot.")
                return
            Xmin, Xmax = float(dclean[col_x].min()), float(dclean[col_x].max())
            Ymin, Ymax = float(dclean[col_y].min()), float(dclean[col_y].max())
            GX = np.linspace(Xmin, Xmax, grid_res)
            GY = np.linspace(Ymin, Ymax, grid_res)
            GXm, GYm = np.meshgrid(GX, GY, indexing="xy")
            ZG = f2d(GXm.ravel(), GYm.ravel()).reshape(GYm.shape)
        
            fig = go.Figure()
            fig.add_trace(go.Heatmap(x=GX, y=GY, z=ZG, colorbar=dict(title=str(col_z)), zsmooth=False, showscale=True, name="z(x,y)"))
            fig.add_trace(go.Contour(x=GX, y=GY, z=ZG, contours=dict(showlines=True), showscale=False, line=dict(width=1),
                                     name="contours", hoverinfo="skip"))
            fig.add_trace(go.Scattergl(x=dclean[col_x], y=dclean[col_y], mode="markers", name="base (x,y)",
                                       marker=dict(size=4, opacity=0.5)))
            fig.add_trace(go.Scattergl(x=out["xi"], y=out["yi"], mode="markers", name="queries (xi,yi)",
                                       marker=dict(size=9, symbol="x")))
            fig.update_layout(xaxis_title=str(col_x), yaxis_title=str(col_y),
                              margin=dict(l=10, r=10, t=10, b=10),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                              height=600)
            st.plotly_chart(fig, use_container_width=True)


with tab1:
    render_tab1()

with tab2:
    render_tab2()
