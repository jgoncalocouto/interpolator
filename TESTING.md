# Tests and feature coverage

The suite combines numerical expectations, parser and export contracts,
Streamlit interaction tests, and checks of the generated chart, column picker,
and support-link content. Tests use in-memory datasets, including a 2,501-query
batch that guards against hidden result caps. They do not contact payment services
or need a running browser or Streamlit server.

## Run the suite

From the project directory, after creating the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/column_picker.test.mjs
```

The JavaScript tests use Node's built-in test runner and require no npm
packages. They check case- and accent-insensitive matching, multiple search terms,
original labels, source order, viewport placement, and keyboard/focus event
handling against a small simulated DOM. They do not render browser pixels.

Measure coverage and enforce the configured minimum:

```powershell
.\.venv\Scripts\python.exe -m coverage run -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m coverage html
```

Open `htmlcov/index.html` for the source report. Coverage includes statements
and branches in `main.py`, `interpolation.py`, `coffee_widget.py`, and
`column_picker.py`, with a 90% minimum. Generated reports are ignored by Git. Coverage is a regression
guard; the numerical assertions and workflow checks establish the behavior.

Verified on 25 November 2026 with the local Python 3.13 environment: all 140
Python tests and all seven Node tests passed. Combined statement-and-branch
coverage was 96.3%, above the 90% gate. These results cover the automated
contracts above; the browser checks below remain separate.

On macOS/Linux, use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe`.

## Feature map

| Feature | Automated checks | Tests |
| --- | --- | --- |
| CSV uploads and pasted tables | Optional headers, duplicate names, quoted separators, consistent row widths, empty cells, encodings, and file streams | `test_interpolation.py`, `test_core_features.py` |
| Import formats | Automatic and explicit column/decimal separators, valid and invalid thousands grouping, scientific notation, header overrides, and ambiguous-format feedback | `test_interpolation.py`, `test_core_features.py`, `test_app.py`, `test_app_features.py` |
| Data preparation | Finite values, excluded-row counts, sorting, duplicate X/X-Y means, retained original strings, and repeated numeric conversion | `test_interpolation.py`, `test_core_features.py`, `test_app.py` |
| Number previews | Original versus parsed values, first five rows before cleaning, query order, and independent source settings | `test_app.py`, `test_app_features.py` |
| 1D calculations | Linear and nearest methods, exact samples, nearest ties, boundaries, scalar/array shapes, and every outside-range policy | `test_interpolation.py`, `test_core_features.py`, `test_app_features.py` |
| 2D calculations | Automatic/grid/scattered/nearest/RBF methods, analytical results, non-affine bilinear values, sample recovery, hull boundaries, and invalid geometry | `test_interpolation.py`, `test_core_features.py`, `test_app_features.py` |
| Query validation and mapping | Whole-batch rejection, nonfinite values, distinct source columns, additional query columns, order, and duplicate queries | `test_interpolation.py`, `test_app.py`, `test_app_features.py` |
| Searchable column pickers | Required values, repaired mappings, registered selection callbacks, original labels, case/accent folding, all-term matching, viewport geometry, and simulated keyboard/focus events | `test_column_picker.py`, `column_picker.test.mjs` |
| Result state | Independent workflows, persistence, changed-input warnings, disabled stale downloads, recalculation, and error recovery | `test_app.py`, `test_app_features.py` |
| Source identity and caching | File-name/raw-cell changes invalidate old exports; export-format changes reuse parsed/prepared inputs; full query batches retain order, duplicates, precision, and chart/export rows | `test_ux_workflows.py` |
| Upload retention | Uploaded file objects, retained bytes, source switching, replacement, and explicit clearing | `test_presentation.py`, `test_app.py`, `test_app_features.py` |
| Charts and statuses | Nearest steps, reference/query coordinates, known-region blanks, outside-result labels, and table preservation if plotting fails | `test_presentation.py`, `test_app.py`, `test_app_features.py` |
| Example data | Usable example workflows and downloadable example contents | `test_app.py`, `test_app_features.py` |
| CSV/TSV downloads | Every offered separator/decimal combination, quoting, Unicode/BOM, precision, missing values, statuses, filenames, MIME types, and unchanged numerical results when export settings change | `test_interpolation.py`, `test_core_features.py`, `test_app.py`, `test_app_features.py` |
| Coffee support widget | Default/custom link and title, escaped attribute content, and safe new-tab attributes | `test_presentation.py` |

All test paths above are under `tests/`. `app_test_support.py` contains common
fixtures and assertions without test methods, so sharing setup does not run
existing tests a second time.

## Continuous integration

`.github/workflows/tests.yml` runs the Python suite and coverage gate plus the
Node column-picker tests on pushes, pull requests, and manual workflow runs.
Its matrix covers Python 3.10 and 3.13 on Linux, plus Python 3.13 on Windows. Coverage XML and HTML reports
are uploaded as workflow artifacts, including on failures when reports can be
generated. The workflow will run after it is published to GitHub.

## Browser checks still required

AppTest exercises Streamlit state and controls without rendering browser
pixels. It does not execute the custom column picker's JavaScript. The shared
fixture changes the same scalar column-mapping state used by the workflow;
separate Python tests exercise picker selection callbacks and Node tests exercise
search, geometry, and keyboard/focus handlers in a simulated DOM. Real popup
positioning, focus, keyboard navigation, and assistive technology behavior require
browser checks.

Upload tests use real uploaded-file objects at the handler boundary,
cached records for portable workflow coverage, and direct file-widget input
when the installed Streamlit testing API supports it. Only that API-specific
check is skipped on older versions. Tests do not operate an operating-system
file chooser.

Before a release, manually check:

1. Both workflows on desktop and at a 390 px viewport: no horizontal page
   overflow, readable results, reachable actions, and tables scrolling within
   their containers. The support link belongs in the footer.
2. Every reference and query column picker: labeled search, case/accent and
   multiple-term matching, no-match recovery, Arrow keys, Enter, Escape, visible
   focus, focus after dependent mappings rerender, and popup placement while
   scrolling or using a phone keyboard.
3. A real CSV upload, replacement and clearing, then a browser download opened
   in the target spreadsheet application with point and comma decimal settings.
4. Chart hover/zoom behavior, preservation of zoom after format-only edits,
   marker shapes, 55 × 55 derived-grid disclosure, and outside-data/blank results.

No automated coverage percentage establishes accessibility, screen-reader
behavior, responsive layout, or compatibility with every spreadsheet locale.
