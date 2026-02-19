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

- `taxonopy resolve`:
    - `examples/resolved/sample.resolved.parquet`
    - `examples/resolved/sample.unsolved.parquet`
- `taxonopy common-names`:
    - `examples/resolved/common/sample.resolved.parquet`
