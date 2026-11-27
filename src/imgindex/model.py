"""Pandera schemas and validation for med-image index DataFrames.

Defines shared and index-type-specific column constraints for DICOM and NIfTI
indexes, plus helpers to validate index CSVs before downstream use.
"""

from __future__ import annotations

from typing import Literal, Optional, Type

import pandera.pandas as pa
import pandas as pd

IndexType = Literal["dicom", "nifti"]

MODALITY_COLUMN = "Modality"
ROI_NAMES_COLUMN = "ROINames"
SEGMENTATION_MODALITY = "SEG"

SUPPORTED_MODALITIES = [
    "CR",
    "CT",
    "DX",
    "FUSION",
    "MG",
    "MR",
    "NM",
    "OT",
    "PR",
    "PT",
    "REG",
    "RF",
    "RTDOSE",
    "RTPLAN",
    "RTSTRUCT",
    "RWV",
    "SC",
    "SEG",
    "SR",
    "US",
    "XA",
]


class BaseSchema(pa.DataFrameModel):
    """Shared columns required by all med-image index files."""

    SampleID: str = pa.Field(nullable=False)
    Modality: str = pa.Field(isin=SUPPORTED_MODALITIES, nullable=False)
    BodyPartExamined: str = pa.Field(nullable=True)


class DicomIndex(BaseSchema):
    """Schema for DICOM index CSVs keyed by series instance UID."""

    SeriesInstanceUID: str = pa.Field(unique=True, nullable=False)


class NiftiIndex(BaseSchema):
    """Schema for NIfTI index CSVs keyed by file path."""

    filepath: str = pa.Field(unique=True, nullable=False)
    ROINames: Optional[str] = pa.Field(nullable=True)

    @pa.dataframe_check(
        error=(
            "If any row has Modality=SEG, ROINames must be present and "
            "non-null for those rows"
        ),
    )
    @classmethod
    def seg_requires_roi_names(cls, index_df: pd.DataFrame) -> bool:
        """Require ROINames for segmentation rows.

        Args:
            index_df: NIfTI index data under validation.

        Returns:
            True when every ``Modality=SEG`` row has a non-null ``ROINames`` value.

        Notes:
            Returns True when no segmentation rows are present.
        """
        is_segmentation_row = index_df[MODALITY_COLUMN] == SEGMENTATION_MODALITY
        if not is_segmentation_row.any():
            return True
        if ROI_NAMES_COLUMN not in index_df.columns:
            return False
        return index_df.loc[is_segmentation_row, ROI_NAMES_COLUMN].notna().all()


def get_index_schema(index_type: IndexType) -> Type[BaseSchema]:
    """Return the Pandera schema for an index type.

    Args:
        index_type: Either ``"dicom"`` or ``"nifti"``.

    Returns:
        The schema class used to validate the requested index format.
    """
    if index_type == "dicom":
        return DicomIndex
    return NiftiIndex


def validate_index(
    index_df: pd.DataFrame,
    index_type: str,
    *,
    lazy: bool = False,
) -> Optional[pd.DataFrame]:
    """Validate an index DataFrame against the appropriate schema.

    Args:
        index_df: Raw or partially cleaned index data loaded from CSV.
        index_type: Either ``"dicom"`` or ``"nifti"``.
        lazy: When True, collect all validation errors and return ``None`` on
            failure instead of raising immediately.

    Returns:
        The validated DataFrame when checks pass, or ``None`` when ``lazy``
        is True and validation fails.

    Raises:
        ValueError: When ``lazy`` is False and the index fails validation.

    Notes:
        Assumes ``index_df`` already represents a single collection index and
        has not been mutated by prior validation calls.
    """
    index_schema = get_index_schema(index_type)

    try:
        validated_index_df = index_schema.validate(index_df, lazy=lazy)
    except (pa.errors.SchemaError, pa.errors.SchemaErrors) as validation_error:
        if not lazy:
            raise ValueError(
                f"Invalid {index_type.upper()} index: {validation_error}"
            ) from validation_error
        print(f"Invalid {index_type.upper()} index: {validation_error}")
        return None

    return validated_index_df


if __name__ == "__main__":
    sample_index_df = pd.read_csv(
        "notebooks/indexed_datasets/.imgtools/Totalsegmentator/index.csv"
    )
    validate_index(sample_index_df, "nifti", lazy=True)
