from typing import Any

import pandas as pd
import pydicom
from pydicom.datadict import dictionary_VR, tag_for_keyword
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

def convert_element_to_int(element_str: str) -> int:
    """
    Converts a DICOM element string representation to an integer.

    Args:
        element_str (str): The DICOM element string representation.

    Returns:
        int: The converted integer value.

    Examples:
        >>> convert_element_to_int('(0028,0010)')
        2621456

    Raises:
        ValueError: If the element format is invalid.

    """
    if element_str.startswith(">"):
        return -1

    elements: list[str] = element_str.strip("()'").split(",")

    # Check if the element has the correct structure
    if len(elements) != 2:
        raise ValueError(
            f"Invalid element format. Element must have the structure '(<INT>,<INT>)': {element_str}"
        )

    # Convert each element from string to integer
    elements_int: list[int]
    elements_int = [int(elem, base=16) for elem in elements]

    # Combine the integers into a single integer
    combined_int: int = (elements_int[0] << 16) + elements_int[1]

    return combined_int


def convert_int_to_element(combined_int: int) -> str:
    """
    Converts a combined integer into a DICOM element string representation.

    Args:
        combined_int (int): The combined integer to be converted.

    Returns:
        str: The DICOM element string representation of the combined integer.

    Examples:
        >>> convert_int_to_element(0x00080060)
        (0008,0060)
        >>> convert_int_to_element(524384)
        (0008,0060)
    """
    assert isinstance(combined_int, int), "combined_int must be an integer."

    if combined_int == -1:
        return "Unknown"

    # Split the integer into two parts
    # i.e 131073 should become (2,1)
    part1: int = combined_int >> 16  # shift right by 16 bits
    part2: int = combined_int & 0xFFFF  # bitwise AND with 0xFFFF (16 bits)

    # Convert the integers to hex strings
    part1_str: str = hex(part1)[2:]
    part2_str: str = hex(part2)[2:]

    # (2,1) should become (0002,0001)
    part1_str = part1_str.zfill(4)
    part2_str = part2_str.zfill(4)

    # capitalize any lowercase letters
    part1_str = part1_str.upper()
    part2_str = part2_str.upper()

    # Combine the hex strings into a single string
    combined_str: str = f"({part1_str},{part2_str})"

    return combined_str




# Pre-compute lookups for commonly used tags to avoid repeated calculations
@lru_cache(maxsize=1024)
def get_tag_info(element_str: str) -> tuple[int, str]:
    """Cached version of element conversion and VR lookup"""
    try:
        combined_int = convert_element_to_int(element_str)
        if combined_int == -1:
            return (-1, "Unknown")
        
        # For metadata tags, we can determine VR quickly
        if combined_int >> 16 == 0x0002:
            # File meta tags have known VRs
            meta_vr_map = {
                0x00020000: "UL",  # FileMetaInformationGroupLength
                0x00020001: "OB",  # FileMetaInformationVersion
                0x00020002: "UI",  # MediaStorageSOPClassUID
                0x00020003: "UI",  # MediaStorageSOPInstanceUID
                0x00020010: "UI",  # TransferSyntaxUID
                0x00020012: "UI",  # ImplementationClassUID
                0x00020013: "SH",  # ImplementationVersionName
            }
            VR = meta_vr_map.get(combined_int, "UN")
        else:
            try:
                VR = dictionary_VR(tag=combined_int)
            except KeyError:
                VR = "Unknown"
        
        return (combined_int, VR)
    except:
        return (-1, "Unknown")

def convert_dicom_value_optimized(val: str, vr: str) -> Any:
    """Optimized value conversion with early returns for common cases"""
    if val == '' or val is None:
        return None
    
    vr = vr.upper()
    
    # Fast path for common VRs that don't need parsing
    if vr in {"PN", "LO", "SH", "UI", "DA", "TM", "CS", "AE", "AS"}:
        return val
    
    # Handle multi-valued strings
    if isinstance(val, str) and '\\' in val:
        values = val.split('\\')
        
        if vr in {"IS", "SS", "US", "SL", "UL", "AT"}:
            return [int(v) for v in values]
        elif vr in {"DS", "FL", "FD"}:
            return [float(v) for v in values]
        elif vr in {"OB", "OW", "OF", "UN", "OL"}:
            return bytes(int(v, 16) for v in values)
        else:
            return values
    else:
        # Single value cases
        if vr in {"IS", "SS", "US", "SL", "UL", "AT"}:
            return int(val)
        elif vr in {"DS", "FL", "FD"}:
            return float(val)
        elif vr in {"OB", "OW", "OF", "UN", "OL"}:
            if isinstance(val, str) and '\\' in val:
                return bytes(int(v, 16) for v in val.split('\\'))
            return bytes([int(val, 16)])
        else:
            return val

def generateFileDatasetFromTags(tags_df: pd.DataFrame) -> pydicom.Dataset:
    """
    Optimized version of generateFileDatasetFromTags.
    """
    ds = pydicom.Dataset()
    ds.ensure_file_meta()
    
    # Pre-allocate lists for batch processing
    tags = []
    values = []
    vrs = []
    
    # Vectorize the initial processing
    for element_str, data in zip(tags_df['element'], tags_df['data']):
        tag, vr = get_tag_info(element_str)
        if tag == -1 or vr == "Unknown":
            continue
        
        # Handle special VR cases
        if vr == "US or SS":
            try:
                # Try to convert to int to check sign
                val_int = int(data)
                vr = "SS" if val_int < 0 else "US"
            except:
                vr = "US"  # Default to US if conversion fails
        
        # Convert value based on VR
        try:
            value = convert_dicom_value_optimized(data, vr)
        except:
            continue
        
        # Store for batch addition
        tags.append(tag)
        values.append(value)
        vrs.append(vr)
    
    # Batch add tags (more efficient than adding one by one)
    for tag, value, vr in zip(tags, values, vrs):
        try:
            if tag >> 16 == 0x0002:  # File meta tags
                ds.file_meta.add_new(tag=tag, VR=vr, value=value)
            else:
                ds.add_new(tag=tag, VR=vr, value=value)
        except:
            continue
    
    # Add DICOM header
    ds.preamble = b"\0" * 128
    return ds
