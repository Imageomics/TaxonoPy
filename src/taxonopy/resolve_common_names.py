import os
import argparse
import polars as pl
import glob
import zipfile
import requests
from pathlib import Path
import shutil

def download_and_extract_backbone(cache_dir: Path):
    """Download and extract the GBIF backbone taxonomy files."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "backbone.zip"
    
    # Direct URL to the GBIF backbone taxonomy
    backbone_url = "https://hosted-datasets.gbif.org/datasets/backbone/current/backbone.zip"
    
    # Check if the taxon files already exist in the cache
    taxon_file = cache_dir / "Taxon.tsv"
    vernacular_file = cache_dir / "VernacularName.tsv"
    
    # If both files already exist, just return their paths
    if taxon_file.exists() and vernacular_file.exists():
        print("Using cached taxonomy files")
        return taxon_file, vernacular_file
    
    # Download if needed
    if not zip_path.exists() or zip_path.stat().st_size < 900_000_000:  # Expect ~926MB
        print(f"Downloading GBIF backbone into cache → {zip_path}")
        try:
            # Remove partial/corrupt file if it exists
            if zip_path.exists():
                zip_path.unlink()
                
            # Download with progress indication
            resp = requests.get(backbone_url, stream=True)
            resp.raise_for_status()
            
            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024*1024):  # 1MB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Progress indication
                        percent = (downloaded / total_size) * 100 if total_size > 0 else 0
                        print(f"\rDownloading: {percent:.1f}% ({downloaded/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB)", end="")
                
                print("\nDownload complete")
        except Exception as e:
            # Clean up partial download
            if zip_path.exists():
                zip_path.unlink()
            print(f"Error downloading backbone taxonomy: {e}")
            raise RuntimeError(f"Failed to download GBIF backbone: {e}")

    # Verify the file exists and has a reasonable size
    if not zip_path.exists():
        raise FileNotFoundError(f"Backbone ZIP file not found at {zip_path}")
    
    file_size_mb = zip_path.stat().st_size / (1024*1024)
    if file_size_mb < 900:  # Expected size is ~926MB
        print(f"Warning: ZIP file size ({file_size_mb:.1f}MB) is smaller than expected (~926MB)")
    
    print(f"Extracting required files from backbone.zip ({file_size_mb:.1f}MB)...")
    
    try:
        # Check and extract from the ZIP file
        with zipfile.ZipFile(zip_path, "r") as z:
            # List available files with case-insensitive matching
            available_files = [f for f in z.namelist()]
            print(f"Found {len(available_files)} files in archive")
            
            # Look for the taxonomy files (case-insensitive)
            taxon_in_zip = next((f for f in available_files if f.lower().endswith("taxon.tsv")), None)
            vernacular_in_zip = next((f for f in available_files if f.lower().endswith("vernacularname.tsv")), None)
            
            if not taxon_in_zip or not vernacular_in_zip:
                print(f"Available files: {[f for f in available_files if f.endswith('.tsv')]}")
                raise ValueError("Required taxonomy files not found in ZIP archive")
            
            # Extract with correct paths
            print(f"Extracting {taxon_in_zip}")
            with z.open(taxon_in_zip) as src, open(taxon_file, "wb") as dst:
                shutil.copyfileobj(src, dst)
                
            print(f"Extracting {vernacular_in_zip}")
            with z.open(vernacular_in_zip) as src, open(vernacular_file, "wb") as dst:
                shutil.copyfileobj(src, dst)
                
            print("Extraction complete")
            
    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid ZIP file")
        # Remove corrupt file to force re-download next time
        if zip_path.exists():
            zip_path.unlink()
        raise RuntimeError("Downloaded backbone ZIP is corrupt. Please try again.")
    
    # Verify extracted files
    if not taxon_file.exists() or not vernacular_file.exists():
        raise FileNotFoundError("Required taxonomy files not extracted successfully")
    
    return taxon_file, vernacular_file

def merge_taxon_id(anno_df, taxon_df):
    """
    This function is used to retrieve taxon_id from taxon_df
    :param anno_df: annotation dataframe
    :param taxon_df: taxon dataframe
    :return: merged dataframe
    """
    new_anno_df = anno_df.clone()
    
    # Cast join key columns to Utf8 and convert empty strings to null
    taxonomic_cols = ['species', 'genus', 'family', 'order', 'class', 'phylum', 'kingdom']
    existing_cols = [col for col in taxonomic_cols if col in new_anno_df.columns]
    
    new_anno_df = new_anno_df.with_columns([
        pl.col(col).cast(pl.Utf8).map_elements(lambda x: None if x == '' else x, return_dtype=pl.Utf8)
        for col in existing_cols
    ])

    print('Start merging with taxon_df')
    for key in ['species', 'genus']:
        if key not in new_anno_df.columns:
            continue
            
        # Select and rename taxonID to avoid conflicts
        backbone_subset = taxon_df.select([
            'canonicalName', 
            pl.col('taxonID').alias(f'taxonID_{key}'),
            'kingdom', 'phylum', 'class', 'order', 'family', 'genus'
        ])
        
        # Get columns that exist in both dataframes for joining
        join_cols = [col for col in ['kingdom', 'phylum', 'class', 'order', 'family', 'genus'] 
                     if col in new_anno_df.columns]
        
        new_anno_df = new_anno_df.join(
            backbone_subset,
            left_on=[key] + join_cols,
            right_on=['canonicalName'] + join_cols,
            how='left'
        )
        
        # Drop canonicalName if it exists
        if 'canonicalName' in new_anno_df.columns:
            new_anno_df = new_anno_df.drop('canonicalName')

    # Only keep the smallest taxonID for each uuid (handle duplicates)
    if 'uuid' in new_anno_df.columns and 'taxonID_genus' in new_anno_df.columns:
        duplicated_uuids = new_anno_df.filter(pl.col('uuid').is_duplicated())
        if len(duplicated_uuids) > 0:
            non_duplicated_df = new_anno_df.filter(~pl.col('uuid').is_in(duplicated_uuids['uuid']))
            duplicated_uuids = duplicated_uuids.group_by('uuid').agg(pl.col('taxonID_genus').min()).join(
                duplicated_uuids, on=['uuid', 'taxonID_genus'], how='inner'
            )
            new_anno_df = pl.concat([non_duplicated_df, duplicated_uuids])

    assert len(new_anno_df) == len(anno_df), f"Length mismatch: {len(new_anno_df)} != {len(anno_df)}"

    return new_anno_df


def merge_common_name(anno_df, common_name_df, taxon_df):
    """
    This function merges common names with annotation dataframe using hierarchical lookup.
    Common names are always derived from backbone lookup data for consistent mapping.
    Prefers English names, falls back to any language if English unavailable.
    Searches from most specific taxonomic rank to least specific.
    
    :param anno_df: annotation dataframe with taxonID
    :param common_name_df: common name dataframe (prioritized)
    :param taxon_df: taxon dataframe for rank information
    :return: merged dataframe
    """
    new_anno_df = anno_df.clone()
    print('Start hierarchical common name lookup using backbone data only')
    
    # Normalize common_name_df to one row per taxonID (handle duplicates)
    common_lookup = (
        common_name_df
        .group_by("taxonID")
        .agg(pl.col("vernacularName").first().alias("common_name"))
    )
    
    # Define hierarchical order of taxonomic ranks
    rank_columns = ['species', 'genus', 'family', 'order', 'class', 'phylum', 'kingdom']
    
    # Find which taxonomic ranks we actually have taxonIDs for
    available_taxonid_cols = [f"taxonID_{rank}" for rank in rank_columns 
                              if f"taxonID_{rank}" in new_anno_df.columns]
    
    # Find which taxonomic classification columns we have 
    available_rank_cols = [rank for rank in rank_columns 
                          if rank in new_anno_df.columns]
    
    # Get taxonIDs for all ranks from taxon_df (this ensures we have the authoritative mapping)
    for rank in available_rank_cols:
        taxonid_col = f"taxonID_{rank}"
        temp_taxonid_col = f"temp_taxonID_{rank}"
        
        # Always look up the authoritative taxonID from taxon_df
        rank_taxa = (
            taxon_df
            .filter(pl.col("taxonRank") == rank)
            .select([pl.col("taxonID").alias(temp_taxonid_col), pl.col("canonicalName").alias(rank)])
        )
        
        new_anno_df = new_anno_df.join(
            rank_taxa,
            on=rank,
            how="left"
        )
        
        # Use the authoritative taxonID, falling back to existing one if lookup failed
        if taxonid_col in new_anno_df.columns:
            new_anno_df = new_anno_df.with_columns([
                pl.coalesce([pl.col(temp_taxonid_col), pl.col(taxonid_col)]).alias(taxonid_col)
            ]).drop(temp_taxonid_col)
        else:
            new_anno_df = new_anno_df.rename({temp_taxonid_col: taxonid_col})
    
    # Initialize common_name column
    new_anno_df = new_anno_df.with_columns(pl.lit(None).cast(pl.Utf8).alias("common_name"))
    
    # Apply hierarchical lookup - check each rank in priority order
    for rank in rank_columns:
        taxonid_col = f"taxonID_{rank}"
        if taxonid_col not in new_anno_df.columns:
            continue
            
        # Join common names for this rank
        temp_df = new_anno_df.join(
            common_lookup.select([
                "taxonID", 
                pl.col("common_name").alias(f"temp_common_{rank}")
            ]),
            left_on=taxonid_col,
            right_on="taxonID",
            how="left"
        )
        
        # Update common_name where it's null and this rank has a name
        new_anno_df = temp_df.with_columns([
            pl.coalesce([
                pl.col("common_name"), 
                pl.col(f"temp_common_{rank}")
            ]).alias("common_name")
        ]).drop(f"temp_common_{rank}")
    
    # Clean up temporary taxonID columns (keep original taxonomic classification columns)
    cleanup_cols = [f"taxonID_{rank}" for rank in rank_columns]
    existing_cleanup_cols = [col for col in cleanup_cols if col in new_anno_df.columns]
    if existing_cleanup_cols:
        new_anno_df = new_anno_df.drop(existing_cleanup_cols)

    assert len(new_anno_df) == len(anno_df), f"Length mismatch: {len(new_anno_df)} != {len(anno_df)}"

    return new_anno_df

def main(annotation_dir=None, output_dir=None):
    """
    Merge common names into resolved output files.
    """
    # Parse from command line
    if annotation_dir is None or output_dir is None:
        parser = argparse.ArgumentParser(
            description="(dev) Merge common names into a directory of .resolved.parquet files"
        )
        parser.add_argument(
            "--resolved-dir",
            dest="annotation_dir",
            required=True,
            help="Where your .resolved.parquet files live"
        )
        parser.add_argument(
            "--output-dir",
            required=True,
            help="Where to write the new, annotated .parquet files"
        )
        args = parser.parse_args()

        # Update config if cache-dir was provided
        if args.cache_dir:
            from taxonopy.config import config
            config.cache_dir = args.cache_dir
            Path(config.cache_dir).mkdir(parents=True, exist_ok=True)

        annotation_dir = args.annotation_dir
        output_dir = args.output_dir
    
    # Use global config's cache_dir
    from taxonopy.config import config
    cache_dir = Path(config.cache_dir)
    taxon_file, common_name_file = download_and_extract_backbone(cache_dir)
    
    # Load the two TSVs
    print(f"Loading taxonomy data from {taxon_file}")
    
    # Load all vernacular names, prioritizing English but keeping others as fallback
    # Turn off schema inference to handle improperly escaped quotes in GBIF data
    vernacular_df = pl.read_csv(common_name_file, separator="\t", infer_schema_length=0, quote_char=None)
    
    # Create prioritized vernacular names: prefer English, fallback to any language
    english_names = (
        vernacular_df
        .filter(pl.col("language") == "en")
        .with_columns([
            pl.col("vernacularName").str.to_lowercase().str.to_titlecase().alias("vernacularName"),
            pl.lit(1).alias("priority")
        ])
        .group_by("taxonID")
        .agg([
            pl.col("vernacularName").first().alias("vernacularName"),
            pl.col("priority").first().alias("priority")
        ])
    )
    
    other_names = (
        vernacular_df
        .filter(pl.col("language") != "en")
        .with_columns([
            pl.col("vernacularName").str.to_lowercase().str.to_titlecase().alias("vernacularName"),
            pl.lit(2).alias("priority")
        ])
        .group_by("taxonID")
        .agg([
            pl.col("vernacularName").first().alias("vernacularName"),
            pl.col("priority").first().alias("priority")
        ])
    )
    
    # Combine with English preference
    common_name_df = (
        pl.concat([english_names, other_names])
        .group_by("taxonID")
        .agg([
            pl.col("vernacularName").sort_by("priority").first().alias("vernacularName")
        ])
    )

    print(f"Loading taxon data from {taxon_file}")
    taxon_df = (
        pl.read_csv(taxon_file, separator="\t", infer_schema_length=0, quote_char=None)
        .filter(
            (pl.col("taxonomicStatus") == "accepted") & 
            (pl.col("canonicalName").is_not_null())
        )
    )
    
    # Find all .resolved.parquet under annotation_dir
    annotation_paths = glob.glob(
        os.path.join(annotation_dir, "**", "*.resolved.parquet"),
        recursive=True
    )

    # Process one-by-one, preserving subdirs
    for idx, annotation_path in enumerate(annotation_paths, start=1):
        print(f"[{idx}/{len(annotation_paths)}] {annotation_path}")
        anno_df = pl.read_parquet(annotation_path)

        new_df = merge_taxon_id(anno_df, taxon_df)
        new_df = merge_common_name(new_df, common_name_df, taxon_df)
        new_df = new_df.with_columns([
            pl.col("scientific_name").cast(pl.Utf8)
        ])

        rel = os.path.relpath(annotation_path, annotation_dir)
        out_path = os.path.join(output_dir, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        new_df.write_parquet(out_path)
        print(f"    → wrote {out_path}")
