# Input

Provide a file or directory containing 7-rank Linnaean taxonomic metadata.
Inputs may be CSV or Parquet. Expected columns include:

- **uuid**: a unique identifier for each sample (required).
- **kingdom, phylum, class, order, family, genus, species**: the taxonomic ranks of the organism (required, may have sparsity).
- **scientific_name**: the scientific name to the most specific rank available (optional).
- **common_name**: the common (i.e. vernacular) name of the organism (optional).

## Example Files

- [sample.parquet (download)](https://raw.githubusercontent.com/Imageomics/TaxonoPy/main/examples/input/sample.parquet)
- [sample.csv (download)](https://raw.githubusercontent.com/Imageomics/TaxonoPy/main/examples/input/sample.csv)
