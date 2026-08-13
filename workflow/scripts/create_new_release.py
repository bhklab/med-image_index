"""
Steps:
1. Run the index
2. Convert indexes to correct format and run validator
3. Concat updated indexes into old index 
4. Push to HuggingFace
"""

import datetime
from huggingface_hub import HfApi, login


import math

import pandas as pd
from pathlib import Path

def format_size_gb(size_gb):
    if size_gb < 0.005:
        return f"{size_gb * 1024:.1f} MB"
    else:
        return f"{size_gb:.2f} GB"

def main():
    #login()
    api = HfApi()

    repo_id = "bhklab2026/med-image-index"
    branch_name = f"TCIA-auto-update-{datetime.date.today().strftime('%d-%m-%Y')}"

    # 1. Create a new branch
    api.create_branch(
        repo_id=repo_id,
        branch=branch_name,
        repo_type="dataset",
        exist_ok=True
    )

    # 2. Determine which indexed_datasets subfolders are being updated
    indexed_datasets_path = Path("data/tcia/index/indexed_datasets")

    delete_patterns = [
        f"indexed_datasets/{folder.name}/**"
        for folder in indexed_datasets_path.iterdir()
        if folder.is_dir()
    ]

    # 4. Generate update summary
    new_collections = pd.read_csv("data/tcia/index/new_collections_table.csv")
    updated_collections = pd.read_csv("data/tcia/index/updated_collections_table.csv")

    new_collections["Size (GB)"] = new_collections["Size (GB)"].apply(lambda x: format_size_gb(x))
    updated_collections["Size (GB)"] = updated_collections["Size (GB)"].apply(lambda x: format_size_gb(x))
    
    new_collections["summary_string"] = new_collections.apply(
        lambda x: (
            f"{x['Collection']}:\n"
            f"    +{x['SeriesCount']} series\n"
            f"    +{x['Size (GB)']} GB\n"
        ),
        axis=1,
    )

    updated_collections["summary_string"] = updated_collections.apply(
        lambda x: (
            f"{x['Collection']}:\n"
            f"    +{x['SeriesCount']} series\n"
            f"    +{x['Size (GB)']} GB\n"
        ),
        axis=1,
    )
    update_summary = f"""
New Collections:

{"".join(new_collections["summary_string"].to_list())}

Updated Collections:

{"".join(updated_collections["summary_string"].to_list())}
    """
    print(update_summary)
    # 5. Create pull request

    # 3. Upload updated indexed_datasets subfolders only
    api.upload_folder(
        folder_path=str(indexed_datasets_path),
        path_in_repo="indexed_datasets",
        repo_id=repo_id,
        repo_type="dataset",
        create_pr=True,
        commit_message="TCIA index update",
        commit_description=update_summary,
        delete_patterns=delete_patterns,
    )


if __name__ == "__main__":
    main()
        