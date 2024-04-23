"""TaxonoPy.

Usage:
  taxonopy <name> [--vernaculars <bool>]
  taxonopy (-f FILE) [--vernaculars <bool>]
  taxonopy (-h | --help)

Options:
  -h --help     Show this screen.
  -f FILE       Specify a file containing species names, one per line.
  -v --vernaculars <bool>  Include vernacular names in the output [default: False].

Examples:
  taxonopy "Tardus migratorius;Panthera leo"
  taxonopy -f species.txt
  taxonopy "Tardus migratorius" -v true
  taxonopy -f species.txt --vernaculars true

"""

from docopt import docopt
from taxonopy.taxonomy_resolver import TaxonomyResolver

def main():
    args = docopt(__doc__)

    resolver = TaxonomyResolver()

    vernaculars = args['--vernaculars'].lower() == 'true'

    names = []
    if args['<name>']:
        names = args['<name>'].split(';')
    elif args['-f']:
        with open(args['-f'], 'r') as f:
            names = f.read().splitlines()

    result = resolver.resolve_names(names, vernaculars=vernaculars)

    # print(result)

if __name__ == '__main__':
    main()
