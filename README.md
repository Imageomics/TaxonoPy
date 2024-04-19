# TaxonoPy

This tool is under development and is unstable.

`TaxonoPy` is a command-line tool for resolving taxonomic hierarchies using the [Global Names Resolver (GNR) API](http://resolver.globalnames.org/). It provides an interface to input species names and retrieve taxonomic classifications conforming to a strict 7-rank Linnehierarchy, helping researchers gather controlled taxonomic data about species.

Specifically, the ranks required include `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, and `species`. Only results exactly matching these ranks are returned.

## Installation

`TaxonoPy` can be installed using `pip` after setting up a virtual environment.

### Virtual Environment Setup

For example, with `conda`, run:
```bash
conda create -n myenv -y
conda activate myenv
```

### Installation with `pip`

To install the latest version of `TaxonoPy` directly from GitHub, run:
```bash
pip install git+ssh://git@github.com/thompsonmj/TaxonoPy.git
```

### Development Installation with `pip`

Clone the repository and install the package in development mode:
```bash
git clone git@github.com:thompsonmj/Taxonopy.git
cd TaxonoPy
pip install -e .[dev]
```

## Usage

`TaxonoPy` can be run from the command line with the following syntax:
```bash
taxonopy <species_name>
taxonopy -f <file_path>
```

For example, to resolve the taxonomic hierarchy of the species name `Homo sapiens`, run:
```bash
taxonopy "Homo sapiens"
```

Or for a list of species names stored in a file, run:
```bash
taxonopy -f ids.txt
```

