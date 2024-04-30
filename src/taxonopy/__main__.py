"""TaxonoPy.

Usage:
  taxonopy <name> [--vernaculars <bool>] [--synonyms <bool>] [--required-ranks=<bool>]
  taxonopy (-f FILE) [--vernaculars <bool>] [--synonyms <bool>] [--required-ranks=<bool>]
  taxonopy (-h | --help)

Options:
  -h --help                   Show this screen.
  -f FILE                     Specify a file containing species names, one per line.
  -v --vernaculars <bool>     Include vernacular names in the output [default: False].
  -s --synonyms <bool>        Use synonyms when resolving names [default: False].
  -r --required-ranks <bool>  Use required rank resolution mode, default to false (i.e. full) [default: False].

Examples:
  taxonopy "Tardus migratorius;Panthera leo"
  taxonopy -f species.txt
  taxonopy "Tardus migratorius" -v true
  taxonopy -f species.txt --vernaculars true --synonyms true

"""

from docopt import docopt
from taxonopy.taxonomy_resolver import TaxonomyResolver, FullResolver
def main():
    args = docopt(__doc__)

    vernaculars = args['--vernaculars'].lower() == 'true'
    synonyms = args['--synonyms'].lower() == 'true'
    use_required_ranks = args['--required-ranks'].lower() == 'true'

    names = []
    if args['<name>']:
        names = args['<name>'].split(';')
    elif args['-f']:
        with open(args['-f'], 'r') as f:
            names = f.read().splitlines()

    if use_required_ranks:
        resolver = TaxonomyResolver()
        result = resolver.resolve_names(names, vernaculars=vernaculars, synonyms=synonyms)
    else:
        resolver = FullResolver()
        result = resolver.resolve_names(names, vernaculars=vernaculars)

    # print(result)

if __name__ == '__main__':
    main()
