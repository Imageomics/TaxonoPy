import argparse
import os
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

    subparsers = parser.add_subparsers(dest='command', required=True)

    resolve_parser = subparsers.add_parser('resolve', help='Resolve taxonomic names')
    resolve_parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to the input Parquet file or directory containing Parquet files"
    )
    resolve_parser.add_argument(
        "-o", "--output-dir",
        required=True,
        help="Directory to save the resolved output files"
    )
    resolve_parser.add_argument(
        "--exec-method",
        choices=['docker'],
        default='docker',
        help="Choose the execution method: docker (currently only Docker is supported)"
    )
    resolve_parser.add_argument(
        "--print-raw-output",
        action='store_true',
        help="Print the raw output from gnverifier"
    )
    resolve_parser.add_argument(
        "--output-format",
        choices=['csv', 'parquet'],
        default='parquet',
        help="Specify the output file format: 'csv' or 'parquet' (default: 'parquet')"
    )

    args = parser.parse_args()

    if args.command == 'resolve':
        # Ensure the output directory exists
        os.makedirs(args.output_dir, exist_ok=True)

        resolve_names(
            input_path=args.input,
            output_dir=args.output_dir,
            exec_method=args.exec_method,
            print_raw_output=args.print_raw_output,
            output_format=args.output_format
        )
        print(f"Taxonomic resolution complete using {args.exec_method}.")

if __name__ == "__main__":
    main()
