import argparse
from taxonopy.resolver import resolve_names
from taxonopy import __version__ 

def main():
    parser = argparse.ArgumentParser(description="Resolve taxonomic names using GNVerifier")

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
        help="Show the version number and exit"
    )

    subparsers = parser.add_subparsers(dest='command')

    resolve_parser = subparsers.add_parser('resolve', help='Resolve taxonomic names')
    resolve_parser.add_argument("-i", "--input", required=True, help="Path to the input file containing scientific names (one per line)")
    resolve_parser.add_argument("-o", "--output", required=True, help="Path to the output JSONL file")
    resolve_parser.add_argument("--exec-method", choices=['docker'], default='docker',
                                help="Choose the execution method: docker (currently only Docker is supported)")

    args = parser.parse_args()

    if args.command == 'resolve':
        resolve_names(input_file=args.input, output_file=args.output, exec_method=args.exec_method)
        print(f"Taxonomic resolution complete using {args.exec_method}. Results saved to {args.output}")

if __name__ == '__main__':
    main()
