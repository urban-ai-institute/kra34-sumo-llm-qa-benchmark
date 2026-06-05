# NetTrafficQA — 4-page Structure

> ACM sigconf two-column. 4-page hard cap (main + appendix combined).
> Refs/GenAI Disclosure 별도 페이지.
> Total prose budget after figures/tables: ~2000–2400 words.

Three scaffolding conditions: **SUMO XML / JSON / Tool-Use**.

---

## Page-level layout (target)

| Page | Section | Words | Notes |
|---|---|---|---|
| 1 (top) | Title, abstract, keywords, CCS | — | Standard. Abstract = 4 sentences, ~120 words. |
| 1 (rest) | §1 Introduction | ~450 | Drafted. |
| 2 (top) | §2 Benchmark | ~600 | Includes Table 1 (Networks), Table 2 (27-type matrix), Figure 1 (prompt example). Spans p.2 mostly. |
| 2–3 | §3 Experimental Setup | ~150 | Compact. Just model, sampling, max_tokens, sample size, runtime, cost. |
| 3 | §4 Results | ~700 | Table 3 (headline accuracy: 3 conditions × 7 categories). Most analytical content. |
| 4 (top) | §5 Discussion + Conclusion | ~350 | 3 paragraphs: Tool advantage, XML ≈ JSON surprise, limitations + implications. |
| 4 (bottom) | GenAI Disclosure | ~80 | Required. |
| (separate) | References | — | Unlimited pages. |

**Total prose: ~2330 words**.

---

## Figures & Tables (3 total — keep tight)

### Table 1 — Networks (small, 4 rows)
| Network | Junctions | Edges | Provenance |
|---|---|---|---|
| grid_8x8 | 64 | 224 | Synthetic (regular) |
| random | 100 | 280 | Synthetic (chaotic) |
| times_square | 229 | 264 | Real-world (OSM) |

**Page**: 2, top of §2.2. Width: single column.

### Table 2 — Question type matrix (27 rows)
Rows = 27 types grouped by category (Network 8 / Demand 6 / Output 8 / Cross 5).
Cols = templated question text + 4 file checkmarks (net / rou / tripinfo / netstate).
L/R columns removed; placeholders ({E}, {V}, {J}, {A,B}, {t1,t2}) explained in caption.

**Page**: 2, §2.3. Width: full text width (`table*`).

### Figure 1 — Side-by-side prompt example (3 conditions)
One question shown under SUMO XML / JSON / Tool-Use side by side.
Currently a placeholder `\fbox`.

**Page**: 2, end of §2.4. Width: single column.

### Table 3 — Headline accuracy (8 rows × 3 cols)
Rows = 7 categories (net-L, net-R, demand-L, demand-R, output-L, output-R, cross) + Overall.
Cols = SUMO XML / JSON / Tool-Use. Cells = % accuracy averaged over 3 networks.
File: `Tables/headline_accuracy.tex` (already populated with real numbers).
**Currently not \input from §4** — bring back once §4 prose is drafted.

**Page**: 3, top of §4. Width: single column.

---

## Per-section weight (확정)

### §1 Introduction (~450 words, 0.75 page) — drafted
- ¶1: SUMO + LLM systems context (AgentSUMO/ChatSUMO/SUMO-MCP).
- ¶2: Gap (TrafficNetQA = net.xml only / production systems sidestep).
- ¶3: Approach (file-type axis × scaffolding axis).
- ¶4: Findings preview (lookup OK, reasoning fails, JSON null).
- Bullet list: 3 contributions.

### §2 Benchmark (~600 words, 1.0 page) — drafted
- 2.1 SUMO files and networks (Table 1).
- 2.2 Questions (Table 2 + 4 sentences).
- 2.3 Scaffolding conditions (Figure 1 + 3 paragraphs).
- (Ground-truth + evaluation moved into §3.)

### §3 Experimental Setup (~150 words, 0.25 page) — outline
- Model: Claude Sonnet 4.6.
- Sampling: default temperature, max_tokens (1024 in-context / 4096 tool).
- Tool agent: 10-turn budget, 60s code timeout, persistent Python session.
- Ground-truth and evaluation paragraph.
- Sample sizes: 5 / type / network = 405 / condition × 3 = 1{,}215 total.
- Runtime + cost note.

### §4 Results (~700 words, 1.5 pages) — TODO prose
Numbers (from `evaluate.py`):
- Overall: XML 76.3 / JSON 77.8 / Tool 98.5.
- 4.1 Headline (Table 3 — input here).
- 4.2 Lookup vs. Reasoning: in-prompt Lookup ~99%, Reasoning ~60%.
  Tool Lookup 100%, Reasoning 97.5%.
- 4.3 Tool advantage source: avg_route_length_in_window +93pp,
  shortest_path_edge_removal +73pp, vehicles_passing_edge +60pp, etc.
- 4.4 The XML ≈ JSON null: 76.3% vs 77.8% (≈ 1.5 pp). Reformatting to JSONL
  does not improve over raw XML; hierarchical layout already exploited.

### §5 Discussion + Conclusion (~350 words, 0.5 page) — outline
- ¶1: When does Tool-Use help? — large-scale enumeration / cross-file.
- ¶2: Surprising null on JSON — implication for prior work claims.
- ¶3: Limitations + implications for ChatSUMO / AgentSUMO / SUMO-MCP.

### GenAI Disclosure (~80 words) — TODO
- Claude Code used for: scaffolding code drafting, prose polish.
- All numerical results from deterministic Python scripts.
- Authors verified all generated code and prose.

---

## Cuts available (priority order if over 4 pages)
1. Compress Table 2 to category-level rather than type-level.
2. Compress Setup to 100 words.
3. Drop Discussion ¶3 limitations (move to single sentence).
