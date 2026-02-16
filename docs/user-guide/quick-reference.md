# Quick Reference

## Install

```console
pip install taxonopy
```

For detailed setup instructions including GNVerifier and troubleshooting, see [Installation](installation.md).

## Sample Input

Download the same sample dataset in either format and place it in `examples/input/`:

- [sample.parquet](https://raw.githubusercontent.com/Imageomics/TaxonoPy/main/examples/input/sample.parquet)
- [sample.csv](https://raw.githubusercontent.com/Imageomics/TaxonoPy/main/examples/input/sample.csv)

_**Sample input**: Note the divergence in kingdoms (Metazoa vs Animalia), missing interior ranks, and fully null entry._
<div class="table-cell-scroll" markdown>

| uuid | kingdom | phylum | class | order | family | genus | species | scientific_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc2a3f9f-c1f9-48df-9b01-d045475b9d5f | Metazoa | Chordata | Mammalia | Primates | Hominidae | Homo | Homo sapiens | Homo sapiens |
| 21ed76d8-9a3b-406e-a1a3-ef244422bf8e | Plantae | Tracheophyta | `null` | Fagales | Fagaceae | Quercus | Quercus alba | Quercus alba |
| 4d166a61-b6e5-4709-91ba-b623111014e9 | Animalia | `null` | `null` | Hymenoptera | Apidae | Apis | Apis mellifera | Apis mellifera |
| 85b96dc2-70ab-446e-afb5-6a4b92b0a450 | `null` | `null` | `null` | `null` | `null` | `null` | Amanita muscaria | `null` |
| 38327554-ffbf-4180-b4cf-63c311a26f4e | Animalia | `null` | `null` | `null` | `null` | `null` | Laelia rosea | `null` |
| 8f688a17-1f7a-42b2-b3dc-bd4c8fc0eee3 | Plantae | `null` | `null` | `null` | `null` | `null` | Laelia rosea | `null` |
| a95f3e29-ed48-41f4-9577-64d4243a0396 | `null` | `null` | `null` | `null` | `null` | `null` | `null` | `null` |

</div>

In the final example entry, there is no available taxonomic data, which can happen in large datasets where there may be a corresponding image but incomplete annotation. 

## Execute a Basic Resolution

```console
taxonopy resolve --input examples/input --output-dir examples/resolved
```

!!! note "Input values"
    There are three kinds of values you can pass to `--input`:

    - A single file path (CSV or Parquet).
    - A flat directory of partitioned files (TaxonoPy will glob everything inside).
    - A directory tree (TaxonoPy will glob recursively and preserve the folder structure in the output).

    In all three cases, the base filename is preserved in the output. That is, the output keeps the original filename(s) and adds `.resolved` / `.unsolved` before the extension.

    If you download both `sample.csv` and `sample.parquet` into `examples/input/`, resolve will fail due to mixed input formats; keep only one format per input directory.

The command above will read in the sample data from `examples/input/`, execute resolution, and write the results to `examples/resolved/`.

By default, outputs are written to Parquet format, whether the input is CSV or Parquet. To set the output format to CSV, use the `--output-format csv` flag.

The output files consist of:

- `sample.resolved.parquet`
- `sample.unsolved.parquet`
- `resolution_stats.json`

The `sample.resolved.parquet` file contains all the entries where some resolution strategy was applied. In this example, it contains:


_**Sample resolved output (selected columns)**: Green highlights show values added during resolution. Yellow highlights indicate values that changed from the input._
<div class="table-cell-scroll" markdown>

| uuid | kingdom | phylum | class | order | family | genus | species | scientific_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc2a3f9f-c1f9-48df-9b01-d045475b9d5f | <span class="cell-changed">Animalia</span><sup>[?](https://verifier.globalnames.org/?all_matches=on&capitalize=on&ds=11&format=html&names=Homo+sapiens "The input lineage here mirrors what the Encyclopedia of Life provides (Metazoa as the clade that maps to the kingdom rank); when queried against GNVerifier, this rank maps to Animalia. Click to see the GNVerifier result.")</sup> | Chordata | Mammalia | Primates | Hominidae | Homo | Homo sapiens | Homo sapiens |
| 21ed76d8-9a3b-406e-a1a3-ef244422bf8e | Plantae | Tracheophyta | <span class="cell-added">Magnoliopsida</span> | Fagales | Fagaceae | Quercus | Quercus alba | Quercus alba |
| 4d166a61-b6e5-4709-91ba-b623111014e9 | Animalia | <span class="cell-added">Arthropoda</span> | <span class="cell-added">Insecta</span> | Hymenoptera | Apidae | Apis | Apis mellifera | Apis mellifera |
| 85b96dc2-70ab-446e-afb5-6a4b92b0a450 | <span class="cell-added">Fungi</span> | <span class="cell-added">Basidiomycota</span> | <span class="cell-added">Agaricomycetes</span> | <span class="cell-added">Agaricales</span> | <span class="cell-added">Amanitaceae</span> | <span class="cell-added">Amanita</span> | Amanita muscaria | `""` |
| 38327554-ffbf-4180-b4cf-63c311a26f4e | Animalia | <span class="cell-added">Arthropoda</span> | <span class="cell-added">Insecta</span> | <span class="cell-added">Lepidoptera</span> | <span class="cell-added">Erebidae</span> | <span class="cell-added">Laelia</span> | Laelia rosea | `""` |
| 8f688a17-1f7a-42b2-b3dc-bd4c8fc0eee3 | Plantae | <span class="cell-added">Tracheophyta</span> | <span class="cell-added">Liliopsida</span> | <span class="cell-added">Asparagales</span> | <span class="cell-added">Orchidaceae</span> | <span class="cell-added">Laelia</span> | Laelia rosea | `""` |

</div>


## Add Common Names

You can add vernacular names to resolved outputs as a post-processing step:

```console
taxonopy common-names --resolved-dir examples/resolved --output-dir examples/resolved/common
```

This command uses GBIF Backbone data only and applies deterministic fallback: species to kingdom, with English names preferred at each rank.

_**Sample common-name output (`examples/resolved/common/sample.resolved.parquet`)**_
<div class="table-cell-scroll" markdown>

| uuid | common_name | kingdom | phylum | class | order | family | genus | species |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc2a3f9f-c1f9-48df-9b01-d045475b9d5f | Human | Animalia | Chordata | Mammalia | Primates | Hominidae | Homo | Homo sapiens |
| 21ed76d8-9a3b-406e-a1a3-ef244422bf8e | Eastern White Oak | Plantae | Tracheophyta | Magnoliopsida | Fagales | Fagaceae | Quercus | Quercus alba |
| 4d166a61-b6e5-4709-91ba-b623111014e9 | Drone-Bee | Animalia | Arthropoda | Insecta | Hymenoptera | Apidae | Apis | Apis mellifera |
| 85b96dc2-70ab-446e-afb5-6a4b92b0a450 | Fly Agaric | Fungi | Basidiomycota | Agaricomycetes | Agaricales | Amanitaceae | Amanita | Amanita muscaria |
| 38327554-ffbf-4180-b4cf-63c311a26f4e | Underwing, Tiger, Tussock, And Allied Moths | Animalia | Arthropoda | Insecta | Lepidoptera | Erebidae | Laelia | Laelia rosea |
| 8f688a17-1f7a-42b2-b3dc-bd4c8fc0eee3 | Orchid | Plantae | Tracheophyta | Liliopsida | Asparagales | Orchidaceae | Laelia | Laelia rosea |

</div>

The `sample.unsolved.parquet` file contains entries that could not be resolved (for example, rows with no usable taxonomy information). In this example, it contains:


_**Sample unsolved output: Sequestered entries with no usable taxonomy information.**_
<div class="table-cell-scroll" markdown>

| uuid | kingdom | phylum | class | order | family | genus | species | scientific_name | common_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a95f3e29-ed48-41f4-9577-64d4243a0396 | `null` | `null` | `null` | `null` | `null` | `null` | `null` | `null` | `null` |

</div>

The `resolution_stats.json` file summarizes counts of how many entries from the input fell into each final status across the `resolved` and `unsolved` files.

TaxonoPy also writes cache data to disk (default: `~/.cache/taxonopy`) so it can trace provenance and avoid reprocessing. Use `--show-cache-path`, `--cache-stats`, or `--clear-cache` if you want to inspect or manage it, or see the [Cache](cache.md) guide for details.

## Trace an Entry

You can trace how a single UUID was resolved. For example, let's trace one of the _Laelia rosea_ entries:

```console
taxonopy trace entry --uuid 8f688a17-1f7a-42b2-b3dc-bd4c8fc0eee3 --from-input examples/input/sample.csv
```

TaxonoPy uses whatever rank context you provide (even if sparse) to disambiguate identical names. _Laelia rosea_ resolves differently under Animalia vs. Plantae as a hemihomonym. If higher ranks are missing, TaxonoPy would not have been able to disambiguate.

Excerpt (incomplete) from the trace output:

```json
{
  "query_plan": {
    "term": "Laelia rosea",
    "rank": "species",
    "source_id": 11
  },
  "resolution_attempts": [
    {
      "status": "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_INNER_RANK_DISAMBIGUATION",
      "resolution_strategy_name": "ExactMatchPrimarySourceAcceptedInnerRankDisambiguation",
      "resolved_classification": {
        "kingdom": "Plantae",
        "phylum": "Tracheophyta",
        "class_": "Liliopsida",
        "order": "Asparagales",
        "family": "Orchidaceae",
        "genus": "Laelia",
        "species": "Laelia rosea"
      }
    }
  ]
}
```
