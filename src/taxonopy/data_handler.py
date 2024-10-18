import polars as pl
import os
import logging

def read_input_file(input_file, input_format):
    """
    Read the input file into a Polars DataFrame based on the format.
    """
    logging.info(f"Reading input {input_format.upper()} file: {input_file}")
    if input_format == 'parquet':
        try:
            return pl.read_parquet(input_file)
        except Exception as e:
            logging.error(f"Error reading Parquet file '{input_file}': {e}")
            raise
    elif input_format == 'csv':
        try:
            return pl.read_csv(input_file)
        except Exception as e:
            logging.error(f"Error reading CSV file '{input_file}': {e}")
            raise
    else:
        raise ValueError(f"Unsupported input format: {input_format}")

def write_output_file(df: pl.DataFrame, output_file, output_format):
    """
    Write the Polars DataFrame to the specified output file in the desired format.
    """
    try:
        if output_format == 'parquet':
            logging.info(f"Writing to Parquet: {output_file}")
            df.write_parquet(output_file)
        elif output_format == 'csv':
            logging.info(f"Writing to CSV: {output_file}")
            df.write_csv(output_file)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
    except Exception as e:
        logging.error(f"Error writing output file '{output_file}': {e}")
        raise

def validate_input_df(input_df: pl.DataFrame):
    """
    Validate that the input DataFrame contains all required columns.
    """
    required_columns = {'scientific_name', 'uuid', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species', 'common_name'}
    missing = required_columns - set(input_df.columns)
    if missing:
        raise ValueError(f"Input data is missing required columns: {missing}")
