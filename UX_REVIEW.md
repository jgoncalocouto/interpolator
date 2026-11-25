# UX review and improvements

This review applies [the shared analytical-tool UX/UI principles](UX_UI_PRINCIPLES.md)
to Interpolator, with implementation work dated 25 November 2026. It builds on
the earlier heuristic review and preserves the existing parsing, numerical,
query-order, session, and export safeguards. Code inspection and automated
workflow checks support the findings below; they are not a study with
representative users or a claim of full accessibility compliance.

| Finding | Implemented change | Principle |
| --- | --- | --- |
| The opening screen required a file before demonstrating the tool. | Built-in reference data and query examples are ready to calculate. | Recognition over recall |
| Four open accordions and long method explanations buried the task. | Three numbered steps; inputs and results sit together; technical help is collapsed. | Minimalist design and progressive disclosure |
| A 1D `st.stop()` could prevent the 2D interface from rendering. | Both workflows render independently and return locally when data is missing. | User control and consistency |
| Results disappeared on the next interaction. | Results persist in session state, with a signature of the calculation inputs. | Visibility of system status |
| Old results could be mistaken for current results. | Changed inputs show a warning and disable CSV export until recalculation. | Error prevention |
| Query conversion silently discarded invalid values. | Queries are validated as a whole; errors identify the value or data row to fix. | Error recovery |
| Reference cleaning and averaging happened without useful accounting. | Visible excluded-row and duplicate counts, with original and prepared previews. | Visibility of system status |
| Selecting the same column for multiple roles could fail. | Each role offers distinct columns; source-specific selections are remembered. | Error prevention |
| Query columns were used by position without mapping controls. | Every 2D query table offers searchable X/Y column selectors, including pasted two-column tables. | User control |
| Internal labels such as `nan`, `regular`, and `xi` added effort. | Plain method names and outside-data policies; table headings include selected source names. | Match with the user's language |
| Outside policies were ignored or failed for some 2D methods. | Consistent region checks for every method and per-query statuses in the table and CSV. | Consistency and trust |
| Decimal commas were ambiguous and could change meaning with line count. | An explicit 1D decimal-comma checkbox; ordinary commas consistently separate queries. | Error prevention |
| Table interpretation depended entirely on automatic delimiter, decimal, and header guesses. | Source-specific import settings expose column separator, decimal separator, and header presence, with an always-visible interpretation summary. | User control and visibility of system status |
| Grouped numbers could be confused with decimals and change scale. | Thousands grouping requires an explicit choice; original cells and parsed numbers appear together before cleaning or averaging. | Error prevention and recognition over recall |
| A fixed CSV format required users to reformat results for their spreadsheet locale. | Download controls offer column and decimal separators, with a text preview and appropriate CSV/TSV extension. Export choices leave calculations intact. | Flexibility and user control |
| Source changes discarded pasted values, uploads, and mappings. | Text and settings survive hidden widgets; uploaded bytes are retained with an explicit clear control. | User control and recovery |
| The nearest-sample chart appeared to interpolate between values. | A step curve uses actual nearest-sample boundaries. | Accurate system feedback |
| Known samples and requested queries used similar marker shapes. | Square known samples, circular in-region queries, and diamond outside queries distinguish their roles without relying on color. Hover labels carry source names and units. | Analytical honesty and accessible communication |
| The sampled 2D display could be mistaken for additional observations. | The result explains its 55 × 55 derived display grid and states that queries use their exact coordinates. Heatmap smoothing is disabled, including for nearest-sample methods. | Analytical honesty |
| Long horizontal legends and a vertical colorbar consumed narrow chart space. | Legends use a single column below the chart and the surface colorbar sits above the plot. Plot ranges are retained during unrelated result rerenders. | Responsive interaction |
| A large floating coffee button competed with the calculation and could cover controls. | A quiet inline text link has a visible label, keyboard focus outline, and 44 px target. It has no floating overlay or animation. | Hierarchy and accessible controls |
| The full-width reference setup pushed results and the main action below a long wall of controls. | One left-hand surface groups known data and query/method/policy controls; a larger right-hand surface starts results at the same height. Framework columns stack on narrow screens. | Task hierarchy and responsive layout |
| Default colors, spacing, and secondary text varied across the interface. | Supported Streamlit theme settings define the purple active state, pale page, white surfaces, shared radii, and readable text. Small action icons supplement labels; focus outlines and reduced-motion styles support interaction. | Consistency and accessible controls |
| Variable search depended on default framework behavior and two-column query tables had no visible mapping choices. | One reusable component provides labeled search for every reference/query role, including two-column tables. Partial, multi-term, case-insensitive, and accent-insensitive matching leaves names and selections intact. Keyboard navigation and a visible empty-search message are included. | Searchable selectors and error prevention |
| Original-versus-parsed previews dominated the main workflow. | The first-five-row comparison is collapsed on demand while the interpretation summary, exclusions, and duplicate handling remain visible. | Progressive disclosure and analytical honesty |
| A replacement upload with the same prepared values could leave a previous result looking current. | Calculation freshness includes original source contents, filename, parsing options, mappings, queries, method, and policy. Previous results identify their saved source and mappings and keep downloads disabled until recalculation. | Trustworthy result provenance |
| Cosmetic interactions repeatedly parsed data and serialized full exports. | Session-local caches retain the latest parsed/prepared data for each workflow and one export buffer per result; dependency changes invalidate the relevant cache without accumulating result history. | Responsive interaction and bounded memory |
| Session retention could be mistaken for saved settings or browser-only processing. | The footer and Session & privacy disclosure identify Streamlit server processing, session-limited retention, explicit upload clearing, and the absence of a portable saved setup. | Accurate privacy and recovery communication |

## Validation and limits

- Numerical tests cover parsing, cleaning, duplicate means, invalid geometry,
  known interpolation values, and outside policies for every 2D method.
  Format checks cover explicit delimiters, decimal and thousands separators,
  header overrides, and CSV serialization.
- Streamlit AppTest checks independent workflows, result persistence, stale
  downloads, invalid queries, mapping, decimal modes, source switching, import
  interpretation previews, and export settings.
- Source-provenance checks cover replacement files with equal prepared values
  for reference and query uploads, and changed original cell spellings. A 2,501-query workflow checks that order,
  duplicate queries, precision, all chart query markers, and full export rows are
  preserved; limited previews do not cap the calculation.
- The numeric preview shows only the first five data rows. Later invalid
  reference rows are counted and available in the original-table preview;
  invalid query rows block calculation. Automatic format detection can still be
  ambiguous, so users should verify the displayed interpretation and scale or
  select explicit settings. Thousands grouping is never inferred.
- Table import controls apply to reference tables and 2D query tables. The 1D
  query list uses its separate decimal-comma option and expects ungrouped values.
- Upload tests cover real uploaded-file objects, retained byte records, and
  direct file-widget input when supported by the installed Streamlit testing
  API. The operating-system file chooser remains a manual check.
- Chart-focused tests verify unsmoothed nearest-sample surfaces, exact query
  coordinates, known-sample payloads, display-grid disclosure, and explanations
  for blank 1D markers. The same tests preserve method, outside-region, and
  chart-failure recovery contracts.
- Initial UI-review verification on 25 November 2026 passed all 140 Python tests and seven Node
  tests, with 96.3% combined statement-and-branch coverage. Picker tests cover
  matching, registered callbacks, simulated keyboard/focus behavior, listener
  cleanup, and popup geometry within a 390 px viewport. These simulated checks
  do not establish actual browser rendering or assistive-technology behavior.
- A 50,000-row 1D reference workload measured parsing, preparation, and input
  hashing at 2.030 s cold and 0.0109 s with valid session caches on this machine.
  This excludes calculation, chart rendering, browser interaction, and export;
  it is a scoped measurement rather than an end-to-end performance guarantee.
- Browser inspection was blocked: the browser access host was unavailable, and
  native Chrome screenshot/input attempts failed with "foreground window did
  not report a process id." The running Streamlit server passed its HTTP health
  check. Desktop/mobile pixels, real keyboard focus after rerenders, chart
  hover/zoom, screen readers, and browser downloads remain unverified.
- Opening each export format in the spreadsheet applications and locales used
  by the intended audience also needs manual validation.
- The later Tips & tricks tab adds an independent 1D Excel formula generator.
  Tests evaluate its emitted expressions and exercise range validation and app
  state. Native Excel calculation, formula clipboard behavior, and localized
  installations remain unverified. See TESTING.md for the current suite results.
- A useful next validation is to watch a few representative users import their
  own data, identify an outside-data query, and export a result without assistance.
