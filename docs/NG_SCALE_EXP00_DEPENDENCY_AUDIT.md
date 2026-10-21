# EXP-00 — dependency audit of the probability/score insertion point (read-only; changes nothing)

Written at base `3a480dd9`; this is a read-only trace and decides nothing or wires nothing. The
`quant_ng` package and its wiring are proposals in the NGA plan, not adopted. The evaluator pin
classification below is read from `ops/section_5a_evaluator_pin.json:pinned_files`.

Corrected on review (2026-10-22): the first draft marked three things NOT FOUND that exist. They are
`frontend_display` and `decision_synthesis` in the response schema, and the bundle RPC that inserts
the prediction row. Their locations are now given in §2–§4. A second, independent review then found
that one sentence of that correction was false: the triplet's columns have three writers, not only
the bundle RPC. It also found two imprecise line ranges. All three are corrected (§1 row 12, §2,
§3).

## 1. Pipeline steps

`run_quant_pipeline(snapshot, provider_state, methodology_version)` validates the selector first
(`src/crypto_probability_engine/quant/pipeline.py:45-55`). “Pure” here means deterministic functions
of the supplied snapshot/settings or supplied states; `global_risk_state()` and
`calibration_state()` are ambient state reads, so are marked separately.

| # | function (file:line) | reads triplet? | reads derived? | writes | PINNED/UNPINNED |
|---|---|---|---|---|---|
| 1 | `assess_epistemic_sufficiency` (`src/crypto_probability_engine/quant/pipeline.py:56`) | No | No | epistemic state; snapshot-derived | PINNED |
| 2 | `compute_trend_mtf` (`src/crypto_probability_engine/quant/pipeline.py:57`) | No | No | trend; snapshot candles | PINNED |
| 3 | `compute_realized_volatility` (`src/crypto_probability_engine/quant/pipeline.py:58`) | No | No | volatility; snapshot candles | PINNED |
| 4 | `compute_liquidity_depth` (`src/crypto_probability_engine/quant/pipeline.py:59`) | No | No | liquidity; snapshot book | PINNED |
| 5 | `compute_volume_anomaly` (`src/crypto_probability_engine/quant/pipeline.py:60`) | No | No | volume anomaly; snapshot candles | PINNED |
| 6 | `compute_execution_realism` (`src/crypto_probability_engine/quant/pipeline.py:61`) | No | No | execution state; liquidity-derived | PINNED |
| 7 | `compute_risk_arbiter` (`src/crypto_probability_engine/quant/pipeline.py:62`) | No | No | risk arbiter; feature-derived | PINNED |
| 8a | `compute_timeout_probability`, then `compute_probability_state` (`src/crypto_probability_engine/quant/pipeline.py:63-74`; producer `src/crypto_probability_engine/quant/probability_three_state.py:45-92`) | Produces triplet | Reads volatility, risk arbiter, epistemic; produces confidence/user-normalized copies | `probability_state` H_primary/H_extended | PINNED |
| 8b | `compute_distributional_probabilities`, then `build_distributional_probability_state` (`src/crypto_probability_engine/quant/pipeline.py:75-96`; state builder `src/crypto_probability_engine/quant/probability_distributional.py:224-268`) | Produces triplet | Reads epistemic; produces confidence/user-normalized copies | `probability_state` H_primary/H_extended | PINNED |
| 9 | `compute_score_stack` (`src/crypto_probability_engine/quant/pipeline.py:97`; `src/crypto_probability_engine/score_stack/score.py:22-49`) | Yes, H_primary up/down | No | score, directional edge, initial disposition | PINNED |
| 10 | `compute_tail_cvar` (`src/crypto_probability_engine/quant/pipeline.py:98`) | No | No | tail risk; candles | PINNED |
| 11 | `global_risk_state` (`src/crypto_probability_engine/quant/pipeline.py:99`) | No | No | reads ambient risk flags | PINNED |
| 12 | `apply_composite_gates` (`src/crypto_probability_engine/quant/pipeline.py:100-109`; `src/crypto_probability_engine/gates/composite.py:43`; the skill gate `apply_skill_gate` is `:91`) | No | Yes: score; plus epistemic/provider/liquidity/tail/execution | gate result and optional forced disposition | PINNED |
| 13 | forced-disposition overlay (`src/crypto_probability_engine/quant/pipeline.py:110-115`) | No | Yes: score disposition | score disposition may be replaced by gate | PINNED |
| 14 | build feature states (`src/crypto_probability_engine/quant/pipeline.py:116-125`) | No | No | features; snapshot/ambient feature inputs | PINNED |
| 15 | `calibration_state` (`src/crypto_probability_engine/quant/pipeline.py:149`) | No | No | calibration state; ambient summary | PINNED |
| 16 | result assembly and `stable_hash(result)` (`src/crypto_probability_engine/quant/pipeline.py:139-159`) | Includes triplet | Includes score/gate/other result | pipeline result and initial hash | PINNED |
| 17 | service skill evidence gate (`src/crypto_probability_engine/api/analysis_service.py:365-370,623-645`) | No | Yes: gate and score disposition | optional gate/score disposition overlay | UNPINNED |
| 18 | presentation builders (`src/crypto_probability_engine/api/analysis_service.py:387-420`; decision brief `src/crypto_probability_engine/detail/decision_brief.py:60-125`; synthesis `src/crypto_probability_engine/detail/decision_synthesis.py:53-130`; detail `src/crypto_probability_engine/detail/builder.py:6-40`) | Synthesis reads triplet; others consume score/gate and/or copy probability | Yes | frontend display, brief, synthesis/labels, detail copies | UNPINNED |
| 19 | response assembly, response `stable_hash` (`src/crypto_probability_engine/api/analysis_service.py:422-490`) | Copies probability state | Copies derived outputs | response and authoritative response hash | UNPINNED |
| 20 | decision view (`src/crypto_probability_engine/api/analysis_service.py:476-489`; builder `src/crypto_probability_engine/detail/decision_view.py:141+`) | Receives quant result | Yes | optional decision view | UNPINNED |
| 21 | `_prediction_row` (`src/crypto_probability_engine/api/analysis_service.py:491-507,1581-1669`) | Yes, H_primary triplet | Gate/calibration/epistemic metadata | persistence row | UNPINNED |
| 22 | quant V2, feature snapshot, derivatives snapshot, persistence scheduling (`src/crypto_probability_engine/api/analysis_service.py:509-569,736-764`) | Feature snapshot starts from prediction row | Quant V2 consumes quant result | ancillary snapshots / persistence payload | UNPINNED |

## 2. Consumer table

The count reported here is 15 consumer rows (a row groups a named value and its listed downstream
call sites; repeated uses inside a function are grouped). Pipeline hashing includes the entire
assembled result by object, not a hand-picked field list
(`src/crypto_probability_engine/quant/pipeline.py:139-159`).

| value | produced at (file:line) | consumed at (file:line, each) | PINNED/UNPINNED | note |
|---|---|---|---|---|
| H_primary/H_extended `p_up_frac`, `p_down_frac`, `p_timeout_frac` | `src/crypto_probability_engine/quant/probability_three_state.py:69-89`; distributional `src/crypto_probability_engine/quant/probability_distributional.py:245-265` | score `src/crypto_probability_engine/score_stack/score.py:22-24`; frontend display `src/crypto_probability_engine/detail/frontend_display.py:234-242`; synthesis interpretation `src/crypto_probability_engine/detail/decision_synthesis.py:66-70,344+`; detail copy `src/crypto_probability_engine/detail/builder.py:38`; prediction row `src/crypto_probability_engine/api/analysis_service.py:1626-1650`; API response `src/crypto_probability_engine/api/analysis_service.py:444`; schema `schemas/quant.schema.json:13-29`; UI render `frontend/app.js:1023-1052,1808-1859` | producers PINNED; score PINNED; others UNPINNED | Authoritative serving shape is probability_state; frontend displays normalized backend fields. |
| `p_up_user_norm_frac`, `p_down_user_norm_frac` | `src/crypto_probability_engine/quant/probability_three_state.py:66-75`; distributional `src/crypto_probability_engine/quant/probability_distributional.py:239-249` | response probability_state `src/crypto_probability_engine/api/analysis_service.py:444`; schema `schemas/quant.schema.json:22-23`; no direct frontend use found | producer PINNED; downstream UNPINNED | User-normalized copies are distinct from triplet fractions. |
| `confidence_frac` (both horizons) | `src/crypto_probability_engine/quant/probability_three_state.py:75-88`; distributional `src/crypto_probability_engine/quant/probability_distributional.py:251-263` | response probability_state `src/crypto_probability_engine/api/analysis_service.py:444`; schema `schemas/quant.schema.json:17,24`; direct frontend consumer NOT FOUND | producer PINNED; downstream UNPINNED | Constant status-based copy, not recalculated in UI. |
| `news_confidence_adj_frac` | `src/crypto_probability_engine/quant/probability_three_state.py:76`; distributional `src/crypto_probability_engine/quant/probability_distributional.py:252` | response probability_state `src/crypto_probability_engine/api/analysis_service.py:444`; schema `schemas/quant.schema.json:25`; frontend consumer NOT FOUND | producer PINNED; downstream UNPINNED | Producer sets zero. |
| `directional_edge` | `src/crypto_probability_engine/score_stack/score.py:24,43-49`; synthesis probability interpretation `src/crypto_probability_engine/detail/decision_synthesis.py:344+` | score feeds gates `src/crypto_probability_engine/quant/pipeline.py:100-109`; brief action/reasons `src/crypto_probability_engine/detail/decision_brief.py:70-88,128-144`; display score disposition `src/crypto_probability_engine/detail/frontend_display.py:235-244`; synthesis labels/interpretation `src/crypto_probability_engine/detail/decision_synthesis.py:66-80,407+`; response `src/crypto_probability_engine/api/analysis_service.py:460,463`; schema `schemas/response.schema.json:81` (`score_stack`, untyped) and `:960-974` (synthesis `probability_interpretation.directional_edge`); frontend `frontend/app.js:1133,1813` | score PINNED; others UNPINNED | Edge is recomputed from triplet by synthesis (see findings). |
| `total_score` | `src/crypto_probability_engine/score_stack/score.py:26-46` | composite gate `src/crypto_probability_engine/quant/pipeline.py:100-109`; display `src/crypto_probability_engine/detail/frontend_display.py:235-244`; run summary/timeframe row `src/crypto_probability_engine/api/analysis_service.py:1739-1744,1749-1762`; repository run/timeframe SQL `src/crypto_probability_engine/persistence/repository.py:883-904,937-949`; frontend score renderer `frontend/app.js:894,931,1069` | score/repository PINNED; others UNPINNED | Derived using edge and risk pressure. |
| score `disposition` | `src/crypto_probability_engine/score_stack/score.py:37-49`; gate override `src/crypto_probability_engine/quant/pipeline.py:110-115`; skill override `src/crypto_probability_engine/api/analysis_service.py:636-645` | brief `src/crypto_probability_engine/detail/decision_brief.py:70-88,128-144`; synthesis `src/crypto_probability_engine/detail/decision_synthesis.py:74-80,103-110,407+`; frontend display `src/crypto_probability_engine/detail/frontend_display.py:235-244`; run/timeframe summaries and rows `src/crypto_probability_engine/api/analysis_service.py:1739-1744,1754-1760`; DB `src/crypto_probability_engine/persistence/repository.py:883-904,937-949` | producer/gate PINNED; service/detail UNPINNED | More than one gate can replace this value. |
| `gate_result.action`, blocks, hard-gate status | `src/crypto_probability_engine/gates/composite.py:54-111`; skill gate `src/crypto_probability_engine/api/analysis_service.py:623-645` | frontend display `src/crypto_probability_engine/detail/frontend_display.py:235-250`; brief `src/crypto_probability_engine/detail/decision_brief.py:69-88`; synthesis labels/actionability `src/crypto_probability_engine/detail/decision_synthesis.py:62-80,85-94`; detail and decision view `src/crypto_probability_engine/detail/builder.py:6-52`, `src/crypto_probability_engine/detail/decision_view.py:141+`; prediction row `src/crypto_probability_engine/api/analysis_service.py:1662-1664`; response/hash `src/crypto_probability_engine/api/analysis_service.py:466,490`; persisted run/timeframe `src/crypto_probability_engine/api/analysis_service.py:1739-1760` | composite PINNED; other files UNPINNED | Derived decision path also reads score and non-probability gates. |
| `frontend_display.prob_*_pct` | `src/crypto_probability_engine/detail/frontend_display.py:234-242` | response `src/crypto_probability_engine/api/analysis_service.py:464`; schema `schemas/response.schema.json:43` (required) and `:146` (`{"type": "object"}`: its fields are not constrained by the schema); frontend `frontend/app.js:894-950,2331+` | UNPINNED | Percent copies directly scale triplet by 100. |
| `decision_synthesis.probability_interpretation` (edge, directional balance, resolution probability, label) | `src/crypto_probability_engine/detail/decision_synthesis.py:66-80,344+` | response `src/crypto_probability_engine/api/analysis_service.py:463`; frontend `frontend/app.js:1064-1140,1808-1859,2216+`; schema `schemas/response.schema.json:962-974` | UNPINNED | Probability interpretation and synthesis labels are separate derived copies. |
| decision brief action/state | `src/crypto_probability_engine/detail/decision_brief.py:77-109,128-144` | detail builder `src/crypto_probability_engine/detail/builder.py:33`; response `src/crypto_probability_engine/api/analysis_service.py:462`; synthesis input `src/crypto_probability_engine/detail/decision_synthesis.py:53-80`; frontend display `frontend/app.js:1064+`; schema response detail fields | UNPINNED | Reads gate and score disposition, not raw triplet. |
| `detail_view.probability_detail`, `score_detail` | `src/crypto_probability_engine/detail/builder.py:33-40` | response hash `src/crypto_probability_engine/api/analysis_service.py:490`; detail persistence payload `src/crypto_probability_engine/api/analysis_service.py:736-764`; schema response detail_view property `schemas/response.schema.json:44` (required) and `:147` (`$ref detail_view.schema.json`); frontend `frontend/app.js:1390-1396` (the whole view) | UNPINNED | Copies full probability and score objects. The frontend takes the whole detail view (`frontend/app.js:1390-1396`, from `/v1/analyze/detail/{run_id}` or the response's `detail_view`); no frontend code names `probability_detail` or `score_detail`. |
| `analysis_hash` (pipeline result) | `src/crypto_probability_engine/quant/pipeline.py:158` | carried in quant result and replaced by service response hash; see `src/crypto_probability_engine/api/analysis_service.py:490`; response consumers `src/crypto_probability_engine/api/analysis_service.py:471-474`; persistence summary/details `src/crypto_probability_engine/api/analysis_service.py:1728-1745,736-764` | pipeline PINNED; service UNPINNED | Pipeline hash digests all `result`; service hash digests full response with blank hash field. |
| persisted prediction triplet | `_prediction_row` `src/crypto_probability_engine/api/analysis_service.py:1626-1650` | pending row and persistence bundle `src/crypto_probability_engine/api/analysis_service.py:563-569,1064,1103-1148`; repository `src/crypto_probability_engine/persistence/repository.py:116-127,328-338`, `rpc/save_forecast_bundle` `:1839-1873` and `rpc/save_prediction_bundle` `:1798-1825`; SQL `migrations/0017_forecast_bundle_rpc.sql:56` calls `save_prediction_bundle` at `:171`, which inserts the row at `migrations/0015_prediction_bundle_rpc.sql:130` (triplet columns `:132-133`, values `:142-143`); the fallback `repository.save_prediction` (`src/crypto_probability_engine/api/analysis_service.py:1175`; used for OOS `oosb-` rows and for repositories without the bundle RPCs) writes the row through `SupabaseRestRepository.save_prediction` (`src/crypto_probability_engine/persistence/repository.py:1764-1796`, a REST insert into `predictions`) or `SupabasePersistenceRepository.save_prediction` (`:1056-1073`, via `_insert_prediction`, `:3081-3110`) | service UNPINNED; repository PINNED; migrations unpinned | The row mapping is passed through unchanged. Three writers set the triplet's columns: the 0015 function and the two repositories' `save_prediction` (corrected on review: an earlier version of this note said "only the 0015 function", which was false). |
| confidence/disposition copies in downstream labels | probability producer and score/gate as above | `src/crypto_probability_engine/detail/decision_synthesis.py:74-80,103-119`; frontend renderers `frontend/app.js:1064-1140,1819-1869` | UNPINNED | Reliability/calibration also conditions interpretation; labels cannot be kept coherent by swapping triplet alone. |

## 3. Persistence and hash

* Pipeline hash: `stable_hash(result)` at `src/crypto_probability_engine/quant/pipeline.py:158`
  serializes the complete `result` assembled at lines 139-157. That includes the full probability
  state (both horizons and confidence/user-normalized fields), score stack (including edge and
  disposition), gate result, and all other assembled states.
* Served hash: `stable_hash(response)` at
  `src/crypto_probability_engine/api/analysis_service.py:490` is the returned `analysis_hash`; the
  response object includes `probability_state`, `score_stack`, `gate_result`, `decision_brief`,
  `decision_synthesis`, `frontend_display`, `detail_view`, and optionally `decision_view` (assembly
  `src/crypto_probability_engine/api/analysis_service.py:422-490`). The initial empty hash field is
  part of the hashed mapping; the resulting value replaces it.
* Prediction row: `_prediction_row` reads exactly H_primary `p_up_frac`, `p_down_frac`,
  `p_timeout_frac` at `src/crypto_probability_engine/api/analysis_service.py:1626-1650`. It also
  persists decision band, methodology version, calibration/reliability/epistemic status, and gate
  action at lines 1651-1668. It does not persist total_score or directional_edge in this row.
* Run summary uses `disposition`, `total_score`, and `analysis_hash` from response at
  `src/crypto_probability_engine/api/analysis_service.py:1728-1745`; DB columns and parameters are
  `disposition`, `total_score`, `analysis_hash` at
  `src/crypto_probability_engine/persistence/repository.py:883-904`.
* Timeframe result uses `disposition`, `total_score`, `prob_up_pct`, `prob_down_pct`,
  `prob_timeout_pct`, `gate_action` at
  `src/crypto_probability_engine/api/analysis_service.py:1749-1762`; repository SQL writes those
  values at `src/crypto_probability_engine/persistence/repository.py:932-949`.
* Detail payload persistence includes response `analysis_hash` and sanitized `detail_view` at
  `src/crypto_probability_engine/api/analysis_service.py:736-764`; repository stores `analysis_hash`
  and JSON detail payload at `src/crypto_probability_engine/persistence/repository.py:909-930`.
* Forecast-bundle calls pass the complete prediction row and snapshots. The service prefers
  `save_forecast_bundle` (`src/crypto_probability_engine/api/analysis_service.py:1064`) and falls
  back to `save_prediction_bundle` (`:1103-1148`). The repository posts `rpc/save_forecast_bundle`
  (`src/crypto_probability_engine/persistence/repository.py:1839-1873`) or
  `rpc/save_prediction_bundle` (`:1798-1825`). In SQL, `public.save_forecast_bundle`
  (`migrations/0017_forecast_bundle_rpc.sql:56`) writes `analysis_runs` (`:117`) and
  `analysis_run_details` (`:151`), then calls `public.save_prediction_bundle` (`:171`), which
  inserts the prediction row (`migrations/0015_prediction_bundle_rpc.sql:130`). When neither bundle
  applies (OOS `oosb-` rows, or a repository without the bundle RPCs), the service falls back to
  `repository.save_prediction` (`src/crypto_probability_engine/api/analysis_service.py:1175`), which
  writes the row through the REST repository
  (`src/crypto_probability_engine/persistence/repository.py:1764-1796`) or the Postgres repository
  (`:1056-1073`, `_insert_prediction` at `:3081-3110`). No request here ran a DB or workflow.

## 4. Response schema and frontend

* `schemas/response.schema.json:22,65` exposes `probability_state` via
  `schemas/quant.schema.json#/properties/probability_state`; that schema defines both arbitrary
  horizon triplets and confidence/user-normalized fields at `schemas/quant.schema.json:13-29`.
* `schemas/response.schema.json:38-47` lists `score_stack`, `decision_brief`, `frontend_display`,
  `detail_view`, `gate_result`, and `analysis_hash` as required. `score_stack` (`:81`) and
  `frontend_display` (`:146`) are untyped objects: the schema does not constrain their fields.
  `decision_synthesis` (assembled at
  `src/crypto_probability_engine/api/analysis_service.py:462-465`) is a property at `:138` referring
  to `$defs/decisionSynthesis` (`:908` onward), whose `probability_interpretation` carries `p_up`,
  `p_down`, `p_timeout` and `directional_edge` (around `:960-974`).
* `frontend/app.js:418` explicitly says renderer recomputes nothing. It reads backend score/display
  at lines 894-950, backend probability interpretation at 1064-1140 and 1819-1869, probability
  display fields via `matrixRawProbability` / `matrixProbabilityBlock` at 1023-1055, and edge at
  1133 and 1813. No probability formula recomputation found in the frontend search.
  `getScoreHeatBand` (`frontend/app.js:388-394`) maps an existing score to a display band; it does
  not recalculate score.

## 5. Findings

1. Swapping only the triplet after the served pipeline is incoherent: `compute_score_stack` has
   already derived directional edge, total score, and disposition at
   `src/crypto_probability_engine/quant/pipeline.py:97` /
   `src/crypto_probability_engine/score_stack/score.py:22-49`. Composite gates consume that score at
   `src/crypto_probability_engine/quant/pipeline.py:100-109`; the pipeline may overwrite score
   disposition afterward at lines 110-115. A later service skill gate may overwrite it again at
   `src/crypto_probability_engine/api/analysis_service.py:623-645`.
2. Presentation derives further copies before response hashing: frontend percentage fields are
   multiplied from H_primary at `src/crypto_probability_engine/detail/frontend_display.py:234-244`;
   decision synthesis reads raw probability to build interpretation and labels at
   `src/crypto_probability_engine/detail/decision_synthesis.py:62-80,344+`; decision brief reads
   score and gates at `src/crypto_probability_engine/detail/decision_brief.py:69-88`. Detail view
   copies both probability and score at `src/crypto_probability_engine/detail/builder.py:33-40`. All
   such artifacts are included in the response hash
   (`src/crypto_probability_engine/api/analysis_service.py:422-490`).
3. Persistence is another branch: prediction row copies H_primary only at
   `src/crypto_probability_engine/api/analysis_service.py:1626-1650`; run/timeframe/detail
   persistence carry score, display probabilities, gate action, hash, or detail copies at
   `src/crypto_probability_engine/api/analysis_service.py:1728-1762,736-764` and
   `src/crypto_probability_engine/persistence/repository.py:883-949`. A triplet replacement must
   precede and feed every branch, or regenerate all branches coherently.
4. Probability recomputation outside `run_quant_pipeline` found only in read-only decision
   interpretation: `src/crypto_probability_engine/detail/decision_synthesis.py:344+` derives edge
   and related interpretation from the triplet;
   `src/crypto_probability_engine/detail/frontend_display.py:234-242` scales it for display. These
   are backend presentation derivations. Frontend recomputation: **NOT FOUND**; it renders backend
   values (`frontend/app.js:418`).
5. Separate from the probability producer, `analysis_hash` is computed twice: the pipeline hash at
   `src/crypto_probability_engine/quant/pipeline.py:158` and the authoritative response hash at
   `src/crypto_probability_engine/api/analysis_service.py:490`. Persisted run/detail artifacts bind
   to the latter (`src/crypto_probability_engine/api/analysis_service.py:1744,736-764`). Both hashes
   and their distinct payloads matter to a future insertion point.
6. Relevant evaluator-pinned implementation files are the two probability modules, pipeline, score
   stack, composite gate, and repository (`ops/section_5a_evaluator_pin.json:pinned_files`). The
   service, detail builders, schemas, and frontend are unpinned by that manifest. A future change
   limited to pinned producer code would therefore leave known unpinned consumers stale.

