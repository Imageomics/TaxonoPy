# TaxonoPy

This tool is under development and is unstable.

`TaxonoPy` (taxon-o-py) is a command-line tool for resolving taxonomic hierarchies using the [Global Names Verifier (gnverifier)](https://github.com/gnames/gnverifier). 

It provides an interface to input species names or other taxon terms and retrieve taxonomic classifications conforming to a strict 7-rank Linnean hierarchy, helping researchers gather controlled taxonomic data about species.

Specifically, the ranks required include `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, and `species`. Only results exactly matching these ranks are returned.

## Installation

`TaxonoPy` can be installed using `uv pip` after setting up a virtual environment.
> Note: `uv` is a fast Rust-based package manager for Python that can be used as a [drop-in replacement](https://astral.sh/blog/uv#a-drop-in-compatible-api) for `pip`.

### Virtual Environment Setup

For example, with `conda`, run:
```bash
conda create -n myenv -c conda-forge --solver=libmamba python uv -y
conda activate myenv
```

### Installation with `uv pip`

To install the latest version of `TaxonoPy` directly from GitHub, run:
```bash
uv pip install git+ssh://git@github.com/Imageomics/TaxonoPy.git
```
or:
```bash
uv pip install git+https://github.com/Imageomics/TaxonoPy.git
```
### Development Installation with `uv pip`

Clone the repository and install the package in development mode with an activated virtual environment:
```bash
git clone git@github.com:Imageomics/Taxonopy.git
cd TaxonoPy
uv pip install -e .[dev]
```

## Usage

```bash
usage: taxonopy [-h] [--version] {resolve} ...

Resolve taxonomic names using GNVerifier

positional arguments:
  {resolve}
    resolve   Resolve taxonomic names

options:
  -h, --help  show this help message and exit
  --version   Show the version number and exit
```

```bash
usage: taxonopy resolve [-h] -i INPUT -o OUTPUT [--exec-method {docker}]

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to the input file containing scientific names (one per line)
  -o OUTPUT, --output OUTPUT
                        Path to the output JSONL file
  --exec-method {docker}
                        Choose the execution method: docker (currently only Docker is supported; Apptainer and API support will be
                        added.)
```

Currently, the input file must be a `.txt` file formated with one term per line. For example:

`names.txt`:
```
Tardus migratorius
Lumbricus terrestris Linnaeus, 1758
Panthera leo
Canis lupus
Canis familiaris
Homo sapiens
```
