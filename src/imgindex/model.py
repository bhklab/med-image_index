import pandera.pandas as pa
import pandas as pd
from typing import Literal, Optional

supported_modalities = ['CR', 'CT', 'DX', 'FUSION', 'MG', 'MR', 'NM', 'OT', 'PR', 'PT', 'REG', 'RF', 'RTDOSE', 'RTPLAN', 'RTSTRUCT', 'RWV', 'SC', 'SEG', 'SR', 'US', 'XA']

class BaseSchema(pa.DataFrameModel):
    SampleID: str = pa.Field(nullable=False)
    Modality: str = pa.Field(isin=supported_modalities, nullable=False)
    BodyPartExamined: str = pa.Field(nullable=True)

class DicomIndex(BaseSchema):
    SeriesInstanceUID: str = pa.Field(unique=True, nullable=False)

class NiftiIndex(BaseSchema):
    filepath: str = pa.Field(unique=True, nullable=False)
    ROINames: Optional[str] = pa.Field(nullable=True)

    @pa.dataframe_check(
        error="If any row has Modality=SEG, ROINames must be present and non-null for those rows",
    )
    @classmethod
    def seg_requires_roi_names(cls, df: pd.DataFrame) -> bool:
        seg = df["Modality"] == "SEG"
        if not seg.any():
            return True
        if "ROINames" not in df.columns:
            return False
        return df.loc[seg, "ROINames"].notna().all()

def validate_index(
    index_df: pd.DataFrame, 
    index_type: Literal["dicom", "nifti"],
    lazy: bool = False
) -> Optional[pd.DataFrame]:
    schema = DicomIndex if index_type == "dicom" else NiftiIndex

    try:
        validated_df = schema.validate(index_df, lazy=lazy)
    except (pa.errors.SchemaError, pa.errors.SchemaErrors) as e:
        if not lazy:
            raise ValueError(f"Invalid {index_type.upper()} index: {e}")
        print(f"Invalid {index_type.upper()} index: {e}")
        return None

    return validated_df

if __name__ == "__main__":
    df = pd.read_csv("notebooks/indexed_datasets/.imgtools/Totalsegmentator/index.csv")
    validate_index(df, "nifti", lazy=True)
