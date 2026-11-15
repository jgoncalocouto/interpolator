# Interpolator

A Streamlit tool for estimating Y from X, or Z from X and Y. Upload a CSV,
paste spreadsheet cells, or try the built-in examples.

## Run locally

Use Python 3.10 or later. From the project directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run main.py
```

Open the local URL printed by Streamlit. On macOS/Linux, use
`.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

## Workflow

1. **Add known data.** Choose an example, upload a CSV, or paste a table.
   Map different columns to the input and output roles, and review the prepared data.
2. **Choose what to estimate.** Enter query values or coordinate pairs, select a
   method and an outside-data policy, then select **Calculate values**.
3. **Inspect results.** Review the chart and status of every query, then download
   the results as CSV. Exports keep the original query order, duplicate queries,
   and full numeric precision (`xi, yi, status` or `xi, yi, zi, status`).

Results stay available across interactions. Changing calculation inputs marks
the previous results and disables their download until you calculate again.
Pasted text, column selections, uploaded files, and results are retained within
the active Streamlit session. A browser refresh or server restart can reset that
session; download results you want to keep. Use **Clear uploaded file** to remove
a retained upload from the current session.

## Input formats

- Tables accept comma, semicolon, tab, or whitespace separators and an optional
  header row. Each row must have the same number of columns. CSV uploads support
  UTF-8 (including BOM) and Windows-1252 text.
- For decimal commas in tables, use tabs or semicolons between columns:
  `0,5;12,5`. Comma-separated tables use commas as column separators.
- A 1D query list accepts newlines, commas, spaces, tabs, or semicolons.
  Commas separate values by default, so `1,2` means two queries.
  Enable **Use decimal commas** to interpret `1,2` as `1.2`; separate those
  values with whitespace or semicolons.
- Reference rows containing missing, nonnumeric, or infinite selected values are
  excluded with a visible count. Repeated reference X values (1D), or X/Y pairs
  (2D), are averaged and reported. Invalid query rows block the whole calculation
  so no query is silently discarded.
- 1D needs at least two distinct X values. 2D needs at least three distinct
  coordinate pairs forming an area; use 1D when the points lie on a line.

## Methods and outside-data behavior

1D supports linear and nearest-sample interpolation. Outside the measured X
range, leave results blank, keep the boundary value, or extend end slopes
(linear interpolation only).

2D supports automatic, scattered linear, nearest sample, bilinear grid, and
smooth RBF interpolation. Automatic uses bilinear interpolation when every X/Y
combination is present and scattered linear otherwise. All 2D methods apply the
selected outside policy consistently: leave blank or use the nearest sample.
The known region is the convex hull of the reference coordinates, which may be
smaller than the rectangle defined by the individual axis ranges. Distances for
nearest samples use the supplied coordinate units; the RBF fit scales its axes.

Outside-data results have explicit statuses in the table and CSV. Blank is the
default because extending beyond known data requires an additional assumption.

## Verify changes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers parsing, known numerical results, outside-data policies, and
Streamlit workflows. AppTest upload checks seed the cached file record because
the testing API does not interact with the browser's file chooser.

See [UX_REVIEW.md](UX_REVIEW.md) for review findings, design decisions, and
remaining validation work.
