# RHYTHMOS Visual Design System

> Scope: visual design, UI craft, interaction, and motion for the existing
> Streamlit application. This document does not change product architecture,
> recovery logic, database schema, information architecture, or data ingestion.
> Status: Phase 2 visual-direction specification.
> Reviewed: 2026-08-07.

## 1. Visual direction

RHYTHMOS should feel calm, precise, scientific, premium, modern, focused,
personal, and trustworthy. It should feel like one carefully crafted software
product rather than a collection of Streamlit pages with local styling.

The visual character comes from restraint:

- Let hierarchy come first from typography, whitespace, and alignment.
- Use surfaces only to establish meaningful levels, not to frame every item.
- Keep one muted blue-green accent for interactive orientation; reserve semantic
  colors for actual state.
- Make numbers stable, aligned, and quietly prominent.
- Prefer flat, lightly separated surfaces over gradients, glow, glass effects,
  thick shadows, or a permanent grid of cards.
- Keep frequently used UI mostly static. Motion confirms an explicit action; it
  does not decorate physiological data.

Do not imitate Apple Health, WHOOP, Oura, Garmin, or Linear. Their lesson is
craft and restraint, not their visual identity.

## 2. Current visual/UI audit

| Area | Current behavior | Why it feels visually weak or inconsistent | Recommended treatment |
| --- | --- | --- | --- |
| Typography | Shared headings are large (`2.75rem` page title), while page CSS introduces many independent title, label, and value sizes. | Type scale and weights vary by domain; Chinese, English, metadata, and numeric hierarchy do not read as one system. | Adopt the restrained scale in section 5 and use it through shared CSS before page-local exceptions. |
| Page width and top spacing | Shared shell gives pages only `.5rem` top padding and forces a `21rem` desktop sidebar. | The page starts abruptly while the sidebar can dominate the visible canvas. | Use a deliberate top rhythm and a narrower, stable navigation rail; cap main reading width without making data views cramped. |
| Background and surfaces | Recovery/training cards use white-to-blue gradients and shadows; Sleep uses white cards; Nutrition mixes theme variables and stronger shadows. | A user sees several visual products, not one RHYTHMOS surface hierarchy. | Use one app canvas, one standard surface, and one optional elevated surface. Remove decorative gradients. |
| Cards | Fixed card heights range from compact 4.35rem nutrition cards to 250px sleep cards and 22–25rem recovery cards. | Equal borders and large heights make every metric appear equally important and create empty, dashboard-like density. | Use content-led height, a three-level card hierarchy, and fewer simultaneous cards. |
| Borders, radii, shadows | Current radii span 8, 10, 14, 16, 20, 24, and pill shapes; borders and shadows differ by page. | The visual language feels accumulated rather than intentional. | Limit normal radii to 6, 10, and 14px; use one thin neutral border and one restrained elevation level. |
| Numeric presentation | Strong values exist, but units, deltas, labels, and baseline evidence use different alignment and weight patterns. | Scanning is slowed when numbers lack a stable typographic rhythm. | Use tabular figures, a fixed label/value/meta order, attached units, and a single delta convention. |
| Sidebar/navigation | The rail uses large branded text, a language selector, and emoji page links. | Emoji are visually uneven across platforms and make a serious performance product feel less precise. | Use a compact wordmark, quiet positioning copy, and consistent 16px monochrome icons or text-first navigation. |
| Buttons and forms | Streamlit controls are widely used with page-specific centering overrides and hidden steppers/clear affordances. | Controls inherit mixed default geometry and can look like a form tool rather than part of a product. | Standardize control height, label spacing, focus ring, primary/secondary/destructive roles, and inline validation. |
| Tabs and expanders | Native tabs and many expanders form the principal disclosure pattern. | They are useful, but default styling and repeated expansion boundaries can fragment visual rhythm. | Style tab underline and disclosure rows consistently; use expanders for evidence/history, not as arbitrary containers. |
| Tables | Some pages use Streamlit dataframes; others render custom centered HTML tables with 3.5rem rows and `nowrap`. | Header/cell behavior, alignment, density, and responsive behavior differ substantially. | Establish one table system: semantic numeric alignment, compact 44px rows, restrained dividers, horizontal scrolling only inside the evidence layer. |
| Charts | Sleep uses custom SVG/Plotly with hard-coded white backgrounds; other charts retain near-default Streamlit/Plotly treatment. | Charts look embedded rather than native and differ in line, marker, grid, and legend language. | Apply the chart language in section 8 to every Plotly and inline SVG figure. |
| Status feedback | Success, warning, error, and info depend heavily on native Streamlit alert banners. | Native banners are visually louder than the content hierarchy and create inconsistent tone across pages. | Use native alerts for critical operational feedback; use compact inline status rows for ordinary data state. |
| Empty/loading states | Empty states are generally `st.info`; loading is mostly a spinner for explicit work. | Safe but generic: the user often sees a framework alert rather than a RHYTHMOS explanation. | Give each empty/degraded state a short explanation and one next step; keep spinner use only for active operations. |
| Responsive behavior | Some page CSS has breakpoints, but card grid, tables, fixed heights, and custom markup vary independently. | Narrow layouts can become tall, wrapped, or horizontally constrained in different ways. | Define one breakpoint policy and test at 320px, 736px, and ordinary desktop width. |

## 3. Background, surface, border, radius, and spacing system

### Background hierarchy

1. **App canvas** — a very light cool neutral in light mode; near-black blue
   neutral in dark mode. It provides calm separation, not decoration.
2. **Standard surface** — the normal background for cards, forms, tables, and
   charts. It is opaque and near the canvas, never translucent glass.
3. **Raised surface** — reserved for a modal, primary contextual panel, or a
   selected/active container. It must not be the default card treatment.
4. **Inset surface** — a subtle fill for read-only cells, grouped controls, or
   an internal data strip. Do not use it around every paragraph.

### Surface and card hierarchy

| Level | Use | Treatment |
| --- | --- | --- |
| L0 — no surface | Page headings, explanatory copy, chart captions, simple status rows | Canvas only; hierarchy through space and type. |
| L1 — standard surface | Forms, tables, ordinary grouped evidence, interactive containers | Opaque surface, 1px neutral border, 10px radius, no shadow. |
| L2 — emphasis surface | A primary summary, selected data group, or contextual action | Opaque surface, 1px stronger border or very faint shadow, 14px radius. One or two maximum in a viewport. |
| L3 — overlay | Dialog, popover, blocking confirmation | Raised surface, clear focus, restrained elevation. |

### Border and shadow philosophy

- Prefer spacing before borders; never box every sibling.
- Standard border: 1px low-contrast neutral. Do not use multiple nested borders
  to create hierarchy.
- Elevated shadow: one soft, low-opacity layer such as `0 1px 2px` plus a
  small ambient shadow. Remove the current broad card shadows and all glows.
- A left rule may denote one contextual status or plan item; do not use it as a
  generic decorative accent.

### Radius system

- `6px` — small inputs, compact cells, status markers.
- `10px` — standard controls and surfaces.
- `14px` — emphasis panels and dialogs.
- `999px` — only compact tags or progress/range tracks; never use pills as the
  default shape for controls and cards.

### Spacing rhythm

Use a 4px base scale: `4, 8, 12, 16, 24, 32, 48`.

- Label to value: 4–6px.
- Value to supporting evidence: 8px.
- Related controls within one group: 8–12px.
- Section heading to content: 16px.
- Section to section: 32px; use 48px only between page-level chapters.
- Main page top: 24px desktop, 16px narrow screens; avoid the current near-zero
  top padding.
- Main content: cap ordinary reading/card layouts at roughly 1180–1240px;
  full-width tables and dense planners may opt out deliberately.

## 4. Color system

### Base palette roles

Use semantic roles rather than page-specific hex values.

| Role | Intent |
| --- | --- |
| `ink` | Primary text; cool near-black, never pure black. |
| `text-secondary` | Supporting evidence and body copy. |
| `text-tertiary` | Metadata, units, table captions, timestamps; maintain readable contrast. |
| `canvas` / `surface` / `inset` | Background hierarchy from section 3. |
| `border-subtle` / `border-strong` | Quiet separation and selected/emphasis separation. |
| `accent` | Muted blue-green for focus, selected navigation, primary action, and chart current point. |
| `positive` | Calm green for supportive/completed states. |
| `caution` | Muted ochre for incomplete, building, or attention states. |
| `negative` | Restrained red only for invalid, destructive, or failed states. |
| `info` | Desaturated blue for neutral system information. |

### Color rules

- Accent is for orientation and explicit action, not decoration.
- A card's entire fill must not change merely because a metric is positive or
  negative; use a small text/rule/status treatment plus a written label.
- Keep purple, yellow, red, green, and blue from becoming a default set of
  peer metric colors.
- Every semantic state needs text, and may use icon/shape plus color.
- Support light and dark appearance through semantic variables; remove hard
  coded white card backgrounds and white Plotly `plot_bgcolor` from shared
  visual treatment.

## 5. Typography and numeric system

### Font stack

Use the platform-native interface stack first, with explicit Chinese fallbacks:

`ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "PingFang TC", "Microsoft YaHei", "Segoe UI", sans-serif`

Do not add a display font. RHYTHMOS should feel native, calm, and legible in
Simplified Chinese, Traditional Chinese, and English.

### Type scale

| Role | Desktop size / line height | Use |
| --- | --- | --- |
| Page title | 32px / 40px, 650 | One title per page. Reduce from the current oversized 2.75rem default. |
| Section title | 20px / 28px, 600 | Major page chapters. |
| Component title | 16px / 24px, 600 | Card, chart, form, and table titles. |
| Body | 14px / 21px, 400 | Explanations, prose, long labels. |
| Label | 12px / 16px, 500 | Metric labels, field labels, table metadata. |
| Caption | 12px / 18px, 400 | Source, freshness, safety, and supporting notes. |
| Metric value | 28px / 32px, 650 | Standard key number. |
| Emphasis value | 36px / 40px, 650 | One primary value only. |

At narrow width, reduce page title to 28px and emphasis value to 32px rather
than scaling all text down.

### Numeric rules

- Apply `font-variant-numeric: tabular-nums` to values, deltas, dates, table
  numerics, and chart labels.
- Keep value, sign, decimal, and unit together: `+4.2%`, `52 ms`, `56 bpm`.
- Use the existing locale formatter; do not hard-code number punctuation.
- Put units in secondary text weight/colour only when their separation remains
  unambiguous. Never leave a unit on a line by itself.
- Align table numbers to the end of their column; do not center every datum by
  default. Center only controls, compact categorical codes, and deliberate
  calendar cells.
- Use a single delta treatment: arrow or signed number followed by concise
  baseline context. Do not use both as competing decoration.

## 6. Component craft and state treatment

### Universal interaction rules

- Interactions should feel immediate: 100–160ms colour/border transitions are
  sufficient. The shared card-inspection response below is the deliberate
  exception: a restrained 180ms, 1px lift that applies consistently to
  first-party information cards.
- `:focus-visible` is a 2px accent ring with 2px offset. Never remove focus.
- Disabled controls retain their label, reduce contrast modestly, and prevent
  pointer interaction; avoid reducing opacity until text becomes unreadable.
- Loading preserves the control's dimensions and changes the label to a clear
  verb phrase such as “Saving…”.
- Success, warning, and error copy is specific to the action. Do not use a
  green/red flash as the only confirmation.

### Fixed card inspection feedback

RHYTHMOS information cards use one permanent visual-response rule. It gives a
precise-pointer user a small sense of surface depth while scanning, without
claiming that a read-only card is a control.

- **Scope:** first-party metric, summary, guidance, system, baseline, load,
  nutrient, and bordered Streamlit information-card surfaces.
- **Timing:** `transform`, `box-shadow`, and `border-color` transition with
  `180ms ease-out`.
- **Hover result:** `translateY(-1px)` and the shared quiet elevation
  `inset 0 1px 0 rgba(255,255,255,.18), 0 20px 36px rgba(0,0,0,.14)`.
- **Availability:** only inside
  `@media (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)`.
  Touch and reduced-motion contexts retain the resting surface.
- **Restraint:** no scale, glow, cursor change, delayed stagger, entry motion,
  or data/value/chart/status animation. The effect is inspection feedback, not
  an affordance for navigation or action.
- **Accessibility:** read-only cards are not focus targets. Genuinely
  interactive controls keep their normal `:focus-visible` ring rather than
  relying on lift for keyboard feedback.
- **Implementation ownership:** the canonical selector list and values live in
  `src/ui_controls.py` as part of `APP_SHELL_CSS`. New card classes must join
  that shared rule rather than introducing page-local motion variants.

### Component matrix

| Component | Default | Hover / active / pressed | Focus / disabled | Loading / success / warning / error |
| --- | --- | --- | --- | --- |
| Metric / recovery / sleep / training card | Static L1 surface; label → value → evidence; content-led height | Shared inspection feedback on precision hover only: 180ms ease-out, 1px lift, quiet elevation. It does not imply clickability; pressed has no scale. | Focus ring only when card is genuinely interactive; noninteractive cards are not focus targets. | Inline semantic row or small rule; never recolor the full card. |
| Navigation item | 36–40px text row, quiet icon, 8px horizontal inset | Slight inset-surface fill on hover; selected state uses accent text/rule, not a saturated pill | Ring around the link; disabled/current page remains legible but inert | Loading is not applicable. Error states belong in page content, not the rail. |
| Primary button | Solid muted accent, 40px high, 10px radius, concise verb | Hover: one shade darker; pressed: return to base or 1px inset, no scale | Clear ring; disabled low-saturation fill with readable label | Preserve width; “Saving…” then a nearby concise confirmation. Error appears adjacent to the relevant form. |
| Secondary / destructive button | Transparent or L1 surface with border; destructive is text/rule-led until confirmation | Subtle background change; destructive does not default to solid red | Same ring; disabled remains visible | Confirm destructive action before success/error feedback. |
| Text, number, select, date input | 40px minimum height; label above; 8px gap; standard L1 border | Border strengthens and surface changes slightly | Accent focus ring; invalid uses text plus border, not colour alone | Maintain entered value while validating; success is a compact adjacent check/copy. |
| Tabs | Text-first, bottom rule, no boxed tab strip | Accent underline becomes visible on hover; selected has ink/accent text and 2px underline | Ring on focused tab; disabled tab is readable | Tabs do not show loading individually; panel may show local loading state. |
| Expander | 44px disclosure row, title left, chevron right, divider only when grouped | Subtle inset on hover; chevron rotates only if supported without layout jump | Native summary remains keyboard reachable | Show a compact state inside the opened body; avoid alerts on the summary row. |
| Status indicator | Inline label plus small dot/rule/icon; use neutral background by default | Not normally interactive | If interactive, receives normal link/button focus | A warning/error explains cause and next step; success is quiet and does not persist unnecessarily. |
| Table | L1 surface, sticky header, 44px rows, text left/numbers right | Row hover only for selectable rows; selected row uses subtle inset and accent rule | Keyboard action remains a real button/link, not a clickable `div` row | Empty, loading, and error states replace tbody with a concise explanation; preserve headers only when useful. |
| Chart container | Prefer L0 or L1, title/caption above, plot without decorative frame | Legend/time-range controls use text-button behavior | Keyboard-accessible controls and textual equivalent | Loading reserves chart space; missing data states explain the absence without fake axes. |

## 7. Streamlit de-Streamlitization strategy

The aim is not to hide Streamlit. It is to let RHYTHMOS's hierarchy, spacing,
and component language dominate the framework defaults.

| Streamlit pattern | Improvement strategy |
| --- | --- |
| Default block container | Shared shell sets intentional page width, top/bottom spacing, and stable scrollbar behavior. Do not repeat container padding rules per page. |
| Sidebar | Keep a stable rail width, reduce decorative copy, replace emoji-heavy links with consistent icon/text treatment, and make selected state clear without disabling visual contrast. |
| `st.metric` | Use only for simple compact facts. Create a shared RHYTHMOS metric wrapper for label/value/delta/baseline when evidence needs hierarchy. |
| Buttons | Standardize native button role styling via scoped CSS; preserve Streamlit accessibility and avoid hand-built clickable HTML. |
| Forms | Give labels, validation, and submit action a consistent rhythm. Do not center every field by force; numerical entry may align end/center only when scanning benefits. |
| Tabs | Restyle native tabs as an underline navigation pattern; reserve them for peer views rather than section layout. |
| Expanders | Use as evidence/history disclosure. Standardize summary height and spacing; avoid nested stacks of expanders. |
| Dataframes | Use the same density/alignment strategy for native and custom tables. Prefer native dataframe where interactivity matters; custom HTML only when its accessibility and responsive behaviour are verified. |
| Alerts | Keep `st.error` for errors and failures. For ordinary informational, complete, and data-quality states, use quiet RHYTHMOS inline status components. |
| Spinner/progress | Spinner only during an explicit task such as OCR/import/sync. Use determinate progress when progress is truly known. Do not make dashboard freshness look like loading. |

## 8. Unified chart visual language

### Plotly and SVG rules

- Use the app canvas/surface background; no hard-coded pure-white plot area.
- Grid lines are sparse, 1px, low-contrast, and horizontal-first. Suppress
  heavy zero lines and chart frames unless a baseline requires one.
- Use 2px line weight, 4–5px markers only for observed points, and direct
  current-point emphasis through the accent colour and a concise label.
- A personal range is a subtle translucent band; baseline center is a quiet
  dashed line; current observation is a solid marker. This relationship must
  be consistent across sleep, recovery, training, and future views.
- Use one primary data series plus at most two supporting series. Avoid a
  rainbow palette and decorative gradients.
- Leave missing samples as gaps. Never connect them visually or fill them with
  zero.
- Use localised axis labels, unit labels, and date formatting. Keep legends
  compact and text-first; hide the Plotly mode bar unless it provides a real
  task.
- Tooltip is compact: date/time, value and unit, baseline context, and source
  status. Do not repeat the whole chart legend in every hover card.
- Selected time range is an explicit control only where it changes a real
  reading task. Default ranges should be stable and documented per chart.
- Every figure has a one-sentence textual summary for non-hover and assistive
  use.

## 9. Interaction and feedback rules

- **Hover:** reveals interactivity, not decoration. Static evidence should not
  pretend to be clickable.
- **Selection:** selected tab, row, navigation item, or date receives a modest
  border/underline/background shift and stays visible after rerun.
- **Expansion:** reveal evidence in place. Preserve page position and avoid
  unnecessary automatic scroll.
- **Save:** disable only the submitted control, preserve its width, then show a
  concise nearby success/failure message. Do not rely solely on a global banner.
- **Error recovery:** retain entered form values, name the invalid field or
  unavailable source, and state the next possible action.
- **Loading:** reserve layout, use explicit operation language, and never show
  decorative loading for a read-only screen.
- **Navigation:** maintain stable rail and content width. Existing stale-frame
  opacity suppression is appropriate; no route slide or fade is needed.

## 10. Motion recommendations

### Motion worth considering

1. **Explicit save/import confirmation** — a 120–160ms local check/label fade
   after a successful form save, OCR confirmation, or planner change.
2. **Expander/tab continuity** — a short, reduced-motion-safe disclosure or
   underline transition only if it does not cause a Streamlit layout jump.
3. **Selection feedback** — subtle background/border interpolation for a
   selected table row, date, or navigation item.

### Elements that should remain static

- Recovery, sleep, neural, training, nutrition, and confidence values.
- Status colours, warnings, error states, and data-quality messages.
- Chart line drawing, range bands, historical data, and current-point markers.
- Page navigation, page title, side rail, and non-card structural surfaces.
- Long tables, raw data, and any content that would move while a user scans it.

All motion must support `prefers-reduced-motion: reduce`, where transitions are
removed without changing meaning or interaction outcome.

## 11. Prototype targets for a later visual exploration

Do not prototype whole pages first. These pieces have the highest leverage.

| Target | Treatment A | Treatment B | Treatment C |
| --- | --- | --- | --- |
| Metric / recovery card | **Evidence stack:** label, value, one baseline line; no enclosing secondary grid. | **Range lane:** value beside a thin personal-range track with a current marker. | **Trend slot:** value with a small fixed-height sparkline below; baseline detail opens on demand. |
| Navigation item | **Text rail:** text-first row with a thin selected rule. | **Grouped rail:** quiet section labels separate core domains from tools. | **Compact icon/text:** 16px monochrome icon plus text; active state is an inset surface, not a pill. |
| Chart container | **Inline figure:** chart sits directly on L0 canvas with title/caption only. | **Evidence surface:** L1 chart surface with an internal baseline legend row. | **Focus panel:** one emphasis surface with chart, range control, and textual trend conclusion. |
| Status indicator | **Inline sentence:** small dot/rule plus direct copy beside the affected field. | **Context row:** full-width but borderless status row beneath a section title. | **Exception panel:** L2 compact callout used only for warning/error/conflict with action copy. |
| Form action group | **Footer action:** quiet form body; submit/secondary actions align at bottom. | **Split field/action:** compact action column only for short recurring rows. | **Progressive detail:** essential fields visible; optional fields live in one well-labelled disclosure. |

Treatments differ by composition and interaction, not merely colour. Validate one
target at a time against light/dark themes, Chinese/English copy, narrow width,
keyboard navigation, and real Streamlit reruns before promoting it to shared UI.

## 12. Prioritized visual improvements

### P0 — resolve first

1. Establish one shared visual foundation: background/surface hierarchy,
   radii, borders, shadows, type scale, control treatment, and dark-theme
   semantics. Current page-local CSS is visibly fragmented.
2. Correct shell width and spacing: deliberate page top rhythm, stable main
   width, and a less dominant sidebar.
3. Remove decorative gradients, excessive fixed-height cards, and equal-priority
   card grids from Recovery, Sleep, Training, and Nutrition.
4. Standardize chart styling and remove hard-coded white Plotly/chart surfaces.

### P1 — important refinement

1. Replace emoji-heavy navigation with a coherent text/icon treatment.
2. Standardize form controls, button roles, tabs, expanders, inline states, and
   save feedback.
3. Establish table density/alignment and accessible narrow-screen behavior.
4. Convert ordinary empty/degraded states from generic framework banners to
   concise RHYTHMOS status copy.

### P2 — polish after the foundation

1. Add the three limited motion treatments from section 10.
2. Refine chart tooltips, legend placement, baseline bands, and selected range
   controls.
3. Tune micro-spacing, copy wrapping, icon optical alignment, and state
   contrast after visual QA on all three languages.

## 13. Exact production files for the visual implementation phase

### Shared foundation

- `src/ui_controls.py` — shared shell, type scale, semantic visual variables,
  Streamlit control styling, reduced-motion rules.
- `src/i18n/ui.py` — sidebar presentation and navigation item treatment.
- `src/ui_tables.py` — shared table density, alignment, header, and responsive
  treatment.

### Page-level visual harmonisation

- `src/dashboard.py` — Training metric, plan, and baseline surfaces.
- `src/pages/1_Sleep.py` — Sleep card system, sparkline/baseline visual language,
  and Plotly chart styling.
- `src/pages/2_Recovery.py` — Recovery card, evidence, form, and status styling.
- `src/pages/3_Nutrition.py` — nutrition summary cards, feedback/status, and
  input rhythm.
- `src/pages/4_System.py` — system status feedback and operational loading
  treatment.
- `src/pages/5_Personal.py` — personal form, metric, and line-chart styling.
- `src/pages/6_Training_Studio.py` — cognitive record tables, controls, and
  recommendation/status styling.
- `src/pages/8_Performance_Planner.py` — planner cards, tabs, progress, and
  status surfaces.
- `src/pages/1_Daily_Log.py` — native tabs, forms, metrics, and table rhythm.
- `src/pages/3_Neural_Readiness.py` — assessment result metrics and form states.
- `src/pages/3_Kubios_Advanced_Metrics.py` — advanced Plotly chart treatment.

No algorithms, database schemas, recovery logic, ingestion modules, or frontend
framework files are required for this visual implementation phase.

## 14. Visual QA checklist

- [ ] Light and dark appearance use semantic surfaces; no page has a hard-coded
      white chart/card that breaks dark mode.
- [ ] Page title, section title, body, label, caption, value, unit, and table
      number follow the type scale.
- [ ] A viewport contains no more than one emphasis surface unless an overlay is
      active.
- [ ] First-party information cards use the shared 180ms / -1px inspection
      response only on hover-capable precision pointers; it remains absent for
      reduced motion and never implies clickability.
- [ ] Primary actions, destructive actions, disabled controls, focus rings, and
      validation errors are distinguishable without colour alone.
- [ ] Tables align text and numbers semantically and remain usable at narrow
      width.
- [ ] Charts share grid, line, marker, baseline, tooltip, and missing-data
      rules.
- [ ] Alerts are used only for the severity they communicate.
- [ ] 320px, 736px, desktop, 80%, 100%, and 125% zoom have been checked.
- [ ] Simplified Chinese, Traditional Chinese, and English have been checked
      for wrapping, term length, unit spacing, and numeric alignment.
- [ ] Reduced motion removes all nonessential animation without breaking
      feedback or state comprehension.
