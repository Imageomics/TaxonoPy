import os
import argparse
import polars as pl
import glob
import zipfile
import requests
from pathlib import Path
import shutil

from taxonopy.constants import TAXONOMIC_RANKS_BY_SPECIFICITY, INVALID_VALUES, TAXONOMIC_RANKS

# Module-level constant for join columns to avoid duplication
PARENT_RANKS = TAXONOMIC_RANKS[:-1]

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

def _normalize_one_column(col: str) -> pl.Expr:
    """Build the Utf8‐cast + empty→null expression for a single column."""
    # Cast to string
    casted = pl.col(col).cast(pl.Utf8)
    # Turn "" into None
    cleaned = casted.map_elements(lambda x: None if str(x).lower() in INVALID_VALUES else x, return_dtype=pl.Utf8)
    # Give it back its original name
    return cleaned.alias(col)

def normalize_taxonomic_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normalize taxonomic columns by casting to Utf8 and converting empty strings to null.
    
    :param df: DataFrame with taxonomic columns
    :return: DataFrame with normalized taxonomic columns
    """
    taxonomic_cols = ['species', 'genus', 'family', 'order', 'class', 'phylum', 'kingdom']
    existing = [c for c in taxonomic_cols if c in df.columns]

    # Build a list of clean‐up expressions, one per column
    exprs = [_normalize_one_column(c) for c in existing]

    # Apply them all at once
    return df.with_columns(exprs)

def join_single_rank(anno_df: pl.DataFrame, taxon_df: pl.DataFrame, rank: str) -> pl.DataFrame:
    """
    Join annotation dataframe with taxon dataframe for a single taxonomic rank.
    
    :param anno_df: Annotation dataframe (should have normalized taxonomic columns)
    :param taxon_df: Taxon dataframe  
    :param rank: Taxonomic rank to join on ('species' or 'genus')
    :return: DataFrame with taxonID_{rank} column added
    """
    if rank not in anno_df.columns:
        return anno_df
        
    # Figure out which higher-rank cols we actually have in the anno_df
    join_cols = [c for c in PARENT_RANKS 
                if c in anno_df.columns and c != rank]

    # Select, rename, and drop duplicate backbone rows on the full key
    # - if the taxon_df actually has a taxonRank column, filter by it;
    # - otherwise just use the whole table
    if "taxonRank" in taxon_df.columns:
        candidate = taxon_df.filter(pl.col("taxonRank") == rank)
    else:
        candidate = taxon_df

    backbone_subset = (
        candidate
        .select(
            pl.col("canonicalName"),
            pl.col("taxonID").alias(f"taxonID_{rank}"),
            *join_cols
        )
        .unique(subset=["canonicalName"] + join_cols)
    )
    
    result = anno_df.join(
        backbone_subset,
        left_on=[rank] + join_cols,
        right_on=['canonicalName'] + join_cols,
        how='left'
    )
    
    # Drop canonicalName if it exists
    if 'canonicalName' in result.columns:
        result = result.drop('canonicalName')
        
    return result


def merge_taxon_id(anno_df, taxon_df):
    """
    This function is used to retrieve taxon_id from taxon_df
    :param anno_df: annotation dataframe
    :param taxon_df: taxon dataframe
    :return: merged dataframe
    """
    new_anno_df = normalize_taxonomic_columns(anno_df.clone())

    print('Start merging with taxon_df')
    for rank in ['species', 'genus']:
        new_anno_df = join_single_rank(new_anno_df, taxon_df, rank)

    # With the backbone_subset de-duped above, joins are one-to-one, so
    # the row count will always match.
    assert len(new_anno_df) == len(anno_df), (
        f"Length mismatch after taxon joins: {len(new_anno_df)} != {len(anno_df)}"
    )

    return new_anno_df


def prioritize_vernacular(vernacular_df: pl.DataFrame) -> pl.DataFrame:
    """
    Prioritize vernacular names with English preference.
    
    :param vernacular_df: Raw GBIF vernacular DataFrame with taxonID, vernacularName, language columns
    :return: DataFrame with columns (taxonID, vernacularName) prioritizing English, then any other language
    """
    # English vernaculars, priority 1
    english = (
        vernacular_df
        .filter(pl.col("language") == "en")
        .with_columns([pl.lit(1).alias("priority")])
        .group_by("taxonID")
        .agg([
            pl.col("vernacularName").first(),
            pl.col("priority").first(),
        ])
    )

    # Non-English vernaculars, priority 2
    other = (
        vernacular_df
        .filter(pl.col("language") != "en")
        .with_columns([pl.lit(2).alias("priority")])
        .group_by("taxonID")
        .agg([
            pl.col("vernacularName").first(),
            pl.col("priority").first(),
        ])
    )

    # Merge and pick the top‐priority name, then drop the priority column
    result = (
        pl.concat([english, other])
          .group_by("taxonID")
          .agg(
            pl.col("vernacularName")
              .sort_by("priority")
              .first()
              .alias("vernacularName")
          )
    )

    # Just in case, ensure we only have the two columns
    return result.select(["taxonID", "vernacularName"])


def apply_hierarchical_common_name_lookup(anno_df: pl.DataFrame, common_lookup: pl.DataFrame) -> pl.DataFrame:
    """
    Apply hierarchical common name lookup from most specific to least specific rank.
    
    :param anno_df: Annotation dataframe with taxonID_* columns
    :param common_lookup: Common name lookup table with (taxonID, common_name) columns
    :return: DataFrame with common_name column populated using hierarchical fallback
    """
    # Define hierarchical order of taxonomic ranks (map class_ to class)
    rank_columns = [r.rstrip('_') for r in TAXONOMIC_RANKS_BY_SPECIFICITY]

    # Initialize common_name column
    result_df = anno_df.with_columns(pl.lit(None).cast(pl.Utf8).alias("common_name"))
    
    # Apply hierarchical lookup - check each rank in priority order
    for rank in rank_columns:
        taxonid_col = f"taxonID_{rank}"
        if taxonid_col not in result_df.columns:
            continue
            
        # Join common names for this rank
        temp_df = result_df.join(
            common_lookup.select([
                "taxonID", 
                pl.col("common_name").alias(f"temp_common_{rank}")
            ]),
            left_on=taxonid_col,
            right_on="taxonID",
            how="left"
        )
        
        # Update common_name where it's null and this rank has a name
        result_df = (
            temp_df
            # pick up the new common_name, drop the temp join field
            .with_columns([
                pl.coalesce([
                    pl.col("common_name"), 
                    pl.col(f"temp_common_{rank}")
                ]).alias("common_name")
            ])
            .drop(f"temp_common_{rank}")
        )
        
        # Drop taxonID column if it exists (may not exist if no matches)
        if "taxonID" in result_df.columns:
            result_df = result_df.drop("taxonID")
    
    return result_df


def override_input_common_name(df: pl.DataFrame, common_lookup: pl.DataFrame) -> pl.DataFrame:
    """
    Override any existing common_name column with backbone-derived common names.
    
    :param df: DataFrame that may have a pre-existing common_name column
    :param common_lookup: Common name lookup table with hierarchical fallback applied
    :return: DataFrame with backbone-derived common_name (input common_name completely replaced)
    """
    # Drop any existing common_name column and apply the backbone lookup
    df_clean = df.drop("common_name") if "common_name" in df.columns else df
    return apply_hierarchical_common_name_lookup(df_clean, common_lookup)


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
    
    # Define hierarchical order of taxonomic ranks (map class_ to class)
    rank_columns = [r.rstrip('_') for r in TAXONOMIC_RANKS_BY_SPECIFICITY]    

    # Find which taxonomic classification columns we have 
    available_rank_cols = [rank for rank in rank_columns 
                          if rank in new_anno_df.columns]
    
    # Get taxonIDs for all ranks from taxon_df (this ensures we have the authoritative mapping)
    for rank in available_rank_cols:
        taxonid_col = f"taxonID_{rank}"
        temp_taxonid_col = f"temp_taxonID_{rank}"
        
        # Always look up the authoritative taxonID from taxon_df
        # Only one row per canonicalName at this rank
        rank_taxa = (
            taxon_df
            .filter(pl.col("taxonRank") == rank)
            .select([
                pl.col("taxonID").alias(temp_taxonid_col),
                pl.col("canonicalName").alias(rank)
            ])
            .unique(subset=[rank])
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
    
    # Override any input common_name with backbone data
    new_anno_df = override_input_common_name(new_anno_df, common_lookup)
    
    # Clean up temporary taxonID columns (keep original taxonomic classification columns)
    cleanup_cols = [f"taxonID_{rank}" for rank in rank_columns]
    existing_cleanup_cols = [col for col in cleanup_cols if col in new_anno_df.columns]
    if existing_cleanup_cols:
        new_anno_df = new_anno_df.drop(existing_cleanup_cols)

    # With all of our backbone joins de-duplicated, we should never change row count:
    assert len(new_anno_df) == len(anno_df), (
        f"Length mismatch after common-name merge: {len(new_anno_df)} != {len(anno_df)}"
    )

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
    print(f"Loading vernacular names from {common_name_file}")

    # Load all vernacular names, prioritizing English but keeping others as fallback
    # Turn off schema inference to handle improperly escaped quotes in GBIF data
    vernacular_df = pl.read_csv(common_name_file, separator="\t", infer_schema_length=0, quote_char=None)
    
    # Create prioritized vernacular names: prefer English, fallback to any language
    common_name_df = prioritize_vernacular(vernacular_df)

    print(f"Loading backbone taxa from {taxon_file}")
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
