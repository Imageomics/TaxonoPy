# TaxonoPy

Welcome! This is the initial MkDocs site for the TaxonoPy project. 

TaxonoPy (taxon-o-py) is a command-line tool for creating an internally consistent taxonomic hierarchy using the [Global Names Verifier (gnverifier)](https://github.com/gnames/gnverifier)
. See below for the structure of inputs and outputs.

## Purpose
The motivation for this package is to create an internally consistent and standardized classification set for organisms in a large biodiversity dataset composed from different data providers that may use very similar and overlapping but not identical taxonomic hierarchies.

Its development has been driven by its application in the TreeOfLife-200M (TOL) dataset. This dataset contains over 200 million samples of organisms from four core data providers:

- [The Global Biodiversity Information Facility (GBIF)](https://www.gbif.org/)
- [BIOSCAN-5M](https://biodiversitygenomics.net/projects/5m-insects/)
- [FathomNet](https://www.fathomnet.org/)
- [The Encyclopedia of Life (EOL)](https://eol.org/)

The names (and classification) of taxa may be (and often are) inconsistent across these resources. This package addresses this problem by creating an internally consistent classification set for such taxa.

## Input
A directory containing Parquet partitions of the seven-rank Linnaean taxonomic metadata for organisms in the dataset. Labels should include:

- **uuid**: a unique identifier for each sample (required).
- **kingdom, phylum, class, order, family, genus, species**: the taxonomic ranks of the organism (required, may have sparsity).
- **scientific_name**: the scientific name to the most specific rank available (optional).
- **common_name**: the common (i.e. vernacular) name of the organism (optional).



See the example data in:
```

- `examples/input/sample.parquet`
- `examples/resolved/sample.resolved.parquet` (generated with `taxonopy resolve`)
- `examples/resolved_with_common_names/sample.resolved.parquet` (generated with `taxonopy common-names`)

```


## Challenges
This taxonomy information is provided by each data provider and original sources, but the classification can be:

- **Inconsistent** — between and within sources (e.g., kingdom *Metazoa* vs. *Animalia*)
- **Incomplete** — missing ranks or containing "holes"
- **Incorrect** — spelling errors, nonstandard terms, or outdated classifications
- **Ambiguous** — homonyms, synonyms, and terms with multiple interpretations

Taxonomic authorities exist to standardize classification, but:

- There are multiple authorities  
- They may disagree  
- A given organism may be missing from some  

## Solution
TaxonoPy uses the taxonomic hierarchies provided by the TOL core data providers to query GNVerifier and create a standardized classification for each sample in the TOL dataset. It prioritizes the [GBIF Backbone Taxonomy](https://verifier.globalnames.org/data_sources/11), since this represents the largest part of the TOL dataset. Where GBIF misses, backup sources such as the [Catalogue of Life](https://verifier.globalnames.org/data_sources/1) and [Open Tree of Life (OTOL) Reference Taxonomy](https://verifier.globalnames.org/data_sources/179) are used.

## Installation
TaxonoPy can be installed with pip after setting up a virtual environment.

### User Installation with pip
To install the latest version of TaxonoPy, run:

``` bash

pip install taxonopy

```

