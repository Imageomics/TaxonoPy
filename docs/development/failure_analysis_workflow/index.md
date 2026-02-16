# Failure Analysis Workflow

A significant portion of TaxonoPy development involves understanding *why* certain taxonomic resolutions fail and whether those failures are expected, data-driven, or indicative of missing strategy coverage.

This workflow was developed during large-scale resolution of the **EOL dataset**, but applies broadly to other sources.

---

## 1. Identify Failed Resolution Entries

Start by locating entries marked as failed in resolved Parquet outputs.
A common failure status encountered during analysis is:

* `FAILED_FORCED_INPUT`

Example command:

```bash
parquet cat <resolved_parquet_files> \
  | grep FAILED_FORCED_INPUT \
  | head \
  | jq
```

This step yields candidate UUIDs for deeper inspection.

---

## 2. Compare Raw Input vs. Final Resolution

For each failed UUID, compare the **raw input taxonomy** with the **final resolved output**.

Typical fields to inspect include:

* `scientific_name`
* `kingdom` → `genus`
* `source_dataset`
* `resolution_status`
* `resolution_strategy`

This comparison often reveals inconsistencies in the input taxonomy (e.g., genus assignments that differ from authoritative sources).

---

## 3. Trace Resolution Decisions

Use the `trace` command to inspect how TaxonoPy attempted to resolve the entry and why it failed.

Example:

```bash
taxonopy --cache-dir <cache_directory> \
  trace entry \
  --uuid "<UUID>" \
  --from-input <source_dataset_directory> \
  --verbose
```

The trace output provides:

* grouping information
* query plan (term, rank, source)
* resolution strategies attempted
* explicit failure reasons
* metadata used for match selection

---

## 4. Verify Against External Authorities (GNVerifier)

To determine whether a failure is due to missing data or genuine ambiguity,
independently verify the same taxonomic name using **Global Names Verifier**.

=== "CLI / Alias Usage"

    ```bash
    gnverifier -j 1 \
      --format compact \
      --capitalize \
      --all_matches \
      --sources 11 \
      "<scientific_name>" | jq
    ```

    This approach uses the GNVerifier command-line tool directly and is
    suitable for shell-based workflows and batch inspection.

=== "API Usage (Programmatic)"

    ```bash
    curl -X POST "https://verifier.globalnames.org/api/v1/verifications" \
      -H "Content-Type: application/json" \
      -d '{
            "names": ["<scientific_name>"],
            "capitalize": true,
            "sources": [11]
          }' | jq
    ```

    This method uses the GNVerifier HTTP API and is appropriate for
    integration into automated pipelines or custom applications.

---

This step confirms whether multiple accepted records exist in authoritative
sources such as GBIF.

## 5. Common Failure Pattern: Multi-Accepted Match Tie

Across analyzed EOL cases, the most frequent failure pattern observed was:

> **Tie between multiple accepted results with equal taxonomic matches**

These failures are typically produced by the strategy:

* `ExactMatchPrimarySourceMultiAcceptedTaxonomicMatch`

Example failure reason from trace output:

```json
{
  "failure_reason": "Tie between N results with equal taxonomic matches"
}
```

---

## 6. Why This Strategy Fails

This strategy is intentionally conservative:

* it prioritizes correctness over forced resolution
* it fails when multiple equally valid “best” matches exist
* it avoids arbitrary selection without clear disambiguation signals

However, analysis shows that many tied matches differ subtly in ways not currently used for secondary discrimination, such as:

* author or publication year suffixes
* infra-specific placeholders (e.g., `spec`)
* rank depth differences
* minor spelling or canonical variations

---