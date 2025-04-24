import os
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
    common_name_df = pd.read_csv('/fs/scratch/PAS2136/jianyang/most_common_name_new.tsv', sep='\t', low_memory=False)
    taxon_df = pd.read_csv('/fs/scratch/PAS2136/jianyang/updated_taxon.tsv', sep='\t', quoting=3, low_memory=False)

    root_dir = '/fs/ess/PAS2136/TreeOfLife_TaxonoPy/2025-04-17'
    annotation_list = os.listdir(root_dir)
    annotation_list = [f for f in annotation_list if 'resolved' in f and f.endswith('.parquet')]
    annotation_list = annotation_list[20:]
    output_dir = '/fs/scratch/PAS2136/TreeOfLife/resolved_taxa_with_common_name'

    for file_index, annotation_file in enumerate(annotation_list):
        print(f"Processing {file_index}/{len(annotation_list)}: {annotation_file}")
        print(f"Loading {annotation_file}...")
        anno_df = pd.read_parquet(os.path.join(root_dir, annotation_file))
        print(f"Loaded {annotation_file} with {len(anno_df)} rows.")
        new_anno_df = merge_taxon_id(anno_df, taxon_df)
        new_anno_df = merge_common_name(new_anno_df, common_name_df)
        new_anno_df['scientific_name'] = new_anno_df['scientific_name'].astype(str)
        new_anno_df.to_parquet(os.path.join(output_dir, annotation_file), index=False)
        print(f"Processed {file_index}/{len(annotation_list)}: {annotation_file} and saved to {output_dir}")
