"""
Carottage des sources/classe1.pdf – classe7.pdf.

Passe sur toutes les pages (sans API) et affiche :
  - nombre d'entrées par page (moy / min / max / σ)
  - total estimé et coût estimé par source
  - récapitulatif global

Usage : python3 probe_sources.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).parent))
from extract import get_text_blocks, segment_entries, segment_table_entries, is_tabular_format

SOURCES_DIR        = Path("sources")
COST_PER_ENTRY_EUR = 0.020   # estimation prudente (vision activée)


def probe_source(pdf_path: Path, class_num: int) -> dict | None:
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  Erreur ouverture : {e}", file=sys.stderr)
        return None

    tabular = is_tabular_format(class_num)
    counts: list[int] = []

    for page_idx in range(doc.page_count):
        page   = doc.load_page(page_idx)
        blocks = get_text_blocks(page)
        groups = segment_table_entries(blocks) if tabular else segment_entries(blocks)
        counts.append(len(groups))

    if not counts:
        return None

    avg       = sum(counts) / len(counts)
    var       = sum((c - avg) ** 2 for c in counts) / len(counts)
    est_total = round(avg * doc.page_count)

    return {
        "class":        class_num,
        "pages":        doc.page_count,
        "format":       "tableau" if tabular else "paragraphes",
        "avg":          avg,
        "min":          min(counts),
        "max":          max(counts),
        "stdev":        math.sqrt(var),
        "est_total":    est_total,
        "est_cost_eur": est_total * COST_PER_ENTRY_EUR,
    }


def main() -> None:
    results: list[dict] = []

    for i in range(1, 9):
        pdf_path = SOURCES_DIR / f"classe{i}.pdf"
        if not pdf_path.exists():
            print(f"  classe{i}.pdf  non trouvé — ignoré", file=sys.stderr)
            continue
        print(f"  classe{i}.pdf …", end=" ", flush=True)
        r = probe_source(pdf_path, i)
        if r is None:
            print("échec")
            continue
        results.append(r)
        print(f"{r['pages']} pages  moy={r['avg']:.1f}  σ={r['stdev']:.1f}")

    if not results:
        print("Aucune source trouvée dans sources/")
        return

    # ── colonnes ─────────────────────────────────────────────────────────────
    #  Cl  Format        Pages   Moy    Min  Max     σ    Total    Coût
    W   = 72
    SEP = "═" * W
    sep = "─" * W

    print()
    print(SEP)
    print(f"  {'Cl':>2}  {'Format':<12}  {'Pages':>5}  {'Moy/p':>5}  {'Min':>3}  {'Max':>3}  {'σ':>4}  {'Total':>7}  {'Coût':>7}")
    print(sep)
    for r in results:
        print(
            f"  {r['class']:>2}  {r['format']:<12}  {r['pages']:>5}"
            f"  {r['avg']:>5.1f}  {r['min']:>3}  {r['max']:>3}  {r['stdev']:>4.1f}"
            f"  {r['est_total']:>7,}  {r['est_cost_eur']:>6.0f} €"
        )
    print(sep)
    tot_pages   = sum(r["pages"]       for r in results)
    tot_entries = sum(r["est_total"]   for r in results)
    tot_cost    = sum(r["est_cost_eur"] for r in results)
    print(
        f"  {'TOTAL':<15}  {tot_pages:>5}"
        f"  {'':>5}  {'':>3}  {'':>3}  {'':>4}"
        f"  {tot_entries:>7,}  {tot_cost:>6.0f} €"
    )
    print(SEP)
    print(f"  Coût unitaire : {COST_PER_ENTRY_EUR:.4f} €/entrée  (vision activée)")
    print(SEP)


if __name__ == "__main__":
    main()
