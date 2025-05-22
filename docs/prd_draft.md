## TaxonoPy Product Requirements Document (PRD)
### 1. Introduction
#### 1.1 Purpose
This document outlines the requirements and design principles for TaxonoPy, a Python package designed to create internally consistent taxonomic hierarchies from diverse
taxonomic data sources. TaxonoPy addresses the challenge of harmonizing taxonomic labels from multiple authorities into a unified, consistent dataset that preferentially
maps to selected taxonomic authorities.
#### 1.2 Scope
TaxonoPy is focused specifically on taxonomic resolution through the Global Names Verifier (GNVerifier) API. It provides a framework for processing, grouping, triggering queries for,
and resolving taxonomic entries across different sources to produce a standardized taxonomic hierarchy.
#### 1.3 Intended Audience
This document is intended for developers working on the TaxonoPy package, including those who may extend or maintain the resolution system in the future.
#### 1.4 Goals

- Create a taxonomic resolution system that can harmonize labels from diverse sources.
- Prioritize taxonomic authorities (e.g., GBIF backbone taxonomy followed by OTOL) through configurable retry logic.
- Maintain internal consistency across resolved taxonomic entries.
- Provide comprehensive provenance tracking for all resolution decisions via immutable attempt chains.
- Support efficient processing of large taxonomic datasets by minimizing redundant input processing and allowing for efficient API query execution.
- Enable flexible, modular, and extensible resolution strategies based on unique "fingerprints".

### 2. System Overview
#### 2.1 System Context
TaxonoPy operates within the context of taxonomic data harmonization for machine learning training datasets. It takes input from various taxonomic aggregators (e.g.,
Encyclopedia of Life, GBIF) and primary data sources (e.g., BIOSCAN, FathomNet) and produces a unified taxonomic classification aligned with preferred taxonomic
authorities.
#### 2.2 User Personas

- Data Scientists: Preparing datasets for machine learning models requiring consistent taxonomic labels.
- Taxonomic Researchers: Harmonizing taxonomic information across different sources.
- Biodiversity Informatics Specialists: Creating standardized taxonomic references.

#### 2.3 High-Level Architecture
TaxonoPy follows a modular architecture with distinct systems:

1.  **Input Parsing:** Reading taxonomic data from input files (Parquet, CSV) into `TaxonomicEntry` objects.
2.  **Entry Grouping:** Aggregating identical taxonomic entries into `EntryGroupRef` objects. Each `EntryGroupRef` represents a unique input taxonomic profile.
3.  **Query System (`query/`):** Responsible for *planning* (initial and retry) and *executing* unique GNVerifier queries efficiently.
    *   `query.planner`: Determines *what* query parameters (`QueryParameters`) are needed initially or for retries based on `EntryGroupRef` data and `ResolutionAttempt` history.
    *   `query.executor`: Takes requests for queries, identifies unique parameter sets, batches them, calls `GNVerifierClient`, parses results, and maps results back to the requesting `EntryGroupRef` keys.
    *   `query.client`: Interacts with the GNVerifier API/tool.
4.  **Resolution System (`resolution/`):** Responsible for interpreting results and driving the resolution process for each `EntryGroupRef`.
    *   `ResolutionAttemptManager`: Orchestrates the overall flow, manages the state (latest `ResolutionAttempt` for each `EntryGroupRef`), applies classification cases, and interacts with the Query System for data fetching.
    *   `resolution.strategy.modes`: Contains modules, each implementing a `check_and_resolve` function for a specific resolution fingerprint. These functions determine the final status or request a retry via the Query System.
5.  **Output Generation (`output_manager.py`):** Produces the harmonized taxonomic dataset (`*.resolved.*`, `*.unsolved.*`) based on the final resolution status stored by the `ResolutionAttemptManager`.

#### 2.4 Workflow Overview

1.  **Parse & Group:** Input data -> `TaxonomicEntry` -> `EntryGroupRef` map (Cached).
2.  **Initialize:** Create `ResolutionAttemptManager` and `GNVerifierClient`.
3.  **Orchestration (in `ResolutionAttemptManager.resolve_all_entry_groups`):**
    *   **Initial Query:**
        *   Call `query.planner.plan_initial_queries(entry_group_map)` -> `initial_plans: Dict[str, QueryParameters]`.
        *   Call `query.executor.execute_queries(initial_plans, client)` -> `initial_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]]`.
        *   Call `manager.create_initial_attempts(initial_results)` -> Creates first `ResolutionAttempt` (status `PROCESSING`) for each `EntryGroupRef`, storing params used and response.
    *   **Resolution Loop:** Continue while retries are scheduled or attempts are processing:
        *   **Classify:** `manager.classify_pending_attempts(entry_group_map)` applies `check_and_resolve` cases to `PROCESSING` attempts.
            *   Cases either return a *new* attempt with a **terminal status** (Success/Failure).
            *   Or, if a retry is needed (e.g., NoMatch), they call `query.planner.plan_retry_query` and create a *new* attempt with status **`RETRY_SCHEDULED`**, storing the planned `QueryParameters` for the next step.
        *   **Collect Retries:** `manager.get_scheduled_retries()` gathers `(eg_key, next_query_params)` for all attempts currently in `RETRY_SCHEDULED` state.
        *   **If No Retries:** Break loop.
        *   **Execute Retries:** Call `query.executor.execute_queries(retries_to_schedule, client)` -> `retry_results`.
        *   **Apply Retry Results:** `manager.apply_retry_results(retry_results)` creates the *next* attempt (status `PROCESSING`) in the chain for each `eg_key`, attaching the new response and linking to the `RETRY_SCHEDULED` attempt via `previous_key`.
4.  **Generate Output:** Use the final state in the `ResolutionAttemptManager` to write `resolved`/`unsolved` files.

### 3. Existing Components
#### 3.1 Data Model (`types/data_classes.py`)
Immutable dataclasses:

-   `TaxonomicEntry`: Raw input data + `uuid`.
-   `EntryGroupRef`: Groups identical `TaxonomicEntry` objects. Represents unique input taxonomy. Has `.key`, taxonomic fields, `entry_uuids`. Central unit for resolution tracking.
-   `QueryParameters`: Simple dataclass holding `term`, `rank`, `source_id` for a specific API query request. Used transiently by Query System and contents stored in `ResolutionAttempt` if needed for retry planning.
-   `ResolutionStatus`: Enum for outcomes (e.g., `PROCESSING`, `EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED`, `EMPTY_INPUT_TAXONOMY`, `RETRY_SCHEDULED`, `NO_MATCH_RETRIES_EXHAUSTED`, `FAILED`). Has helper properties (`is_successful`, etc.). Values are unique tuples `(name, (groups...))`.
-   `ResolutionAttempt`: Records one step in the resolution chain *for a specific `EntryGroupRef`*. Contains:
    *   `entry_group_key`: Links back to the `EntryGroupRef`.
    *   `query_term_used`, `query_rank_used`, `data_source_id_used`: Params that generated this attempt's response.
    *   `status`, `resolved_classification`, `gnverifier_response`, `error`, `resolution_strategy_name`, `failure_reason`.
    *   `previous_key`: Links to the prior attempt *in the same chain*.
    *   `scheduled_query_params`: Stores the *next* `QueryParameters` if `status` is `RETRY_SCHEDULED`.
    *   `metadata`: For non-essential info.
    *   `.key`: Unique SHA256 hash.

**Relationships:**
*   Input Row -> `TaxonomicEntry` (1:1)
*   `TaxonomicEntry` -> `EntryGroupRef` (N:1)
*   `EntryGroupRef` -> `ResolutionAttempt` Chain (1:N, tracked by manager via `EntryGroupRef.key` -> latest `Attempt.key`, linked by `previous_key`)
*   `ResolutionAttempt` (if `RETRY_SCHEDULED`) -> `QueryParameters` (1:1, stored in `scheduled_query_params`)
*   `QueryParameters` (unique set needed) -> API Call (N:1, via Query Executor batching)
*   API Call Result -> `ResolutionAttempt` (1:N distribution, creating next step in relevant chains)

Provenance Trace: Output `uuid` -> `TaxonomicEntry` -> `EntryGroupRef` (via map) -> Final `ResolutionAttempt` (via manager state) -> Trace back chain via `previous_key`. Each attempt shows parameters used, response, and strategy name.

To trace the provenance of a resolved taxonomic entry (or failed resolution), every UUID in an output file should be traceable back to the original input data, the query term(s) used to resolve it, and the resolution strategy that led to the final result.

#### 3.2 Input Parsing (`input_parser.py`)
<!-- TODO: add section -->

#### 3.3 Entry Grouping (`entry_grouper.py`)
<!-- TODO: add section -->

#### 3.4 Query Planning (`query/planner.py`)
*   `plan_initial_queries`: Determines first `QueryParameters` for each `EntryGroupRef`.
*   `plan_retry_query`: Determines the *next* `QueryParameters` based on current attempt, history (via manager access), and `EntryGroupRef` data, following precedence rules. Returns `None` if retries exhausted.

#### 3.5 Query Execution (`query/executor.py`)
*   `execute_queries`: Takes a dictionary mapping `EntryGroupRef.key` -> `QueryParameters`. Identifies unique `QueryParameters`, batches them to submit to `client`, calls `client`, parses results, distributes results back into a dictionary mapping `EntryGroupRef.key` -> `(params_used, response)`. Handles API errors/mismatches.

#### 3.6 Resolution Attempt Management & Classification (`resolution/attempt_manager.py`)
*   Central orchestrator (`resolve_all_entry_groups`).
*   Manages state (`_entry_group_latest_attempt`, `_all_attempts`).
*   Integrates with Query System (calls planner, executor).
*   Applies classification cases (`classify_pending_attempts`).
*   Creates all `ResolutionAttempt` objects via `create_attempt`.

#### 3.7 Caching System (`cache_manager.py`)
<!-- TODO: add section -->
cache pre-processing

### 4. Resolution Strategy System Requirements
(Focus on Fingerprint model)
-   System allows defining distinct resolution "fingerprints".
-   Each fingerprint maps to a deterministic outcome (`ResolutionStatus` or request for retry).
-   Modular implementation via `check_and_resolve` functions in `resolution/strategy/modes/`.
-   Unhandled fingerprints result in `UNSOLVED` output (via `PROCESSING` or `FAILED` status).
-   Clear provenance via `ResolutionAttempt.resolution_strategy_name` and chain.

#### 4.x Resolution Strategy Status Logic
(`ResolutionStatus` enum defines outcomes. Add `RETRY_SCHEDULED`, `NO_MATCH_RETRIES_EXHAUSTED`).

### 5. Technical Requirements
Priority levels:
- 1: Critical
- 2: Important
- 3: Nice to have
- 4: Future consideration
- 5: Undecided

#### 5.1 Performance Requirements
- Support efficient processing and Minimize redundant API calls through effective grouping and caching (2). `EntryGroupRef` deduplication of calls to GNVerifier significantly and sufficiently improves efficiency. No need to batch `QueryParameter` objects.
- Trustworthiness of results through logs, cache (for tracing), clear case definitions, etc. (1)
- Support parallel processing where applicable (4)
- Maintain reasonable memory usage even with large datasets (3)

#### 5.2 Caching Requirements

- Cache GNVerifier results to avoid redundant API calls (1)
- Use content-based invalidation to ensure cache freshness (2)
- Support configuration of cache parameters (size, expiration) (3)
- Provide diagnostics for cache performance (2)

#### 5.3 Error Handling Requirements

- Gracefully handle and recover from API errors (1)
- Record detailed diagnostics for resolution failures (1)
- Provide clear error messages for debugging (2)
- Implement retry mechanisms for transient failures (3)

#### 5.4 Logging and Diagnostics

- Comprehensive logging of resolution process (1)
- Detailed metadata recording for all resolution decisions (1)
    - Enables provenance tracing of objects from raw input entries to resolved output entries with
      metadata about the resolution process
    - Accomplished through `TaxonomicEntry`, `EntryGroupRef`, `QueryGroupRef`, and `ResolutionAttempt` objects linked
      through keys  
- Statistical reporting on resolution outcomes (2)
- Support for debugging complex resolution scenarios (1)
    - To be accomplished through decoupling resolution strategies applied to `ResolutionAttempt` objects
      from other methods such as reading inputs, planning queries, and writing outputs.

#### 5.5 Testing Requirements

- Comprehensive unit tests for all resolution strategies (4)
- Integration tests for the complete resolution workflow (4)
- Test cases for challenging taxonomic resolution scenarios (1)
- Performance benchmarks for optimization (3)

### 6. Fingerprint-Based Resolution Design
For resolution, we plan to implement a series of specific cases that seek to match instances of the following data in relationship among each other within a `ResolutionAttempt` object:
- The input entry taxonomic data (hierarchy and scientific name)
- The query rank and term used for a GNVerifier call
- The full GNVerifier response

Depending on the facts of the contents and relationships among these data, we can develop logical assertions that, when true, ascribe a definitive status to the entry/resolution.

In this manner, fine-grained resolution assessments may be made to assign equally fine-grained statuses, supporting incremental coverage of cases encountered from the input data.

Ideally, a maximal number of input entries can be moved into a status indicating both 'terminal' and 'success', prioritizing implementation of cases with the greatest coverage.

If entries represented by a `ResolutionAttempt` object are not matched to any defined cases, they are written to an output of `*.unsolved.parquet` for further investigation and generation of a new resolution case to meet the need of that set of entries.

#### 6.1 Core Components
1.  **Case Modules (`resolution/strategy/modes/*.py`):** Implement `check_and_resolve` for one fingerprint.
2.  **`check_and_resolve` Function:** Signature `(attempt, entry_group, manager)`. Checks fingerprint. If no match, returns `None`. If match:
    *   For **terminal outcome**: Performs action, calls `manager.create_attempt` with final status, returns new attempt.
    *   For **retry**: Calls `query.planner.plan_retry_query`. If params returned, calls `manager.create_attempt` with `RETRY_SCHEDULED` status storing next params, returns new attempt. If `None` returned (exhausted), calls `manager.create_attempt` with `NO_MATCH_RETRIES_EXHAUSTED` status, returns new attempt.
3.  **Condition/Action Helpers:** Optional, reusable logic.
4.  **`ResolutionAttemptManager.resolve_all_entry_groups`:** Orchestrates the overall flow, including calls to Query System and the classification loop.
5.  **`CLASSIFICATION_CASES` List (`resolution/attempt_manager.py`):** Ordered list of `check_and_resolve` function references. First match wins.

#### 6.2 Adding a New Resolution Case
1.  Define Fingerprint (set of assertions about data in `ResolutionAttempt`) & Target Status (or Retry Need). Add new corresponding `ResolutionStatus`.
2.  Create Case Module (`modes/*.py`).
3.  Implement `check_and_resolve`: check fingerprint; if match, perform action, call planner if retry needed, call `manager.create_attempt` with appropriate status/data, return new attempt.
4.  Register Case Function in `CLASSIFICATION_CASES` list in `attempt_manager.py`.

#### 6.3 Handling Unmatched Cases
Attempts left `PROCESSING` after classification loop finishes will result in `UNSOLVED` output. Can add a default final case to assign `FAILED` explicitly.

### 7. Edge Cases and Challenge Scenarios
<!-- TODO: add section -->

### 8. Implementation Priorities
1.  **Refactor Core:** Implement revised data model (`ResolutionAttempt`, `QueryParameters`), overhaul `ResolutionAttemptManager` (state, `create_attempt`, `resolve_all_entry_groups`), refactor `query` module (`planner`, `executor`), adapt `cli.py`, `output_manager.py`. (Current Task)
2.  Adapt existing case modules (`empty_input`, `exact_match_primary_source_accepted`) to new `check_and_resolve` signature and interaction with planner/manager.
3.  Implement `NO_MATCH_NONEMPTY_QUERY` case using `plan_retry_query` and `RETRY_SCHEDULED`/`NO_MATCH_RETRIES_EXHAUSTED` statuses.
4.  Implement further cases (synonyms, homonyms, etc.).

### 9. Success Criteria
#### 9.1 Functional Success

- Successfully resolve 90% of input taxonomic labels--i.e. Over 90% of input entries are written to a *.resolved.parquet file and up to 10% are written to a *.unsolved.parquet file
- Linked objects can be traced along a graph of the following data, preserving provenance for all resolution decisions:
    - input Parquet file (`<input-filename>.parquet`)
    - `TaxonomicEntry` objects
    - `EntryGroupRef` objects
    - `QueryGroupRef` objects
    - `ResolutionAttempt` objects
    - output Parquet file (`<input-filename>.resolved.parquet` or `<input-resolved>.unsolved.parquet`)

#### 9.2 Technical Success

- Modular, extensible resolution strategy system which can be be extended or modified in just the `resolution/` module
- Clear, well-documented strategy interfaces
- Efficient processing of large datasets
- Comprehensive testing coverage

#### 9.3 Usability Success

- Clear docs for using the CLI and using the outputs (output files and cached objects)
- Clear documentation for extending the system
- Example strategies for reference implementation
- Detailed logging and diagnostics
- Straightforward configuration options
