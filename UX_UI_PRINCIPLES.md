# Shared UX/UI principles for analytical tools

Reference application: TSPlotter. Prepared 25 November 2026.

Use this standalone guide when improving Interpolator or another analytical
application. It captures the design decisions used in TSPlotter and explains
how to transfer them without losing the receiving application's workflow or
numerical safeguards. It is a design brief, not a requirement to adopt
TSPlotter's framework, libraries, feature count, or browser-only architecture.

**Priority order:** trustworthy results, clear workflow, responsive interaction,
accessible controls, then visual polish. The behavioral rules below are the
baseline; visual tokens are starting values to adapt and verify.

## 1. Organize the screen around the user's task

Keep the working sequence obvious: **bring data → choose an operation → inspect
results → export**. Use the application's own verbs: TSPlotter says **Update
chart**; Interpolator says **Calculate values**.

| Area | Purpose | Rule |
| --- | --- | --- |
| Header | App identity and current activity | One clear title and concise status; keep decoration secondary. |
| Context area | Data source, shared setup, reusable settings | Use a sidebar when these controls genuinely apply across the workspace. |
| Main controls | Choices needed for the next calculation | Keep common choices visible and near the primary action. |
| Results | Chart, table, counts, interpretation | Give results the largest useful area and identify the inputs they represent. |
| Result actions | Download data or image | Place actions beside the result they export and name their scope. |
| Supporting tools | Import details, appearance, previews, technical help | Expand on demand; keep essential validity information visible. |

Preserve separate modes when they answer different questions. Unify duplicate
screens when a setting can express the difference. Avoid adding a second
navigation hierarchy for the same task.

## 2. Reduce clutter through hierarchy and disclosure

- Use one visually dominant action per calculation workflow. Secondary actions
  use outlined buttons; minor actions use quieter text buttons.
- Group related fields under short, descriptive headings. Prefer a few coherent
  groups over a card around every field.
- Reveal dependent controls when relevant: grouping bins after choosing a group,
  custom parsing after choosing a custom format, method options after the method.
- Put detailed formulas, formatting overrides, and appearance controls in
  expandable sections. Keep the selected method, interpretation summary,
  important limitations, and current errors visible.
- Show only useful counts. Every summary number must help explain the data,
  calculation, or result; avoid decorative dashboard metrics.
- Keep support/donation links secondary to the working interface.

## 3. Use a restrained, consistent visual system

These are the actual TSPlotter starting tokens. Reuse them through shared theme
variables instead of scattering slightly different colors and sizes throughout
the application.

| Role | TSPlotter baseline |
| --- | --- |
| Typeface | Inter, followed by system sans-serif fallbacks |
| Base text | 14 px |
| Page background | `#f6f7fb` |
| Surface/card background | `#ffffff` |
| Default control background | `#fafbfe` |
| Main text | `#252b3b` |
| Secondary text | `#737b90` |
| Dividers/borders | `#e5e7ee` |
| Primary action / active state | `#6251c6` |
| Soft active background | `#f0edff` |
| Card radius | 10 px |
| Control radius | 7 px |
| Normal control height | Approximately 40 px |
| Desktop sidebar | Approximately 274 px |

Use consistent spacing, aligned field edges, subtle borders, and restrained
shadows. Make titles more prominent through size and weight, rather than adding
many accent colors. Use small line icons alongside action labels.

Treat the palette as a visual reference, not proof of accessibility compliance.
Check contrast at the actual text size and on every background. Essential labels
and numerical values must remain readable; do not copy tiny metadata text into
important instructions. Provide comfortable touch targets on phones.

## 4. Make every variable selector searchable

Apply the same searchable control to every dataset-variable choice: input/output
roles, X/Y/Z mappings, time columns, groups, signals, and filter columns.

- Opening the picker exposes a clearly labeled search field. Typing filters
  labels without changing the underlying selection or source names.
- Match partial names without case sensitivity; support multiple search terms
  and accent-insensitive matching while preserving the original labels.
- A single selection replaces the previous value and closes the popup. Required
  choices have no accidental clear action. Optional roles offer explicit
  **(none)** where that choice is valid.
- Multiple selections stay open while choosing items. Show removable chips and
  an overflow count; provide **Clear selection**.
- An empty search result says so and preserves existing choices.
- Keep the search field visible when scrolling the option list.
- Support keyboard opening, arrow navigation, Enter, Escape, and visible focus.
  Restore focus to the visible trigger when a choice rebuilds dependent fields.

Use ordinary dropdowns for short, fixed settings such as scale or method unless
they also need search. Reuse one picker implementation so new fields cannot
silently lose search or keyboard behavior.

## 5. Make edits, results, and saved settings distinct

The user must be able to answer: **What did I edit? What produced these results?
Have I saved my setup?**

| State | Expected behavior |
| --- | --- |
| No usable input yet | Explain the next step and offer an example where possible. |
| Inputs edited | Mark results as needing an update; retain useful work where safe. |
| Calculating | Name the current activity, prevent conflicting submissions, and support cancellation when practical. |
| Results current | Show results, relevant counts, and enabled scoped exports. |
| Invalid input or failure | Explain what to fix; preserve user input and allow recovery. |
| Configuration unsaved | Show a separate settings indicator, independent of calculation freshness. |

Disable result exports when calculation inputs have changed. Never present a
previous dataset's results as belonging to a newly selected source. Formatting
choices that do not alter calculation values should not force recalculation.

Preview, statistics, and other independent tools should depend on their own
required inputs, rather than being blocked by unrelated unfinished chart fields.
If cancellation clears a dataset or requires reopening a file, explain that
recovery step explicitly.

## 6. Keep repeated analyses consistent and independent

Where multiple analyses are useful, give them the same **Add**, **Duplicate**,
**Remove**, title, and **Edit settings** pattern. Keep one selected editor instead
of displaying every instance's full settings simultaneously.

Duplicating creates independent settings. Removing or editing one analysis must
preserve the others. Put data/image exports on their owning result. Make shared
filters or settings visibly shared; keep local settings with their analysis.

Link chart ranges only when variables, scales, and units are compatible. Keep
series and category colors stable across filtering and reordering. This pattern
is optional capability, not a requirement to add multiple instances to every app.

## 7. Treat analytical honesty as a UI requirement

- Show how imported data was interpreted, especially ambiguous numeric formats.
  Put original values and prepared values close enough to compare.
- Report exclusions, invalid values, duplicates, and transformations separately
  when they affect interpretation. Never silently change numeric scale or query
  meaning to make an import succeed.
- Clearly label limited previews. Preview pagination must not limit calculations
  or full exports.
- TSPlotter deliberately retains all observations. Preserve this choice; improve
  expensive searches, rendering, and memory use instead of introducing hidden
  point caps or downsampling.
- For an interpolation tool, distinguish measured inputs, interpolated values,
  extrapolated values, and display grids. A surface drawn on a grid is a derived
  visualization, not additional measured data; identify its resolution when it
  affects interpretation.
- Make chart geometry match the selected method. A nearest-sample result should
  not appear to be a smooth interpolation.
- Keep labels, units, legends, row counts, query statuses, and CSV output
  consistent. Display rounding must not reduce exported numeric precision.

## 8. Make speed and memory part of the design

Measure with realistic files and actual actions: opening data, changing inputs,
calculating, hovering, zooming, panning, opening statistics, and exporting.
Separate data preparation, calculation, rendering, and interaction costs.

Keep simple edits and chart exploration independent from expensive calculation.
Reuse data and valid intermediate results when inputs have not changed. Invalidate
caches when their source, parsing, filters, method, or other dependencies change.
Do not accumulate an unlimited history of large cached arrays.

Batch or stream large work, keep long tasks off the interaction path where the
framework supports it, and release obsolete chart resources. Progress messages
must reflect real work. Cancellation or a newer request must prevent an older
calculation from replacing the current result.

Preserve zoom, selections, and valid inputs during unrelated edits. A responsive
interface should not repeatedly rebuild the entire working area for cosmetic
changes. Establish performance budgets for the receiving app after measuring it;
TSPlotter's timings are not a guarantee for another workload or machine.

## 9. Design errors and recovery as normal workflow

Explain the problem, its location, and the next useful action. Prefer
**“Query row 12 has a nonnumeric X value. Correct it and calculate again.”** over
an exception name or stack trace.

Distinguish an empty result from an invalid configuration and a failed operation.
Keep the user's draft available to correct. Validate before expensive work and
before exporting misleading output. Avoid confirmation dialogs for routine,
reversible edits; reserve them for actions with meaningful loss or consequences.

If portable settings are offered, version and validate them, explain missing
column mappings, and keep the last valid setup when loading fails. Store reusable
preferences separately from dataset contents. Local recovery and server-session
retention are different mechanisms and must be described accurately.

## 10. Support keyboards and narrow screens deliberately

Use real labels, logical focus order, semantic controls, visible focus indicators,
and readable status messages. Icons and color supplement text; they must not be
the only way to identify an action, series, or error. Honor reduced-motion choices.

On desktop, keep the primary working area useful without a long wall of setup
controls. On mobile, turn a sidebar into an explicit drawer, stack result cards,
and let wide tables scroll within their containers rather than widening the page.

At a 390 px viewport, fields, search popups, chart tools, and primary actions must
fit and remain reachable. Opening a drawer moves focus inside and prevents
interaction behind it; closing returns focus to its trigger. Escape closes the
innermost popup before closing the drawer. Preserve useful work across resizing.

## 11. Apply the approach to Interpolator

This mapping is based on the local Interpolator README and UX review, not a new
audit of its live deployment.

| Preserve | Apply from TSPlotter |
| --- | --- |
| Independent 1D and 2D modes | Focused tabs with consistent controls; missing data in one mode must not block the other. |
| Known data → query/method/policy → results | Make the three steps visually clear and keep **Calculate values** near the query controls. |
| Reference and query column mappings | Use searchable X/Y/Z role selectors with visible selected source names. |
| Import interpretation and numeric previews | Keep the interpretation summary and original-versus-parsed comparison; collapse detailed overrides. |
| Excluded-row and duplicate handling | Keep counts and the existing calculation rules visible and numerically unchanged. |
| Outside-data policies | Show the chosen policy near the method and preserve per-query statuses in tables and exports. |
| Persistent results with stale-download protection | Keep that state model; make freshness and recovery clear in the shared visual language. |
| Locale-aware CSV/TSV and format preview | Keep format controls beside downloads; changing output formatting preserves calculated values. |

In particular, preserve query order, duplicate queries, full numeric precision,
invalid-query validation, and existing handling of duplicate reference points.
Distinguish known-data markers, estimated curves/surfaces, and requested query
points with labels and more than color alone.

Keep truly shared settings in a sidebar if useful. Data and settings belonging
only to one mode should stay with that mode. Do not force TSPlotter's global
dataset model or six-panel limits onto Interpolator.

Interpolator currently uses Streamlit and server-side processing. That is a valid
implementation choice. A UI improvement does not require a JavaScript migration
and does not justify claiming that uploaded files stay on the user's device.
Describe actual upload/session behavior and preserve the explicit clear-upload
control. Prefer supported framework theming and components over fragile DOM hacks.

## 12. Review the result against observable outcomes

- [ ] A first-time user can load an example, complete the core task, and export
      without reading the implementation notes.
- [ ] Common controls and the primary action are easy to find; advanced detail
      is available without dominating the screen.
- [ ] Every variable picker, including dynamically added fields, supports search.
- [ ] Changed inputs, current results, and saved settings are distinguishable;
      stale result exports are blocked.
- [ ] Import interpretation, exclusions, method behavior, and outside-data
      statuses remain correct in both the UI and exports.
- [ ] Empty, invalid, busy, cancelled, and recoverable-error states are understandable.
- [ ] Switching modes, editing settings, resizing, and changing output format
      preserve the appropriate inputs and results.
- [ ] Keyboard-only use, focus after rerenders, and nested Escape behavior work.
- [ ] Desktop and 390 px mobile layouts have readable results, reachable actions,
      and no horizontal page overflow; popups and legends do not obscure controls.
- [ ] Typical and large workloads remain responsive without silent data reduction.
- [ ] Privacy, processing location, settings recovery, and session retention copy
      match the receiving application's actual behavior.

Use targeted numerical/workflow checks plus visual and keyboard inspection for
the changed behavior. Separate what was actually verified from what still needs
review; screenshots or passing unit tests alone do not establish full usability
or accessibility compliance.

## Implementation brief to share with another developer or agent

> Use this guide to improve Interpolator's UI. First inspect its current workflow
> and preserve its calculation, parsing, validation, query-order, precision,
> session, and export behavior. Apply the visual hierarchy, shared tokens,
> searchable variable selectors, clear result states, responsive layout, and
> recovery patterns. Keep the independent 1D/2D modes and their three-step flow.
> Adapt the patterns to the existing framework; treat any technology migration
> or new analytical features as a separate decision. Verify the changed workflows
> on desktop, mobile, and keyboard, and report any unverified limitations.

## Reference implementation in TSPlotter

These files are optional examples when the TSPlotter repository is available;
the guide above can be copied on its own.

- [Visual tokens and responsive layout](src/style.css)
- [Workspace, actions, state, and messages](src/main.js)
- [Searchable single- and multiple-variable pickers](src/pickers.js)
- [Portable configuration](src/config.js) and [device recovery](src/workspace-recovery.js)
- [Behavioral acceptance criteria](tests/PARITY.md), [visual/keyboard checks](tests/browser-ui.mjs),
  and [variable-picker workflows](tests/browser-variable-pickers.mjs)
