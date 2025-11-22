# Help
You may view the help for the command line interface by running:

```bash
taxonopy --help
```
This will show you the available commands and options:

```
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