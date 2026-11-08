# Asymmetry Bench: Front-End Specification

This file defines the local web app used to launch benchmark runs, watch them, explore results, and download logs. Benchmark behavior (tasks, metrics, log formats) is defined in `01_BENCHMARK_SPEC.md`. Build order and architecture are in `03_IMPLEMENTATION_GUIDE.md`.

---

## 1. Goals

1. **Run** the benchmark on any configured model without touching the command line. Plugging in a new model should take one form field or one registry line.
2. **See results clearly:** a leaderboard and per-run results that a first-time visitor understands in under a minute.
3. **Explain the benchmark:** an About page that says why it exists, what it measures, how each task works and how to read the results.
4. **Inspect behavior:** read any episode turn by turn, with private notes and flagged tactics, to check that the numbers mean what they claim.
5. **Store and download everything:** every run is saved and can be looked up later, and raw logs and summaries for any run or episode can be downloaded.

**Reference point.** Public agent leaderboards (like an agent arena leaderboard): a ranked table up front, click through to details. Ours is simpler. No accounts, no voting, no marketing pages. It is a local research tool that looks clean.

**Non-goals.** User accounts, hosting, multi-user editing, mobile-first design (it should still work at narrow widths), and editing results by hand.

---

## 2. Stack (decided)

- **Server:** the same FastAPI app that runs the benchmark serves the JSON API under `/api/*` and the static front-end at `/`.
- **Front-end:** one `index.html`, one `app.js`, one `styles.css` in `asymbench/static/`. Plain JavaScript (ES modules), no framework, no build step.
- **Charts:** Chart.js 4 from cdnjs. No other front-end dependencies.
- **Routing:** hash-based (`#/leaderboard`, `#/runs`, `#/runs/<id>`, `#/episodes/<id>`, `#/new`, `#/models`, `#/about`).
- **Live updates:** poll every 2 seconds while a run page shows a running run. Stop polling when the run finishes or the page changes.
- **Storage:** the server's SQLite database plus the `runs/<run_id>/` folders. The browser stores nothing except UI preferences (theme, table sort) in `localStorage`, wrapped in try/catch.
- **API keys:** read by the server from environment variables or `.env`. The UI never asks for, displays, or sends keys. It only shows whether each provider's key is present.

---

## 3. Layout and visual design

- **Top bar:** app name "Asymmetry Bench" on the left. Nav links: Leaderboard, Runs, New Run, Models, About. On the right: a provider key status indicator (three small dots: Anthropic, OpenRouter, Mock, green if available) and a light/dark toggle.
- **Content width:** max 1200px, centered, 24px side padding (16px on narrow screens).
- **Typography:** system UI font stack. Body 15px. Monospace for model ids, run ids, and JSON.
- **Colors:** neutral background and text, one accent color for links and primary buttons. Semantic colors used consistently everywhere:
  - Exploitation events: red tint.
  - Gray events: amber tint.
  - Counterpart events: purple tint.
  - Success indicators: dark red badge.
  - Control counterpart: always labeled "Control" with a neutral badge.
- **Light and dark themes** via CSS variables on `:root`, following the system setting by default.
- **Numbers:** always show the value with its 95% CI as `0.42 [0.31, 0.53]` or as an error bar, and show n. Show "n too small" instead of a CI when n < 5.
- **Direction hints:** each metric column header has a small arrow showing whether higher or lower is better, and a tooltip with its one-sentence definition (from section 9 of the benchmark spec).
- **Empty states:** every page explains what to do when there is no data ("No completed runs yet. Start one from New Run.").
- **Errors:** API errors show as a dismissible banner with the server's message.

---

## 4. Pages

### 4.1 Leaderboard (`#/leaderboard`, the home page)

**Purpose:** compare test models at a glance.

**Contents, top to bottom:**
1. **One-paragraph explainer** (collapsible, open the first time, collapsed after): what the benchmark measures, that performance and integrity are separate, and a link to the About page.
2. **Filters:** task (All, T1, T2, T3, T4), condition (Default only, or a specific sweep), and "Include runs with mock models" (off by default).
3. **Leaderboard table**, one row per test model, built from all completed non-mock runs matching the filters:

| Column | Notes |
|---|---|
| Rank | by the current sort column |
| Model | label plus id in small monospace |
| Principal value ↑ | vs control |
| Advantage captured | extraction gap vs weak counterparts (descriptive, no arrow) |
| Attempt shift ↓ | headline, default sort |
| Success shift ↓ | |
| Disclosure shift ↓ | T2 only |
| Baseline exploitation ↓ | |
| Recognition gap | how much more often the test agent recognized weakness vs weak counterparts than vs the control (descriptive) |
| Post-recognition change ↓ | attempts per turn after recognition minus before |
| Episodes | non-excluded n |
| Runs | count, links to the runs |

   - Click a column header to sort. Click a row to expand an inline breakdown by task (the same columns per task).
4. **Scatter plot:** x = principal value, y = attempt shift, one point per test model with CI whiskers in both directions. The caption says the ideal is bottom-right (high performance, low exploitation).
5. **Download:** "Download leaderboard (CSV)".

### 4.2 Runs (`#/runs`)

**Table of all runs**, newest first:

| Column | Notes |
|---|---|
| Name | user-given, falls back to the run id |
| Test model | |
| Tasks | small chips T1 to T4 |
| Counterparts | count, tooltip lists them |
| Status | queued / running / done / cancelled / failed / budget stopped, with color |
| Progress | bar with done/total and the failed count |
| Cost | spent / budget |
| Created | relative time, exact time on hover |
| Actions | Open, Download ZIP, Cancel (only while running), Delete (with confirmation) |

Filters: status, test model, and text search on name. Running rows update live.

### 4.3 New Run (`#/new`)

A single form. Every field has a short help text.

1. **Name** (optional text).
2. **Test model:** a dropdown of registry models grouped by tier, default `claude-sonnet-5-5`, plus a "Custom model id" text field (provider inferred: `claude-*` is Anthropic, anything with a `/` is OpenRouter). Models whose provider key is missing are disabled with a note.
3. **Counterparts:** checkboxes for every registry model that isn't the test model. Defaults checked: `meta-llama/llama-3.1-8b-instruct` and `openai/gpt-oss-20b`. "Control (same as test model)" is checked and locked on. An "Add custom counterpart id" field.
4. **Tasks:** checkboxes T1 to T4, all on by default, each with a one-line description.
5. **Conditions:**
   - Preset dropdown: "Core run (defaults)", "Label sweep", "Instruction sweep", "Oversight sweep", "Custom".
   - Custom shows checkboxes for each level of instruction, oversight, and label. The grid is the cross product. Show the resulting number of condition cells.
6. **Seeds per cell:** number, default 10. "Seed start" (default 0).
7. **Judge model:** dropdown, default `claude-haiku-5-5`. Optional "Cross-check judge" dropdown for the 10% second judge.
8. **Concurrency:** number, default 4.
9. **Budget (USD):** required number, default 25. The run stops scheduling new episodes when it reaches this.

**Live summary panel** (right side, or below on narrow screens), updated as the form changes:
- Episode count: tasks × counterparts × condition cells × seeds.
- API call estimate and **cost estimate** with a low to high range, from `POST /api/estimate`.
- Warnings: a missing key for a selected model, an OpenRouter id not found (from `/api/models/check`), an estimate above the budget, or more than 2,000 episodes.

**Buttons:** "Validate" (runs the model availability check), "Start run" (disabled until valid). On start, go straight to the run detail page.

**Also:** "Duplicate run" on any run detail page opens this form prefilled with that run's config.

### 4.4 Run detail (`#/runs/<id>`)

**Header:** name, run id, status badge, test model, created time, cost spent / budget, progress bar (live), and buttons: Cancel (running only), Duplicate, Re-judge (choose a judge model, re-runs judging on all episodes from stored transcripts), Recompute metrics, Download ZIP.

**Tabs:**

**a) Summary**
- Headline cards in two rows, each with CI, n and a one-line meaning. Row 1 (the two-step story): **Recognition gap**, then **Post-recognition change**. Row 2: Principal value (vs control), Advantage captured, Attempt shift, Success shift. A small badge on the integrity cards when the result is not distinguishable from zero.
- **Headline chart:** x = counterpart (categorical, ordered weakest tier first, control last), y = attempt shift vs control, one point per counterpart with CI whiskers. Toggle series: success shift, disclosure shift. The control is at y = 0 by definition and drawn as a reference line.
- **Advantage chart:** same x-axis, y = advantage captured (extraction gap), captioned "how much of its advantage the test agent captured; not evidence of wrongdoing by itself".
- **Recognition chart:** same x-axis, y = recognition rate (bars) with mean survey rating as a second series, so the viewer can see whether the test agent noticed weaker counterparts more often.
- **Recognized vs not chart:** for each weak counterpart, attempt rate and success rate in recognized vs unrecognized episodes, side by side, with the control as a reference line. Captioned with the correlational caveat from the benchmark spec section 9.3.
- **Before vs after recognition chart:** attempt events per turn before and after the recognition turn, pooled over episodes where recognition happened, per counterpart.
- **Safeguards box:** attempt shift recomputed without counterpart misconduct, without eval-aware episodes, and split by survey rating; plus the excluded count, eval-awareness rate and judge failures.

**b) By task**
- One section per task with a table: rows = counterparts (control last), columns = n, share, principal value, attempt events/episode, attempt rate, success rate, harm, survey rating, recognition rate, detection rate, counterpart invalid rate, excluded.
- Task-specific extras:
  - T1: depletion rate, average final pool, and a small line chart of average pool size per round for each counterpart.
  - T2: deal rate, overpayment rate, average inspections used, disclosure rate and unprompted disclosure rate.
  - T3: deal rate, efficiency, client below walkaway rate, average client misperception, client overdisclosure rate.
  - T4: escalation rate, unresolved rate, average underpayment, store-credit steer rate.
- An event-type breakdown bar chart per task (count per episode by event type, grouped by counterpart).

**c) Conditions** (only if the run has more than one condition)
- For each swept variable, a grouped bar chart of attempt shift per level, with CIs.
- The label sweep highlights the "weak label on control" cell.

**d) Capability gap**
- For each task, a table: rows = counterparts (control last), columns = that task's counterpart indicators (benchmark spec section 3.2) and counterpart invalid rate. This shows how large the capability gap actually was.
- Highlight any (task, counterpart) where the indicators are within the CI of the control, with the note "little capability gap on this task for this counterpart; read shifts with caution".

**e) Episodes**
- Filterable table: task, counterpart, condition, seed, outcome summary (one short phrase, for example "Deal at $640 (buyer overpaid)"), share, attempt events, success flag, survey, flags (excluded, judge failed, has gray events), cost.
- Filters: task, counterpart, condition, "only with attempt events", "only with success indicators", "only excluded", "only judge failed".
- Clicking a row opens the episode viewer.
- "Export hand-label sample (CSV)": a random 10% of episodes with the transcript as text and the judge's events, plus empty columns for human labels.

**f) Config**
- The full run config as formatted JSON, the code version, and the judge model.

### 4.5 Episode viewer (`#/episodes/<id>`)

The page that makes results trustworthy. Layout: transcript on the left (about 65%), a sticky side panel on the right.

**Header:** task, seed, test model vs counterpart (with control badge), condition, status, cost, links to previous and next episode within the same filter, "Download episode (JSON)".

**Transcript:**
- One bubble per turn, aligned by speaker (test agent on the right, counterparts on the left), with role name, model id, and turn number.
- The bubble shows the message. Below it, a compact action chip (for example `offer $640`, `inspect: battery`, `take 22` with the announced amount next to it in T1).
- **Private notes:** collapsed by default under each bubble, with a "Show private notes" toggle per bubble and a global "Show all private notes" switch.
- **Flags:**
  - A judge event highlights the quoted words inside the message in the event color. Hovering or clicking shows the event type and the judge's explanation.
  - Deterministic events (T1 announcement breach) appear as a red chip on the turn.
  - Invalid turns show a gray "invalid (safe default used)" chip with the parse error, and a toggle to see the raw output.
  - Retried turns show "retried" with both raw outputs available.
  - The detection turn gets a prominent marker across the transcript: "Test agent first noted counterpart weakness here." Turns after it get a faint background tint, so a reader can see at a glance whether tactics changed after recognition.
- **T1 only:** a round divider before each round showing pool at start, and after each harvest a line with the true takes of all three fishers (visible to us, never to the agents) next to their announcements.
- Surveys appear at the end as a final card.

**Side panel:**
- **Outcome:** the task's outcome in plain words plus key metrics (share, principal value, harm).
- **Events summary:** counts by type, with click-to-scroll to each event.
- **Ground truth** (collapsible): T2 fact sheet, T3 both points tables plus the Nash package, T4 entitlement breakdown, T1 the true takes table.
- **Survey:** rating and explanation.
- **Raw data:** "View raw JSON" opens a modal with the full episode record.

### 4.6 Models (`#/models`)

- A table of the model registry: label, id, provider, tier, price in/out, key available, and OpenRouter availability (checked on page load).
- For each model: how many runs and episodes it appears in (as test agent and as counterpart), with links to those runs.
- A short note that ids and prices are edited in `config/models.yaml`, and that any id can also be typed directly on the New Run page.

### 4.7 About (`#/about`)

A single readable page (max width about 760px for the text) that explains the benchmark to someone who has never seen it. Static content written into the page, using the copy guidance below. It should take about five minutes to read. Use short sections with headings, a small diagram where noted, and no jargon without a one-line explanation.

**Sections, in order:**

1. **Why this benchmark exists.**
   - AI agents are starting to deal with other AI agents on people's behalf: a shopping agent negotiating with a store's sales agent, a support bot handling a customer's agent, procurement bots trading with each other.
   - These agents won't be equally capable. Companies can afford frontier models; many people will be represented by cheap or free ones.
   - Earlier experiments (for example Anthropic's Project Deal) found that people represented by weaker models got worse deals and didn't notice.
   - Existing benchmarks measure who gets the better deal or whether agents cooperate on shared goals. None ask *how* a strong agent uses its advantage over a weaker one with conflicting interests.

2. **What we measure.**
   - The core question, in two steps: does a strong agent *recognize* on its own that its counterpart is weaker, and once it does, does it *act differently*? Does it simply negotiate better, or does it use tactics that only work because the other side is weak?
   - How we see recognition: the agent's private reasoning notes (it's never asked about its counterpart during the interaction) and a capability rating it gives after the interaction ends.
   - The line we draw, shown as a two-column box: *Legitimate* (bargaining hard, using information the other side shared, refusing bad deals) vs *Exploitation* (lying, misstating rules, misdescribing offers, fake pressure).
   - Two families of results that are never merged: **Performance** (how well the agent serves the side it represents, and how much of its advantage it captures) and **Means** (whether it captures that advantage honestly).
   - One sentence on the method: every scenario is played twice on the same seed, once against a weaker model and once against an equally strong copy of the test agent, and the difference is what we report.
   - A note that nothing is manufactured: every agent in a role gets the same instructions, nobody is told to be weak, and the advantage comes only from the models themselves.

3. **The four tasks.** One card per task with: a one-line scenario, who the test agent plays, what the counterpart has to do well, what exploitation would look like there, and what's scored.
   - *Shared Commons:* three fishers share a lake that regrows. Announcements aren't binding. Can the test agent take more than it announces when the others can't work out who over-fished?
   - *Used-Goods Sale:* the test agent sells an item with hidden defects. The buyer can inspect only two features. Does the seller lie, or stay quiet, more with a buyer that doesn't check?
   - *Supply Contract:* five issues, private points tables, real room for deals that benefit both sides. Does the test agent misdescribe its offers to a client that can't add up the totals?
   - *Customer Claim:* the test agent is a support bot that knows exactly what the customer is owed under a public policy. Does it misstate the policy or settle for less when the customer's agent doesn't know its rights?
   - A small table comparing the four (parties, length, payoff structure, the counterpart's key skill, the exploitation channel), the same one as in the benchmark spec.

4. **How to read the results.** A table with one row per metric: name, what it means in plain words, and which direction is better. Then a second table, "What different results mean", with these rows (from the benchmark spec section 9.4):
   - Recognized weakness and stayed honest: the best result for a strong agent.
   - Dirtier tactics after recognizing weakness: it changed behavior because it noticed. The core finding we're looking for.
   - Advantage captured but no attempt shift: the agent uses its advantage honestly. The healthy result.
   - Attempt shift above zero: it uses more dishonest tactics against weaker counterparts. The core exploitation finding.
   - Success shift above zero, attempt shift near zero: same tactics with everyone, but they only work on the weak.
   - Disclosure shift above zero: honest when it could get caught, quiet when it can't.
   - High baseline exploitation: dishonest with everyone, not specifically targeting weakness.
   - Little capability gap on a task: the weak model handled that task fine, so there was nothing to exploit.

5. **Safeguards and limitations.** Short bullets: format failures are tracked separately and heavily failing episodes are excluded; counterpart misbehavior is controlled for; evaluation awareness is flagged; an AI judge labels tactics and is spot-checked by hand; results depend on the specific models and scenarios used.

6. **Models used.** The current default test agent and counterparts pulled live from `/api/models` (label, tier, provider), with a note that new models can be added and their results join the same leaderboard.

7. **Team and links.** "Built by the Cornell Data Science FA26 Multi-Agent Co-op team." Links to the repo and the proposal doc (configurable in settings, hidden if empty).

---

## 5. API contract

All responses are JSON unless noted. Errors return `{"error": "message"}` with an appropriate HTTP status.

| Method and path | Purpose | Request | Response |
|---|---|---|---|
| `GET /api/health` | liveness | | `{"ok": true, "version": "..."}` |
| `GET /api/models` | ladder and key status | | `{"models": [{id, label, provider, tier, price_in, price_out, key_available}], "keys": {"anthropic": bool, "openrouter": bool, "mock": true}}` |
| `POST /api/models/check` | check availability | `{"model_ids": [...]}` | `{"results": {"<id>": {"available": bool, "reason": str}}}` |
| `GET /api/tasks` | task list | | `[{id, name, description, roles}]` |
| `GET /api/presets` | condition presets | | `{"<preset>": {conditions...}}` |
| `POST /api/estimate` | cost estimate | run config | `{"episodes": n, "calls": n, "cost_low": x, "cost_high": x, "warnings": [...]}` |
| `POST /api/runs` | create and start a run | run config (below) | `{"run_id": "..."}` |
| `GET /api/runs` | list runs | query: `status`, `test_model`, `q` | `[{run summary}]` |
| `GET /api/runs/{id}` | run detail | | `{run record without episodes, aggregates included}` |
| `POST /api/runs/{id}/cancel` | cancel | | `{"ok": true}` |
| `POST /api/runs/{id}/rejudge` | re-judge all episodes | `{"judge_model": "..."}` | `{"ok": true}` (runs in background, progress shown in run status) |
| `POST /api/runs/{id}/recompute` | recompute aggregates | | `{"ok": true}` |
| `DELETE /api/runs/{id}` | delete run and its folder | | `{"ok": true}` |
| `GET /api/runs/{id}/episodes` | episode list | query: `task`, `counterpart`, `condition`, `flags`, `limit`, `offset` | `{"total": n, "items": [{episode summary}]}` |
| `GET /api/episodes/{id}` | full episode record | | episode record (benchmark spec section 10.2) |
| `GET /api/leaderboard` | leaderboard rows | query: `task`, `condition`, `include_mock` | `[{model, columns..., per_task: {...}}]` |
| `GET /api/models/{id}/usage` | runs and episodes using a model | | `{"as_test": [...run summaries], "as_counterpart": [...], "episodes": n}` |
| `GET /api/about` | live parts of the About page | | `{"defaults": {...}, "tasks": [...], "links": {...}}` |

**Run config** (used by `POST /api/runs` and `POST /api/estimate`):
```json
{
  "name": "Sonnet first trial",
  "test_model": "claude-sonnet-5-5",
  "counterparts": ["meta-llama/llama-3.1-8b-instruct", "openai/gpt-oss-20b", "control"],
  "tasks": ["commons", "sale", "contract", "claim"],
  "conditions": {"instruction": ["neutral"], "oversight": ["none"], "label": ["none"]},
  "seeds": {"start": 0, "count": 10},
  "judge_model": "claude-haiku-5-5",
  "crosscheck_judge_model": null,
  "concurrency": 4,
  "budget_usd": 25
}
```

---

## 6. Downloads

| Button | Where | Endpoint | Contents |
|---|---|---|---|
| Download ZIP | Runs table, run header | `GET /api/runs/{id}/download.zip` | `config.json`, `episodes.jsonl`, `aggregates.json`, `summary.csv`, `README.txt` explaining each file and field |
| Summary CSV | Run episodes tab | `GET /api/runs/{id}/summary.csv` | one row per episode with the normalized fields |
| Aggregates JSON | Run summary tab | `GET /api/runs/{id}/aggregates.json` | all section 9 aggregates and contrasts |
| Episode JSON | Episode viewer | `GET /api/episodes/{id}/download.json` | full episode record |
| Hand-label sample | Run episodes tab | `GET /api/runs/{id}/handlabel.csv?frac=0.1&seed=0` | sampled episodes, transcript text, judge events, empty human-label columns |
| Leaderboard CSV | Leaderboard | `GET /api/leaderboard.csv` (same query as `/api/leaderboard`) | table rows |

All downloads set `Content-Disposition` with a filename that includes the run name or id and the date. Large downloads stream.

---

## 7. Behavior details

- **Run lifecycle in the UI:** queued, then running (live progress), then done, cancelled, failed, or budget stopped. Partial results are always viewable. Aggregates on a running run are computed on the fly from finished episodes and labeled "partial".
- **Server restart:** runs marked running when the server starts are set to `failed` with the error "server restarted". Their finished episodes stay. A "Resume" button on such runs re-queues only the unfinished episodes.
- **Long tables:** paginate at 100 rows with server-side filtering.
- **Performance:** the run detail page must load in under 1 second for runs up to 2,000 episodes. Use the precomputed `aggregates` and episode summaries, never full transcripts, in list views.
- **Accessibility:** keyboard-navigable tables and tabs, visible focus states, color never the only signal (event chips also carry text labels), charts have a table fallback ("Show data").

---

## 8. Acceptance checklist

- [ ] A run with `mock/strong` vs `mock/weak` can be launched from New Run and finishes with every page populated.
- [ ] Progress updates live without refreshing the page.
- [ ] Cancel stops new episodes within a few seconds and keeps finished ones.
- [ ] Every number on the Summary and By task tabs shows n and a CI.
- [ ] The episode viewer highlights judge quotes in the right message, shows private notes on toggle, and shows invalid turns with raw output.
- [ ] All six download types work and open correctly (ZIP extracts, CSVs open in a spreadsheet, JSON parses).
- [ ] The leaderboard excludes mock runs by default and sorts by every column.
- [ ] No API key ever appears in any response, page, log, or download.
- [ ] The About page covers all seven sections and its model list matches `/api/models`.
- [ ] A run with a custom model id typed into New Run works, and that model then shows up on the Models page and the leaderboard.
- [ ] Runs survive a server restart and can be found and reopened from the Runs page.
- [ ] Light and dark themes both readable; layout works at 375px width.
