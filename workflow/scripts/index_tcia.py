from imgindex.tcia.index import IndexTCIA

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index new TCIA collections.")
    parser.add_argument("--date", type=str, required=True, help="Date in format dd/mm/yyyy.")
    parser.add_argument("--apply", type=bool, required=False, default=True, help="Download and apply update or just produce summary of new data.")

    args = parser.parse_args()

    index = IndexTCIA(output_path="data/tcia/index")
    index.run(since=args.date, apply=args.apply)
