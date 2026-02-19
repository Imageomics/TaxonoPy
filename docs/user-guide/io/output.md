# Output

When you run `taxonopy resolve`, TaxonoPy writes two outputs for each input file:

- **Resolved**: `<input_name>.resolved.<csv|parquet>`
- **Unsolved**: `<input_name>.unsolved.<csv|parquet>`

The output directory mirrors the input directory structure. Output format is
controlled by the `--output-format` flag (`csv` or `parquet`).

## What’s Inside

Each output row corresponds to one input record. Resolved entries contain the
standardized taxonomy where available, while unsolved entries preserve the
original input ranks. Both outputs include resolution metadata such as status
and strategy information.

Running through the sample resolution results in the following core files:

- `examples/resolved/sample.resolved.parquet` (generated with `taxonopy resolve`)
- `examples/resolved_with_common_names/sample.resolved.parquet` (generated with `taxonopy common-names`)
