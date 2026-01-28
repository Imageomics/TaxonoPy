---
title: Home
hide:
  - title
---

# TaxonoPy {: .taxonopy-home-title }

![TaxonoPy banner](_assets/taxonopy_banner.svg)

<h2 style="text-align:center; margin-top:0;">Cleanly Aligned Biodiversity Taxonomy</h2>
<div align="center">
  <a href="https://doi.org/10.5281/zenodo.15499454">
    <img src="https://zenodo.org/badge/789041700.svg" alt="DOI">
  </a>
  <a href="https://pypi.org/project/taxonopy">
    <img src="https://img.shields.io/pypi/v/taxonopy.svg" alt="PyPI - Version">
  </a>
  <a href="https://pypi.org/project/taxonopy">
    <img src="https://img.shields.io/pypi/pyversions/taxonopy.svg" alt="PyPI - Python Version">
  </a>
</div>

Welcome! This is the initial MkDocs site for the TaxonoPy project. 

TaxonoPy (taxon-o-py) is a command-line tool for creating an internally consistent 7-rank Linnaean taxonomic hierarchy using the [Global Names Verifier (gnverifier)](https://github.com/gnames/gnverifier).
It does not define its own authority; instead it leans on trusted sources indexed by GNVerifier, such as the Catalogue of Life and the GBIF Backbone Taxonomy. See the full list of [GNVerifier data sources](https://verifier.globalnames.org/data_sources).

Support for flexible source selection is still evolving. Today, TaxonoPy ships with a pinned default GNVerifier source configuration (currently GBIF Backbone Taxonomy, source 11), while additional sources remain available through GNVerifier.

## Package Purpose
TaxonoPy helps build a single, internally consistent classification across large biodiversity datasets assembled from multiple providers, each of which may use overlapping but non‑identical taxonomic hierarchies. The goal is AI-ready biodiversity data with clean, aligned taxonomy.

Its development has been driven by its application in the TreeOfLife-200M (TOL) dataset. This dataset contains over 200 million samples of organisms from four core data providers:

- [The Global Biodiversity Information Facility (GBIF)](https://www.gbif.org/)
- [BIOSCAN-5M](https://biodiversitygenomics.net/projects/5m-insects/)
- [FathomNet](https://www.fathomnet.org/)
- [The Encyclopedia of Life (EOL)](https://eol.org/)

Across these resources, taxon names and classifications often conflict. TaxonoPy resolves those differences into a coherent, standardized taxonomy for the combined dataset.

!!! warning
    TaxonoPy does not guarantee perfect alignment or edge case coverage; it is a progressive effort to improve taxonomic coverage in an evolving landscape.
    If you have suggestions or encounter bugs, please see the [Contributing](development/contributing/index.md) page.


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
