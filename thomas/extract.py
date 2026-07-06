"""
Pensionnaire extractor — PyMuPDF layout + Claude vision → SQLite.

Usage:
    python essai.py source7.pdf --pages 1-3
    python essai.py source7.pdf --probe 5     # test schéma sur 5 pages aléatoires
    python essai.py source7.pdf --no-vision   # texte seul
    ANTHROPIC_API_KEY=sk-... python essai.py source7.pdf -o output
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import anthropic
import fitz  # PyMuPDF


# ── Constants ─────────────────────────────────────────────────────────────────

SCALE = 2.0          # PDF points → rendered pixels
EUR_USD_RATE = 0.92  # ECB reference rate — update as needed

# claude-opus-4-8 pricing (USD / 1M tokens)
PRICE_INPUT       = 5.00
PRICE_OUTPUT      = 25.00
PRICE_CACHE_WRITE = 6.25
PRICE_CACHE_READ  = 0.50


# ── Cost helpers ──────────────────────────────────────────────────────────────

def tokens_cost_eur(
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    usd = (
        input_tokens        / 1_000_000 * PRICE_INPUT
        + output_tokens     / 1_000_000 * PRICE_OUTPUT
        + cache_write_tokens / 1_000_000 * PRICE_CACHE_WRITE
        + cache_read_tokens  / 1_000_000 * PRICE_CACHE_READ
    )
    return usd * EUR_USD_RATE


class CostTracker:
    def __init__(self) -> None:
        self.input_tokens       = 0
        self.output_tokens      = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens  = 0
        self.calls              = 0

    def add(self, usage: anthropic.types.Usage) -> None:
        self.calls              += 1
        self.input_tokens       += usage.input_tokens
        self.output_tokens      += usage.output_tokens
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens  += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens
                + self.cache_write_tokens + self.cache_read_tokens)

    @property
    def cost_eur(self) -> float:
        return tokens_cost_eur(
            self.input_tokens, self.output_tokens,
            self.cache_write_tokens, self.cache_read_tokens,
        )

    def line(self) -> str:
        return f"{self.calls} appels  {self.total_tokens:,} tok  {self.cost_eur:.4f}€"


# ── SQLite ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    class        INTEGER NOT NULL,
    page         INTEGER NOT NULL,
    image_path   TEXT,
    file_size_kb INTEGER,
    text         TEXT,
    nb_entries   INTEGER,
    processed_at TEXT,
    UNIQUE(class, page)
);

CREATE TABLE IF NOT EXISTS pensionnaires (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    class                INTEGER NOT NULL,
    page                 INTEGER NOT NULL,
    entry_number         INTEGER,
    x                    INTEGER,
    y                    INTEGER,
    x_fin                INTEGER,
    y_fin                INTEGER,
    last_name            TEXT,
    first_name           TEXT,
    widow_of             TEXT,
    title                TEXT,
    sex                  TEXT,
    age                  INTEGER,
    birth_year           INTEGER,
    total_amount         INTEGER,
    incoherence          INTEGER,
    jobs                 TEXT,
    detailed_pensions    TEXT,
    suggestions          TEXT,
    input_tokens         INTEGER DEFAULT 0,
    output_tokens        INTEGER DEFAULT 0,
    cache_write_tokens   INTEGER DEFAULT 0,
    cache_read_tokens    INTEGER DEFAULT 0,
    cost_eur             REAL DEFAULT 0.0,
    entry_hash           TEXT UNIQUE,
    extracted_at         TEXT DEFAULT (datetime('now')),
    wikidata_id          TEXT,
    wikidata_score       REAL,
    prosocour_id         TEXT,
    prosocour_score      REAL
);
"""


_MIGRATIONS = [
    "ALTER TABLE pensionnaires RENAME COLUMN line TO entry_number",
    "ALTER TABLE pensionnaires RENAME COLUMN file TO class",
    "ALTER TABLE pages RENAME COLUMN file TO class",
    "ALTER TABLE pensionnaires ADD COLUMN entry_number INTEGER",
    "ALTER TABLE pensionnaires ADD COLUMN widow_of TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN birth_year INTEGER",
    "ALTER TABLE pensionnaires ADD COLUMN incoherence INTEGER",
    "ALTER TABLE pensionnaires ADD COLUMN suggestions TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN cache_write_tokens INTEGER DEFAULT 0",
    "ALTER TABLE pensionnaires ADD COLUMN cache_read_tokens INTEGER DEFAULT 0",
    "ALTER TABLE pensionnaires ADD COLUMN cost_eur REAL DEFAULT 0.0",
    "ALTER TABLE pensionnaires ADD COLUMN entry_hash TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN extracted_at TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN wikidata_id TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN wikidata_score REAL",
    "ALTER TABLE pensionnaires ADD COLUMN prosocour_id TEXT",
    "ALTER TABLE pensionnaires ADD COLUMN prosocour_score REAL",
]


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn


def _entry_hash(class_num: int, page: int, text: str) -> str:
    return hashlib.sha1(f"{class_num}|{page}|{text[:300]}".encode()).hexdigest()


def is_processed(conn: sqlite3.Connection, h: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM pensionnaires WHERE entry_hash = ?", (h,)
    ).fetchone() is not None


def save_pensionnaire(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO pensionnaires (
            class, page, entry_number, x, y, x_fin, y_fin,
            last_name, first_name, widow_of, title, sex, age, birth_year,
            total_amount, incoherence, jobs, detailed_pensions, suggestions,
            input_tokens, output_tokens, cache_write_tokens, cache_read_tokens,
            cost_eur, entry_hash, extracted_at,
            wikidata_id, wikidata_score,
            prosocour_id, prosocour_score
        ) VALUES (
            :class, :page, :entry_number, :x, :y, :x_fin, :y_fin,
            :last_name, :first_name, :widow_of, :title, :sex, :age, :birth_year,
            :total_amount, :incoherence, :jobs, :detailed_pensions, :suggestions,
            :input_tokens, :output_tokens, :cache_write_tokens, :cache_read_tokens,
            :cost_eur, :entry_hash, :extracted_at,
            :wikidata_id, :wikidata_score,
            :prosocour_id, :prosocour_score
        )
    """, row)
    conn.commit()


def save_page(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO pages
            (class, page, image_path, file_size_kb, text, nb_entries, processed_at)
        VALUES
            (:class, :page, :image_path, :file_size_kb, :text, :nb_entries, :processed_at)
    """, row)
    conn.commit()


def db_global_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT
            COUNT(*)                                                      AS total,
            SUM(cost_eur)                                                 AS total_cost_eur,
            AVG(cost_eur)                                                 AS avg_cost_eur,
            SUM(input_tokens+output_tokens+cache_write_tokens
                +cache_read_tokens)                                       AS total_tokens,
            SUM(CASE WHEN incoherence=1 THEN 1 ELSE 0 END)               AS nb_incoherences,
            COUNT(DISTINCT class)                                         AS nb_classes
        FROM pensionnaires
    """).fetchone()
    return {
        "total":           row[0] or 0,
        "total_cost_eur":  row[1] or 0.0,
        "avg_cost_eur":    row[2] or 0.0,
        "total_tokens":    row[3] or 0,
        "nb_incoherences": row[4] or 0,
        "nb_classes":      row[5] or 0,
    }


def export_pensionnaire(row: sqlite3.Row | dict) -> dict:
    """
    Reconstruit un enregistrement pensionnaire complet en fusionnant
    les colonnes SQLite et les blobs JSON.
    C'est le format canonique — utilisé pour l'export JSON et le probe.
    """
    if isinstance(row, sqlite3.Row):
        row = dict(row)

    incoherence = row.get("incoherence")
    if incoherence is not None:
        incoherence = bool(incoherence)

    return {
        "class":       row.get("class"),
        "page":        row.get("page"),
        "entryNumber": row.get("entry_number"),
        "xyStart":     [row.get("x"), row.get("y")],
        "xyEnd":       [row.get("x_fin"), row.get("y_fin")],
        "extractedAt": row.get("extracted_at"),
        "cost": {
            "eur":             row.get("cost_eur", 0.0),
            "inputTokens":      row.get("input_tokens", 0),
            "outputTokens":     row.get("output_tokens", 0),
            "cacheWriteTokens": row.get("cache_write_tokens", 0),
            "cacheReadTokens":  row.get("cache_read_tokens", 0),
        },
        "person": {
            "lastName":    row.get("last_name", ""),
            "firstName":   row.get("first_name", ""),
            "widowOf":     row.get("widow_of"),
            "title":       row.get("title"),
            "sex":         row.get("sex", ""),
            "age":         row.get("age"),
            "birthYear":   row.get("birth_year"),
            "totalAmount": row.get("total_amount"),
            "incoherence": incoherence,
        },
        "jobs":             json.loads(row.get("jobs") or "[]"),
        "detailedPensions": json.loads(row.get("detailed_pensions") or "[]"),
        "wikidata":  (
            {"id": row.get("wikidata_id"),   "score": row.get("wikidata_score")}
            if row.get("wikidata_id") else None
        ),
        "prosocour": (
            {"id": row.get("prosocour_id"),  "score": row.get("prosocour_score")}
            if row.get("prosocour_id") else None
        ),
        "_suggestions": json.loads(row.get("suggestions") or "[]"),
    }


def export_all(conn: sqlite3.Connection, out_path: Path | None = None) -> None:
    """Export all pensionnaires from DB as a JSON array (stdout or file)."""
    rows = conn.execute(
        "SELECT * FROM pensionnaires ORDER BY class, page, entry_number"
    ).fetchall()
    data = [export_pensionnaire(r) for r in rows]
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"{len(data)} pensionnaires exportés → {out_path}")
    else:
        print(text)


# ── Charge DB (référentiel Versailles) ───────────────────────────────────────

def _normalize(s: str) -> str:
    """Lowercase, strip accents and punctuation for fuzzy matching."""
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", s).strip()


def _charge_sim(a: str, b: str) -> float:
    """
    SequenceMatcher + pénalité de longueur pour éviter les faux positifs par préfixe.
    Ex : "lieutenant général" vs "lieutenant" → pénalisé même si le ratio brut est élevé.
    score = seq_ratio × (0.65 + 0.35 × len_ratio)
    """
    if not a or not b:
        return 0.0
    seq       = SequenceMatcher(None, a, b).ratio()
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    return seq * (0.65 + 0.35 * len_ratio)


def load_charge_db(path: Path) -> tuple[list[dict], dict[str, list[int]]]:
    """
    Parse charge.rehydrate.json (concatenated JSON objects) into:
    - charge_db: list of compact dicts
    - word_index: inverted word → [indices] for fast pre-filtering
    """
    text    = path.read_text(encoding="utf-8").strip()
    decoder = json.JSONDecoder()
    db: list[dict] = []
    pos = 0
    while pos < len(text):
        chunk = text[pos:].lstrip()
        if not chunk:
            break
        try:
            obj, end = decoder.raw_decode(chunk)
        except json.JSONDecodeError:
            break
        pos += (len(text[pos:]) - len(chunk)) + end

        src    = obj.get("_source", {})
        denorm = src.get("denormalization", {}) or {}
        inst   = denorm.get("institution", {}) or {}

        # Build institution path from sorted non-null niveaux
        levels = []
        for key in sorted(inst.keys()):
            node = inst[key]
            if isinstance(node, dict) and node.get("nom"):
                levels.append(node["nom"])
        institution_path = " > ".join(levels) if levels else None

        nom_raw     = src.get("nom_affichage", "").strip()
        nom_normalise = src.get("nom_affichage_normalise", "").strip()

        db.append({
            "id":          obj.get("_id", ""),
            "nom":         nom_raw,
            "nom_clean":   _normalize(nom_normalise or nom_raw),
            "institution": institution_path,
        })

    # Inverted word index (words ≥ 3 chars)
    word_index: dict[str, list[int]] = {}
    for i, entry in enumerate(db):
        for word in entry["nom_clean"].split():
            if len(word) >= 3:
                word_index.setdefault(word, []).append(i)

    return db, word_index


def match_charge(
    query: str,
    db: list[dict],
    word_index: dict[str, list[int]],
    threshold: float = 0.65,
) -> dict | None:
    """Return best charge match or None if below threshold."""
    q = _normalize(query)
    if not q or not db:
        return None

    # Pre-filter via shared words
    q_words = {w for w in q.split() if len(w) >= 3}
    candidates: set[int] = set()
    for w in q_words:
        candidates.update(word_index.get(w, []))
    pool = [db[i] for i in candidates] if candidates else db

    best_score, best = 0.0, None
    for entry in pool:
        score = _charge_sim(q, entry["nom_clean"])
        if score > best_score:
            best_score, best = score, entry

    if best_score >= threshold and best:
        return {
            "chargeMatchId":          best["id"],
            "chargeMatchNom":         best["nom"],
            "chargeMatchInstitution": best["institution"],
            "chargeMatchScore":       round(best_score, 3),
        }
    return None


def _match_job_obj(
    job_obj: dict | None,
    db: list[dict],
    word_index: dict[str, list[int]],
) -> None:
    """Add chargeMatch fields in-place to a job sub-object (if present and non-null)."""
    if not isinstance(job_obj, dict):
        return
    q = " ".join(filter(None, [job_obj.get("title"), job_obj.get("entity")]))
    m = match_charge(q, db, word_index)
    if m:
        job_obj.update(m)


def enrich_charge_matches(
    data: dict,
    db: list[dict],
    word_index: dict[str, list[int]],
) -> None:
    """Add chargeMatch fields in-place to pension jobs and onBehalfPersons jobs."""
    for pension in data.get("detailedPensions", []):
        # Match the pension's own job sub-object
        _match_job_obj(pension.get("job"), db, word_index)

        # Match each linked person's job sub-object
        for person in pension.get("onBehalfPersons", []):
            _match_job_obj(person.get("job"), db, word_index)


# ── Wikidata ──────────────────────────────────────────────────────────────────

_WIKIDATA_API   = "https://www.wikidata.org/w/api.php"
_wikidata_cache: dict[str, dict | None] = {}


def _wd_get(params: dict) -> dict:
    params["format"] = "json"
    url = _WIKIDATA_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"User-Agent": "PensionnairesExtractor/1.0 (historical research)"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _job_titles_from_data(data: dict) -> list[str]:
    titles: list[str] = []
    for pension in data.get("detailedPensions", []):
        job = pension.get("job") or {}
        for field in ("title", "militaryRank", "entity"):
            v = job.get(field)
            if v:
                titles.append(v)
    return titles


def search_wikidata(
    last_name: str,
    first_name: str,
    birth_year: int | None,
    job_titles: list[str],
) -> dict | None:
    """
    Search Wikidata for a person by name ± birth year ± occupation.
    Returns {"wikidataId", "wikidataScore"} or None.

    Score = name_sim × year_factor + occupation_bonus (capped at 1.0)
      name_sim    : SequenceMatcher ratio on normalised full name
      year_factor : 1.0 if birth year ±1, 0.25 if year conflicts, 0.6–0.7 if unknown
      occ_bonus   : +0.15 if any job keyword appears in Wikidata description
    Returned only if name_sim ≥ 0.45 AND final score ≥ 0.40.
    """
    name_query = f"{first_name} {last_name}".strip()
    if not name_query:
        return None

    cache_key = f"{name_query}|{birth_year}"
    if cache_key in _wikidata_cache:
        return _wikidata_cache[cache_key]

    try:
        # ── Step 1 : search by name → QIDs + descriptions ─────────────────
        s_data = _wd_get({
            "action": "wbsearchentities",
            "search": name_query,
            "language": "fr",
            "type": "item",
            "limit": "5",
        })
        hits = s_data.get("search", [])
        if not hits:
            _wikidata_cache[cache_key] = None
            return None

        # ── Step 2 : get birth dates (P569) for candidates ─────────────────
        time.sleep(0.25)
        qids = [h["id"] for h in hits]
        e_data = _wd_get({
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "claims|labels",
            "languages": "fr|en",
        })
        entities = e_data.get("entities", {})

        q_name    = _normalize(name_query)
        job_norms = [_normalize(t) for t in job_titles if t]

        best_score, best = 0.0, None

        for hit, qid in zip(hits, qids):
            entity = entities.get(qid, {})
            if entity.get("missing"):
                continue

            # Name similarity
            labels = entity.get("labels", {})
            label  = (labels.get("fr") or labels.get("en") or {}).get("value", "")
            name_sim = SequenceMatcher(None, q_name, _normalize(label)).ratio()
            if name_sim < 0.45:
                continue

            # Birth year factor
            entity_by: int | None = None
            for claim in entity.get("claims", {}).get("P569", []):
                ms = claim.get("mainsnak", {})
                if ms.get("snaktype") == "value":
                    t = ms.get("datavalue", {}).get("value", {}).get("time", "")
                    try:
                        entity_by = int(t[1:5])
                    except (ValueError, IndexError):
                        pass
                    break

            if birth_year and entity_by:
                year_factor = 1.0 if abs(entity_by - birth_year) <= 1 else 0.25
            elif birth_year or entity_by:
                year_factor = 0.70  # one side has year, other doesn't
            else:
                year_factor = 0.60  # no year info on either side

            # Occupation bonus: match job keywords against Wikidata description
            occ_bonus = 0.0
            desc_norm = _normalize(hit.get("description", ""))
            if desc_norm and job_norms:
                desc_words = set(desc_norm.split())
                for jn in job_norms:
                    jn_words = {w for w in jn.split() if len(w) >= 4}
                    if jn_words & desc_words:
                        occ_bonus = 0.15
                        break

            score = min(name_sim * year_factor + occ_bonus * name_sim, 1.0)

            if score > best_score:
                best_score = score
                best = {
                    "wikidataId":    qid,
                    "wikidataScore": round(score, 3),
                }

        result = best if best_score >= 0.40 else None
        _wikidata_cache[cache_key] = result
        return result

    except Exception as e:
        print(f"  [wikidata] {e}", file=sys.stderr)
        _wikidata_cache[cache_key] = None
        return None


# ── Prosocour ─────────────────────────────────────────────────────────────────

_PROSOCOUR_URL   = "https://www.prosocour.chateauversailles-recherche.fr/api/public/v2/personnes/search"
_prosocour_cache: dict[str, dict | None] = {}


def _prosocour_post(body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req  = urllib.request.Request(
        _PROSOCOUR_URL, data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "PensionnairesExtractor/1.0 (historical research)",
            "Accept":       "*/*",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _parse_prosocour_year(date_str: str) -> int | None:
    """Parse "1615" or "27-05-1651" → int year."""
    if not date_str:
        return None
    try:
        return int(date_str.strip().split("-")[-1])
    except (ValueError, IndexError):
        return None


def search_prosocour(
    last_name: str,
    first_name: str,
    birth_year: int | None,
    job_titles: list[str],
) -> dict | None:
    """
    Search Prosocour (Versailles) for a person.
    Score = (last_sim×0.6 + first_sim×0.4) × year_factor + occ_bonus×name_sim
    Returned only if score ≥ 0.40 AND last_sim ≥ 0.45.
    """
    if not last_name:
        return None

    cache_key = f"ps:{last_name}|{first_name}|{birth_year}"
    if cache_key in _prosocour_cache:
        return _prosocour_cache[cache_key]

    q = last_name.lower().strip()
    body = {
        "size": 10,
        "sort": [{"_score": {"order": "desc"}}, {"_id": "asc"}],
        "where": {"$or": [
            {"noms.nom": q}, {"noms.nom.raw": q}, {"noms.nom.__pauc": q},
        ]},
    }

    try:
        resp   = _prosocour_post(body)
        hits   = resp.get("result", {}).get("hits", [])

        q_last  = _normalize(last_name)
        q_first = _normalize(first_name) if first_name else ""
        job_norms = [_normalize(t) for t in job_titles if t]

        best_score, best = 0.0, None

        for hit in hits:
            src    = hit.get("source", {})
            hit_id = hit.get("id", "")

            # Last name similarity (best across all noms)
            noms = [n.get("nom", "") for n in src.get("noms", []) if n.get("nom")]
            if not noms:
                continue
            last_sim = max(SequenceMatcher(None, q_last, _normalize(n)).ratio() for n in noms)
            if last_sim < 0.45:
                continue

            # First name similarity
            prenoms   = [p.get("prenom", "").strip() for p in src.get("prenoms", []) if p.get("prenom")]
            first_sim = (
                max(SequenceMatcher(None, q_first, _normalize(p)).ratio() for p in prenoms)
                if prenoms and q_first else 0.0
            )

            name_sim = last_sim * 0.6 + first_sim * 0.4

            # Birth year factor
            naiss_date = ((src.get("naissance") or {}).get("date") or {}).get("date", "")
            candidate_by = _parse_prosocour_year(naiss_date)
            if birth_year and candidate_by:
                year_factor = 1.0 if abs(candidate_by - birth_year) <= 1 else 0.25
            elif birth_year or candidate_by:
                year_factor = 0.70
            else:
                year_factor = 0.60

            # Occupation bonus: SequenceMatcher entre job titles et charges Prosocour
            # Seuil strict ≥ 0.70 requis pour compter
            occ_bonus = 0.0
            if job_norms:
                charges = (src.get("denormalization") or {}).get("charges", []) or []
                charge_norms = [
                    _normalize(((ch.get("charge") or {}).get("nom") or ""))
                    for ch in charges
                ]
                charge_norms = [c for c in charge_norms if c]
                if charge_norms:
                    best_occ = max(
                        _charge_sim(jn, cn)
                        for jn in job_norms
                        for cn in charge_norms
                    )
                    if best_occ >= 0.70:
                        occ_bonus = best_occ * 0.20  # bonus proportionnel, max 0.20

            score = min(name_sim * year_factor + occ_bonus * name_sim, 1.0)
            if score > best_score:
                best_score = score
                best = {"prosocourId": hit_id, "prosocourScore": round(score, 3)}

        result = best if best_score >= 0.40 else None
        _prosocour_cache[cache_key] = result
        return result

    except Exception as e:
        print(f"  [prosocour] {e}", file=sys.stderr)
        _prosocour_cache[cache_key] = None
        return None


# ── Layout helpers ────────────────────────────────────────────────────────────

def extract_page_image(page: fitz.Page, output_path: Path) -> int:
    pix = page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), alpha=False)
    pix.save(str(output_path))
    return output_path.stat().st_size


def get_text_blocks(page: fitz.Page) -> list[dict]:
    raw = page.get_text("dict")
    blocks = []
    for b in raw.get("blocks", []):
        if b.get("type") != 0:
            continue
        text = " ".join(
            span["text"]
            for line in b.get("lines", [])
            for span in line.get("spans", [])
        ).strip()
        if not text:
            continue
        blocks.append({"bbox": b["bbox"], "text": text, "lines": b.get("lines", [])})
    blocks.sort(key=lambda b: (round(b["bbox"][1] / 5) * 5, b["bbox"][0]))
    return blocks


def is_entry_header(block: dict) -> bool:
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if len(text) < 3:
                continue
            is_bold = bool(span.get("flags", 0) & 16)
            is_caps = text == text.upper() and any(c.isalpha() for c in text)
            if is_bold or is_caps:
                if not re.match(r"^(Report|Total|A reporter|Suite|Folio)\b", text, re.I):
                    return True
    return False


def segment_entries(blocks: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for block in blocks:
        if is_entry_header(block) and current:
            groups.append(current)
            current = [block]
        else:
            current.append(block)
    if current:
        groups.append(current)
    return groups


# ── Tabular format (classe1–4) ─────────────────────────────────────────────────

_TABULAR_CLASSES   = {1, 2, 3, 4}
_NAME_COL_MAX_X0   = 115   # x0 boundary for the name column (pt)
_NAME_COL_MIN_W    = 30    # minimum width to qualify as a name block (pt)
_ENTRY_Y_GAP_MIN   = 30.0  # minimum y0-to-y0 gap (pt) to start a new entry

_TABULAR_SKIP_PREFIXES = ("NOMS", "REPORT", "TOTAL", "A REPORTER", "SUITE", "FOLIO", "SOMMES")


def is_tabular_format(class_num: int) -> bool:
    return class_num in _TABULAR_CLASSES


def _is_name_block_tabular(block: dict) -> bool:
    """True when this block is a name-column entry trigger in the tabular layout."""
    x0, _y0, x1, _y1 = block["bbox"]
    w    = x1 - x0
    text = block["text"].strip()

    if x0 >= _NAME_COL_MAX_X0 or w < _NAME_COL_MIN_W:
        return False
    if len(text) <= 3:
        return False

    t_up = text.upper()
    if any(t_up.startswith(kw) for kw in _TABULAR_SKIP_PREFIXES):
        return False

    return any(c.isalpha() for c in text)


def segment_table_entries(blocks: list[dict]) -> list[list[dict]]:
    """
    Segment a tabular page (classe1–4) into per-entry groups.

    A new entry is triggered by a name-column block whose y0 is ≥ 30 pt
    below the previous trigger — this separates distinct persons while
    tolerating multi-line names that span several blocks.
    """
    groups: list[list[dict]] = []
    current: list[dict] = []
    last_trigger_y: float = -999.0

    for block in blocks:
        if _is_name_block_tabular(block):
            y0 = block["bbox"][1]
            if y0 - last_trigger_y >= _ENTRY_Y_GAP_MIN:
                if current:
                    groups.append(current)
                current = [block]
                last_trigger_y = y0
                continue
        current.append(block)

    if current:
        groups.append(current)

    return groups


def union_bbox(blocks: list[dict]) -> tuple[float, float, float, float]:
    return (
        min(b["bbox"][0] for b in blocks),
        min(b["bbox"][1] for b in blocks),
        max(b["bbox"][2] for b in blocks),
        max(b["bbox"][3] for b in blocks),
    )


def crop_entry_png(page: fitz.Page, bbox: tuple) -> bytes:
    rect = fitz.Rect(*bbox) + fitz.Rect(-5, -5, 5, 5)
    rect &= page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), clip=rect, alpha=False)
    return pix.tobytes("png")


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es un expert en dépouillement de documents historiques français du XVIIIe siècle.
Tu reçois le texte OCR et/ou une image d'une fiche de pensionnaire extraite d'un registre royal de pensions de 1789.

STRUCTURE DU DOCUMENT :
Chaque fiche est organisée en deux colonnes :

Colonne gauche :
  1. NOM en LETTRES CAPITALES
  2. Entre parenthèses : prénom(s), parfois suivi de "veuf/veuve de [nom du défunt]"
  3. Âge en 1789
  4. Liste des pensions — pour chacune :
       a. Code département verseur : lettre ou abréviation (ex : "G", "M. du R.", "M.", "Gd. Ch.")
       b. Année d'obtention de la pension
  5. Description de chaque pension : motifs, type (réversion/retraite/pension/rente…),
     durée de service, charge ou profession concernée, entité employeuse,
     et éventuellement des personnes liées (père, grand-père, mari, fils…) dont les
     services ou fonctions justifient la pension, chacun avec ses propres détails.
  ⚠ UNE SEULE pension : le montant n'est généralement PAS précisé dans la description.
  ⚠ PLUSIEURS pensions : chaque montant est indiqué individuellement.

Colonne droite : montant TOTAL des pensions (en livres tournois).

VÉRIFICATION DE COHÉRENCE :
Calcule la somme des amount dans detailedPensions.
  somme ≠ totalAmount → "incoherence": true
  somme = totalAmount → "incoherence": false
  impossible à vérifier (pension unique sans montant détaillé, ou montants partiels) → "incoherence": null

SUGGESTIONS DE SCHÉMA :
Si des informations du texte ne peuvent pas être capturées fidèlement par ce schéma
(structure nouvelle, cas non prévu), note-les dans `_suggestions` (tableau de chaînes courtes).
Si tout est bien capturé, laisse `_suggestions: []`.

Retourne UNIQUEMENT un objet JSON valide — pas de markdown, pas de commentaires, pas d'explication.

Schéma JSON :
{
  "person": {
    "lastName":    "",      // NOM en MAJUSCULES
    "firstName":   "",      // prénom(s)
    "widowOf":     null,    // "Prénom NOM" du défunt si veuf/veuve de …, sinon null
    "title":       null,    // "Comte", "Dlle", "Sieur", "Chev."… ou null
    "sex":         "",      // "male" | "female" — déduire du titre/prénom/"veuve"/"demoiselle"
    "age":         null,    // âge en 1789 (entier) ou null
    "birthYear":   null,    // année de naissance (calculée ou explicite) ou null
    "totalAmount": null,    // montant total colonne droite (entier livres) ou null
    "incoherence": null     // true | false | null
  },
  "jobs": [],
  "detailedPensions": [
    {
      "text":                     "",   // extrait source complet de cette pension
      "department":               null, // code département verseur (ex: "G") ou null
      "year":                     null, // année d'obtention (ex: "1769") ou null
      "amount":                   null, // montant en livres (entier) ou null
      "deduction":                null, // false si "sans retenue", sinon null
      "type":                     null, // "pension" | "retraite" | "réversion" | "rente" | autre
      "reasons":                  [],   // liste de motifs/raisons de la pension
      "job": {                          // charge/profession justifiant la pension (null si absente)
        "text":            "",          // extrait source décrivant le poste
        "title":           "",          // intitulé exact du poste (hors grade militaire)
        "entity":          null,        // organisation employeuse
        "militaryRank":    null,        // grade militaire isolé (ex: "capitaine", "lieutenant de vaisseau") ou null
        "reformedRank":    false,       // true si grade "réformé" (régiment dissous, demi-solde)
        "serviceDuration": null,        // durée de service liée à ce poste (ex: "30 ans", "depuis 1754")
        "details":         null,
        "geodata":         null,
        "previous":        false        // true si "ancien", "ci-devant" (ex: "ancien capitaine" → militaryRank:"capitaine", previous:true)
      },
      "serviceDuration":          null, // durée de service totale du pensionnaire (si distincte du job)
      "recognitionOfHisServices": null, // "current" (services en cours) | "past" (anciens) | null
      "temporary":                null, // true si pension temporaire (supprimée si remplacement), false si permanente, null si inconnu
      "beneficiaryScope":         null, // "self" | "selfAndOthers" | "othersOnly"
      "details":                  null,
      "geodata":                  null,
      "onBehalfPersons": [              // personnes liées justifiant la pension (peut être vide)
        {
          "relation": null,             // "père", "grand-père", "mari", "fils", "mère"…
          "name":     null,             // nom de la personne si mentionné
          "deceased": null,             // true si "feu" ou veuf/ve de cette personne ; false si vivant ; null si inconnu
          "job": {                      // charge/poste de cette personne (null si absent)
            "text":            "",
            "title":           "",
            "entity":          null,
            "militaryRank":    null,
            "reformedRank":    false,
            "serviceDuration": null,
            "details":         null,
            "geodata":         null,
            "previous":        false
          }
        }
      ]
    }
  ],
  "_isPensionnaire":      true,   // false si en-tête, pied de page, total, report…
  "_inheritFromPrevious": false,  // true si "même motif/considération/ci-dessus/idem" → héritage du pensionnaire précédent
  "_suggestions": []              // suggestions d'amélioration du schéma (vide si rien à signaler)
}

Règles :
- Champ absent → null (scalaires), [] (tableaux), "" (chaînes obligatoires lastName/firstName).
- Ne jamais inventer d'informations absentes du texte.
- Montants : entiers en livres tournois (arrondir si virgule).
- jobs : laisse toujours [] — pour ce document, les postes sont dans detailedPensions[].job.
- detailedPensions[].job : null uniquement si aucun poste/charge n'est mentionné pour cette pension.
- detailedPensions[].job.previous : true uniquement si "ancien", "ci-devant".
- detailedPensions[].job.entity : nom EXACT de l'organisation tel qu'il apparaît dans le texte. Ne jamais généraliser ni fusionner.
  L'identité d'un poste militaire = (militaryRank + entity). Même grade dans un régiment différent = poste totalement différent.
  Exemples : "capitaine au régiment de recrues d'Aix" ≠ "capitaine du régiment des gardes françaises" ;
             "régiment de l'Ile-de-France, ci-devant Montmorin" ≠ "régiment des gardes françaises".
- detailedPensions[].job.geodata et detailedPensions[].geodata : extraire toute référence géographique explicite (ville, région, province, place forte…) mentionnée dans le texte de la pension ou du poste. Exemples : "garnison d'Armagnac" → entity="bataillon de la garnison d'Armagnac", geodata="Armagnac" ; "place de Metz" → geodata="Metz". Ne pas inventer si absent.
- detailedPensions[].deduction : false si "sans retenue", sinon null.
- _isPensionnaire : false si le texte est clairement un en-tête de page, un total ("Report", "À reporter", somme générale…), un pied de page ou tout texte sans lien avec une fiche individuelle.
- _inheritFromPrevious : true si le texte contient "même motif", "même considération", "ci-dessus", "idem", "id." ou toute formule renvoyant au pensionnaire précédent. Dans ce cas, reprends les champs de detailedPensions du pensionnaire précédent (fourni en contexte) et ne précise que les champs qui diffèrent explicitement dans le texte courant. Les champs person (nom, âge, montant…) sont toujours ceux du pensionnaire courant.
"""


SYSTEM_PROMPT_TABULAR = """\
Tu es un expert en dépouillement de documents historiques français du XVIIIe siècle.
Tu reçois le texte OCR et/ou une image d'une entrée de pensionnaire extraite d'un tableau royal de pensions de 1789.

STRUCTURE DU TABLEAU (7 colonnes) :
  Col 1. Département qui verse la pension (code lettre ou abréviation, ex : "G", "M.", "F.", "Gd. Ch.")
         Ce code figure en début de ligne, avant ou après le nom selon l'OCR.
  Col 2. NOM (Prénom) — patronyme en MAJUSCULES, prénom entre parenthèses
  Col 3. Âge en 1789 (entier)
  Col 4. Années des pensions — une ligne par pension, ex : "1764", "1775"
  Col 5. Sommes détaillées — montant de chaque pension en livres tournois, une par ligne
  Col 6. Total des pensions (somme colonne 5)
  Col 7. Motifs et observations — description du poste, des services, de la raison de la pension

IMPORTANT : le texte OCR mélange parfois les colonnes. Utilise l'image pour rétablir l'alignement.
Si plusieurs lignes en col 4+5, chaque ligne = une pension distincte avec ses propres motifs en col 7.

VÉRIFICATION DE COHÉRENCE :
Calcule la somme des amount dans detailedPensions.
  somme ≠ totalAmount → "incoherence": true
  somme = totalAmount → "incoherence": false
  impossible à vérifier → "incoherence": null

SUGGESTIONS DE SCHÉMA :
Si des informations ne peuvent pas être capturées fidèlement par ce schéma, note-les dans `_suggestions`.

Retourne UNIQUEMENT un objet JSON valide — pas de markdown, pas de commentaires, pas d'explication.

Schéma JSON :
{
  "person": {
    "lastName":    "",      // NOM en MAJUSCULES
    "firstName":   "",      // prénom(s)
    "widowOf":     null,    // "Prénom NOM" du défunt si veuf/veuve de …, sinon null
    "title":       null,    // titre honorifique ("Comte", "Dlle", "Chev."…) ou null
    "sex":         "",      // "male" | "female"
    "age":         null,    // âge col 3 (entier) ou null
    "birthYear":   null,    // année de naissance (calculée ou explicite) ou null
    "totalAmount": null,    // total col 6 (entier livres) ou null
    "incoherence": null     // true | false | null
  },
  "jobs": [],
  "detailedPensions": [
    {
      "text":                     "",   // extrait source complet de cette ligne de pension
      "department":               null, // code département col 1 (ex: "G") ou null
      "year":                     null, // année col 4 (ex: "1769") ou null
      "amount":                   null, // montant col 5 (entier livres) ou null
      "deduction":                null, // false si "sans retenue", sinon null
      "type":                     null, // "pension" | "retraite" | "réversion" | "rente" | autre
      "reasons":                  [],   // motifs/raisons extraits de col 7
      "job": {
        "text":            "",
        "title":           "",
        "entity":          null,        // nom EXACT de l'organisation
        "militaryRank":    null,
        "reformedRank":    false,
        "serviceDuration": null,
        "details":         null,
        "geodata":         null,
        "previous":        false
      },
      "serviceDuration":          null,
      "recognitionOfHisServices": null,
      "temporary":                null,
      "beneficiaryScope":         null,
      "details":                  null,
      "geodata":                  null,
      "onBehalfPersons": [
        {
          "relation": null,
          "name":     null,
          "deceased": null,
          "job": {
            "text":            "",
            "title":           "",
            "entity":          null,
            "militaryRank":    null,
            "reformedRank":    false,
            "serviceDuration": null,
            "details":         null,
            "geodata":         null,
            "previous":        false
          }
        }
      ]
    }
  ],
  "_isPensionnaire":      true,
  "_inheritFromPrevious": false,
  "_suggestions": []
}

Règles :
- Champ absent → null (scalaires), [] (tableaux), "" (chaînes obligatoires lastName/firstName).
- Ne jamais inventer d'informations absentes du texte.
- Montants : entiers en livres tournois (arrondir si virgule).
- jobs : laisse toujours [].
- detailedPensions[].job : null si aucune charge/poste mentionné.
- detailedPensions[].job.entity : nom EXACT de l'organisation.
  L'identité d'un poste militaire = (militaryRank + entity). Même grade, régiment différent = poste différent.
- detailedPensions[].job.geodata et detailedPensions[].geodata : extraire toute référence géographique explicite.
- detailedPensions[].job.previous : true uniquement si "ancien", "ci-devant".
- _isPensionnaire : false si en-tête, total (Report, À reporter…) ou pied de page.
- _inheritFromPrevious : true si "même motif", "idem", "ci-dessus"…
"""


# ── Claude call ───────────────────────────────────────────────────────────────

_INHERIT_RE = re.compile(
    r"\b(même\s+(motif|considération|raison|cause)|ci[-\s]?dessus|idem|id\.)\b",
    re.IGNORECASE,
)


def extract_entry(
    client: anthropic.Anthropic,
    text: str,
    image_bytes: bytes | None,
    tracker: CostTracker,
    previous_data: dict | None = None,
    system_prompt: str | None = None,
) -> tuple[dict[str, Any], dict]:
    content: list[dict] = []
    if image_bytes:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(image_bytes).decode(),
            },
        })

    user_text = f"Texte OCR de la fiche :\n\n{text}"
    if previous_data and _INHERIT_RE.search(text):
        prev_pensions = previous_data.get("detailedPensions", [])
        user_text += (
            "\n\nPENSIONNAIRE PRÉCÉDENT (pour héritage si 'même motif / ci-dessus') :\n"
            + json.dumps({"detailedPensions": prev_pensions}, ensure_ascii=False, indent=2)
        )
    user_text += "\n\nRetourne le JSON."

    content.append({"type": "text", "text": user_text})

    prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
    )
    tracker.add(response.usage)

    u  = response.usage
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    usage = {
        "input_tokens":       u.input_tokens,
        "output_tokens":      u.output_tokens,
        "cache_write_tokens": cw,
        "cache_read_tokens":  cr,
        "cost_eur":           tokens_cost_eur(u.input_tokens, u.output_tokens, cw, cr),
    }

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw), usage


def _call_with_retry(
    client: anthropic.Anthropic,
    text: str,
    image_bytes: bytes | None,
    tracker: CostTracker,
    label: str,
    previous_data: dict | None = None,
    system_prompt: str | None = None,
) -> tuple[dict, dict]:
    for attempt in range(3):
        try:
            return extract_entry(client, text, image_bytes, tracker, previous_data, system_prompt)
        except json.JSONDecodeError as e:
            print(f"  [{label}] JSON invalide (tentative {attempt+1}): {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  [{label}] Rate limit — attente {wait}s…", file=sys.stderr)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            print(f"  [{label}] API {e.status_code}: {e.message}", file=sys.stderr)
            if e.status_code < 500:
                break
            time.sleep(5)
        except Exception as e:
            print(f"  [{label}] Erreur: {e}", file=sys.stderr)
            break
    return {}, {}


# ── Processing ────────────────────────────────────────────────────────────────

def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    conn: sqlite3.Connection,
    client: anthropic.Anthropic,
    no_vision: bool = False,
    page_range: tuple[int, int] | None = None,
    charge_db: list[dict] | None = None,
    charge_index: dict[str, list[int]] | None = None,
) -> CostTracker:
    doc       = fitz.open(pdf_path)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    start     = (page_range[0] - 1) if page_range else 0
    end       = page_range[1]       if page_range else doc.page_count
    tracker   = CostTracker()
    m_class   = re.search(r'classe(\d+)', pdf_path.stem, re.IGNORECASE)
    class_num = int(m_class.group(1)) if m_class else 0
    tabular   = is_tabular_format(class_num)
    sys_prompt = SYSTEM_PROMPT_TABULAR if tabular else SYSTEM_PROMPT
    last_data: dict | None = None  # dernière extraction réussie (pour héritage)

    for page_idx in range(start, min(end, doc.page_count)):
        page     = doc.load_page(page_idx)
        page_num = page_idx + 1
        stem     = pdf_path.stem

        img_path  = images_dir / f"{stem}_{page_num:03d}p.png"
        file_size = extract_page_image(page, img_path)

        blocks    = get_text_blocks(page)
        page_text = "\n".join(b["text"] for b in blocks)
        groups    = segment_table_entries(blocks) if tabular else segment_entries(blocks)

        print(f"\n  ── Page {page_num} ── {len(groups)} entrée(s)", file=sys.stderr)
        skipped = 0

        for idx, group in enumerate(groups, 1):
            if not group:
                continue

            entry_text = "\n".join(b["text"] for b in group)
            h = _entry_hash(class_num, page_num, entry_text)

            if is_processed(conn, h):
                skipped += 1
                continue

            bbox = union_bbox(group)
            x, y         = round(bbox[0] * SCALE), round(bbox[1] * SCALE)
            x_fin, y_fin = round(bbox[2] * SCALE), round(bbox[3] * SCALE)

            # Print position before API call so XY is always visible
            print(f"    {idx:2}. xy=[{x},{y}→{x_fin},{y_fin}]  …", end="", file=sys.stderr)

            image_bytes: bytes | None = None
            if not no_vision:
                try:
                    image_bytes = crop_entry_png(page, bbox)
                except Exception as e:
                    print(f" crop:{e}", file=sys.stderr)

            data, usage = _call_with_retry(
                client, entry_text, image_bytes, tracker, f"p{page_num}.{idx}",
                previous_data=last_data,
                system_prompt=sys_prompt,
            )
            if not data:
                print(" ÉCHEC", file=sys.stderr)
                continue

            # Skip non-pensionnaire entries (headers, footers, totals…)
            if not data.get("_isPensionnaire", True):
                print(" [hors-sujet, ignoré]", file=sys.stderr)
                continue

            # Héritage du pensionnaire précédent si "même motif / ci-dessus"
            if data.get("_inheritFromPrevious") and last_data:
                # Claude a déjà fusionné via le contexte ; fallback si detailedPensions vide
                if not data.get("detailedPensions") and last_data.get("detailedPensions"):
                    import copy
                    data["detailedPensions"] = copy.deepcopy(last_data["detailedPensions"])
                print(" [héritage précédent]", end="", file=sys.stderr)

            # Enrich jobs/pensions with charge DB matches (in-place)
            if charge_db and charge_index:
                enrich_charge_matches(data, charge_db, charge_index)

            person = data.get("person", {})

            job_titles = _job_titles_from_data(data)

            # Wikidata + Prosocour identity lookups (always active)
            wd_match = search_wikidata(
                person.get("lastName", ""),
                person.get("firstName", ""),
                person.get("birthYear"),
                job_titles,
            )
            ps_match = search_prosocour(
                person.get("lastName", ""),
                person.get("firstName", ""),
                person.get("birthYear"),
                job_titles,
            )
            incoherence = person.get("incoherence")
            if isinstance(incoherence, bool):
                incoherence = 1 if incoherence else 0

            suggestions = data.get("_suggestions", [])

            row = {
                "class":        class_num,
                "page":         page_num,
                "entry_number": idx,
                "x":           x,
                "y":           y,
                "x_fin":       x_fin,
                "y_fin":       y_fin,
                "last_name":   person.get("lastName", ""),
                "first_name":  person.get("firstName", ""),
                "widow_of":    person.get("widowOf"),
                "title":       person.get("title"),
                "sex":         person.get("sex", ""),
                "age":         person.get("age"),
                "birth_year":  person.get("birthYear"),
                "total_amount": person.get("totalAmount"),
                "incoherence": incoherence,
                "jobs":              json.dumps(data.get("jobs", []), ensure_ascii=False),
                "detailed_pensions": json.dumps(data.get("detailedPensions", []), ensure_ascii=False),
                "suggestions":       json.dumps(suggestions, ensure_ascii=False),
                "input_tokens":       usage.get("input_tokens", 0),
                "output_tokens":      usage.get("output_tokens", 0),
                "cache_write_tokens": usage.get("cache_write_tokens", 0),
                "cache_read_tokens":  usage.get("cache_read_tokens", 0),
                "cost_eur":           usage.get("cost_eur", 0.0),
                "entry_hash":         h,
                "extracted_at":       datetime.now().isoformat(timespec="seconds"),
                "wikidata_id":        wd_match.get("wikidataId")      if wd_match else None,
                "wikidata_score":     wd_match.get("wikidataScore")   if wd_match else None,
                "prosocour_id":       ps_match.get("prosocourId")     if ps_match else None,
                "prosocour_score":    ps_match.get("prosocourScore")  if ps_match else None,
            }
            save_pensionnaire(conn, row)

            # ── Enriched record to stdout (current run only) ──────────────────
            name      = person.get("lastName", "?")
            cost      = usage.get("cost_eur", 0.0)
            total_tok = sum(usage.get(k, 0) for k in (
                "input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"
            ))
            flags  = " ⚠INCOH" if incoherence == 1 else ""
            flags += f" 💡{len(suggestions)}" if suggestions else ""
            print(f" {name}  {cost:.5f}€  {total_tok:,}tok{flags}", file=sys.stderr)

            print(json.dumps(export_pensionnaire(row), ensure_ascii=False, indent=2))

            if suggestions:
                for s in suggestions:
                    print(f"        💡 {s}", file=sys.stderr)

            last_data = data  # mémorise pour héritage éventuel du prochain pensionnaire

        if skipped:
            print(f"    ({skipped} entrée(s) déjà traitée(s) — ignorée(s))", file=sys.stderr)

        save_page(conn, {
            "class":        class_num,
            "page":         page_num,
            "image_path":   img_path.name,
            "file_size_kb": file_size // 1024,
            "text":         page_text,
            "nb_entries":   len(groups),
            "processed_at": datetime.now().isoformat(timespec="seconds"),
        })

    return tracker


# ── Stats ─────────────────────────────────────────────────────────────────────

def print_stats(conn: sqlite3.Connection, session: CostTracker, db_path: Path) -> None:
    s   = db_global_stats(conn)
    sep = "═" * 62

    # Collect unique suggestions from DB
    rows = conn.execute(
        "SELECT suggestions FROM pensionnaires WHERE suggestions IS NOT NULL AND suggestions != '[]'"
    ).fetchall()
    all_suggestions: list[str] = []
    for (sg,) in rows:
        try:
            all_suggestions.extend(json.loads(sg))
        except Exception:
            pass
    unique_suggestions = sorted(set(all_suggestions))

    print()
    print(sep)
    print("  STATISTIQUES FINALES")
    print(sep)
    print(f"  Session courante")
    print(f"    Appels API              : {session.calls}")
    print(f"    Tokens session          : {session.total_tokens:,}")
    print(f"    Coût session            : {session.cost_eur:.4f}€")
    print(f"  Base de données ({db_path.name})")
    print(f"    Classes traitées        : {s['nb_classes']}")
    print(f"    Pensionnaires extraits  : {s['total']:,}")
    print(f"    Coût total              : {s['total_cost_eur']:.4f}€")
    print(f"    Coût moyen              : {s['avg_cost_eur']:.5f}€ / pensionnaire")
    print(f"    Tokens totaux           : {s['total_tokens']:,}")
    print(f"    Incohérences détectées  : {s['nb_incoherences']}")
    if unique_suggestions:
        print(f"  Suggestions de schéma ({len(unique_suggestions)}) :")
        for sg in unique_suggestions:
            print(f"    💡 {sg}")
    print(sep)
    print("  Solde disponible → console.anthropic.com/settings/billing")
    print(sep)


# ── Probe ─────────────────────────────────────────────────────────────────────

def probe_schema(
    pdf_path: Path,
    client: anthropic.Anthropic,
    n_pages: int,
    no_vision: bool,
    charge_db: list[dict] | None = None,
    charge_index: dict[str, list[int]] | None = None,
) -> None:
    doc       = fitz.open(pdf_path)
    sampled   = sorted(random.sample(range(doc.page_count), min(n_pages, doc.page_count)))
    m_class   = re.search(r'classe(\d+)', pdf_path.stem, re.IGNORECASE)
    class_num = int(m_class.group(1)) if m_class else 0
    tabular    = is_tabular_format(class_num)
    sys_prompt = SYSTEM_PROMPT_TABULAR if tabular else SYSTEM_PROMPT
    print(f"Probe — pages : {[p+1 for p in sampled]}", file=sys.stderr)
    tracker = CostTracker()

    for page_idx in sampled:
        page   = doc.load_page(page_idx)
        blocks = get_text_blocks(page)
        groups = segment_table_entries(blocks) if tabular else segment_entries(blocks)
        print(f"\n{'─'*60}", file=sys.stderr)
        print(f"  Page {page_idx+1} — {len(groups)} entrée(s)", file=sys.stderr)

        for group in groups[:3]:
            if not group:
                continue

            bbox = union_bbox(group)
            x, y         = round(bbox[0] * SCALE), round(bbox[1] * SCALE)
            x_fin, y_fin = round(bbox[2] * SCALE), round(bbox[3] * SCALE)

            text = "\n".join(b["text"] for b in group)
            image_bytes = None
            if not no_vision:
                try:
                    image_bytes = crop_entry_png(page, bbox)
                except Exception:
                    pass

            data, usage = _call_with_retry(
                client, text, image_bytes, tracker, f"probe-p{page_idx+1}",
                system_prompt=sys_prompt,
            )
            if not data:
                continue
            if not data.get("_isPensionnaire", True):
                print(f"  [hors-sujet ignoré]", file=sys.stderr)
                continue

            if charge_db and charge_index:
                enrich_charge_matches(data, charge_db, charge_index)

            # Reconstruct full enriched record (same format as DB export)
            person = data.get("person", {})
            record = export_pensionnaire({
                "class":        class_num,
                "page":         page_idx + 1,
                "entry_number": None,
                "x":           x,   "y":     y,
                "x_fin":       x_fin, "y_fin": y_fin,
                "extracted_at": datetime.now().isoformat(timespec="seconds"),
                "cost_eur":           usage.get("cost_eur", 0.0),
                "input_tokens":       usage.get("input_tokens", 0),
                "output_tokens":      usage.get("output_tokens", 0),
                "cache_write_tokens": usage.get("cache_write_tokens", 0),
                "cache_read_tokens":  usage.get("cache_read_tokens", 0),
                "last_name":   person.get("lastName", ""),
                "first_name":  person.get("firstName", ""),
                "widow_of":    person.get("widowOf"),
                "title":       person.get("title"),
                "sex":         person.get("sex", ""),
                "age":         person.get("age"),
                "birth_year":  person.get("birthYear"),
                "total_amount": person.get("totalAmount"),
                "incoherence": person.get("incoherence"),
                "jobs":              json.dumps(data.get("jobs", []), ensure_ascii=False),
                "detailed_pensions": json.dumps(data.get("detailedPensions", []), ensure_ascii=False),
                "suggestions":       json.dumps(data.get("_suggestions", []), ensure_ascii=False),
            })
            print(json.dumps(record, ensure_ascii=False, indent=2))
            print(f"  coût: {usage.get('cost_eur', 0):.5f}€", file=sys.stderr)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Probe terminé — {tracker.line()}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrait les pensionnaires (PyMuPDF + Claude) → SQLite."
    )
    parser.add_argument("pdf", nargs="?", default="source7.pdf")
    parser.add_argument("-o", "--output", default="output")
    parser.add_argument("-d", "--db", default=None, help="Fichier SQLite (défaut: output/<pdf>.db)")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--pages", metavar="DEBUT-FIN")
    parser.add_argument("--probe", metavar="N", type=int, default=0,
                        help="Tester le schéma sur N pages aléatoires (sans écrire en base)")
    parser.add_argument("--export", metavar="FICHIER.json", default=None,
                        help="Exporter tous les pensionnaires de la base en JSON enrichi")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"Erreur : {pdf_path} introuvable", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db) if args.db else Path("data/sources.db")
    conn    = init_db(db_path)
    client  = anthropic.Anthropic()

    # Load charge referential if present next to the PDF or in cwd
    charge_db: list[dict] = []
    charge_index: dict[str, list[int]] = {}
    for candidate in [pdf_path.parent / "charge.rehydrate.json", Path("charge.rehydrate.json")]:
        if candidate.exists():
            print(f"Chargement référentiel des charges ({candidate.name})…", file=sys.stderr)
            t0 = time.monotonic()
            charge_db, charge_index = load_charge_db(candidate)
            print(f"  {len(charge_db)} charges indexées en {time.monotonic()-t0:.1f}s", file=sys.stderr)
            break

    if args.export:
        export_all(conn, Path(args.export))
        return

    if args.probe:
        probe_schema(pdf_path, client, args.probe, args.no_vision,
                     charge_db or None, charge_index or None)
        return

    page_range: tuple[int, int] | None = None
    if args.pages:
        parts = args.pages.split("-")
        a = int(parts[0])
        b = int(parts[1]) if len(parts) > 1 else a
        page_range = (a, b)

    print(f"Traitement : {pdf_path.name}  →  {db_path}", file=sys.stderr)
    if args.no_vision:
        print("Mode texte seul", file=sys.stderr)
    if page_range:
        print(f"Pages {page_range[0]}–{page_range[1]}", file=sys.stderr)

    session = CostTracker()
    try:
        session = process_pdf(
            pdf_path, output_dir, conn, client, args.no_vision, page_range,
            charge_db or None, charge_index or None,
        )
    except KeyboardInterrupt:
        print("\n\nInterrompu — stats partielles :", file=sys.stderr)

    print_stats(conn, session, db_path)


if __name__ == "__main__":
    main()
