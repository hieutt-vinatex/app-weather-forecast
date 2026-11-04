# Advanced Analytics Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scope-aware Gap, Scatter, and 10×10 digit Transition Matrix charts without changing existing charts or adding load-time chart work.

**Architecture:** Derive all new datasets with pure TypeScript functions from the snapshot already held by the dashboard. Render the three ECharts only inside a collapsed-by-default advanced analytics section, so no extra canvas, calculation, network request, or backend schema is added to the initial view.

**Tech Stack:** React 18, TypeScript 5.7, ECharts 5.5 Canvas renderer, Tailwind CSS 3.4, Vitest 2.1, Testing Library

**Spec:** `docs/superpowers/specs/2026-11-04-advanced-analytics-charts-design.md`

## Global Constraints

- Preserve every existing chart and dashboard function; do not rename or remove existing sections.
- Gap, Scatter, and Transition Matrix must all consume the current `PrizeScope` (`all`, `db`, `g1`…`g7`).
- Reuse the existing snapshot; make no backend, API contract, cache, or publication changes.
- Add no runtime dependency and no network request.
- Keep advanced analytics closed by default; while closed, create zero new ECharts instances and run none of the new analytics builders.
- Gap uses complete eligible draws, Scatter uses available scoped results, and Transition Matrix is 10×10 over final digits with row percentages.
- Keep ECharts animation disabled and retain existing Canvas/lazy-update/dispose behavior.
- ECharts production chunk must remain within 5% of the current approximately 1,012 KiB raw baseline.

## Review Focus

- Unsorted records and duplicate numbers in one draw must yield chronological, aggregated Scatter points — covered by Task 1 tests.
- Missing or incomplete scoped draws must not inflate Gap values — covered by Task 1 tests.
- Never-seen numbers must remain distinguishable from observed numbers with the same numeric gap — covered by Task 1 and Task 2 tests.
- Empty or single-result transition input must produce 100 finite zero-valued cells — covered by Task 1 tests.
- Closing the section after opening must dispose/unmount all three charts, and changing scope must not reuse stale analytics — covered by Task 3 tests.

---

### Task 1: Pure scope-aware analytics calculations

**Files:**
- Create: `frontend/src/utils/advancedAnalytics.ts`
- Create: `frontend/src/utils/advancedAnalytics.test.ts`
- Read: `frontend/src/utils/prizes.ts`
- Read: `frontend/src/types/gdb.ts`

**Interfaces:**
- Consumes: `GdbRecord`, `PrizeScope`, `PRIZES`, `resultsForScope(record, scope)`, and `lastTwo(value)`.
- Produces: `ScatterPoint`, `GapStat`, `TransitionCell`, `buildScatterPoints(records, scope)`, `buildGapStats(records, scope)`, and `buildDigitTransitionMatrix(records, scope)` for Task 2.

- [ ] **Step 1: Write failing Scatter calculation tests**

Add tests named `aggregates duplicate scoped results by chronological draw` and `does not leak results from another prize`. Assert that:

```ts
buildScatterPoints([laterRecord, earlierRecord], "g7")
// is ordered by ISO date and returns one { date, dateLabel, dayName, number: "07", value: 7, count: 2 }
// for two 07 results on the same date.
```

- [ ] **Step 2: Run the Scatter tests and verify failure**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts`

Expected: FAIL because `./advancedAnalytics` does not exist.

- [ ] **Step 3: Implement the Scatter interface**

In `advancedAnalytics.ts`, add:

```ts
export interface ScatterPoint {
  date: string;
  dateLabel: string;
  dayName: string;
  number: string;
  value: number;
  count: number;
}

export function buildScatterPoints(
  records: GdbRecord[],
  scope: PrizeScope,
): ScatterPoint[];
```

Sort a copied record array by ISO date, aggregate on `date + lastTwo(value)`, and never mutate the input.

- [ ] **Step 4: Run the Scatter tests and verify pass**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts`

Expected: PASS for both Scatter tests.

- [ ] **Step 5: Write failing Gap calculation tests**

Add tests named `computes current and maximum gaps in complete scoped draws`, `ignores incomplete scoped draws`, and `marks all never-seen numbers as lower bounds`. Use a three-draw fixture where `10` appears in draws 1 and 3 and assert:

```ts
expect(byNumber.get("10")).toMatchObject({ currentGap: 0, maxGap: 1, observed: true });
expect(byNumber.get("99")).toMatchObject({ currentGap: 3, maxGap: 3, observed: false });
expect(buildGapStats(records, "g7")).toHaveLength(100);
```

For incomplete coverage, give `g7` fewer than its four expected results and assert that draw does not increase either gap.

- [ ] **Step 6: Run the Gap tests and verify failure**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts -t "gap|never-seen|incomplete"`

Expected: FAIL because `buildGapStats` is not exported.

- [ ] **Step 7: Implement the Gap interface**

Add:

```ts
export interface GapStat {
  number: string;
  currentGap: number;
  maxGap: number;
  observed: boolean;
}

export function buildGapStats(
  records: GdbRecord[],
  scope: PrizeScope,
): GapStat[];
```

Derive the expected count from `PRIZES` (sum to 27 for `all`), keep only draws with exactly that many scoped values, treat appearance once per draw via a `Set`, and return 00–99 in numeric order.

- [ ] **Step 8: Run the Gap tests and verify pass**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts -t "gap|never-seen|incomplete"`

Expected: PASS.

- [ ] **Step 9: Write failing Transition Matrix tests**

Add tests named `counts adjacent final-digit transitions in chronological scope order`, `normalizes percentages per from row`, and `returns finite zero cells for fewer than two results`. Assert 100 cells, exact counts for a known `1 → 2 → 1` sequence, row `1` percentages summing to 100, and every empty/single-result cell having `count: 0` and `rowPercentage: 0`.

- [ ] **Step 10: Run the matrix tests and verify failure**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts -t "transition|percentages|fewer"`

Expected: FAIL because `buildDigitTransitionMatrix` is not exported.

- [ ] **Step 11: Implement the Transition Matrix interface**

Add:

```ts
export interface TransitionCell {
  fromDigit: number;
  toDigit: number;
  count: number;
  rowPercentage: number;
}

export function buildDigitTransitionMatrix(
  records: GdbRecord[],
  scope: PrizeScope,
): TransitionCell[];
```

Flatten scoped results from ISO-date-sorted records without reordering values inside a draw, count adjacent unit-digit pairs including draw boundaries, and round row percentages to two decimals.

- [ ] **Step 12: Run all analytics tests**

Run: `cd frontend && npm test -- --run src/utils/advancedAnalytics.test.ts`

Expected: PASS with all Scatter, Gap, and Transition tests.

- [ ] **Step 13: Commit Task 1**

```bash
git add frontend/src/utils/advancedAnalytics.ts frontend/src/utils/advancedAnalytics.test.ts
git commit -m "feat: add scope-aware analytics calculations"
```

### Task 2: Gap, Scatter, and Transition chart components

**Files:**
- Modify: `frontend/src/components/charts/HistoryScatterChart.tsx:1-72`
- Create: `frontend/src/components/charts/GapChart.tsx`
- Create: `frontend/src/components/charts/TransitionMatrixChart.tsx`
- Create: `frontend/src/components/charts/AdvancedCharts.test.tsx`
- Read: `frontend/src/components/charts/EChart.tsx`
- Read: `frontend/src/utils/chartTheme.ts`

**Interfaces:**
- Consumes: Task 1's three builders and data interfaces; existing `EChart`, `GdbRecord`, `PrizeScope`, `Theme`, `chartTheme`, and palette.
- Produces: `GapChart`, revised `HistoryScatterChart`, and `TransitionMatrixChart`, each accepting `{ records: GdbRecord[]; scope: PrizeScope; theme: Theme }` for Task 3.

- [ ] **Step 1: Write failing option-level component tests**

Mock `./EChart` as a component that captures `option`, `height`, and `ariaLabel`. Add tests that render each chart and assert:

- Scatter passes the selected scope to its builder, uses Y range 0–99, represents aggregated `count` in symbol size/tooltip, and its ARIA label says the chart follows the selected prize.
- Gap contains 100 categories and exactly two bar series named `Hiện tại` and `Lớn nhất`; never-seen tooltip text uses `≥ N kỳ`; horizontal `dataZoom` is present.
- Transition Matrix contains 100 heatmap cells, both axes are `0`…`9`, and tooltip includes count plus row percentage.

- [ ] **Step 2: Run the component tests and verify failure**

Run: `cd frontend && npm test -- --run src/components/charts/AdvancedCharts.test.tsx`

Expected: FAIL because two components do not exist and `HistoryScatterChart` has no `scope` prop.

- [ ] **Step 3: Revise `HistoryScatterChart`**

Change its props to the common interface, replace direct `record.gdb` mapping with `buildScatterPoints(records, scope)`, keep the date category axis and 0–99 Y axis, size points from aggregated `count`, and update tooltip/ARIA copy to mention scoped results rather than only the special prize.

- [ ] **Step 4: Implement `GapChart`**

Create the common-prop memoized component. Build its ECharts option from `buildGapStats`, with two bar series, 00–99 categories, horizontal inside/slider zoom, theme tokens, integer Y axis, scoped ARIA label, and lower-bound tooltip wording for `observed: false`.

- [ ] **Step 5: Implement `TransitionMatrixChart`**

Create the common-prop memoized component. Convert each `TransitionCell` to `[toDigit, fromDigit, rowPercentage, count]`, render a 10×10 heatmap with FROM rows and TO columns, use a 0–100 visual map, and show both exact count and two-decimal row percentage in the tooltip.

- [ ] **Step 6: Run the chart component tests**

Run: `cd frontend && npm test -- --run src/components/charts/AdvancedCharts.test.tsx`

Expected: PASS.

- [ ] **Step 7: Run type checking through the production build**

Run: `cd frontend && npm run build`

Expected: TypeScript and Vite complete successfully.

- [ ] **Step 8: Commit Task 2**

```bash
git add frontend/src/components/charts/HistoryScatterChart.tsx frontend/src/components/charts/GapChart.tsx frontend/src/components/charts/TransitionMatrixChart.tsx frontend/src/components/charts/AdvancedCharts.test.tsx
git commit -m "feat: add advanced analytics charts"
```

### Task 3: Deferred advanced analytics section and dashboard integration

**Files:**
- Create: `frontend/src/components/AdvancedAnalyticsSection.tsx`
- Create: `frontend/src/components/AdvancedAnalyticsSection.test.tsx`
- Modify: `frontend/src/features/dashboard/Dashboard.tsx:9-26,164-184`

**Interfaces:**
- Consumes: Task 2's three common-prop chart components, `Card`/`SectionCard`, `GdbRecord`, `PrizeScope`, `Theme`, and the dashboard's existing `scopeLabel`.
- Produces: `AdvancedAnalyticsSection({ records, scope, scopeLabel, theme }): JSX.Element`, integrated once into `Dashboard` without modifying existing chart calls.

- [ ] **Step 1: Write failing deferred-render tests**

Mock the three chart components with labeled `role="img"` sentinels. Assert that the section initially shows a button named `Mở phân tích`, has `aria-expanded="false"`, and renders none of the sentinels.

- [ ] **Step 2: Run the deferred-render test and verify failure**

Run: `cd frontend && npm test -- --run src/components/AdvancedAnalyticsSection.test.tsx`

Expected: FAIL because `AdvancedAnalyticsSection` does not exist.

- [ ] **Step 3: Implement the collapsed section shell**

Create:

```ts
interface AdvancedAnalyticsSectionProps {
  records: GdbRecord[];
  scope: PrizeScope;
  scopeLabel: string;
  theme: Theme;
}

export function AdvancedAnalyticsSection(
  props: AdvancedAnalyticsSectionProps,
): JSX.Element;
```

Use a closed `useState(false)`, `useId()` for the controlled panel id, a semantic button with `aria-expanded`/`aria-controls`, toggled labels `Mở phân tích` / `Đóng phân tích`, and conditional rendering so closed content is absent from the DOM.

- [ ] **Step 4: Run the closed-state test and verify pass**

Run: `cd frontend && npm test -- --run src/components/AdvancedAnalyticsSection.test.tsx -t "initially"`

Expected: PASS.

- [ ] **Step 5: Write failing open, close, and scope-update tests**

Assert that clicking open mounts exactly the three sentinels, clicking close removes them, the heading includes `scopeLabel`, and rerendering from `scope="all"` to `scope="g7"` forwards `g7` to every mounted chart without retaining `all` output.

- [ ] **Step 6: Run the interaction tests and verify failure**

Run: `cd frontend && npm test -- --run src/components/AdvancedAnalyticsSection.test.tsx -t "open|close|scope"`

Expected: FAIL until the chart grid and prop forwarding exist.

- [ ] **Step 7: Add the responsive chart layout**

When open, render Gap and Scatter in a two-column grid at `xl`, followed by the full-width Transition Matrix. Use Vietnamese titles/descriptions from the design and pass the identical `{ records, scope, theme }` to each chart.

- [ ] **Step 8: Integrate the section into `Dashboard`**

Import `AdvancedAnalyticsSection` and render it after the existing top/cold number cards and before `HistoryTable` with:

```tsx
<AdvancedAnalyticsSection
  records={data.data}
  scope={prizeScope}
  scopeLabel={scopeLabel}
  theme={theme}
/>
```

Do not alter or move any existing chart invocation.

- [ ] **Step 9: Run section and existing frontend tests**

Run: `cd frontend && npm test -- --run src/components/AdvancedAnalyticsSection.test.tsx src/components/PrizeNavigation.test.tsx src/utils/absence.test.ts`

Expected: PASS; closed/open behavior, prize navigation, and existing absence behavior remain green.

- [ ] **Step 10: Commit Task 3**

```bash
git add frontend/src/components/AdvancedAnalyticsSection.tsx frontend/src/components/AdvancedAnalyticsSection.test.tsx frontend/src/features/dashboard/Dashboard.tsx
git commit -m "feat: add deferred analytics dashboard section"
```

### Task 4: Full regression, performance budget, and visual verification

**Files:**
- Modify only if verification exposes a defect: files owned by Tasks 1–3 and their tests
- Verify: `frontend/package-lock.json` remains unchanged
- Verify: `app/` and `cloudflare/worker/` remain unchanged

**Interfaces:**
- Consumes: the complete implementation from Tasks 1–3.
- Produces: a verified frontend build with the original dashboard preserved and the performance constraints demonstrated.

- [ ] **Step 1: Run the complete frontend test suite**

Run: `cd frontend && npm test -- --run`

Expected: all tests pass with no unhandled warnings.

- [ ] **Step 2: Run lint**

Run: `cd frontend && npm run lint`

Expected: exit 0 with zero warnings.

- [ ] **Step 3: Build and check bundle constraints**

Run: `cd frontend && npm run build && du -k dist/assets/echarts-*.js dist/assets/index-*.js | sort -n`

Expected: build succeeds; ECharts raw chunk is no more than 1,063 KiB (1,012 KiB + 5%); no new third-party chunk appears; entry size growth is limited to the new application code.

- [ ] **Step 4: Verify repository scope**

Run: `git diff --name-only HEAD~3..HEAD`

Expected: only the frontend files listed in Tasks 1–3 are present; the already-committed spec/plan fall before this three-commit range, and `frontend/package-lock.json`, `app/`, and `cloudflare/worker/` are absent.

- [ ] **Step 5: Perform browser verification**

Run: `cd frontend && npm run dev -- --host 127.0.0.1`

Check 30/60/90 days and scopes `all`, `db`, `g3`, `g7` in light/dark themes and a narrow viewport. Confirm existing charts remain visible; closed analytics creates no chart DOM; opening shows accurate tooltips/labels; closing removes the charts; axes and matrix remain readable without horizontal page overflow.

- [ ] **Step 6: Commit any verification-only repairs, if needed**

If Step 1–5 required changes, rerun the failed check and commit only the repair:

```bash
git add <repaired-files-and-tests>
git commit -m "fix: harden advanced analytics charts"
```

If no repair was needed, do not create an empty commit.
