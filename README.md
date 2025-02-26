# TaxonoPy
This tool is under development and is unstable.

`TaxonoPy` (taxon-o-py) is a command-line tool for creating an internally consistent taxonomic hierarchy using the [Global Names Verifier (gnverifier)](https://github.com/gnames/gnverifier). 

## Purpose
The motivation for this package is to create an internally consistent and standardized classification set for organisms in the TreeOfLife (TOL) dataset.

This dataset contains over 200 million samples of organisms from sources including ...

- The GLobal Biodiversity Information Facility (GBIF)
- BIOSCAN-5M
- Labeled Information Library of Alexandria: Biology and Conservation (LILA-BC)
- FathomNet
- The Encyclopedia of Life (EOL)


Notably, this package is not a taxonomic authority, and it does not provide a definitive classification for any organism. It is a tool for creating an internally consistent classification set for a list of organisms, which may contain entries with inconsistent naming compared to other well-regarded taxonomic authorities. 
It is up to the user to determine the appropriateness of the classification for their use case, which may differ from their preferred taxonomic authority.

### Input

A directory containing Parquet partitions of the seven-rank Linnaean taxonomic metadata for organisms in the dataset. Labels should include:
- `uuid`: a unique identifier for each sample (required).
- `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`: the taxonomic ranks of the organism (required, may have sparsity).
- `scientific_name`: the scientific name of the organism, to the most specific rank available (optional).
- `common_name`: the common (i.e. vernacular) name of the organism (optional).

### Challenges
This taxonomy information is provided by each data source, but the classification is ...

- **Inconsistent**: both between and within sources (e.g. kingdom Metazoa vs. Animalia).
- **Incomplete**: many samples are missing one or more ranks. Some have 'holes' where higher and lower ranks are present, but intermediate ranks are missing.
- **Incorrect**: some samples have incorrect classifications. This can come in the form of spelling errors, nonstandard ideosyncratic terms, or outdated classifications.
- **Ambiguous**: homonyms, synonyms, and other terms that can be interpreted in multiple ways unless handled systematically.

Taxonomic authorities exist to standardize classification, but ...
- There are many authorities.
- They may disagree.
- A given organism may be missing from some.

### Solution
`TaxonoPy` uses the taxonomic hierarchies provided by the TOL sources to query GNVerifier and create a standardized classification for each sample in the TOL dataset. It prioritizes the GBIF backbone taxonomy, since this represents the largest part of the TOL dataset. Where GBIF misses, the Open Tree of Life (OTOL) taxonomy is used.[^1]

## Installation

`TaxonoPy` can be installed with `pip` after setting up a virtual environment.

### User Installation with `pip`

To install the latest version of `TaxonoPy` directly from GitHub, run:
```console
pip install git+ssh://git@github.com/Imageomics/TaxonoPy.git
```
or
```console
pip install git+https://github.com/Imageomics/TaxonoPy.git
```

### Development Installation with `pip`

Clone the repository and install the package in development mode with an activated virtual environment:
```console
git clone git@github.com:Imageomics/Taxonopy.git
cd TaxonoPy
```
Set up and activate a virtual environment.

Install the package in development mode:
```console
pip install -e .[dev]
```
> [!WARNING]
> This section is deprecated, some options will be changed
> ### Usage
> ```console
> usage: taxonopy [-h] [--version] -i INPUT -o OUTPUT_DIR [--batch-size > BATCH_SIZE] [--output-format {csv,parquet}] [--force-input] [--print-raw-output]
>                 [--gnverifier-image GNVERIFIER_IMAGE] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
> 
> TaxonoPy: Resolve taxonomic names using GNVerifier
> 
> options:
>   -h, --help            show this help message and exit
>   --version             Show version number and exit
>   -i INPUT, --input INPUT
>                         Path to input Parquet file or directory containing Parquet files
>   -o OUTPUT_DIR, --output-dir OUTPUT_DIR
>                         Directory to save resolved and investigation output files
>   --batch-size BATCH_SIZE
>                         Number of name queries to process in each GNVerifier batch (default: 10000)
>   --output-format {csv,parquet}
>                         Output file format (default: parquet)
>   --force-input         Force use of input metadata without resolution
>   --gnverifier-image GNVERIFIER_IMAGE
>                         Docker image for GNVerifier (default: gnames/gnverifier:v1.2.2)
>   --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
>                         Set logging level (default: INFO)
> ```

## Development

This section assumes that you have installed the package in development mode.

### OpenAPI Specification Managment and Type Generation

`TaxonoPY` uses GNVerifier to generate and integrates with its API from its OpenAPI specification.

The script that handles this is `scripts/generate_gnverifier_types.py`, which saves `api_specs/gnverifier_openapi.json` and from this produces `src/taxonopy/types/gnverifier.py`.

To check for changes in the OpenAPI specification, run:
```console
python scripts/generate_gnverifier_types.py
```

If the OpenAPI specification has changed, you will need to decide whether to update the generated types. 

The script will save `api_specs/gnverifier_openapi.json.new` and `src/taxonopy/types/gnverifier.py.new` for you to compare with the existing files and decide whether to overwrite them and make any necessary changes to the rest of the codebase.

[^1]: Second priority and lower data sources have not been firmly established or implemented yet.
