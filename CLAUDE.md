# Cloud9 x JetBrains: Sky's The Limit Hackathon 2026

Project repo for our entry. This file holds the hackathon facts so any session can pick up the work.
Sources: cloud9.devpost.com (Overview, Resources, Official Rules; pasted 2026-11-19, since Devpost blocks automated fetches),
the GRID starter repo, and jetbrains.com/air.

## Status

- Category: **2 (League of Legends)**
- Project idea: C9 Draft Planner. Design: [docs/design/2026-11-19-draft-planner.md](docs/design/2026-11-19-draft-planner.md). Setup steps, milestones and progress tracker: [docs/design/2026-11-19-implementation-plan.md](docs/design/2026-11-19-implementation-plan.md). Read both before starting work, and tick tracker items as they finish.
- Unknown: the per-category prize breakdown (not on the pages pasted so far).
- Ownership confirmed: the entry is solely the entrant's.

## Workflow

- Solo personal repo: commit and push directly to `main`. No feature branches or PRs.
- Add files individually and run the GRID data pre-push check (below) before every push.

## Key dates (Pacific Time)

| Milestone | Date |
|---|---|
| Submissions open | 17 Nov 2026, 11:00 am |
| **Submission deadline** | **12 Jan 2027, 11:00 am** |
| Judging | 27 Jan - 3 Feb 2027 |
| Winners announced | ~8 Feb 2027, 12:00 pm |

## Categories (one per submission)

| # | Focus | Featured blueprints |
|---|---|---|
| 1 | VALORANT / Game Changers scouting tool for pro coaches | Utility Placement & Ability Analysis Engine; Operator Tendency & Sniper Profiler |
| 2 | LoL macro scouting and draft management | Automated Macro Scouting Tool; Modular Draft Organizer with Fearless Draft |
| 3 | Mini game playable at a Cloud9 booth (Rider recommended) | Reaction, drafting, aim or quick strategy games; simple controls, score end-screen |
| Bonus | Best AI-Powered Workflow Story | Case study or short video on how JetBrains/AI tools helped the build |

- Own ideas are allowed in every category. GRID data is optional everywhere.
- Inspiration from the Resources tab: Cat 1 map visualizations of smoke coverage and positioning, opponent Operator positioning and buy patterns. Cat 2 opponent pick/ban tendencies with C9-specific draft recommendations, champion-pool and Fearless tracking across a series.
- Anything inspired by a Riot title must use original names, art, sounds and assets and follow Riot's developer policies: https://developer.riotgames.com/policies/general
- Cloud9 teams in the data: **Cloud9** (VCT Americas), **Cloud9 GC** (Game Changers), **Cloud9 Kia** (LCS).

## Category specifics (Submission Specifics tab)

Every entry also needs a **Tooling Explanation**: which JetBrains tools were used and what each did. Other editors may be used alongside them.

### Category 1: VALORANT tactical scouting

- **Goal:** cut manual VOD review for C9 VALORANT and Game Changers coaches by visualizing opponent utility and weapon tendencies. Users are coaches and players with little technical expertise: clear heatmaps, simple filters, direct actionable insights.
- **Utility placement:** where opponents use abilities. Priority order: placeable utility (Cypher trapwires, Killjoy alarm bots, Vyse walls, Chamber trips), then recon, smokes, reactive stall, flashes.
- **Operator profiler:** how often a team buys or holds the Operator (or Odin), which player/agent uses it, where they set up on defense (aggressive forward vs passive angles), and whether possession shifts between players.
- **Filters:** opponent team, map, player, agent, composition, patch, side, weapon, ability.
- **Visuals:** density heatmaps or hard counts ("75/100 rounds") per map location.
- **Evidence:** always show sample size, rounds/matches analyzed and event frequency.
- **Landing locations:** GRID gives the caster's position and time, not where the ability lands. Inference is optional; exact reconstruction not required.
- **Next level:** anti-strat suggestions for C9 (e.g. a lineup to clear a heavily trapped zone); self-scouting C9's own predictable tendencies.
- **Judges require** at least one data-backed tactical insight for C9 with supporting evidence, derived visually, not via a chatbot. Examples:
  - "Opponent A most often (60%) uses their Sentinel utility at Point (X, Y) on Map B."
  - "Team C's primary Operator player holds aggressive angles at Location D, 80% between 0-20s in the round, and only 10% between 20-40s."

### Category 2: LoL macro scouting and draft management

- **Goal:** replace spreadsheet chaos in C9 draft preparation.
- **Draft tendency analysis:** opponent pick/ban patterns from champion pools, patch data and recent games; recommend C9-specific draft strategies.
- **Draft organizer:** simulate and track pick/ban phases under current Fearless Draft rules (shrinking champion pools in Game 3 or 5).
- **Macro context:** jungle pathing and early objective setups, as supporting context for draft insights.
- **Next level:** "how to win" counter-strategies (e.g. "Opponent X picks Sejuani 70% in Game 1; banning her drops their Game 2 Fearless win rate by 15%"); a live predicted win rate that updates as the draft progresses.
- **Judges require** a clearly useful draft capability for C9 prep, answering questions such as:
  - "What pick/ban tendencies repeat most often for this opponent?"
  - "How does the opponent's draft strategy shift in a Fearless Draft Game 3, 4, or 5 scenario?"

### Category 3: Event mini game

- **Goal:** a fast, fun game fans play at a Cloud9/JetBrains booth.
- **Fast:** one session under 3 minutes; high replayability.
- **Intuitive:** simple controls (mouse-only, arrow keys, one button), no tutorial needed; aim trainer or reaction game style.
- **Booth-ready:** resets cleanly between players; stays responsive under sustained use.
- **Theme:** optional (Cloud9, JetBrains, VALORANT, LoL or other gaming); Riot-inspired work must be original.
- **Next level:** test a real competitive skill (flick shots, reaction time); a local leaderboard on a second monitor that works without Wi-Fi.
- **Judges require** a complete loop (start, play, end/score screen) and proof of repeated booth use (clean reset, sustained responsiveness).

## Hard requirements

- **At least one JetBrains tool must be used**: IntelliJ IDEA, PyCharm, WebStorm, Rider, DataGrip, JetBrains Air or Junie. Develop in a JetBrains IDE; VS Code alone fails Stage 1.
- New project, or significant update after 17 Nov 2026 (new features, redesign, new data; not bug fixes or docs).
- Must install and run consistently and work as shown in the video.
- Entry must be the entrant's original work and solely owned by the entrant.

## Submission checklist

1. Public GitHub/GitLab/Bitbucket repo with all source, assets and run instructions.
2. Open-source `LICENSE` file at the root, detected in the repo's About section. Use MIT or Apache 2.0; no AGPL.
3. Commit `.idea/`, `.junie/` or `.air/` as evidence of JetBrains use (encouraged).
4. Live demo URL if a website; otherwise a judge-accessible build (repo install steps, itch.io, download link). Free and unrestricted until judging ends; include login credentials if private.
5. Text description: features, and which JetBrains tools were used for what.
6. Methodology write-up: approach and how it solves the category's problem.
7. Demo video under 3 minutes, public on YouTube, showing the project working on its target device. No copyrighted music or third-party trademarks without permission.
8. Optional bonus: URL to a write-up or video, e.g. `AI_SHOWCASE.md` in the repo.
9. All materials in English.

## Judging

- Stage 1, pass/fail: fits the theme and reasonably applies JetBrains tools.
- Stage 2, five equally weighted criteria (tie-break in this order):
  1. Technological implementation: thorough use of JetBrains tools; working, non-trivial build
  2. Design: complete, coherent product, not a proof of concept
  3. Potential impact: credible, specific real problem for a real audience, and the demo shows it solved
  4. Quality of the idea: creative, differs from existing concepts
  5. Presentation: video shows it end to end; clear problem, audience and why it matters
- Judges may use AI-driven analysis and need not run the project: **the video and description carry most of the weight.**
- Bonus prize is judged on how clearly the entry shows use of JetBrains IDEs, Junie or Air.

## Prizes and perks

- $25,000 cash pool, GDC Festival of Gaming tickets and travel, JetBrains subscriptions, Cloud9 gear. Per-category split not yet known.
- Each registrant gets 1 All Products Pack code and 1 AI Ultimate code (2 months; needs an IDE licence, All Products Pack or trial/EAP; student licences don't work), emailed within 5 business days of registering.
- Help: Cloud9 Discord office hours.

## Eligibility notes

- Adults, teams and organizations. A team appoints one Representative who submits.
- Excluded: Brazil, Quebec, Russia, Crimea, Cuba, Iran, North Korea, OFAC-sanctioned countries; anyone tied to Cloud9, JetBrains, GRID, Devpost or a judge.
- Multiple submissions allowed if substantially different.
- Entrant keeps IP; Cloud9, JetBrains and Devpost may use it for promotion for 3 years.

## GRID data (starter repo)

Repo: https://github.com/cloud9esports/stl-hackathon-2026-grid-starter (about 1.4 GB). Read its `README.md` and `AGENTS.md` before writing data code.

**Licence rules (proprietary, not open source):**
- **Never commit the data** to this repo: no `.zst`, decompressed `.jsonl`, `meta/` or `series.csv` copies, or extracts, caches or databases built from it (`.parquet`, `.sqlite`, `.duckdb`). Committing it is redistribution, even in a private repo. If data is ever committed, stop and tell the user before pushing.
- Clone the data repo **beside** this project, not inside it, as a sibling folder of this repo. Code reads it via env var `STL_DATA_DIR`, defaulting to `../stl-hackathon-2026-grid-starter`.
- Charts, screenshots, aggregate results and code are fine to commit. Small excerpts only to demo to judges.
- Hackathon use only; no commercial use; licence ends when the hackathon ends.
- AI tools may process the data; opt out of training/retention wherever a tool offers it.

`.gitignore` must include:

```gitignore
stl-hackathon-2026-grid-starter/
*.zst
*.jsonl
*.parquet
*.sqlite
*.duckdb
```

Pre-push check (must print nothing):

```bash
git ls-files | grep -Ei '\.(zst|jsonl|parquet|sqlite|duckdb)$|stl-hackathon-2026-grid-starter'
```

**Layout:**

| Path | Content |
|---|---|
| `val/series.csv`, `lol/series.csv` | Index of matches: `series_id, event, stage, scheduled_start, teams, file, ability_supplement` |
| `val/events_{seriesId}_grid.jsonl.zst` | 857 VALORANT series (VCT Americas, Masters, Game Changers, 2025-2026) |
| `lol/events_{seriesId}_grid.jsonl.zst` | 745 LoL series (LCK, LEC, LTA N/S, LCS, 2025-2026) |
| `val-ability-supplements/{seriesId}.jsonl.zst` | Per ability cast: 3D position, aim, velocity |
| `meta/*.csv` | tournaments, teams, players, characters, games (map, patch, winner, scores), rosters (player, agent/champion per game) |

**Format and usage:**
- One zstd-compressed JSON Lines file per series. Stream it; never decompress the corpus (VALORANT is ~160 GB uncompressed, up to ~1 GB per match). Python 3.14+: `from compression import zstd`; older: `pip install zstandard`.
- Envelope: `id, correlationId, occurredAt (UTC), seriesId, sequenceNumber, events[]`.
- Event: `id, type, actor, action, target, seriesState, seriesStateDelta, includesFullState`; `type == "{actor.type}-{action}-{target.type}"`.
- `!` before the action reverses an earlier event (`player-!purchased-item`, `series-!started-game`); undo it when replaying.
- `seriesState` is a full snapshot after the event; final box score is the last event's `seriesState`. Don't print whole envelopes.
- IDs are strings; join on IDs, not names. `meta/` IDs are unique per `title` (`val`/`lol`), so join on `(title, id)`.
- Positions `{x, y}`: centimetres in VALORANT, Summoner's Rift units in LoL; `map.bounds` gives the play area.
- LoL draft: `team-picked-character`, `team-banned-character`, and `draftActions` in state.
- Supplement joins on `grid_event_id == events[].id` of `player-used-ability`.
- Answer roster/result questions from `meta/` first; don't glob directories or open every file.

**Caveats:** not every scheduled match is present; abandoned VALORANT maps are rolled back by `series-!started-game` (drop those game IDs); a few series miss a game or `team-won-series` (derive results per game); VCT Americas 2025 positions are 1 Hz instead of ~5 Hz; team names change, so use team IDs; VALORANT series `2855902` is invalidated.

**GRID API docs:** https://docs.grid.gg/public/documentation. Not yet read (JavaScript-rendered; automated fetch returns an empty page). The starter repo's files are enough to build without the API.

## JetBrains tools

- **JetBrains Air** (https://www.jetbrains.com/air/): agentic development environment. Runs agents such as Junie, Claude Agent, Codex, Copilot, OpenCode and any ACP-compatible agent. Surfaces: JetBrains IDEs, web (air.jetbrains.cloud), CLI. In the IDE: parallel agent sessions per project, review agent diffs with IDE tools, leave line comments for the agent. Bring your own provider subscription/API key, or JetBrains AI credits. Get started: https://www.jetbrains.com/air/ides/
- **Junie**: JetBrains' coding agent (write, debug, refactor, run tests).
- **IDEs**: PyCharm (Python, data analysis), WebStorm (JS/TS dashboards), Rider (Cat 3 games with Unity, Unreal, Godot), IntelliJ IDEA, DataGrip.
- Cat 3 engines suggested: Unity, Godot, Unreal, Phaser, PixiJS.
- Keep evidence of tool use (`.idea/`, `.junie/`, `.air/`, `AI_SHOWCASE.md`) as the work happens; it feeds Stage 1, criterion 1 and the bonus prize.

## Open questions

- Category and idea choice.
- Prize split per category.
