"""

Usage:
  taxonopy <name>
  taxonopy (-f FILE)

Options:
  -h --help     Show this screen.
  -f FILE       Specify a file containing species names, one per line.

Examples:
  taxonopy "Tardus migratorius"
  taxonopy -f species.txt

"""

from docopt import docopt
from taxonopy.taxonomy_resolver import TaxonomyResolver

def main():
    args = docopt(__doc__)

    resolver = TaxonomyResolver()

    names = []
    if args['<name>']:
        names = args['<name>'].split(';')
    elif args['-f']:
        with open(args['-f'], 'r') as f:
            names = f.read().splitlines()

    result = resolver.resolve_names(names)

    print(result)

if __name__ == '__main__':
    main()
