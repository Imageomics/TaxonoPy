---
title: Home
hide:
  - title
---

# TaxonoPy {: .taxonopy-home-title }

![TaxonoPy banner](_assets/taxonopy_banner.svg)

<h2 style="text-align:center; margin-top:0;">Reproducibly Aligned Biological Taxonomies</h2>
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

TaxonoPy (taxon-o-pie) is a command-line tool for creating reproducibly aligned biological taxonomies using the [Global Names Verifier (GNVerifier)](https://github.com/gnames/gnverifier).

## Package Purpose
TaxonoPy aligns data to a single, internally consistent 7-rank Linnaean taxonomic hierarchy across large biodiversity datasets assembled from multiple providers, each of which may use overlapping but nonuniform taxonomies. The goal is AI-ready biodiversity data with clean, aligned taxonomy.

The initial development of this package was driven by its application in the [TreeOfLife-200M dataset](https://huggingface.co/datasets/imageomics/TreeOfLife-200M). This dataset contains over 200 million labeled images of organisms from four core data providers:

- [The Global Biodiversity Information Facility (GBIF)](https://www.gbif.org/)
- [BIOSCAN-5M](https://biodiversitygenomics.net/projects/5m-insects/)
- [FathomNet](https://www.fathomnet.org/)
- [The Encyclopedia of Life (EOL)](https://eol.org/)

Across these resources, taxon names and classifications often conflict. TaxonoPy resolves those differences into a coherent, standardized taxonomy for the combined dataset.

## Challenges
Taxonomic information provided by different data providers or original sources (e.g., to an aggregator) can result in classifications that are:

- **Inconsistent** — between and within sources (e.g., kingdom *Metazoa* vs. *Animalia*)
- **Incomplete** — missing ranks or containing "holes"
- **Incorrect** — spelling errors, nonstandard terms, or outdated classifications
- **Ambiguous** — homonyms, synonyms, and terms with multiple interpretations

Taxonomic authorities exist to standardize classification, but:

- There are multiple authorities  
- They may disagree  
- A given organism may be missing from some  
- Taxonomy is not fixed—it will change over time with new discoveries and evolving concepts

## Solution
TaxonoPy uses the taxonomic lineages provided by diverse sources to submit batched queries to GNVerifier and resolve to a standardized classification path for each sample in the dataset. It is currently configured to prioritize alignment to the [GBIF Backbone Taxonomy](https://verifier.globalnames.org/data_sources/11). Where GBIF misses, backup sources of the [Catalogue of Life](https://verifier.globalnames.org/data_sources/1) and [Open Tree of Life (OTOL) Reference Taxonomy](https://verifier.globalnames.org/data_sources/179) are used.

## Getting Started
To get started with TaxonoPy, see the [Quick Reference](user-guide/quick-reference.md) guide.

---

!!! warning
    Taxonomic classifications are human-constructed models of biological diversity, not direct representations of biological reality.
    Names and ranks reflect taxonomic concepts that may vary between authorities, evolve over time, and differ in scope or interpretation.

    TaxonoPy aims to produce a **consistent, transparent, and fit-for-purpose classification** suitable for large-scale data integration and AI workflows.
    It prioritizes internal coherence and interoperability across datasets and providers by aligning source data to a selected reference taxonomy.
    
    It is a progressive effort to improve taxonomic alignment in an evolving landscape.
    If you have suggestions or encounter bugs, please see the [Contributing](development/contributing/index.md) page.