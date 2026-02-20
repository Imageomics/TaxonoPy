# Output

When you run `taxonopy resolve`, TaxonoPy writes two outputs for each input file:

- **Resolved**: `<input_name>.resolved.<csv|parquet>`
- **Unsolved**: `<input_name>.unsolved.<csv|parquet>`

The output directory mirrors the input directory structure. Output format is
controlled by the `--output-format` flag (`csv` or `parquet`).

TaxonoPy also writes a manifest file to the output directory before creating
any other files. This manifest lists every file the run intends to produce and
is used by `--full-rerun` to clean up precisely. Each command writes its own
manifest (`taxonopy_resolve_manifest.json` and
`taxonopy_common_names_manifest.json` respectively) so they coexist safely if
both commands share an output directory. See [Reruns](reruns.md) for details.

## What’s Inside

Each output row corresponds to one input record. Resolved entries contain the
standardized taxonomy where available, while unsolved entries preserve the
original input ranks. Both outputs include resolution metadata such as status
and strategy information.

Running through the sample resolution results in the following core files:

- `taxonopy resolve`:
    - `examples/resolved/sample.resolved.parquet`
    - `examples/resolved/sample.unsolved.parquet`
    - `examples/resolved/resolution_stats.json`
    - `examples/resolved/taxonopy_resolve_manifest.json`
- `taxonopy common-names`:
    - `examples/resolved/common/sample.resolved.parquet`
    - `examples/resolved/common/taxonopy_common_names_manifest.json`
