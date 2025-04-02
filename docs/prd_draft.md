## TaxonoPy Product Requirements Document (PRD)
### 1. Introduction
#### 1.1 Purpose
This document outlines the requirements and design principles for TaxonoPy, a Python package designed to create internally consistent taxonomic hierarchies from diverse taxonomic data sources. TaxonoPy addresses the challenge of harmonizing taxonomic labels from multiple authorities into a unified, consistent dataset that preferentially maps to selected taxonomic authorities.
#### 1.2 Scope
TaxonoPy is focused specifically on taxonomic resolution through the Global Names Verifier (GNVerifier) API. It provides a framework for processing, grouping, planning, and resolving taxonomic entries across different sources to produce a standardized taxonomic hierarchy.
#### 1.3 Intended Audience
This document is intended for developers working on the TaxonoPy package, including those who may extend or maintain the resolution system in the future.
#### 1.4 Goals

- Create a taxonomic resolution system that can harmonize labels from diverse sources
- Prioritize taxonomic authorities (e.g., GBIF backbone taxonomy followed by OTOL)
- Maintain internal consistency across resolved taxonomic entries
- Provide comprehensive provenance tracking for all resolution decisions
- Support efficient batch processing of large taxonomic datasets
- Enable flexible, modular, and extensible resolution strategies

### 2. System Overview
#### 2.1 System Context
TaxonoPy operates within the context of taxonomic data harmonization for machine learning training datasets. It takes input from various taxonomic aggregators (e.g., Encyclopedia of Life, GBIF) and primary data sources (e.g., BIOSCAN, FathomNet) and produces a unified taxonomic classification aligned with preferred taxonomic authorities.
#### 2.2 User Personas

- Data Scientists: Preparing datasets for machine learning models requiring consistent taxonomic labels
- Taxonomic Researchers: Harmonizing taxonomic information across different sources
- Biodiversity Informatics Specialists: Creating standardized taxonomic references

#### 2.3 High-Level Architecture
TaxonoPy follows a modular architecture with distinct transformation stages:

1. Input Parsing: Reading taxonomic data from input files (Parquet, CSV)
2. Entry Grouping: Aggregating identical taxonomic entries to minimize API calls
3. Query Planning: Planning optimal GNVerifier queries
4. Resolution: Applying resolution strategies to match entries to standardized taxonomies based on results from GNVerifier (including handling of query retries with alternative authorities or query terms)
5. Output Generation: Producing the harmonized taxonomic dataset mirroring the input data structure

#### 2.4 Workflow Overview

1. Parse input taxonomic data into TaxonomicEntry objects
2. Group identical entries into EntryGroupRef objects
3. Plan efficient queries as QueryGroupRef objects
4. Execute GNVerifier queries and create initial ResolutionAttempt objects
5. Apply resolution strategies to determine the standardized taxonomy
6. If resolution fails, retry with alternative terms, strategies, or authorities
7. Generate output with resolved taxonomic hierarchies

### 3. Existing Components
#### 3.1 Data Model ()
The core data model consists of:

- `TaxonomicEntry`: Represents a single taxonomic entry from the input data. One `TaxonomicEntry` object corresponds to a single taxonomic label entry in the input dataset.
- `EntryGroupRef`: Groups identical taxonomic entries to minimize API calls. One `EntryGroupRef` object is assigned a unique group key based on a SHA-256 hash of the taxonomic data and corresponds to a group taxonomic entries with identical taxonomic data, where group members are referenced by a set of entry UUIDs.
- `QueryGroupRef`: Organizes entry groups by query term for efficient API usage. One `QueryGroupRef` object corresponds to a group of entry groups that share the same query term for use with the same GNVerifier data authority, where group members are referenced by a set of group SHA-256 keys.
    - As data is processed, some queries will yield successful resulotions (`ResolutionAttempt` objects with terminal `ResolutionStatus`), while others will not (`ResolutionAttempt` objects with non-terminal `ResolutionStatus`).
    - When a query fails from receiving a no-match result, a new `QueryGroupRef` object is created with a new data authority or a new query term. This is repeated until a terminal resolution status is achieved (either success or failure).
- `ResolutionAttempt`: Records a single resolution attempt and its outcome/status.
- `ResolutionStatus`: Enumerates possible statuses for resolution attempts. Contains a fine-grained indication with coarse-grained embedded metadata in the enum members like `"terminal"` or `"non-terminal"`, `"success"` or `"failure"`.

For every `TaxonomicEntry` object, there is a single entry in the input data (members static within a dataset).
For every `EntryGroupRef` object, there is a group of `TaxonomicEntry` objects (members are static within a dataset).
For every `QueryGroupRef` object, there is a group of `EntryGroupRef` objects (members are static within a dataset).
For every `EntryGroupRef` object, there may be multiple `QueryGroupRef` objects, each with a unique combination of query term derived from the `EntryGroupRef` object's taxonomic data and data authority.
For every `QueryGroupRef` object, there is a single `ResolutionAttempt` object.
For every `ResolutionAttempt` object, there is a single `ResolutionStatus`, corresponding to its `QueryGroupRef`.

To trace the provenance of a resolved taxonomic entry (or failed resolution), every UUID in an output file should be traceable back to the original input data, the query term(s) used to resolve it, and the resolution strategy that led to the final result.

#### 3.2 Input Parsing
<!-- TODO: add section -->

#### 3.3 Entry Grouping
<!-- TODO: add section -->

#### 3.4 Query Planning
<!-- TODO: add section -->

#### 3.5 Query Execution
<!-- TODO: add section -->

#### 3.6 Resolution Attempt Management
<!-- TODO: add section -->

#### 3.7 Caching System
<!-- TODO: add section -->

### 4. Resolution Strategy System Requirements 
<!-- TODO: add section -->
#### 4.x Resolution Strategy Status Logic
The `ResultionStatus` enum contains a fine-grained indication of the status of a resolution attempt, with coarser groupings embedded in the enum members.

The following coarse groups are defined:
- `"processing"`: The resolution attempt is in progress and has not yet reached a final state.
- `"terminal"`: The resolution attempt has reached a final state and is ready to be written to an output file, either success or failure.
- `"non-terminal"`: The resolution attempt is still in progress and has not yet reached a final state.
- `"success"`: The resolution attempt has successfully resolved the taxonomic entry. This is also a terminal state.
- `"failure"`: The resolution attempt has failed to resolve the taxonomic entry. This is also a terminal state.
- `"non-terminal"`: The resolution attempt is still in progress and has not yet reached a final state.
- `"retry"`: The resolution attempt is to be retried with a different query term or data authority.

<!-- TODO: decide whethe to add 'original taxonomic data' -->

The following fine-grained statuses are defined:
- `SINGULAR_EXACT_MATCH`
  - Exactly one result?
    - → "results": [ { … } ] has length 1.
  - Exact match?
    - → "matchType": "Exact" is present in both the overall response and in the result entry.
  - Accepted status?
    - → "taxonomicStatus": "Accepted" must be true.
  - Full set of classification ranks?
    - → "classificationRanks" must be exactly "kingdom|phylum|class|order|family|genus|species" (or its equivalent based on valid EntryGroupRef data).
  - Exact match of classification path?
    - → "classificationPath" must exactly match the taxonomic terms of the originating EntryGroupRef (in the same order).
  - Data source check?
    - → "dataSourceId": 11 (i.e. GBIF) is required.
  - Query consistency?
    - → The QueryGroupRef (and therefore the ResolutionAttempt) must reflect the same query term and rank as derived from the EntryGroupRef’s most specific valid taxonomic data.  

### 5. Technical Requirements
Priority levels:
- 1: Critical
- 2: Important
- 3: Nice to have
- 4: Future consideration
- 5: Undecided

Indicated in parentheses after each requirement.

#### 5.1 Performance Requirements

- Support efficient batch processing of large taxonomic datasets (1)
- Minimize redundant API calls through effective grouping and caching (1)
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

### 6. Resolution Strategy Implementation
<!-- TODO: add section -->

### 7. Edge Cases and Challenge Scenarios
<!-- TODO: add section -->

### 8. Implementation Priorities
<!-- TODO: add section -->

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
