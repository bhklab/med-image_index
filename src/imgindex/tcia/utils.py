"""Convert imgtools output to index.csv."""

from pathlib import Path
import hashlib
import pandas as pd
from imgtools.dicom import Interlacer

from imgindex.model import validate_index


def generate_sample_id(ids):
    """Generate a sample ID from a list of IDs."""
    sorted_ids = sorted(map(str, ids))
    key = "|".join(sorted_ids)
    return hashlib.sha256(key.encode()).hexdigest()


def convert_crawl_to_df(
    crawl_db: dict,
) -> pd.DataFrame:
    """Convert imgtools output of a collection to a med-imagenet valid index.csv."""

    main_db = []
    for series_uid, series_data in crawl_db.items():
        record = series_data[next(iter(series_data))]
        if 'ReferencedSeriesUID' not in record:
            record['ReferencedSeriesUID'] = ''  # Add empty string as default
        if 'ReferencedModality' not in record:
                    record['ReferencedModality'] = ''  # Add empty string as default
        if 'folder' not in record:
                            record['folder'] = ''  # Add empty string as default
        if 'SubSeries' not in record:
                            record['SubSeries'] = 1  # Add empty string as default
        if 'instances' in record:
                                    record['instances'] = len(record['instances'].keys())
        main_db.append({
            **record
        })
    return pd.DataFrame(main_db).fillna("")

def propagate_sample_id(s):
    ids = s[s != ""].unique()
    if len(ids) > 1:
        raise ValueError(f"Multiple SampleIDs found: {ids}")
    return ids[0] if len(ids) else ""

def create_sample_ids_and_validate(updated_df: pd.DataFrame):

    interlacer = Interlacer(updated_df)
    if 'SampleID' not in updated_df.columns:
        updated_df['SampleID'] = ""
    else:
        updated_df['SampleID'] = updated_df['SampleID'].fillna("")
    samples = interlacer.query_all()

    for sample in samples:
        sample_series_uids = [series.SeriesInstanceUID for series in sample]

        mask = updated_df["SeriesInstanceUID"].isin(sample_series_uids)

        # SampleID is just a hash of the parent node. 
        sample_id = generate_sample_id([sample_series_uids[0]])

        updated_df.loc[mask, "SampleID"] = sample_id
    
    mask = updated_df["SampleID"] == ""
    updated_df.loc[mask, 'SampleID'] = updated_df.loc[mask, 'SeriesInstanceUID'].apply(lambda x: generate_sample_id([x]))
    validated_df = validate_index(updated_df, "dicom", lazy=True)
    if validated_df is None:
        raise ValueError(f"Invalid index")
    
    return updated_df

# if __name__ == "__main__":
#     from imgnet.collections.store import IndexedDatasets

#     new_index_path = Path("new_index")
#     new_index_path.mkdir(parents=True, exist_ok=True)

#     indexed_datasets = IndexedDatasets()
#     for collection in indexed_datasets.collections:
#         if indexed_datasets.file_type(collection).value == "dicom":
#             print(f"Converting collection {collection}")
#             imgtools_path = indexed_datasets.imgtools_path / collection
#             main_db = convert_to_db(imgtools_path)
#             collection_path = new_index_path / collection
#             collection_path.mkdir(parents=True, exist_ok=True)
#             main_db.to_csv(collection_path / "index.csv", index=False)
#             print(f"Finished converting collection {collection}")



            