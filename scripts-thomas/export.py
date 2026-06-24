"""
Export pensionnaires DB → output/sources.json

Usage:
    python3 export.py
    python3 export.py --db data/sources.db --out output/sources.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extract import export_all, init_db

DB_DEFAULT  = Path("data/sources.db")
OUT_DEFAULT = Path("output/sources.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporte la base pensionnaires en JSON enrichi."
    )
    parser.add_argument("--db",  default=str(DB_DEFAULT),  metavar="FICHIER.db")
    parser.add_argument("--out", default=str(OUT_DEFAULT), metavar="FICHIER.json")
    args = parser.parse_args()

    db_path  = Path(args.db)
    out_path = Path(args.out)

    if not db_path.exists():
        print(f"Erreur : base introuvable ({db_path})", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)
    export_all(conn, out_path)


if __name__ == "__main__":
    main()
