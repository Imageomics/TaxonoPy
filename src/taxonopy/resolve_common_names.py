import os
import argparse
import pandas as pd
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
        print(f"Downloading GBIF backbone (~926MB) into cache → {zip_path}")
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
    new_anno_df = anno_df.copy()
    new_anno_df = new_anno_df.replace('', None)
    new_anno_df = new_anno_df.replace(pd.NA, None)

    print('Start merging with taxon_df')
    for key in ['species', 'genus']:
        new_anno_df = pd.merge(
            new_anno_df,
            taxon_df[['canonicalName', 'taxonID', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus']],
            how='left',
            left_on=[key, 'kingdom', 'phylum', 'class', 'order', 'family', 'genus'],
            right_on=['canonicalName', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus'],
            suffixes=('', f'_{key}')
        )
        new_anno_df = new_anno_df.drop(columns=['canonicalName'])
    new_anno_df.rename(columns={'taxonID': 'taxonID_species'}, inplace=True)

    # Only keep the smallest taxonID for each uuid
    duplicated_uuids = new_anno_df[new_anno_df.duplicated(subset='uuid', keep=False)]
    non_duplicated_df = new_anno_df[~new_anno_df['uuid'].isin(duplicated_uuids['uuid'])]
    duplicated_uuids = duplicated_uuids.loc[duplicated_uuids.groupby('uuid')['taxonID_genus'].idxmin()]
    new_anno_df = pd.concat([non_duplicated_df, duplicated_uuids], ignore_index=True)

    assert len(new_anno_df) == len(anno_df), f"Length mismatch: {len(new_anno_df)} != {len(anno_df)}"

    return new_anno_df


def merge_common_name(anno_df, common_name_df):
    """
    This function is used to merge common name with annotation dataframe
    :param anno_df: annotation dataframe with taxonID
    :param common_name_df: common name dataframe
    :return: merged dataframe
    """
    new_anno_df = anno_df.copy()
    print('Start merging with common_name_df')
    for key in ['species', 'genus']:
        new_anno_df = pd.merge(
            new_anno_df,
            common_name_df,
            how='left',
            left_on=f'taxonID_{key}',
            right_on='taxonID',
            suffixes=('', f'_{key}')
        )
        new_anno_df = new_anno_df.drop(columns=['taxonID'])

    print('Update the common_name column')
    new_anno_df.rename(columns={'vernacularName': 'vernacularName_species'}, inplace=True)
    for key in ['species', 'genus']:
        new_anno_df['common_name'] = new_anno_df.apply(
            lambda x: x['common_name'] if x['common_name'] is not None else x[f'vernacularName_{key}'],
            axis=1
        )
        new_anno_df = new_anno_df.drop(columns=[f'vernacularName_{key}'])
        new_anno_df = new_anno_df.drop(columns=[f'taxonID_{key}'])

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
    common_name_df = (
        pd.read_csv(common_name_file, sep="\t", low_memory=False)
          .query("language == 'en'")
    )
    common_name_df["vernacularName"] = (
        common_name_df["vernacularName"]
          .str.lower()
          .str.capitalize()
    )
    common_name_df = (
        common_name_df
          .groupby("taxonID")["vernacularName"]
          .agg(lambda x: x.value_counts().index[0])
          .reset_index()
    )

    print(f"Loading taxon data from {taxon_file}")
    taxon_df = (
        pd.read_csv(taxon_file, sep="\t", quoting=3, low_memory=False)
          .query("taxonomicStatus == 'accepted' and canonicalName.notnull()")
    )
    
    # Find all .resolved.parquet under annotation_dir
    annotation_paths = glob.glob(
        os.path.join(annotation_dir, "**", "*.resolved.parquet"),
        recursive=True
    )

    # Process one-by-one, preserving subdirs
    for idx, annotation_path in enumerate(annotation_paths, start=1):
        print(f"[{idx}/{len(annotation_paths)}] {annotation_path}")
        anno_df = pd.read_parquet(annotation_path)

        new_df = merge_taxon_id(anno_df, taxon_df)
        new_df = merge_common_name(new_df, common_name_df)
        new_df["scientific_name"] = new_df["scientific_name"].astype(str)

        rel = os.path.relpath(annotation_path, annotation_dir)
        out_path = os.path.join(output_dir, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        new_df.to_parquet(out_path, index=False)
        print(f"    → wrote {out_path}")
