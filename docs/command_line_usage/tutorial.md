# Command Line Tutorial

**Command ```resolve```:**
The ```resolve``` command is used to perform taxonomic resolution on a dataset. It takes a directory of Parquet partitions as input and outputs a directory of resolved Parquet partitions.
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

**Command ```trace```**:
The ```trace``` command is used to trace the provenance of a taxonomic entry. It takes a UUID and an input path as arguments and outputs the full path of the entry through TaxonoPy.
```
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

**Command ```common-names```:**
The ```common-names``` command is used to merge vernacular names into the resolved output. It takes a directory of resolved Parquet partitions as input and outputs a directory of resolved Parquet partitions with common names.

```
usage: taxonopy common-names [-h] --resolved-dir ANNOTATION_DIR --output-dir OUTPUT_DIR

options:
  -h, --help            show this help message and exit
  --resolved-dir ANNOTATION_DIR
                        Directory containing your *.resolved.parquet files
  --output-dir OUTPUT_DIR
                        Directory to write annotated .parquet files
```

Note that the ```common-names``` command is a post-processing step and should be run after the ```resolve``` command.

## Example Usage
To perform taxonomic resolution on a dataset with subsequent common name annotation, run:
```
taxonopy resolve \
    --input /path/to/formatted/input \
    --output-dir /path/to/resolved/output
```
```
taxonopy common-names \
    --resolved-dir /path/to/resolved/output \
    --output-dir /path/to/resolved_with_common-names/output
```
TaxonoPy creates a cache of the objects associated with input entries for use with the ```trace``` command. By default, this cache is stored in the ```~/.cache/taxonopy``` directory.

## Development

See the [Wiki Development Page](https://github.com/Imageomics/TaxonoPy/wiki/Development) for development instructions.