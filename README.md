# TaxonoPy

`TaxonoPy` (taxon-o-py) is a command-line tool for creating an internally consistent taxonomic hierarchy using the [Global Names Verifier (gnverifier)](https://github.com/gnames/gnverifier). 

## Purpose
The motivation for this package is to create an internally consistent and standardized classification set for organisms in the TreeOfLife (TOL) dataset.

This dataset contains over 200 million samples of organisms from sources including ...

- The GLobal Biodiversity Information Facility (GBIF)
- BIOSCAN-5M
- FathomNet
- The Encyclopedia of Life (EOL)


This package is a tool for creating an internally consistent classification set for a list of organisms whose entries have inconsistent naming. 

### Input

A directory containing Parquet partitions of the seven-rank Linnaean taxonomic metadata for organisms in the dataset. Labels should include:
- `uuid`: a unique identifier for each sample (required).
- `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`: the taxonomic ranks of the organism (required, may have sparsity).
- `scientific_name`: the scientific name of the organism, to the most specific rank available (optional).
- `common_name`: the common (i.e. vernacular) name of the organism (optional).

See the example data in 
- `examples/input/sample.parquet`
- `examples/resolved/sample.resolved.parquet` (generated with [`taxonopy resolve`](#commands-resolve))
- `examples/resolved_with_common_names/sample.resolved.parquet` (generated with [`taxonopy common-names`](#commands-common-names))

### Challenges
This taxonomy information is provided by each data provider and the original sources, but the classification can be...

- **Inconsistent**: both between and within sources (e.g. kingdom Metazoa vs. Animalia).
- **Incomplete**: many samples are missing one or more ranks. Some have 'holes' where higher and lower ranks are present, but intermediate ranks are missing.
- **Incorrect**: some samples have incorrect classifications. This can come in the form of spelling errors, nonstandard ideosyncratic terms, or outdated classifications.
- **Ambiguous**: homonyms, synonyms, and other terms that can be interpreted in multiple ways unless handled systematically.

Taxonomic authorities exist to standardize classification, but ...
- There are many authorities.
- They may disagree.
- A given organism may be missing from some.

### Solution
`TaxonoPy` uses the taxonomic hierarchies provided by the TOL sources to query GNVerifier and create a standardized classification for each sample in the TOL dataset. It prioritizes the GBIF backbone taxonomy, since this represents the largest part of the TOL dataset. Where GBIF misses, backup sources such as the Catalogue of Life and Open Tree of Life (OTOL) taxonomy are used.

## Installation

`TaxonoPy` can be installed with `pip` after setting up a virtual environment.

### User Installation with `pip`

To install the latest version of `TaxonoPy`, run:
```console
pip install taxonopy
```

### Development Installation with `pip`

Clone the repository and install the package in development mode with an activated virtual environment:
```console
git clone git@github.com:Imageomics/TaxonoPy.git
cd TaxonoPy
```
Set up and activate a virtual environment.

Install the package in development mode:
```console
pip install -e .[dev]
```

### Usage
You may view the help for the command line interface by running:
```console
taxonopy --help
```
This will show you the available commands and options:
```console
usage: taxonopy [-h] [--cache-dir CACHE_DIR] [--show-cache-path] [--cache-stats] [--clear-cache] [--show-config] [--version] {resolve,trace,common-names} ...

TaxonoPy: Resolve taxonomic names using GNVerifier and trace data provenance.

positional arguments:
  {resolve,trace,common-names}
    resolve             Run the taxonomic resolution workflow
    trace               Trace data provenance of TaxonoPy objects
    common-names        Merge vernacular names (post-process) into resolved outputs

options:
  -h, --help            show this help message and exit
  --cache-dir CACHE_DIR
                        Directory for TaxonoPy cache (can also be set with TAXONOPY_CACHE_DIR environment variable) (default: None)
  --show-cache-path     Display the current cache directory path and exit (default: False)
  --cache-stats         Display statistics about the cache and exit (default: False)
  --clear-cache         Clear the TaxonoPy object cache. May be used in isolation. (default: False)
  --show-config         Show current configuration and exit (default: False)
  --version             Show version number and exit
```
#### Commands: `resolve`
The `resolve` command is used to perform taxonomic resolution on a dataset. It takes a directory of Parquet partitions as input and outputs a directory of resolved Parquet partitions.
```
usage: taxonopy resolve [-h] -i INPUT -o OUTPUT_DIR [--output-format {csv,parquet}] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--log-file LOG_FILE] [--force-input] [--batch-size BATCH_SIZE] [--all-matches]
                        [--capitalize] [--fuzzy-uninomial] [--fuzzy-relaxed] [--species-group] [--refresh-cache]

options:
  -h, --help            show this help message and exit
  -i, --input INPUT     Path to input Parquet or CSV file/directory
  -o, --output-dir OUTPUT_DIR
                        Directory to save resolved and unsolved output files
  --output-format {csv,parquet}
                        Output file format
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set logging level
  --log-file LOG_FILE   Optional file to write logs to
  --force-input         Force use of input metadata without resolution

GNVerifier Settings:
  --batch-size BATCH_SIZE
                        Max number of name queries per GNVerifier API/subprocess call
  --all-matches         Return all matches instead of just the best one
  --capitalize          Capitalize the first letter of each name
  --fuzzy-uninomial     Enable fuzzy matching for uninomial names
  --fuzzy-relaxed       Relax fuzzy matching criteria
  --species-group       Enable group species matching

Cache Management:
  --refresh-cache       Force refresh of cached objects (input parsing, grouping) before running.
  ```
It is recommended to keep GNVerifier settings at their defaults.

#### Commands: `trace`
The `trace` command is used to trace the provenance of a taxonomic entry. It takes a UUID and an input path as arguments and outputs the full path of the entry through TaxonoPy.
```console
usage: taxonopy trace [-h] {entry} ...

positional arguments:
  {entry}
    entry     Trace an individual taxonomic entry by UUID

options:
  -h, --help  show this help message and exit

usage: taxonopy trace entry [-h] --uuid UUID --from-input FROM_INPUT [--format {json,text}] [--verbose]

options:
  -h, --help            show this help message and exit
  --uuid UUID           UUID of the taxonomic entry
  --from-input FROM_INPUT
                        Path to the original input dataset
  --format {json,text}  Output format
  --verbose             Show full details including all UUIDs in group
```

#### Commands: `common-names`
The `common-names` command is used to merge vernacular names into the resolved output. It takes a directory of resolved Parquet partitions as input and outputs a directory of resolved Parquet partitions with common names.
```console
usage: taxonopy common-names [-h] --resolved-dir ANNOTATION_DIR --output-dir OUTPUT_DIR

options:
  -h, --help            show this help message and exit
  --resolved-dir ANNOTATION_DIR
                        Directory containing your *.resolved.parquet files
  --output-dir OUTPUT_DIR
                        Directory to write annotated .parquet files
```
Note that the `common-names` command is a post-processing step and should be run after the `resolve` command.

### Example Usage

To perform taxonomic resolution on a dataset with subsequent common name annotation, run:
```console
taxonopy resolve \
    --input /path/to/formatted/input \
    --output-dir /path/to/resolved/output
```
```console
taxonopy common-names \
    --resolved-dir /path/to/resolved/output \
    --output-dir /path/to/resolved_with_common-names/output
```

TaxonoPy creates a cache of the objects associated with input entries for use with the `trace` command. By default, this cache is stored in the `~/.cache/taxonopy` directory. You 

## Development

This section assumes that you have installed the package in development mode.

### OpenAPI Specification Managment and Type Generation

`TaxonoPy` uses GNVerifier to generate and integrates with its API from its OpenAPI specification.

The script that handles this is `scripts/generate_gnverifier_types.py`, which saves `api_specs/gnverifier_openapi.json` and from this produces `src/taxonopy/types/gnverifier.py`.

To check for changes in the OpenAPI specification, run:
```console
python scripts/generate_gnverifier_types.py
```

If the OpenAPI specification has changed, you will need to decide whether to update the generated types. 

The script will save `api_specs/gnverifier_openapi.json.new` and `src/taxonopy/types/gnverifier.py.new` for you to compare with the existing files and decide whether to overwrite them and make any necessary changes to the rest of the codebase.

