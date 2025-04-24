import os
import argparse
import pandas as pd


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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve common names for taxa")
    parser.add_argument('--common_name_file', type=str, required=True, help='Path to the common name file')
    parser.add_argument('--taxon_file', type=str, required=True, help='Path to the taxonID file')
    parser.add_argument('--annotation_dir', type=str, required=True, help='Directory containing annotation files')
    parser.add_argument('--output_dir', type=str, required=True, help='Directory to save the output files')
    args = parser.parse_args()

    # Load the common name dataframes and keep the most common ones for each taxonID
    common_name_df = pd.read_csv(args.common_name_file, sep='\t', low_memory=False)
    common_name_df = common_name_df[common_name_df['language'] == 'en']
    common_name_df['vernacularName'] = common_name_df['vernacularName'].str.lower()
    common_name_df['vernacularName'] = common_name_df['vernacularName'].str.capitalize()
    common_name_df = common_name_df.groupby('taxonID')['vernacularName'].agg(lambda x: x.value_counts().index[0]).reset_index()

    # Load the taxon dataframe and keep the valid ones
    taxon_df = pd.read_csv(args.taxon_file, sep='\t', quoting=3, low_memory=False)
    taxon_df = taxon_df.loc[
        (taxon_df['taxonomicStatus'] == 'accepted') &
        (taxon_df['canonicalName'].notnull())
    ]

    # Filter the common name dataframe
    annotation_list = os.listdir(args.annotation_dir)
    annotation_list = [f for f in annotation_list if 'resolved' in f and f.endswith('.parquet')]

    # Ensure the output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # Process each annotation file
    for file_index, annotation_file in enumerate(annotation_list):
        print(f"Processing {file_index}/{len(annotation_list)}: {annotation_file}")
        print(f"Loading {annotation_file}...")
        anno_df = pd.read_parquet(os.path.join(args.annotation_dir, annotation_file))
        print(f"Loaded {annotation_file} with {len(anno_df)} rows.")
        new_anno_df = merge_taxon_id(anno_df, taxon_df)
        new_anno_df = merge_common_name(new_anno_df, common_name_df)
        new_anno_df['scientific_name'] = new_anno_df['scientific_name'].astype(str)
        new_anno_df.to_parquet(os.path.join(args.output_dir, annotation_file), index=False)
        print(f"Processed {file_index}/{len(annotation_list)}: {annotation_file} and saved to {args.output_dir}")
