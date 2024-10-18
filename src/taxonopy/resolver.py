import os
import polars as pl
from taxonopy.data_handler import read_input_file, write_output_file, validate_input_df
from taxonopy.container_handler import ContainerHandler
from taxonopy.matcher import check_match_case
from taxonopy.utils import KINGDOM_SYNONYMS, extract_required_ranks
from tqdm import tqdm
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

BATCH_SIZE = 10000  # Number of names to process in each batch (should probably make this a CLI argument)

def resolve_names(input_path, output_dir, exec_method='docker', print_raw_output=False, output_format='parquet'):
    """
    Resolve taxonomic names from a single Parquet file or a directory containing multiple Parquet files.
    """
    if not os.path.exists(input_path):
        logging.error(f"Input path '{input_path}' does not exist.")
        return

    # Determine if input_path is a file or directory
    if os.path.isfile(input_path):
        input_files = [input_path]
    elif os.path.isdir(input_path):
        # List all .parquet files in the directory (non-recursive)
        input_files = [
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if os.path.isfile(os.path.join(input_path, f)) and f.lower().endswith('.parquet')
        ]
        if not input_files:
            logging.warning(f"No Parquet files found in directory '{input_path}'.")
    else:
        logging.error(f"Input path '{input_path}' is neither a file nor a directory.")
        return

    if not input_files:
        logging.info("No files to process.")
        return

    # Initialize ContainerHandler
    container_handler = ContainerHandler()

    # Initialize list to hold all data
    all_data = []

    # Initialize progress bar for multiple files
    file_iterator = input_files

    for input_file in file_iterator:
        try:
            # Read input Parquet file
            input_df = read_input_file(input_file, 'parquet')
            validate_input_df(input_df)
            logging.info(f"Loaded {input_df.height} rows from '{input_file}'.")

            # Add a column to track the source file
            input_df = input_df.with_columns([
                pl.lit(os.path.basename(input_file)).alias("source_file")
            ])

            # Create combination_key for making unique combinations to avoid duplicated queries to the resolver
            input_df = input_df.with_columns([
                (
                    pl.col("scientific_name").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("kingdom").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("phylum").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("class").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("order").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("family").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("genus").fill_null("None").cast(pl.Utf8) +
                    "|" +
                    pl.col("species").fill_null("None").cast(pl.Utf8)
                ).alias("combination_key")
            ])

            all_data.append(input_df)

        except Exception as e:
            logging.error(f"Failed to read '{input_file}': {e}")
            continue  # Skip to the next file

    if not all_data:
        logging.info("No data loaded from input files.")
        return

    # Concatenate all data into a single DataFrame
    combined_df = pl.concat(all_data)
    logging.info(f"Total rows aggregated from all files: {combined_df.height}")

    # Deduplicate based on combination_key
    unique_combinations_df = combined_df.unique(subset=["combination_key"])
    logging.info(f"Identified {unique_combinations_df.height} unique combinations across all files.")

    # Group by combination_key to map uuids and source_files
    grouped_df = combined_df.group_by("combination_key").agg([
        pl.col("uuid").alias("uuids"),
        pl.col("source_file").alias("source_files")
    ])

    # Convert grouped DataFrame to a nested dictionary
    combination_to_uuids_sources = {
        row['combination_key']: {
            'uuids': row['uuids'],
            'source_files': row['source_files']
        }
        for row in grouped_df.iter_rows(named=True)
    }

    # Prepare search terms from unique combinations
    all_search_terms = []
    combination_indices = []  # To keep track of the starting index for each combination in all_search_terms

    unresolved_combinations = {}

    # Initialize progress bar for search terms preparation
    search_preparation_iterator = tqdm(
        unique_combinations_df.iter_rows(),
        total=unique_combinations_df.height,
        desc="Preparing Search Terms",
        unit="combination"
    )

    for row in search_preparation_iterator:
        # Extract individual rank values from combination_key
        combination_key = row[unique_combinations_df.columns.index('combination_key')]
        if combination_key is None:
            logging.warning(f"Combination key is None. Skipping.")
            continue

        parts = combination_key.split('|')
        if len(parts) != 8:
            logging.warning(f"Unexpected number of parts in combination_key '{combination_key}'. Skipping.")
            continue

        scientific_name = parts[0]
        kingdom = parts[1]
        phylum = parts[2]
        class_ = parts[3]
        order = parts[4]
        family = parts[5]
        genus = parts[6]
        species = parts[7]

        classification_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']
        classification_path = [kingdom, phylum, class_, order, family, genus, species]

        # Determine the list of search terms (from most specific to least specific)
        if species and species.lower() != 'none':
            term_index = classification_ranks.index('species')
        elif genus and genus.lower() != 'none':
            term_index = classification_ranks.index('genus')
        elif family and family.lower() != 'none':
            term_index = classification_ranks.index('family')
        elif order and order.lower() != 'none':
            term_index = classification_ranks.index('order')
        elif class_ and class_.lower() != 'none':
            term_index = classification_ranks.index('class')
        elif phylum and phylum.lower() != 'none':
            term_index = classification_ranks.index('phylum')
        else:
            term_index = classification_ranks.index('kingdom')

        # Collect all terms from the identified rank down to 'kingdom'
        search_terms = classification_path[:term_index + 1][::-1]  # Reverse slice up to term_index

        # Ensure 'kingdom' is present
        if 'kingdom' in classification_ranks:
            kingdom_input = kingdom  # Already extracted
        else:
            # Handle the case where 'kingdom' is not in classification_ranks
            reason = "No 'kingdom' in classification ranks."
            unresolved_combinations[combination_key] = {
                'scientific_name': scientific_name,
                'classification_ranks': '|'.join(classification_ranks),
                'classification_path': '|'.join(classification_path),
                'reason': reason
            }
            logging.warning(f"Skipping combination {combination_key}: {reason}")
            continue  # Skip to next combination

        # Store the starting index of this combination's search terms
        combination_indices.append(len(all_search_terms))
        all_search_terms.extend(search_terms)

    # Now, run the resolver on all search terms
    name_batches = [all_search_terms[i:i + BATCH_SIZE] for i in range(0, len(all_search_terms), BATCH_SIZE)]
    logging.info(f"Divided search terms into {len(name_batches)} batches of size {BATCH_SIZE}.")

    # Initialize progress bar for batch processing
    batch_iterator = tqdm(name_batches, desc="Processing Batches", unit="batch") if len(name_batches) > 1 else name_batches

    all_results = []
    for batch in batch_iterator:
        try:
            batch_results = container_handler.run_container_with_batch_query(batch, print_raw_output=print_raw_output)
            all_results.extend(batch_results)
        except Exception as e:
            logging.error(f"Error processing batch: {e}")
            continue  # Skip this batch and continue

    # Process each unique combination
    resolved_combinations = {}

    # Initialize lists to store resolved and unresolved rows
    resolved_rows = []
    unresolved_rows = []

    # Initialize progress bar for matching results
    match_iterator = tqdm(
        unique_combinations_df.iter_rows(),
        total=unique_combinations_df.height,
        desc="Matching Results",
        unit="combination"
    )

    for row in match_iterator:
        combination_key = row[unique_combinations_df.columns.index('combination_key')]
        if combination_key is None:
            logging.warning(f"Combination key is None. Skipping.")
            continue

        parts = combination_key.split('|')
        if len(parts) != 8:
            logging.warning(f"Unexpected number of parts in combination_key '{combination_key}'. Skipping.")
            continue

        scientific_name = parts[0]
        kingdom = parts[1]
        phylum = parts[2]
        class_ = parts[3]
        order = parts[4]
        family = parts[5]
        genus = parts[6]
        species = parts[7]

        classification_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']
        classification_path = [kingdom, phylum, class_, order, family, genus, species]

        # Check if 'kingdom' exists and is not 'None'
        if kingdom.lower() == 'none' or not kingdom:
            # If 'kingdom' is missing, log it as unresolved and continue to the next row
            unresolved_combinations[combination_key] = {
                'scientific_name': scientific_name,
                'classification_ranks': '|'.join(classification_ranks),
                'classification_path': '|'.join(classification_path),
                'reason': "No 'kingdom' in classification ranks."
            }
            logging.warning(f"Skipping combination {combination_key}: No 'kingdom' in classification ranks.")
            continue  # Skip this combination

        # Determine the list of search terms for this combination
        try:
            start_index = combination_indices.pop(0)  # Get the first index
        except IndexError:
            logging.error(f"No combination index available for {combination_key}. Skipping.")
            continue

        # Calculate end index based on the number of search terms
        num_search_terms = sum([1 for term in classification_path if term.lower() != 'none'])
        end_index = start_index + num_search_terms
        search_terms_subset = all_search_terms[start_index:end_index]
        results_subset = all_results[start_index:end_index]

        # Try each search term until a match is found
        matching_result_found = False
        resolved = None
        search_term_used = None

        for search_term, result in zip(search_terms_subset, results_subset):
            # Filter and prioritize results that have 'classificationPath' and 'classificationRanks'
            filtered_results = [
                r for r in result.get('results', [])
                if 'classificationPath' in r and 'classificationRanks' in r
            ]

            if not filtered_results:
                continue  # Try the next search term

            # Iterate over the filtered results and check for matching kingdoms
            for best_result in filtered_results:
                resolved_candidate = extract_required_ranks(
                    best_result,
                    supplied_name=result.get('name'),
                    required_ranks=['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']
                )

                # Extract and normalize the resolved kingdom
                resolved_kingdom_raw = resolved_candidate['classification'].get('kingdom')
                resolved_kingdom = KINGDOM_SYNONYMS.get(resolved_kingdom_raw, resolved_kingdom_raw)

                if resolved_kingdom == kingdom:
                    matching_result_found = True
                    resolved = resolved_candidate
                    search_term_used = search_term
                    break  # Exit the loop with a found matching result

            if matching_result_found:
                break  # Found a match for this search term

        if matching_result_found and resolved:
            # Apply matching logic (cases a, b, c, d, e)
            case, resolved_ranks, resolved_path = check_match_case(
                resolved,
                classification_ranks,
                dict(zip(classification_ranks, classification_path)),
                search_term_used
            )

            resolved_combinations[combination_key] = {
                "search_string": search_term_used,
                "resolved_ranks": '|'.join(resolved_ranks),
                "resolved_path": '|'.join(resolved_path),
                "case": case
            }

            # Retrieve UUIDs associated with this combination
            uuids = combination_to_uuids_sources.get(combination_key, {}).get('uuids', [])
            for uuid in uuids:
                resolved_rows.append({
                    'uuid': uuid,
                    'scientific_name': scientific_name,
                    'resolved_ranks': '|'.join(resolved_ranks),
                    'resolved_path': '|'.join(resolved_path),
                    'case': case,
                    'original_common_name': None  # Update if common_name is needed
                })
        else:
            # No match found even after trying higher-level terms
            uuids = combination_to_uuids_sources.get(combination_key, {}).get('uuids', [])
            for uuid in uuids:
                unresolved_rows.append({
                    'uuid': uuid,
                    'scientific_name': scientific_name,
                    'reason': "No match found; using input classification as resolution.",
                    'original_common_name': None  # Update if common_name is needed
                })

    # After processing, save unresolved combinations to a file for further investigation
    if unresolved_combinations:
        # Construct the DataFrame manually
        unresolved_df_missing_kingdom = pl.DataFrame(
            [
                {
                    "combination_key": key,
                    "scientific_name": val["scientific_name"],
                    "classification_ranks": '|'.join(classification_ranks),
                    "classification_path": '|'.join(classification_path),
                    "reason": val["reason"]
                }
                for key, val in unresolved_combinations.items()
            ]
        )
        unresolved_file_missing_kingdom = os.path.join(
            output_dir,
            f"unresolved_due_to_missing_kingdom.{output_format}"
        )
        write_output_file(unresolved_df_missing_kingdom, unresolved_file_missing_kingdom, output_format)
        logging.info(f"Saved unresolved combinations due to missing 'kingdom' to {unresolved_file_missing_kingdom}.")

    # Save resolved and unresolved rows to DataFrames
    logg
    resolved_df_output = pl.DataFrame(resolved_rows) if resolved_rows else pl.DataFrame()
    unresolved_df_output = pl.DataFrame(unresolved_rows) if unresolved_rows else pl.DataFrame()

    # Merge resolved_df with original combined_df to get source_file information
    if not resolved_df_output.is_empty():
        resolved_df_output = resolved_df_output.join(
            combined_df.select(['uuid', 'source_file']),
            on='uuid',
            how='left'
        )

    if not unresolved_df_output.is_empty():
        unresolved_df_output = unresolved_df_output.join(
            combined_df.select(['uuid', 'source_file']),
            on='uuid',
            how='left'
        )

    # Group resolved_df_output by 'source_file' and save each group separately
    logging.info("Grouping resolved and unresolved rows by 'source_file' and saving to separate files.")
    if not resolved_df_output.is_empty():
        resolved_groups = resolved_df_output.group_by("source_file")
        for group_key, group_df in resolved_groups:
            source_file = group_key if not isinstance(group_key, tuple) else group_key[0]
            base_name = os.path.splitext(source_file)[0]
            output_file = os.path.join(output_dir, f"{base_name}.resolved.{output_format}")
            group_df = group_df.drop(['source_file'])
            write_output_file(group_df, output_file, output_format)
            logging.info(f"Saved resolved rows to {output_file}.")

    # Group unresolved_df_output by 'source_file' and save each group separately
    logging.info("Grouping unresolved rows by 'source_file' and saving to separate files.")
    if not unresolved_df_output.is_empty():
        unresolved_groups = unresolved_df_output.group_by("source_file")
        for group_key, group_df in unresolved_groups:
            source_file = group_key if not isinstance(group_key, tuple) else group_key[0]
            base_name = os.path.splitext(source_file)[0]
            unresolved_file_unresolved = os.path.join(
                output_dir,
                f"{base_name}_unresolved.{output_format}"
            )
            group_df = group_df.drop(['source_file'])
            write_output_file(group_df, unresolved_file_unresolved, output_format)
            logging.info(f"Saved unresolved rows to {unresolved_file_unresolved}.")

    logging.info("All files have been processed and resolved.")
