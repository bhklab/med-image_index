from imgindex.tcia.index import update_index
from nbiatoolkit.nbia import NBIAClient
from pathlib import Path
import datetime


def main(
    NBIA_USERNAME: str,
    NBIA_PASSWORD: str,
    date: str,
):
    client = NBIAClient(username=NBIA_USERNAME, password=NBIA_PASSWORD, timeout_seconds=1000, max_concurrent_requests=32)
    print("Client connection established.")
    
    
    output_path = Path("indexed_datasets")
    output_path.mkdir(parents=True, exist_ok=True)
    
    update_index(
        output_path=output_path, 
        date=datetime.datetime.strptime(date, "%d/%m/%Y").date().strftime("%d/%m/%Y"), 
        is_dry=True,
        client=client,
    )


if __name__ == "__main__":
    
    import argparse

    parser = argparse.ArgumentParser(description="Run a dry run index for TCIA collections.")
    parser.add_argument("--NBIA_USERNAME", type=str, required=True, help="NBIA username")
    parser.add_argument("--NBIA_PASSWORD", type=str, required=True, help="NBIA password")
    parser.add_argument("--date", type=str, required=True, help="Date in format dd/mm/yyyy")

    args = parser.parse_args()

    main(
        NBIA_USERNAME=args.NBIA_USERNAME,
        NBIA_PASSWORD=args.NBIA_PASSWORD,
        date=args.date,
    )
        