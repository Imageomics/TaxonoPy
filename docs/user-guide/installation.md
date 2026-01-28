# Installation

TaxonoPy can be installed with pip after setting up a virtual environment.

```console
pip install taxonopy
```

## GNVerifier Dependency

TaxonoPy relies on the GNVerifier CLI to resolve taxonomic names. When you run
`taxonopy resolve`, it will automatically try the following:

1. **Docker (recommended).** If Docker is available, TaxonoPy checks for the
   configured GNVerifier image (default: `gnames/gnverifier:v1.2.5`) and pulls it
   if needed. The first run may take a bit longer while the image downloads.
   See [gnames/gnverifier on Docker Hub](https://hub.docker.com/r/gnames/gnverifier).
2. **Local GNVerifier.** If Docker is unavailable or the image pull fails,
   TaxonoPy looks for a local `gnverifier` binary on your `PATH`. The version
   used will be whatever is installed on your system, which may differ from the
   pinned container version. For install instructions, see the GNVerifier README:
   [gnverifier installation](https://github.com/gnames/gnverifier?tab=readme-ov-file#installation).

If neither Docker nor a local GNVerifier is available, TaxonoPy will raise an
error when you attempt to resolve names. In that case, install Docker or install
GNVerifier locally and ensure the `gnverifier` command is available.
