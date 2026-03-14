import customtkinter as ctk
import sqlite3, os, re, subprocess, sys, random, webbrowser
from PIL import Image
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import requests, urllib.parse
import tkinter as tk
from functools import partial
import json
from typing import Optional, Tuple
import textwrap

DB = "movies.db"
POSTERS = Path("posters"); POSTERS.mkdir(exist_ok=True)
SETTINGS_FILE = Path("movie_inventory_settings.json")  # <- NEW

THEMES = {
    "Blue": {
        "accent": "#1f6aa5",
        "accent_hover": "#184f7d",
        "selected_border": "#4a90e2",
        "hover_border": "#4a90e2",
        "danger": "#c0392b",
        "danger_hover": "#962d22",
    },
    "Emerald": {
        "accent": "#198754",
        "accent_hover": "#146c43",
        "selected_border": "#38d996",
        "hover_border": "#38d996",
        "danger": "#c0392b",
        "danger_hover": "#962d22",
    },
    "Purple": {
        "accent": "#7b61ff",
        "accent_hover": "#634cd1",
        "selected_border": "#a78bfa",
        "hover_border": "#a78bfa",
        "danger": "#c0392b",
        "danger_hover": "#962d22",
    },
    "Amber": {
        "accent": "#d97706",
        "accent_hover": "#b45309",
        "selected_border": "#f59e0b",
        "hover_border": "#f59e0b",
        "danger": "#c0392b",
        "danger_hover": "#962d22",
    },
    "Crimson": {
        "accent": "#b91c1c",
        "accent_hover": "#991b1b",
        "selected_border": "#ef4444",
        "hover_border": "#ef4444",
        "danger": "#7f1d1d",
        "danger_hover": "#641818",
    },
    "Slate": {
        "accent": "#475569",
        "accent_hover": "#334155",
        "selected_border": "#94a3b8",
        "hover_border": "#94a3b8",
        "danger": "#b91c1c",
        "danger_hover": "#991b1b",
    },
}

def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# -------------------- DB helpers --------------------
def db():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    con = db()
    con.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY,
        tmdb_id INTEGER,             -- kept for future use, not used offline
        title TEXT,
        year INTEGER,
        genres TEXT,
        overview TEXT,
        poster_path TEXT,
        watch_count INTEGER DEFAULT 0,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP,
        file_path TEXT,
        runtime_minutes INTEGER,
        resolution TEXT
    )""")
    # safe schema upgrades if coming from older versions
    for col_def in [
        ("added_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("file_path", "TEXT"),
        ("runtime_minutes", "INTEGER"),
        ("resolution", "TEXT"),
        ("tmdb_id", "INTEGER"),
        # --- TV / hierarchy fields ---
        ("media_type", "TEXT DEFAULT 'movie'"),   # movie | show | episode
        ("show_id", "INTEGER"),                   # episodes point to a show row
        ("season", "INTEGER"),
        ("episode", "INTEGER"),
    ]:
        try:
            con.execute(f"ALTER TABLE movies ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

     # helpful indices (safe to try)
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_movies_media_type ON movies(media_type)")
    except Exception:
        pass
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_movies_show_se_ep ON movies(show_id, season, episode)")
    except Exception:
        pass
 
    # backfill media_type for old rows
    try:
        con.execute("UPDATE movies SET media_type='movie' WHERE media_type IS NULL OR media_type=''")
    except Exception:
        pass            
            
    con.execute("UPDATE movies SET added_at = COALESCE(added_at, CURRENT_TIMESTAMP)")
    con.commit(); con.close()

def delete_movie(movie_id: int):
    con = db()
    con.execute("DELETE FROM movies WHERE id=?", (movie_id,))
    con.commit()
    con.close()


# -------------------- Filename -> title guess --------------------
COMMON_TAGS = [
    r"\b\d{3,4}p\b", r"\b4k\b", r"\b8k\b", r"\buhd\b", r"\bhdr10(\+)?\b", r"\bdv\b",
    r"\bblu[- ]?ray\b", r"\bbrrip\b", r"\bwebrip\b", r"\bweb[- ]?dl\b", r"\bdvdrip\b",
    r"\bh264\b", r"\bh265\b", r"\bhevc\b", r"\bx264\b", r"\bx265\b",
    r"\bac3\b", r"\bdts\b", r"\batmos\b",
    r"\bremux\b", r"\bproper\b", r"\brepack\b",
    r"\bextended\b", r"\bdirectors[’']? cut\b",
    r"\bs0?\d{1,2}e\d{1,3}\b",
]

def guess_title_year_from_filename(path):
    name = os.path.splitext(os.path.basename(path))[0]
    s = re.sub(r"[._]+", " ", name)
    for pat in COMMON_TAGS:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    m = re.search(r"\b(19|20)\d{2}\b", s)
    year = int(m.group(0)) if m else None
    if year:
        s = re.sub(rf"\b{year}\b", " ", s)
    s = re.sub(r"\(\d{4}\)$", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s, year

# -------------------- ffprobe (optional) --------------------
def ffprobe_info(path):
    """Return (runtime_minutes, resolution_text) or (None, None) if ffprobe is missing."""
    try:
        out = subprocess.check_output(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.STDOUT, text=True, timeout=10
        ).strip()
        dur_s = float(out) if out else None
        minutes = int(round(dur_s/60.0)) if dur_s else None
    except Exception:
        minutes = None
    res = None
    try:
        out = subprocess.check_output(
            ["ffprobe","-v","error","-select_streams","v:0",
             "-show_entries","stream=width,height",
             "-of","csv=p=0", path],
            stderr=subprocess.STDOUT, text=True, timeout=10
        ).strip()
        if out and "," in out:
            w,h = out.split(",",1)
            res = f"{w}x{h}"
    except Exception:
        res = None
    return minutes, res

# -------------------- Wikipedia search helpers (Discover tab) --------------------
def wiki_search_titles(query, limit=10, lang="en"):
    """
    Returns list of dicts: [{pageid, title, description}]
    Uses Wikipedia Action API search.
    """
    q = (query or "").strip()
    if not q:
        return []

    headers = {"User-Agent": "MovieInventoryOffline/0.1 (contact: you@example.com)"}

    # 1) search
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": q,
        "srlimit": int(limit),
    }
    try:
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers=headers, timeout=12)
        if r.status_code != 200:
            return []
        hits = r.json().get("query", {}).get("search", []) or []
    except Exception:
        return []

    if not hits:
        return []

    pageids = [str(h.get("pageid")) for h in hits if h.get("pageid")]
    if not pageids:
        return []

    # 2) fetch descriptions for these pageids (optional but nice)
    params2 = {
        "action": "query",
        "format": "json",
        "pageids": "|".join(pageids),
        "prop": "pageterms",
        "wbptterms": "description",
    }
    desc_map = {}
    try:
        r2 = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params2, headers=headers, timeout=12)
        if r2.status_code == 200:
            pages = (r2.json().get("query", {}) or {}).get("pages", {}) or {}
            for pid, p in pages.items():
                terms = p.get("terms") or {}
                d = ""
                if isinstance(terms.get("description"), list) and terms["description"]:
                    d = terms["description"][0]
                desc_map[int(pid)] = d
    except Exception:
        pass

    out = []
    for h in hits:
        pid = h.get("pageid")
        title = h.get("title") or ""
        if not pid or not title:
            continue
        out.append({
            "pageid": int(pid),
            "title": title,
            "description": desc_map.get(int(pid), "")
        })
    return out


def fetch_wikipedia_metadata_by_pageid(pageid, dest_folder="posters", lang="en"):
    """
    Fetches a specific Wikipedia page by pageid for reliable selection.
    Returns same dict format as fetch_wikipedia_metadata().
    """
    headers = {"User-Agent": "MovieInventoryOffline/0.1 (contact: you@example.com)"}

    params = {
        "action": "query",
        "format": "json",
        "pageids": str(int(pageid)),
        "prop": "pageimages|extracts|pageterms",
        "exintro": 1,
        "explaintext": 1,
        "piprop": "original|thumbnail",
        "pithumbsize": 800,
    }

    try:
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers=headers, timeout=12)
        if r.status_code != 200:
            return None
        pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
        page = pages.get(str(int(pageid)))
        if not page:
            return None
    except Exception:
        return None

    page_title = page.get("title") or ""
    page_title = re.sub(r"\s*\((film|movie)\)\s*$", "", page_title, flags=re.IGNORECASE)
    overview = page.get("extract") or ""

    # try to detect year from description/overview
    desc = ""
    terms = page.get("terms") or {}
    if isinstance(terms.get("description"), list) and terms["description"]:
        desc = terms["description"][0]

    yr = None
    for source in filter(None, [desc, overview]):
        m = re.search(r"\b(19|20)\d{2}\b", source)
        if m:
            try:
                y = int(m.group(0))
                if 1878 <= y <= 2100:
                    yr = y
                    break
            except:
                pass

    # poster
    img_url = None
    if isinstance(page.get("original"), dict) and page["original"].get("source"):
        img_url = page["original"]["source"]
    elif isinstance(page.get("thumbnail"), dict) and page["thumbnail"].get("source"):
        img_url = page["thumbnail"]["source"]

    poster_path = None
    if img_url:
        try:
            os.makedirs(dest_folder, exist_ok=True)
            stem = (page_title or f"page_{pageid}").replace(" ", "_")[:64]
            fn = Path(dest_folder) / f"{stem}.jpg"
            img_r = requests.get(img_url, headers=headers, timeout=15)
            if img_r.status_code == 200 and len(img_r.content) > 1000:
                with open(fn, "wb") as f:
                    f.write(img_r.content)
                poster_path = str(fn)
        except Exception:
            poster_path = None

    if not poster_path:
        poster_path = fetch_wikipedia_poster_fallback(page_title, dest_folder=dest_folder, lang=lang)

    wikidata_entity = _wikidata_get_entity_id_from_pageid(pageid, lang=lang)
    wd_meta = fetch_wikidata_metadata(wikidata_entity, lang=lang) if wikidata_entity else {}

    final_year = wd_meta.get("year") or yr

    result = {
        "title": page_title,
        "year": final_year,
        "overview": overview,
        "poster_path": poster_path,
        "genres": wd_meta.get("genres", "") or "",
        "runtime_minutes": wd_meta.get("runtime_minutes"),
    }

    print("fetch_wikipedia_metadata_by_pageid result:", result)
    return result



# -------------------- Wikipedia fetch + summary shortener --------------------
def fetch_wikipedia_metadata(title, year=None, dest_folder="posters", lang="en"):
    """
    Robust metadata fetch via Wikipedia Action API.
    Returns {title, year, overview, poster_path, genres, runtime_minutes}
    """
    if not title:
        return None

    headers = {
        "User-Agent": "MovieInventoryOffline/0.1 (contact: you@example.com)"
    }

    def try_query(query_text):
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query_text,
            "gsrlimit": 1,
            "prop": "pageimages|extracts|pageterms|pageprops",
            "ppprop": "wikibase_item",
            "exintro": 1,
            "explaintext": 1,
            "piprop": "original|thumbnail",
            "pithumbsize": 800,
        }
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php",
                         params=params, headers=headers, timeout=12)
        if r.status_code != 200:
            return None
        pages = r.json().get("query", {}).get("pages", {})
        if not pages:
            return None
        return next(iter(pages.values()))

    q = title.strip()
    queries = []
    if year:
        queries.append(f"{q} {year} film")
    queries += [f"{q} film", q]

    page = None
    for query_text in queries:
        page = try_query(query_text)
        if page:
            break
    if not page:
        return None

    page_title = page.get("title") or title
    page_title = re.sub(r"\s*\((film|movie)\)\s*$", "", page_title, flags=re.IGNORECASE)
    overview = page.get("extract") or ""

    # Year from description/overview
    desc = ""
    terms = page.get("terms") or {}
    if isinstance(terms.get("description"), list) and terms["description"]:
        desc = terms["description"][0]
    yr = year
    for source in filter(None, [desc, overview]):
        m = re.search(r"\b(19|20)\d{2}\b", source)
        if m:
            try:
                y = int(m.group(0))
                if 1878 <= y <= 2100:
                    yr = y
                    break
            except:
                pass

    # Poster URL
    img_url = None
    if isinstance(page.get("original"), dict) and page["original"].get("source"):
        img_url = page["original"]["source"]
    elif isinstance(page.get("thumbnail"), dict) and page["thumbnail"].get("source"):
        img_url = page["thumbnail"]["source"]

    poster_path = None
    if img_url:
        try:
            os.makedirs(dest_folder, exist_ok=True)
            stem = page_title.replace(" ", "_")[:64]
            fn = Path(dest_folder) / f"{stem}.jpg"
            img_r = requests.get(img_url, headers=headers, timeout=15)
            if img_r.status_code == 200 and len(img_r.content) > 1000:
                with open(fn, "wb") as f:
                    f.write(img_r.content)
                poster_path = str(fn)
        except Exception:
            poster_path = None

    if not poster_path:
        poster_path = fetch_wikipedia_poster_fallback(page_title, dest_folder=dest_folder, lang=lang)

    wikidata_entity = (page.get("pageprops") or {}).get("wikibase_item")
    wd_meta = fetch_wikidata_metadata(wikidata_entity, lang=lang) if wikidata_entity else {}

    final_year = wd_meta.get("year") or yr

    result = {
        "title": page_title,
        "year": final_year,
        "overview": overview,
        "poster_path": poster_path,
        "genres": wd_meta.get("genres", "") or "",
        "runtime_minutes": wd_meta.get("runtime_minutes"),
    }

    print("fetch_wikipedia_metadata result:", result)
    return result

def shorten_overview(text, max_sentences=3, max_chars=700):
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    out = " ".join(sentences[:max_sentences]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out

def fetch_wikipedia_poster_fallback(page_title: str, dest_folder="posters", lang="en") -> Optional[str]:
    """
    Fallback poster fetch using Wikipedia REST summary endpoint.
    Returns local poster path or None.
    """
    if not page_title:
        return None

    try:
        safe_title = urllib.parse.quote(page_title.replace(" ", "_"))
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe_title}"

        headers = {
            "User-Agent": "MovieInventoryOffline/0.1 (contact: you@example.com)"
        }

        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            return None

        data = r.json()
        thumb = (data.get("thumbnail") or {}).get("source")
        if not thumb:
            return None

        os.makedirs(dest_folder, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", page_title)[:64]
        fn = Path(dest_folder) / f"{stem}.jpg"

        img_r = requests.get(thumb, headers=headers, timeout=15)
        if img_r.status_code == 200 and len(img_r.content) > 1000:
            with open(fn, "wb") as f:
                f.write(img_r.content)
            return str(fn)

    except Exception:
        pass

    return None


# -------------------- Wikidata helpers --------------------
def _safe_int_from_time_string(val: str) -> Optional[int]:
    """
    Parses values like '+1999-03-31T00:00:00Z' and returns 1999.
    """
    if not val:
        return None
    m = re.match(r"^\+?(-?\d{1,6})-", str(val))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _wikidata_get_entity_id_from_pageid(pageid: int, lang="en") -> Optional[str]:
    """
    Gets the Wikidata entity id (like Q12345) linked to a Wikipedia page.
    """
    headers = {"User-Agent": "MovieInventoryOffline/0.1 (contact: you@example.com)"}
    params = {
        "action": "query",
        "format": "json",
        "pageids": str(int(pageid)),
        "prop": "pageprops",
        "ppprop": "wikibase_item",
    }
    try:
        r = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params=params,
            headers=headers,
            timeout=12
        )
        if r.status_code != 200:
            return None
        pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
        page = pages.get(str(int(pageid))) or {}
        return page.get("pageprops", {}).get("wikibase_item")
    except Exception:
        return None


def _wikidata_label_map(ids: list[str], lang="en") -> dict[str, str]:
    """
    Resolve Wikidata ids to labels using wbgetentities.
    Returns { 'Q11424': 'film', ... }
    """
    ids = [x for x in ids if x]
    if not ids:
        return {}

    try:
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(ids),
            "props": "labels",
            "languages": f"{lang}|en",
        }
        r = requests.get("https://www.wikidata.org/w/api.php", params=params, timeout=15)
        if r.status_code != 200:
            return {}

        data = r.json()
        entities = data.get("entities", {}) or {}

        out = {}
        for qid, ent in entities.items():
            labels = ent.get("labels", {}) or {}
            label = None
            if lang in labels:
                label = labels[lang].get("value")
            elif "en" in labels:
                label = labels["en"].get("value")
            if label:
                out[qid] = label
        return out
    except Exception:
        return {}
        
def _wikidata_extract_time_minutes(amount_str: str) -> Optional[int]:
    """
    Parses Wikidata quantity strings like '+102' into minutes.
    """
    if not amount_str:
        return None
    try:
        return int(round(float(str(amount_str).replace("+", "").strip())))
    except Exception:
        return None


def fetch_wikidata_metadata(entity_id: str, lang="en") -> dict:
    """
    Fetch structured metadata from Wikidata.

    Useful properties:
    P577 = publication date
    P136 = genre
    P2047 = duration
    """
    result = {
        "year": None,
        "genres": "",
        "runtime_minutes": None,
    }

    if not entity_id:
        return result

    try:
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return result

        data = r.json()
        entity = (data.get("entities", {}) or {}).get(entity_id, {}) or {}
        claims = entity.get("claims", {}) or {}

        # ---- Year (P577: publication date) ----
        try:
            p577 = claims.get("P577", [])
            if p577:
                snak = p577[0].get("mainsnak", {}) or {}
                dv = snak.get("datavalue", {}) or {}
                val = dv.get("value", {}) or {}
                time_str = val.get("time")
                year = _safe_int_from_time_string(time_str)
                if year and 1878 <= year <= 2100:
                    result["year"] = year
        except Exception:
            pass

        # ---- Genres (P136) ----
        genre_ids = []
        try:
            for item in claims.get("P136", []):
                snak = item.get("mainsnak", {}) or {}
                dv = snak.get("datavalue", {}) or {}
                val = dv.get("value", {}) or {}
                qid = val.get("id")
                if qid:
                    genre_ids.append(qid)
        except Exception:
            pass

        if genre_ids:
            label_map = _wikidata_label_map(genre_ids, lang=lang)
            genres = []
            for qid in genre_ids:
                lab = label_map.get(qid)
                if lab and lab not in genres:
                    genres.append(lab)
            result["genres"] = ", ".join(genres[:6])

        # ---- Runtime (P2047: duration) ----
        try:
            p2047 = claims.get("P2047", [])
            if p2047:
                snak = p2047[0].get("mainsnak", {}) or {}
                dv = snak.get("datavalue", {}) or {}
                val = dv.get("value", {}) or {}
                amount = val.get("amount")
                minutes = _wikidata_extract_time_minutes(amount)
                if minutes and 1 <= minutes <= 10000:
                    result["runtime_minutes"] = minutes
        except Exception:
            pass

    except Exception:
        pass

    return result

# -------------------- Data ops --------------------
def list_movies(filter_mode="all", search_term="", genre="All", sort_key="title_asc",
               nav_mode: str = "root", nav_show_id: Optional[int] = None):
    con = db()
    # Root: show movies + shows (no episodes)
    # Show view: show episodes for that show_id
    base = "SELECT id, title, year, watch_count, genres, file_path, media_type, show_id, season, episode FROM movies"
    clauses, params = [], []
    
    if nav_mode == "show":
        clauses.append("media_type='episode'")
        clauses.append("show_id=?")
        params.append(int(nav_show_id or 0))
        
    else:
        # show movies always
        # show shows only if they have at least one episode
        clauses.append("""
            (
                media_type='movie'
                OR (
                    media_type='show'
                    AND EXISTS (
                        SELECT 1 FROM movies e
                        WHERE e.media_type='episode' AND e.show_id = movies.id
                    )
                )
            )
        """)

    if filter_mode == "unwatched":
        clauses.append("watch_count=0")
    elif filter_mode == "watched":
        clauses.append("watch_count>0")
    if search_term:
        clauses.append("title LIKE ?")
        params.append(f"%{search_term}%")
    if genre != "All":
        clauses.append("genres LIKE ?")
        params.append(f"%{genre}%")
    if clauses:
        base += " WHERE " + " AND ".join(clauses)

    order_map = {
        "title_asc":   "title COLLATE NOCASE ASC",
        "title_desc":  "title COLLATE NOCASE DESC",
        "year_asc":    "COALESCE(year, 9999) ASC, title COLLATE NOCASE ASC",
        "year_desc":   "COALESCE(year, 0) DESC, title COLLATE NOCASE ASC",
        "watched_asc": "watch_count ASC, title COLLATE NOCASE ASC",
        "watched_desc":"watch_count DESC, title COLLATE NOCASE ASC",
        "added_desc":  "datetime(added_at) DESC",
        "added_asc":   "datetime(added_at) ASC",
    }
    
    if nav_mode == "show":
        # Episodes sort by season/episode, then title
        base += " ORDER BY COALESCE(season, 0) ASC, COALESCE(episode, 0) ASC, title COLLATE NOCASE ASC"
    else:
        base += f" ORDER BY {order_map.get(sort_key, 'title COLLATE NOCASE ASC')}"
  

    rows = con.execute(base, params).fetchall()
    con.close()
    return rows

def get_genres():
    con = db()
    rows = con.execute("SELECT DISTINCT genres FROM movies").fetchall()
    con.close()
    genres = set()
    for r in rows:
        if r[0]:
            for g in r[0].split(","):
                g = g.strip()
                if g: genres.add(g)
    return sorted(genres)

def increment_watch(movie_id):
    con = db()
    con.execute("UPDATE movies SET watch_count = watch_count+1 WHERE id=?", (movie_id,))
    con.commit(); con.close()

def upsert_movie(values):
    """
    values: dict with keys:
      id (optional), title, year, genres, overview,
      poster_path, file_path, runtime_minutes, resolution
      media_type ('movie'|'show'|'episode'), show_id, season, episode

    If id is provided and exists, update that row.
    Otherwise fall back to file_path or (title, year) to find or insert.
    """
    con = db()
    cur = con.cursor()

    row = None
    movie_id = values.get("id")

    # 1) If we have an explicit id from EditDialog, prefer that
    if movie_id is not None:
        row = cur.execute("SELECT id FROM movies WHERE id=?", (movie_id,)).fetchone()

    # 2) Otherwise try to match by file_path
    if row is None and values.get("file_path"):
        row = cur.execute(
            "SELECT id FROM movies WHERE file_path=?",
            (values["file_path"],)
        ).fetchone()

    # 3) Otherwise try title + year
    if row is None and values.get("title") and values.get("year"):
        row = cur.execute(
            "SELECT id FROM movies WHERE title=? AND year=?",
            (values["title"], values["year"])
        ).fetchone()

    if row is not None:
        movie_id = row[0]
        cur.execute(
            """UPDATE movies
               SET title=?,
                   year=?,
                   genres=?,
                   overview=?,
                   poster_path=?,
                   file_path=?,
                   runtime_minutes=?,
                   resolution=?,
                   media_type=?,
                   show_id=?,
                   season=?,
                   episode=?
             WHERE id=?""",
            (
                values.get("title"),
                values.get("year"),
                values.get("genres"),
                values.get("overview"),
                values.get("poster_path"),
                values.get("file_path"),
                values.get("runtime_minutes"),
                values.get("resolution"),
                values.get("media_type", "movie"),
                values.get("show_id"),
                values.get("season"),
                values.get("episode"),
                movie_id,
            ),
        )
    else:
        cur.execute(
            """INSERT INTO movies
               (title, year, genres, overview, poster_path,
                file_path, runtime_minutes, resolution,
                media_type, show_id, season, episode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values.get("title"),
                values.get("year"),
                values.get("genres"),
                values.get("overview"),
                values.get("poster_path"),
                values.get("file_path"),
                values.get("runtime_minutes"),
                values.get("resolution"),
                values.get("media_type", "movie"),
                values.get("show_id"),
                values.get("season"),
                values.get("episode"),
            ),
        )
        movie_id = cur.lastrowid

    con.commit()
    con.close()
    return movie_id


# -------------------- Stats --------------------
def get_stats():
    con = db()

    # --- Counts by type ---
    movies_total = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='movie'"
    ).fetchone()[0]

    shows_total = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='show'"
    ).fetchone()[0]

    episodes_total = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='episode'"
    ).fetchone()[0]

    # --- Watched counts ---
    movies_watched = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='movie' AND watch_count>0"
    ).fetchone()[0]

    episodes_watched = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND watch_count>0"
    ).fetchone()[0]

    # --- Total watch counts ---
    movies_watch_total = con.execute(
        "SELECT IFNULL(SUM(watch_count),0) FROM movies WHERE media_type='movie'"
    ).fetchone()[0]

    episodes_watch_total = con.execute(
        "SELECT IFNULL(SUM(watch_count),0) FROM movies WHERE media_type='episode'"
    ).fetchone()[0]

    # --- Top watched (movies only) ---
    top_movies = con.execute("""
        SELECT title, watch_count
        FROM movies
        WHERE media_type='movie' AND watch_count>0
        ORDER BY watch_count DESC, title ASC
        LIMIT 10
    """).fetchall()

    # --- Top watched (episodes only, show title included) ---
    top_episodes = con.execute("""
        SELECT
            COALESCE(s.title, 'Unknown Show') AS show_title,
            e.season, e.episode,
            e.title,
            e.watch_count
        FROM movies e
        LEFT JOIN movies s ON s.id = e.show_id
        WHERE e.media_type='episode' AND e.watch_count>0
        ORDER BY e.watch_count DESC, show_title ASC
        LIMIT 10
    """).fetchall()

    # --- Recently added (all types, show context for episodes) ---
    recent = con.execute("""
        SELECT
            m.media_type,
            m.title,
            m.year,
            datetime(m.added_at),
            s.title AS show_title,
            m.season,
            m.episode
        FROM movies m
        LEFT JOIN movies s ON s.id = m.show_id
        ORDER BY datetime(m.added_at) DESC
        LIMIT 10
    """).fetchall()

    # --- Genres (movies only, since shows/episodes usually have blank genres) ---
    rows = con.execute("""
        SELECT genres FROM movies
        WHERE media_type='movie' AND genres IS NOT NULL AND genres<>''
    """).fetchall()

    con.close()

    genre_counts = {}
    for (gstr,) in rows:
        for g in [s.strip() for s in gstr.split(",") if s.strip()]:
            genre_counts[g] = genre_counts.get(g, 0) + 1
    top_genres = sorted(genre_counts.items(), key=lambda x: (-x[1], x[0]))[:10]

    return {
        "movies_total": int(movies_total),
        "shows_total": int(shows_total),
        "episodes_total": int(episodes_total),

        "movies_watched": int(movies_watched),
        "movies_unwatched": int(movies_total - movies_watched),

        "episodes_watched": int(episodes_watched),
        "episodes_unwatched": int(episodes_total - episodes_watched),

        "movies_watch_total": int(movies_watch_total),
        "episodes_watch_total": int(episodes_watch_total),

        "top_movies": top_movies,
        "top_episodes": top_episodes,

        "recent": recent,
        "top_genres": top_genres,
    }
    
# -------------------- Edit Dialog --------------------
class EditDialog(ctk.CTkToplevel):
    def __init__(self, master, values):
        super().__init__(master)
        self.title("Edit Movie")
        self.geometry("600x520")
        self.resizable(False, False)
        self.values = values.copy()
        self.saved = False

        self.transient(master); self.grab_set(); self.focus_force()
        self.update_idletasks()
        px, py = master.winfo_rootx(), master.winfo_rooty()
        pw, ph = master.winfo_width(), master.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")

        grid = ctk.CTkFrame(self); grid.pack(fill="both", expand=True, padx=12, pady=12)

        def row(label, widget):
            r = row.idx; row.idx += 1
            ctk.CTkLabel(grid, text=label, anchor="w").grid(row=r, column=0, sticky="ew", padx=6, pady=6)
            widget.grid(row=r, column=1, sticky="ew", padx=6, pady=6)
        row.idx = 0

        self.e_title = ctk.CTkEntry(grid); self.e_title.insert(0, values.get("title") or "")
        self.e_year  = ctk.CTkEntry(grid); self.e_year.insert(0, str(values.get("year") or ""))
        self.e_genre = ctk.CTkEntry(grid); self.e_genre.insert(0, values.get("genres") or "")
        self.e_run   = ctk.CTkEntry(grid); self.e_run.insert(0, str(values.get("runtime_minutes") or ""))
        self.e_res   = ctk.CTkEntry(grid); self.e_res.insert(0, values.get("resolution") or "")
        self.file_row = ctk.CTkFrame(grid, fg_color="transparent")
        self.file_row.grid_columnconfigure(0, weight=1)

        self.e_file = ctk.CTkEntry(self.file_row)
        self.e_file.insert(0, values.get("file_path") or "")
        self.e_file.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.file_browse_btn = ctk.CTkButton(
            self.file_row,
            text="Browse",
            width=90,
            command=self.browse_video_file
        )
        self.file_browse_btn.grid(row=0, column=1, sticky="e")

        self.e_over  = ctk.CTkTextbox(grid, height=120)
        self.e_over.insert("1.0", values.get("overview") or "")

        self.poster_path = values.get("poster_path")
        self.poster_btn = ctk.CTkButton(grid, text="Choose Poster", command=self.choose_poster)
        self.fetch_btn = ctk.CTkButton(grid, text="Fetch Metadata (Wikipedia)", command=self.fetch_from_wiki)

        row("Title", self.e_title)
        row("Year", self.e_year)
        row("Genres (comma separated)", self.e_genre)
        row("Runtime minutes", self.e_run)
        row("Resolution", self.e_res)
        row("File path", self.file_row)
        row("Overview", self.e_over)
        row("Poster", self.poster_btn)
        row("Fetch (Wiki)", self.fetch_btn)

        grid.columnconfigure(1, weight=1)

        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=12, pady=6)

        self.save_btn = ctk.CTkButton(btns, text="Save", command=self.on_save)
        self.save_btn.pack(side="right", padx=6)

        self.cancel_btn = ctk.CTkButton(btns, text="Cancel", command=self.destroy)
        self.cancel_btn.pack(side="right", padx=6)

        self.apply_theme()

    def apply_theme(self):
        theme = None

        try:
            if hasattr(self.master, "_theme"):
                theme = self.master._theme()
        except Exception:
            theme = None

        if not theme:
            return

        button_widgets = [
            getattr(self, "file_browse_btn", None),
            getattr(self, "poster_btn", None),
            getattr(self, "fetch_btn", None),
            getattr(self, "save_btn", None),
            getattr(self, "cancel_btn", None),
        ]

        for btn in button_widgets:
            if btn is not None:
                try:
                    btn.configure(
                        fg_color=theme["accent"],
                        hover_color=theme["accent_hover"]
                    )
                except Exception:
                    pass
                    
                try:
                    self.cancel_btn.configure(
                        fg_color="#444444" if str(ctk.get_appearance_mode()).lower() == "dark" else "#d9d9d9",
                        hover_color="#555555" if str(ctk.get_appearance_mode()).lower() == "dark" else "#cfcfcf"
                    )
                except Exception:
                    pass

    def browse_video_file(self):
        filetypes = [
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.m4v *.wmv"),
            ("All files", "*.*"),
        ]

        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=filetypes
        )
        if not path:
            return

        self.e_file.delete(0, "end")
        self.e_file.insert(0, path)

        # Optional nice bonus: auto-fill runtime and resolution if available
        try:
            minutes, res = ffprobe_info(path)

            if minutes is not None:
                self.e_run.delete(0, "end")
                self.e_run.insert(0, str(minutes))

            if res:
                self.e_res.delete(0, "end")
                self.e_res.insert(0, res)
        except Exception:
            pass

    def choose_poster(self):
        path = filedialog.askopenfilename(
            title="Pick poster image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp")]
        )
        if not path:
            return

        src = Path(path)

        # 1) If the user picked a file that is already in the posters folder,
        #    don't copy it again – just use it as-is.
        try:
            if src.resolve().parent == POSTERS.resolve():
                self.poster_path = str(src.resolve())
                return
        except Exception:
            # if resolve() fails for some reason, just fall back to copy logic
            pass

        # 2) Otherwise, copy it into posters/ with a stable name based on title
        title_for_name = (self.e_title.get() or src.stem or "poster").strip()
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title_for_name)[:64]  # sanitize
        dest = POSTERS / f"{safe}.jpg"

        try:
            img = Image.open(src).convert("RGB")
            img.save(dest, "JPEG", quality=92)
            self.poster_path = str(dest)
        except Exception as e:
            messagebox.showerror("Poster error", str(e))


    def fetch_from_wiki(self):
        title = (self.e_title.get() or "").strip()
        year_text = (self.e_year.get() or "").strip()
        year = int(year_text) if year_text.isdigit() else None

        if not title:
            messagebox.showinfo("Wikipedia", "Enter a title first.")
            return

        self.fetch_btn.configure(state="disabled")
        try:
            meta = fetch_wikipedia_metadata(title, year, dest_folder=str(POSTERS))
        finally:
            self.fetch_btn.configure(state="normal")

        if not meta:
            messagebox.showinfo("Wikipedia", "No Wikipedia summary found for that title.")
            return

        if meta.get("title"):
            self.e_title.delete(0, "end")
            self.e_title.insert(0, meta["title"])

        if meta.get("year"):
            self.e_year.delete(0, "end")
            self.e_year.insert(0, str(meta["year"]))

        if meta.get("overview"):
            short = shorten_overview(meta["overview"], max_sentences=3, max_chars=700)
            self.e_over.delete("1.0", "end")
            self.e_over.insert("1.0", short)

        self.e_genre.delete(0, "end")
        if meta.get("genres"):
            self.e_genre.insert(0, meta["genres"])

        self.e_run.delete(0, "end")
        if meta.get("runtime_minutes"):
            self.e_run.insert(0, str(meta["runtime_minutes"]))

        if meta.get("poster_path"):
            self.poster_path = meta["poster_path"]   # <- this line ensures the poster is saved
            messagebox.showinfo("Wikipedia", "Metadata + poster fetched. Click Save to apply.")
        else:
            messagebox.showinfo("Wikipedia", "Metadata fetched (no poster found). Click Save to apply.")

    def on_save(self):
        def safe_int(s):
            try:
                return int(s)
            except:
                return None
        self.values.update({
            "title": (self.e_title.get() or "").strip(),
            "year": safe_int((self.e_year.get() or "").strip()),
            "genres": (self.e_genre.get() or "").strip(),
            "runtime_minutes": safe_int((self.e_run.get() or "").strip()),
            "resolution": (self.e_res.get() or "").strip(),
            "file_path": (self.e_file.get() or "").strip(),
            "overview": (self.e_over.get("1.0","end") or "").strip(),
            "poster_path": self.poster_path
        })
        if not self.values["title"]:
            messagebox.showwarning("Missing title", "Title is required")
            return
            
        self.saved = True
        self.destroy()

# -------------------- App UI --------------------
class MovieApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VisionVault")

        # --- TV navigation state ---
        self.nav_mode = "root"   # "root" or "show"
        self.nav_show_id: Optional[int] = None
        
        # --- NEW: load settings ---
        self.settings = load_settings()
        
        self.current_theme_name = self.settings.get("theme_name", "Blue")
        if self.current_theme_name not in THEMES:
            self.current_theme_name = "Blue"
        
        # Remember last view mode, but do NOT apply it yet (grid can change layout)
        self._saved_view_mode = self.settings.get("view_mode", "list")
        if self._saved_view_mode not in ("list", "grid"):
            self._saved_view_mode = "list"

        
        geom = self.settings.get("window_geometry")
        if geom:
            self.geometry(geom)
        else:
            self.geometry("1200x850")

        # load appearance mode from settings
        saved_mode = self.settings.get("appearance_mode", "Dark")
        if saved_mode not in ("Dark", "Light", "System"):
            saved_mode = "Dark"
        ctk.set_appearance_mode(saved_mode)

        ctk.set_default_color_theme("blue")

        # let us run custom cleanup / save on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_menubar()

        # Tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_library = self.tabs.add("Library")
        self.tab_discover = self.tabs.add("Discover")
        self.tab_stats = self.tabs.add("Stats")

        # Top bar container
        topbar = ctk.CTkFrame(self.tab_library)
        topbar.pack(fill="x", padx=10, pady=5)

        # ROW 1: theme + view + search + add controls
        row1 = ctk.CTkFrame(topbar)
        row1.pack(fill="x", pady=(0, 4))

        # Back button (hidden until inside a show)
        self.back_btn = ctk.CTkButton(
            row1, text="Back",
            width=70,
            command=self.go_back
        )
        self.back_btn.pack(side="left", padx=(0, 6))
        self.back_btn.pack_forget()

        # View mode toggle
        self.view_mode = tk.StringVar(value="list")  # 'list' or 'grid'

        # Remember what the user was using in the root library (grid or list)
        self.root_view_mode = self.view_mode.get()

        # Search (stretches)
        self.search_entry = ctk.CTkEntry(row1, placeholder_text="Search title...")
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh_list())

        # Add-by-title entry (shorter, still visible)
        self.add_title_entry = ctk.CTkEntry(row1, placeholder_text="Add by Title...")
        self.add_title_entry.pack(side="left", padx=(0, 6), ipadx=40)

        self.add_title_btn = ctk.CTkButton(
            row1, text="Add", width=80,
            command=self.add_by_title
        )
        self.add_title_btn.pack(side="left", padx=(0, 6))

        self.add_file_btn = ctk.CTkButton(
            row1, text="Add by File", width=110,
            command=self.add_by_file
        )
        self.add_file_btn.pack(side="left")

        self.import_tv_btn = ctk.CTkButton(
            row1,
            text="Import TV Show",
            width=190,
            command=self.import_encoded_tv_folder
        )
        self.import_tv_btn.pack(side="left", padx=(6, 0))


        # ROW 2: filters + sort aligned to the right
        row2 = ctk.CTkFrame(topbar)
        row2.pack(fill="x")

        # left spacer so everything else hugs the right edge
        ctk.CTkLabel(row2, text="").pack(side="left", expand=True)

        self.filter_opt = ctk.CTkOptionMenu(
            row2,
            values=["All", "Unwatched", "Watched"],
            command=lambda _: self.refresh_list()
        )
        self.filter_opt.pack(side="right", padx=(6, 0))

        self.genre_opt = ctk.CTkOptionMenu(
            row2,
            values=["All"],
            command=lambda _: self.refresh_list()
        )
        self.genre_opt.pack(side="right", padx=(6, 0))

        self.sort_opt = ctk.CTkOptionMenu(
            row2,
            values=[
                "Title A→Z", "Title Z→A",
                "Year ↑", "Year ↓",
                "Watched ↑", "Watched ↓",
                "Recently added", "Oldest added",
            ],
            command=lambda _: self.refresh_list()
        )
        self.sort_opt.set("Title A→Z")
        self.sort_opt.pack(side="right")

        # ---- Drag-resizable split (styled) ----
        self.split = tk.PanedWindow(
            self.tab_library,
            orient="horizontal",
            sashwidth=8,
            sashrelief="flat",
            bd=0,
            bg=self._paned_bg(),
            cursor="arrow",
            opaqueresize=False
        )
        self.split.pack(fill="both", expand=True, padx=10, pady=10)

        left = ctk.CTkFrame(self.split)
        right = ctk.CTkFrame(self.split)

        self.split.add(left, minsize=240)   # left list pane
        self.split.add(right, minsize=420)  # right detail pane

        # LEFT: list
        self.listbox = ctk.CTkTextbox(left)
        self.listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # bigger font for list view
        self.list_font = ctk.CTkFont(family="Segoe UI", size=15)  # change size to taste
        try:
            self.listbox._textbox.configure(spacing1=2, spacing3=2)  # top/bottom spacing per line
        except Exception:
            pass
        self.listbox.configure(font=self.list_font)

        self.listbox.configure(state="disabled", cursor="arrow")
        self.selected_id = None
        self.line_to_id = {}

        # make list feel selectable
        self.listbox.bind("<Enter>", lambda e: self.listbox.configure(cursor="hand2"))
        self.listbox.bind("<Leave>", lambda e: self.listbox.configure(cursor="arrow"))


        # Grid scroller container (Canvas + inner frame + scrollbar)
        self.grid_scroll = ctk.CTkFrame(left)
        self.grid_scroll.pack_forget() # hidden until grid mode

        # Apply saved view mode immediately (no visible flip)
        saved_vm = self.settings.get("view_mode", "list")
        if saved_vm not in ("list", "grid"):
            saved_vm = "list"

        self.view_mode.set(saved_vm)
        self._show_view(saved_vm)


        self.grid_canvas = tk.Canvas(self.grid_scroll, highlightthickness=0, bd=0,
                                     bg=self._paned_bg())
        self.grid_vsb = ctk.CTkScrollbar(self.grid_scroll, command=self.grid_canvas.yview)
        self.grid_canvas.configure(yscrollcommand=self.grid_vsb.set)
        self.grid_inner = ctk.CTkFrame(self.grid_canvas)


        self.grid_canvas.create_window((0, 0), window=self.grid_inner, anchor="nw")
        self.grid_canvas.pack(side="left", fill="both", expand=True)
        self.grid_vsb.pack(side="right", fill="y")


        # ensure scrollregion updates
        def _on_frame_config(event=None):
            self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        self.grid_inner.bind("<Configure>", _on_frame_config)


        # mouse wheel scrolling on grid
        def _on_mousewheel(event):
            delta = -1 if event.delta > 0 else 1
            self.grid_canvas.yview_scroll(delta, "units")
        self.grid_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # RIGHT: poster + description + buttons
        right.pack_propagate(False)

        # poster
        self.poster_label = ctk.CTkLabel(right, text="")
        self.poster_label.pack(pady=(10, 6))

        # safe blank image to avoid TclError when clearing
        _blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        self._blank_img = ctk.CTkImage(light_image=_blank, dark_image=_blank, size=(1, 1))
        self._poster_image = self._blank_img
        self.poster_label.configure(image=self._blank_img, text="")


        # description frame + scrollbar
        desc_frame = ctk.CTkFrame(right)
        desc_frame.pack(expand=True, fill="both", pady=(6, 10), padx=10)

        self.desc_box = ctk.CTkTextbox(desc_frame, wrap="word", activate_scrollbars=True)
        self.desc_box.pack(side="left", expand=True, fill="both")
        self.desc_box.configure(state="disabled")

        scrollbar = ctk.CTkScrollbar(desc_frame, command=self.desc_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.desc_box.configure(yscrollcommand=scrollbar.set)

        # action buttons
        btn_row = ctk.CTkFrame(right)
        btn_row.pack(pady=6)
        self.watch_btn = ctk.CTkButton(btn_row, text="Mark as Watched", command=self.mark_watched)
        self.watch_btn.pack(side="left", padx=5)

        self.edit_btn = ctk.CTkButton(btn_row, text="Edit Details", command=self.edit_selected)
        self.edit_btn.pack(side="left", padx=5)

        self.delete_btn = ctk.CTkButton(btn_row, text="Delete", fg_color="red", hover_color="#aa0000", command=self.delete_selected)
        self.delete_btn.pack(side="left", padx=5)

        self.play_btn = ctk.CTkButton(btn_row, text="Play", command=self.play_selected)
        self.play_btn.pack(side="left", padx=5)

        # place sash once after layout is ready
        # Populate first, then restore sash once the correct view is built
        self.after(1, self._post_ui_init)

        def _install_sash_cursor(self):
            # how close (px) the mouse must be to the sash to show resize cursor
            self._sash_hover_pad = 6

            def on_motion(event):
                try:
                    sash_x, _ = self.split.sash_coord(0)   # current sash position in split coords
                except Exception:
                    self.split.configure(cursor="arrow")
                    return

                # event.x is also in split coords
                if abs(event.x - sash_x) <= self._sash_hover_pad:
                    self.split.configure(cursor="sb_h_double_arrow")
                else:
                    self.split.configure(cursor="arrow")

            def on_leave(event):
                self.split.configure(cursor="arrow")

            self.split.bind("<Motion>", on_motion)
            self.split.bind("<Leave>", on_leave)

        self.selected_id = None
        self.listbox.bind("<ButtonRelease-1>", self.select_movie)
        # Right-click context menu (list)
        self.listbox.bind("<Button-3>", self._on_list_right_click)          # Windows/Linux
        self.listbox.bind("<Control-Button-1>", self._on_list_right_click)  # macOS fallback
        
        # Context menu
        self._build_context_menu()


        # -------------------- Discover tab UI --------------------
        disc_top = ctk.CTkFrame(self.tab_discover)
        disc_top.pack(fill="x", padx=10, pady=10)

        self.disc_search_entry = ctk.CTkEntry(disc_top, placeholder_text="Search Wikipedia (movie title)...")
        self.disc_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.disc_search_entry.bind("<Return>", lambda e: self.discover_search())
        self.disc_search_entry.focus_set()

        self.disc_year_entry = ctk.CTkEntry(disc_top, width=90, placeholder_text="Year")
        self.disc_year_entry.pack(side="left", padx=(0, 8))

        self.disc_search_btn = ctk.CTkButton(disc_top, text="Search", width=90, command=self.discover_search)
        self.disc_search_btn.pack(side="left")

        disc_split = tk.PanedWindow(
            self.tab_discover,
            orient="horizontal",
            sashwidth=8,
            sashrelief="flat",
            bd=0,
            bg=self._paned_bg(),
            cursor="arrow",
            opaqueresize=False
        )
        disc_split.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        disc_left = ctk.CTkFrame(disc_split)
        disc_right = ctk.CTkFrame(disc_split)
        disc_split.add(disc_left, minsize=280)
        disc_split.add(disc_right, minsize=420)

        # results list (clickable, not editable)
        self.disc_results = ctk.CTkTextbox(disc_left)
        self.disc_results.pack(fill="both", expand=True, padx=10, pady=10)
        self.disc_results.configure(state="disabled", cursor="arrow")
        self.disc_results.bind("<Enter>", lambda e: self.disc_results.configure(cursor="hand2"))
        self.disc_results.bind("<Leave>", lambda e: self.disc_results.configure(cursor="arrow"))
        self.disc_results.bind("<ButtonRelease-1>", self.discover_select)

        self.disc_line_to_page = {}
        self.disc_selected_meta = None

        # preview poster
        self.disc_poster_label = ctk.CTkLabel(disc_right, text="")
        self.disc_poster_label.pack(pady=(10, 6))
        self.disc_poster_label.configure(image=self._blank_img, text="")

        # preview text
        disc_desc_frame = ctk.CTkFrame(disc_right)
        disc_desc_frame.pack(expand=True, fill="both", pady=(6, 10), padx=10)

        self.disc_desc = ctk.CTkTextbox(disc_desc_frame, wrap="word", activate_scrollbars=True)
        self.disc_desc.pack(side="left", expand=True, fill="both")
        self.disc_desc.configure(state="disabled")

        disc_scroll = ctk.CTkScrollbar(disc_desc_frame, command=self.disc_desc.yview)
        disc_scroll.pack(side="right", fill="y")
        self.disc_desc.configure(yscrollcommand=disc_scroll.set)

        # action row
        disc_btns = ctk.CTkFrame(disc_right)
        disc_btns.pack(pady=(0, 12))

        self.disc_add_btn = ctk.CTkButton(disc_btns, text="Add to Library", state="disabled", command=self.discover_add)
        self.disc_add_btn.pack(side="left", padx=6)

        self.disc_status = ctk.CTkLabel(disc_right, text="", anchor="w")
        self.disc_status.pack(fill="x", padx=10, pady=(0, 8))

        # Stats tab
        self.stats_top = ctk.CTkFrame(self.tab_stats)
        self.stats_top.pack(fill="x", padx=10, pady=10)

        self.lbl_totals = ctk.CTkLabel(self.stats_top, text="", justify="left")
        self.lbl_totals.pack(side="left", padx=10)

        self.btn_refresh_stats = ctk.CTkButton(self.stats_top, text="Refresh Stats", command=self.refresh_stats)
        self.btn_refresh_stats.pack(side="right", padx=10)

        self.stats_mid = ctk.CTkFrame(self.tab_stats)
        self.stats_mid.pack(fill="both", expand=True, padx=10, pady=5)

        self.col_top = ctk.CTkTextbox(self.stats_mid, width=360)
        self.col_top.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.col_genres = ctk.CTkTextbox(self.stats_mid, width=360)
        self.col_genres.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.col_recent = ctk.CTkTextbox(self.stats_mid, width=360)
        self.col_recent.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # Status bar
        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0,8))

        self.grid_ids = []
        self.grid_tile_frames = {}
        self.grid_cols = 3

        self._bind_shortcuts()
        self.apply_theme()
        self.refresh_stats()

    # -------- helpers --------

    def _ctx_convert_to_3d(self):
        if not self._ctx_target_id:
            return

        fpath = self._get_file_path(int(self._ctx_target_id))
        if not fpath or not os.path.exists(fpath):
            self.set_status("No valid file path to send to VisionDepth3D.")
            return

        vd3d_path = self._find_vd3d_executable()

        if vd3d_path:
            try:
                subprocess.Popen([vd3d_path, fpath])
                self.set_status("Opened file in VisionDepth3D.")
            except Exception as e:
                self.set_status(f"Could not launch VisionDepth3D: {e}")
        else:
            try:
                webbrowser.open("https://github.com/VisionDepth/VisionDepth3D")
                self.set_status("VisionDepth3D not found. Opened download page.")
            except Exception as e:
                self.set_status(f"Could not open VisionDepth3D releases page: {e}")

    def _theme(self):
        return THEMES.get(self.current_theme_name, THEMES["Blue"])


    def apply_theme(self):
        theme = self._theme()

        button_widgets = [
            getattr(self, "add_title_btn", None),
            getattr(self, "add_file_btn", None),
            getattr(self, "import_tv_btn", None),
            getattr(self, "back_btn", None),
            getattr(self, "watch_btn", None),
            getattr(self, "edit_btn", None),
            getattr(self, "play_btn", None),
            getattr(self, "disc_add_btn", None),
            getattr(self, "disc_search_btn", None),
            getattr(self, "btn_refresh_stats", None),
        ]

        for btn in button_widgets:
            if btn is not None:
                try:
                    btn.configure(
                        fg_color=theme["accent"],
                        hover_color=theme["accent_hover"]
                    )
                except Exception:
                    pass

        try:
            self.delete_btn.configure(
                fg_color=theme["danger"],
                hover_color=theme["danger_hover"]
            )
        except Exception:
            pass

        try:
            self.filter_opt.configure(
                fg_color=theme["accent"],
                button_color=theme["accent"],
                button_hover_color=theme["accent_hover"]
            )
        except Exception:
            pass

        try:
            self.genre_opt.configure(
                fg_color=theme["accent"],
                button_color=theme["accent"],
                button_hover_color=theme["accent_hover"]
            )
        except Exception:
            pass

        try:
            self.sort_opt.configure(
                fg_color=theme["accent"],
                button_color=theme["accent"],
                button_hover_color=theme["accent_hover"]
            )
        except Exception:
            pass

        try:
            self._highlight_selected_grid_tile()
        except Exception:
            pass

    def set_theme(self, theme_name: str):
        if theme_name not in THEMES:
            return

        self.current_theme_name = theme_name
        self.apply_theme()
        self.refresh_list()

    def _ensure_selected_tile_visible_smooth(self):
        if self.view_mode.get() != "grid" or self.nav_mode != "root":
            return
        if not self.selected_id:
            return

        tile = self.grid_tile_frames.get(self.selected_id)
        if not tile:
            return

        try:
            self.grid_canvas.update_idletasks()
            self.grid_inner.update_idletasks()

            canvas_h = self.grid_canvas.winfo_height()
            inner_h = self.grid_inner.winfo_height()
            if canvas_h <= 1 or inner_h <= 1:
                return

            tile_y = tile.winfo_y()
            tile_h = tile.winfo_height()

            top_frac, bottom_frac = self.grid_canvas.yview()
            current_top = top_frac * inner_h
            current_bottom = bottom_frac * inner_h

            pad = 20
            target_top = None

            if tile_y < current_top + pad:
                target_top = max(0, tile_y - pad)
            elif (tile_y + tile_h) > (current_bottom - pad):
                target_top = min(
                    max(0, inner_h - canvas_h),
                    tile_y + tile_h - canvas_h + pad
                )

            if target_top is None:
                return

            self._smooth_scroll_grid_to(target_top)
        except Exception:
            pass

    def _smooth_scroll_grid_to(self, target_top: float, steps: int = 10, delay: int = 12):
        try:
            self.grid_canvas.update_idletasks()
            self.grid_inner.update_idletasks()

            inner_h = self.grid_inner.winfo_height()
            canvas_h = self.grid_canvas.winfo_height()
            if inner_h <= 1 or canvas_h <= 1:
                return

            max_top = max(0, inner_h - canvas_h)
            target_top = max(0, min(target_top, max_top))

            top_frac, _ = self.grid_canvas.yview()
            start_top = top_frac * inner_h

            distance = target_top - start_top
            if abs(distance) < 2:
                if inner_h > 0:
                    self.grid_canvas.yview_moveto(target_top / inner_h)
                return

            # cancel previous scroll animation if one is running
            job = getattr(self, "_grid_scroll_job", None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                self._grid_scroll_job = None

            self._grid_scroll_step = 0

            def ease_out(t: float) -> float:
                return 1 - (1 - t) * (1 - t)

            def animate():
                try:
                    self._grid_scroll_step += 1
                    t = self._grid_scroll_step / steps
                    t = min(1.0, t)

                    pos = start_top + distance * ease_out(t)
                    self.grid_canvas.yview_moveto(pos / max(inner_h, 1))

                    if t < 1.0:
                        self._grid_scroll_job = self.after(delay, animate)
                    else:
                        self._grid_scroll_job = None
                except Exception:
                    self._grid_scroll_job = None

            animate()
        except Exception:
            pass

    def _bind_shortcuts(self):
        self.bind_all("<Return>", self._on_key_enter)
        self.bind_all("<space>", self._on_key_space)
        self.bind_all("<Delete>", self._on_key_delete)
        self.bind_all("<BackSpace>", self._on_key_back)
        self.bind_all("<Escape>", self._on_key_back)
        self.bind_all("<Up>", self._on_key_up)
        self.bind_all("<Down>", self._on_key_down)
        self.bind_all("<Left>", self._on_key_left)
        self.bind_all("<Right>", self._on_key_right)
        self.bind_all("<Key-e>", self._on_key_edit)
        self.bind_all("<Key-E>", self._on_key_edit)

    def _shortcut_allowed(self):
        focused = self.focus_get()
        if focused is None:
            return True

        # block shortcuts if a popup/dialog is active
        try:
            if focused.winfo_toplevel() is not self:
                return False
        except Exception:
            return False

        # allow library list textbox and grid canvas/buttons
        try:
            if focused == self.listbox or focused == self.listbox._textbox:
                return True
        except Exception:
            pass

        try:
            if focused == self.grid_canvas:
                return True
        except Exception:
            pass

        # block while typing in true input widgets
        blocked_widgets = {
            self.search_entry,
            self.add_title_entry,
            self.disc_search_entry,
            self.disc_year_entry,
        }

        if focused in blocked_widgets:
            return False

        try:
            cls = focused.winfo_class()
            if cls in ("Entry", "TEntry", "Spinbox", "TCombobox"):
                return False
        except Exception:
            pass

        return True

    def _select_item_by_id(self, mid: int, enter_show: bool = False):
        if not mid:
            return

        mt = self._get_media_type(mid)

        if enter_show and self.nav_mode == "root" and mt == "show":
            self.enter_show(mid)
            self.focus_set()
            return

        self.selected_id = int(mid)
        self._load_details(int(mid))
        self._highlight_selected_id_in_list()
        self._highlight_selected_grid_tile()
        self.focus_set()

        if self.view_mode.get() == "grid" and self.nav_mode == "root":
            self.after(10, self._ensure_selected_tile_visible_smooth)
            
    def _highlight_selected_grid_tile(self):
        for mid in getattr(self, "grid_tile_frames", {}).keys():
            self._set_tile_visual_state(mid, hovered=False)

    def _grid_tile_colors(self):
        theme = self._theme()

        if str(ctk.get_appearance_mode()).lower() == "dark":
            return {
                "normal_fg": "#2b2b2b",
                "hover_fg": "#353535",
                "selected_fg": "#2f3440",
                "normal_border": "#2b2b2b",
                "hover_border": theme["hover_border"],
                "selected_border": theme["selected_border"],
            }

        return {
            "normal_fg": "#e9e9e9",
            "hover_fg": "#f2f2f2",
            "selected_fg": "#eaf2ff",
            "normal_border": "#e9e9e9",
            "hover_border": theme["hover_border"],
            "selected_border": theme["selected_border"],
        }
        
    def _set_tile_visual_state(self, mid: int, hovered: bool = False):
        frame = getattr(self, "grid_tile_frames", {}).get(mid)
        if not frame:
            return

        colors = self._grid_tile_colors()
        is_selected = bool(self.selected_id and int(mid) == int(self.selected_id))

        try:
            if is_selected:
                frame.configure(
                    fg_color=colors["selected_fg"],
                    border_width=2,
                    border_color=colors["selected_border"]
                )
            elif hovered:
                frame.configure(
                    fg_color=colors["hover_fg"],
                    border_width=2,
                    border_color=colors["hover_border"]
                )
            else:
                frame.configure(
                    fg_color=colors["normal_fg"],
                    border_width=0,
                    border_color=colors["normal_border"]
                )
        except Exception:
            pass

    def _bind_tile_hover(self, widget, mid: int):
        widget.bind("<Enter>", lambda e, m=mid: self._set_tile_visual_state(m, hovered=True), add="+")
        widget.bind("<Leave>", lambda e, m=mid: self._set_tile_visual_state(m, hovered=False), add="+")

    def _move_list_selection(self, delta: int):
        ids = [self.line_to_id[k] for k in sorted(self.line_to_id.keys())]
        if not ids:
            return

        if not self.selected_id or self.selected_id not in ids:
            target = ids[0]
        else:
            idx = ids.index(self.selected_id)
            idx = max(0, min(len(ids) - 1, idx + delta))
            target = ids[idx]

        self._select_item_by_id(target, enter_show=False)

    def _move_grid_selection(self, delta: int):
        ids = list(getattr(self, "grid_ids", []))
        if not ids:
            return

        if not self.selected_id or self.selected_id not in ids:
            target = ids[0]
        else:
            idx = ids.index(self.selected_id)
            idx = max(0, min(len(ids) - 1, idx + delta))
            target = ids[idx]

        self._select_item_by_id(target, enter_show=False)

    def _on_key_enter(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.selected_id:
            self.play_selected()
            return "break"

    def _on_key_space(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.selected_id:
            self.mark_watched()
            return "break"

    def _on_key_delete(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.selected_id:
            self.delete_selected()
            return "break"

    def _on_key_edit(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.selected_id:
            self.edit_selected()
            return "break"

    def _on_key_back(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.nav_mode == "show":
            self.go_back()
            return "break"

    def _on_key_up(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.view_mode.get() == "grid" and self.nav_mode == "root":
            self._move_grid_selection(-self.grid_cols)
        else:
            self._move_list_selection(-1)
        return "break"

    def _on_key_down(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.view_mode.get() == "grid" and self.nav_mode == "root":
            self._move_grid_selection(self.grid_cols)
        else:
            self._move_list_selection(1)
        return "break"

    def _on_key_left(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.view_mode.get() == "grid" and self.nav_mode == "root":
            self._move_grid_selection(-1)
            return "break"

    def _on_key_right(self, event=None):
        if not self._shortcut_allowed():
            return
        if self.view_mode.get() == "grid" and self.nav_mode == "root":
            self._move_grid_selection(1)
            return "break"


    def _clamp_lines(self, text: str, max_chars_per_line: int = 28, max_lines: int = 2) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        lines = textwrap.wrap(text, width=max_chars_per_line)
        if len(lines) <= max_lines:
            return "\n".join(lines)

        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[:-3] + "...") if len(last) >= 3 else (last + "...")
        return "\n".join(lines)

    def _list_sel_colors(self):
        # pick colors that look fine in dark/light mode
        if str(ctk.get_appearance_mode()).lower() == "dark":
            return ("#2a4d7a", "white")   # bg, fg
        return ("#cfe3ff", "black")

    def _highlight_list_line(self, line_no: int):
        # CTkTextbox wraps a tk.Text at ._textbox
        t = self.listbox._textbox

        bg, fg = self._list_sel_colors()

        # tag style (configure once is fine)
        try:
            t.tag_configure("vv_selected", background=bg, foreground=fg)
        except Exception:
            pass

        # remove previous highlight
        try:
            t.tag_remove("vv_selected", "1.0", "end")
        except Exception:
            pass

        # add highlight to this line
        start = f"{line_no}.0"
        end = f"{line_no}.0 lineend"
        try:
            t.tag_add("vv_selected", start, end)
            t.mark_set("insert", start)
            t.see(start)  # keep it visible if list is scrolled
        except Exception:
            pass

    def _highlight_selected_id_in_list(self):
        """After refresh_list() rebuilds the textbox, re-highlight the current selected_id."""
        if not self.selected_id:
            return
        # find the line number that maps to selected_id
        for line_no, mid in self.line_to_id.items():
            if mid == self.selected_id:
                self._highlight_list_line(line_no)
                return

    def _on_grid_right_click(self, event, mid: int):
        # select it so details match
        self.select_by_id(mid)

        self._ctx_set_target(mid)
        self._popup_context_menu(event)
        return "break"

    def parse_encoded_episode_filename(self, path: str):
        """
        Supports:
          'Show Title - S01E01 - Episode Name.ext'
          'Show Title - S01E01.ext'
        Returns (show_title, season, episode, ep_title) or None
        """
        name = os.path.splitext(os.path.basename(path))[0].strip()

        m = re.search(
            r"(?i)^(.*?)\s*-\s*S(\d{1,3})E(\d{1,4})(?:\s*-\s*(.*?))?\s*$",
            name
        )
        if not m:
            return None

        show_title = (m.group(1) or "").strip(" ._-")
        season = int(m.group(2))
        episode = int(m.group(3))
        ep_title = (m.group(4) or "").strip(" ._-")

        if not show_title:
            return None

        # If there was no explicit episode title, fall back to the filename stem
        if not ep_title:
            ep_title = f"S{season:02d}E{episode:02d}"

        return show_title, season, episode, ep_title

    def _parse_episode_tag(self, path: str) -> Optional[Tuple[int, int, str]]:
        """
        Returns (season, episode, show_guess) if filename contains SxxEyy or 1x02 style.
        show_guess is a cleaned title guess from the left side of the match.
        """
        name = os.path.splitext(os.path.basename(path))[0]

        m = re.search(r"(?i)\bS(\d{1,2})\s*E(\d{1,3})\b", name)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            left = name[:m.start()].strip(" ._-")
            show_guess, _ = guess_title_year_from_filename(left) if left else guess_title_year_from_filename(path)
            return season, episode, (show_guess or "").strip()

        m = re.search(r"(?i)\b(\d{1,2})\s*x\s*(\d{1,3})\b", name)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            left = name[:m.start()].strip(" ._-")
            show_guess, _ = guess_title_year_from_filename(left) if left else guess_title_year_from_filename(path)
            return season, episode, (show_guess or "").strip()

        return None


    def _ensure_show_row(self, show_title: str, year: Optional[int] = None) -> Optional[int]:
        """Find or create a show row, return show_id."""
        show_title = (show_title or "").strip()
        if not show_title:
            return None

        try:
            con = db()
            row = con.execute(
                "SELECT id FROM movies WHERE media_type='show' AND title=?",
                (show_title,)
            ).fetchone()
            con.close()
            if row:
                return int(row[0])
        except Exception:
            pass

        # create show
        show_values = {
            "title": show_title,
            "year": year,
            "genres": "",
            "overview": "",
            "poster_path": None,
            "file_path": None,
            "runtime_minutes": None,
            "resolution": None,
            "media_type": "show",
            "show_id": None,
            "season": None,
            "episode": None,
        }
        return upsert_movie(show_values)



    def discover_search(self):
        q = (self.disc_search_entry.get() or "").strip()
        if not q:
            self.disc_status.configure(text="Type a movie title to search.")
            return

        self.disc_status.configure(text="Searching Wikipedia...")
        self.disc_add_btn.configure(state="disabled")
        self.disc_selected_meta = None
        self.disc_poster_label.configure(image=self._blank_img, text="")

        self.disc_desc.configure(state="normal")
        self.disc_desc.delete("1.0", "end")
        self.disc_desc.configure(state="disabled")

        results = wiki_search_titles(q, limit=12, lang="en")

        self.disc_results.configure(state="normal")
        self.disc_results.delete("1.0", "end")
        self.disc_line_to_page = {}

        if not results:
            self.disc_results.insert("end", "No results.\n")
            self.disc_results.configure(state="disabled")
            self.disc_status.configure(text="No results found.")
            return

        for i, r in enumerate(results, start=1):
            title = r.get("title", "")
            desc = (r.get("description") or "").strip()
            line = f"{i}: {title}"
            if desc:
                line += f"  •  {desc}"
            self.disc_results.insert("end", line + "\n")
            self.disc_line_to_page[i] = r

        self.disc_results.configure(state="disabled")
        self.disc_status.configure(text=f"Results: {len(results)}. Click one to preview.")


    def discover_select(self, event=None):
        # figure out clicked line
        try:
            idx = self.disc_results.index(f"@{event.x},{event.y}") if event else self.disc_results.index("insert")
            line_no = int(str(idx).split(".")[0])
        except Exception:
            return

        r = self.disc_line_to_page.get(line_no)
        if not r:
            return

        pageid = r.get("pageid")
        if not pageid:
            return

        self.disc_status.configure(text="Loading preview...")
        self.disc_add_btn.configure(state="disabled")
        self.disc_selected_meta = None

        meta = fetch_wikipedia_metadata_by_pageid(pageid, dest_folder=str(POSTERS), lang="en")
        if not meta:
            self.disc_status.configure(text="Could not load that page.")
            return

        # apply optional year override if user typed one
        ytxt = (self.disc_year_entry.get() or "").strip()
        if ytxt.isdigit():
            meta["year"] = int(ytxt)

        # shorten overview for UI
        full_over = meta.get("overview") or ""
        short = shorten_overview(full_over, max_sentences=3, max_chars=900)

        title = meta.get("title") or "Unknown"
        year = meta.get("year")
        genres = meta.get("genres") or ""
        runtime = meta.get("runtime_minutes")

        header = f"{title} ({year})" if year else title

        details = []
        if genres:
            details.append(f"Genres: {genres}")
        if runtime:
            details.append(f"Runtime: {runtime} min")

        preview_text = header
        if details:
            preview_text += "\n" + "\n".join(details)
        preview_text += "\n\n" + (short or "No summary found.")

        self.disc_desc.configure(state="normal")
        self.disc_desc.delete("1.0", "end")
        self.disc_desc.insert("1.0", preview_text)
        self.disc_desc.configure(state="disabled")

        # poster
        p = meta.get("poster_path")
        if p and os.path.exists(p):
            try:
                img = Image.open(p).convert("RGBA").copy()
                tw, th = self._fit_poster_size(*img.size, max_w=260, max_h=390)
                self._disc_poster_img = ctk.CTkImage(light_image=img, dark_image=img, size=(tw, th))
                self.disc_poster_label.configure(image=self._disc_poster_img, text="")
            except Exception:
                self.disc_poster_label.configure(image=self._blank_img, text="Poster error")
        else:
            self.disc_poster_label.configure(image=self._blank_img, text="No poster")

        self.disc_selected_meta = meta
        self.disc_add_btn.configure(state="normal")
        self.disc_status.configure(text="Preview loaded. Click Add to Library.")


    def discover_add(self):
        meta = self.disc_selected_meta
        if not meta:
            return

        values = {
            "title": (meta.get("title") or "").strip(),
            "year": meta.get("year"),
            "genres": meta.get("genres") or "",
            "overview": shorten_overview(meta.get("overview") or "", max_sentences=3, max_chars=900),
            "poster_path": meta.get("poster_path"),
            "file_path": None,
            "runtime_minutes": meta.get("runtime_minutes"),
            "resolution": None,
        }
        if not values["title"]:
            self.disc_status.configure(text="Missing title, cannot add.")
            return

        upsert_movie(values)
        self.refresh_list()
        self.refresh_stats()
        self.set_status(f"Added: {values['title']}")
        self.disc_status.configure(text="Added to Library.")
        self.disc_add_btn.configure(state="disabled")


    def _restore_last_selected(self):
        mid = self.settings.get("last_selected_id")
        if not mid:
            return

        # make sure it still exists (movie might have been deleted)
        try:
            con = db()
            row = con.execute("SELECT id FROM movies WHERE id=?", (mid,)).fetchone()
            con.close()
            if not row:
                return
        except Exception:
            return

        # load details on the right
        self._load_details(mid)


    def _post_ui_init(self):
        # build whatever view we’re in (grid/list) first
        self.refresh_list()

        # NEW: restore last selected after list/grid exists
        self.after(1, self._restore_last_selected)

        # now restore sash AFTER the widgets have real sizes
        self.after(150, self._restore_layout)


    def _paned_bg(self):
        # match CTk background roughly for dark/light modes
        return "#1e1e1e" if str(ctk.get_appearance_mode()).lower() == "dark" else "#ededed"

    def _place_sash_initial(self):
        # kept for backward compat – now just calls the new restore
        self._restore_layout()

    def _restore_layout(self):
        """Restore sash position from settings or fall back to middle."""
        self.split.update_idletasks()
        total = self.split.winfo_width()
        if total <= 0:
            return

        # if we have a saved sash X, use it
        sash_x = self.settings.get("split_sash_x")
        if isinstance(sash_x, int):
            try:
                self.split.sash_place(0, sash_x, 1)
                return
            except Exception:
                pass

        # fallback – about 55% like you had before
        try:
            self.split.sash_place(0, int(total * 0.55), 1)
        except Exception:
            pass

    def _startup_restore(self):
        # Restore sash while we're in stable list mode
        self._restore_layout()

        # Then apply saved view mode after layout settles
        self.after(150, self._apply_saved_view_mode)

    def _apply_saved_view_mode(self):
        mode = getattr(self, "_saved_view_mode", "list")
        if mode not in ("list", "grid"):
            mode = "list"

        # Only switch if needed
        if self.view_mode.get() != mode:
            self.view_mode.set(mode)
            self._show_view(mode)

            # Populate the correct view
            self.refresh_list()

        # One more restore after grid builds so it can't "jump" the sash
        self.after(150, self._restore_layout)


    def _fit_poster_size(self, w, h, max_w=260, max_h=390):
        scale = min(max_w / max(w, 1), max_h / max(h, 1))
        return int(w * scale), int(h * scale)

    # --- Grid helpers & caches ---
    def _ensure_placeholder(self):
        if getattr(self, "_ph_img", None) is None:
            ph = Image.new("RGB", (300, 450), (42, 42, 42))
            self._ph_img = ctk.CTkImage(light_image=ph, dark_image=ph, size=(150, 225))
        return self._ph_img

    def _load_tile_image(self, poster_path: str | None, max_w=150, max_h=225):
        # cache CTkImage by file path + target size to avoid GC and speed up
        if not hasattr(self, "_tile_img_cache"):
            self._tile_img_cache = {}
        key = (poster_path or "__none__", max_w, max_h)
        if key in self._tile_img_cache:
            return self._tile_img_cache[key]
        try:
            if poster_path and os.path.exists(poster_path):
                img = Image.open(poster_path).convert("RGBA")
                tw, th = self._fit_poster_size(*img.size, max_w=max_w, max_h=max_h)
                ctki = ctk.CTkImage(light_image=img, dark_image=img, size=(tw, th))
            else:
                ctki = self._ensure_placeholder()
        except Exception:
            ctki = self._ensure_placeholder()
        self._tile_img_cache[key] = ctki
        return ctki

    def select_by_id(self, mid: int):
        self._select_item_by_id(mid, enter_show=True)
        
    def _get_media_type(self, mid: int) -> str:
        try:
            con = db()
            row = con.execute("SELECT media_type FROM movies WHERE id=?", (mid,)).fetchone()
            con.close()
            if row and row[0]:
                return str(row[0])
        except Exception:
            pass
        return "movie"

    def enter_show(self, show_id: int):
        # Save current root view mode before switching into show
        if self.nav_mode == "root":
            self.root_view_mode = self.view_mode.get()

        self.nav_mode = "show"
        self.nav_show_id = int(show_id)

        # show Back button
        try:
            self.back_btn.pack(side="left", padx=(0, 6))
        except Exception:
            pass

        # Force list view inside shows (episodes)
        if self.view_mode.get() != "list":
            self.view_mode.set("list")
            self._show_view("list")

        self.selected_id = None
        self._clear_details()
        self.refresh_list()
        self.set_status("Viewing show episodes.")

    def go_back(self):
        self.nav_mode = "root"
        self.nav_show_id = None
        self.selected_id = None
        self._clear_details()

        try:
            self.back_btn.pack_forget()
        except Exception:
            pass

        # Restore the view the user had before entering the show
        mode = getattr(self, "root_view_mode", "list")
        if mode not in ("list", "grid"):
            mode = "list"

        if self.view_mode.get() != mode:
            self.view_mode.set(mode)
            self._show_view(mode)

        self.refresh_list()
        self.set_status("Back to Library.")

    def _clear_details(self):
        try:
            self.desc_box.configure(state="normal")
            self.desc_box.delete("1.0", "end")
            self.desc_box.configure(state="disabled")
        except Exception:
            pass
        try:
            self.poster_label.configure(image=self._blank_img, text="")
        except Exception:
            pass

    def _load_details(self, mid: int):
        con = db()
        row = con.execute(
            """SELECT id,title,overview,poster_path,file_path,
                      runtime_minutes,resolution,genres,year
               FROM movies WHERE id=?""",
            (mid,)
        ).fetchone()
        con.close()
        if not row:
            return

        self.selected_id = mid
        title = row[1]; overview = row[2] or ""
        fpath = row[4]; runm = row[5]; res = row[6]; genres = row[7]; year = row[8]

        extra = []
        if runm:  extra.append(f"Runtime: {runm} min")
        if res:   extra.append(f"Resolution: {res}")
        if genres: extra.append(f"Genres: {genres}")
        if year:  extra.append(f"Year: {year}")
        if fpath: extra.append(f"File: {fpath}")

        info = ("\n".join(extra)).strip()
        text = f"{title}\n\n{overview}"
        if info:
            text += f"\n\n{info}"

        self.desc_box.configure(state="normal")
        self.desc_box.delete("1.0", "end")
        self.desc_box.insert("1.0", text)
        self.desc_box.configure(state="disabled")
        self.desc_box.configure(cursor="arrow")


        poster_path = row[3]
        if poster_path and os.path.exists(poster_path):
            try:
                img = Image.open(poster_path).convert("RGBA").copy()
                tw, th = self._fit_poster_size(*img.size, max_w=260, max_h=390)
                self._poster_image = ctk.CTkImage(light_image=img, dark_image=img, size=(tw, th))
                self.poster_label.configure(image=self._poster_image, text="")
            except Exception:
                self._poster_image = self._blank_img
                self.poster_label.configure(image=self._blank_img, text="Poster error")
        else:
            self._poster_image = self._blank_img
            self.poster_label.configure(image=self._blank_img, text="No poster")

    def set_status(self, msg):
        self.status.configure(text=msg)

    def _build_menubar(self):
        menubar = tk.Menu(self)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Add by Title", command=self.add_by_title)
        file_menu.add_command(label="Add by File", command=self.add_by_file)
        file_menu.add_command(label="Import TV Show", command=self.import_encoded_tv_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="List View", command=lambda: self.set_view_mode("list"))
        view_menu.add_command(label="Grid View", command=lambda: self.set_view_mode("grid"))
        menubar.add_cascade(label="View", menu=view_menu)

        # Themes
        themes_menu = tk.Menu(menubar, tearoff=0)

        appearance_menu = tk.Menu(themes_menu, tearoff=0)
        appearance_menu.add_command(label="Dark", command=lambda: self.set_appearance_mode_menu("Dark"))
        appearance_menu.add_command(label="Light", command=lambda: self.set_appearance_mode_menu("Light"))
        appearance_menu.add_command(label="System", command=lambda: self.set_appearance_mode_menu("System"))
        themes_menu.add_cascade(label="Appearance Mode", menu=appearance_menu)

        color_menu = tk.Menu(themes_menu, tearoff=0)
        for theme_name in THEMES.keys():
            color_menu.add_command(label=theme_name, command=lambda n=theme_name: self.set_theme(n))
        themes_menu.add_cascade(label="Color Theme", menu=color_menu)

        menubar.add_cascade(label="Themes", menu=themes_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About VisionVault", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)
        self.menubar = menubar

    def set_view_mode(self, mode: str):
        if mode not in ("list", "grid"):
            return
        if self.view_mode.get() == mode:
            return

        self.view_mode.set(mode)
        self._show_view(mode)
        self.refresh_list()

    def set_appearance_mode_menu(self, mode: str):
        if mode not in ("Dark", "Light", "System"):
            return

        ctk.set_appearance_mode(mode)

        try:
            self.split.configure(bg=self._paned_bg())
        except Exception:
            pass

        try:
            self.grid_canvas.configure(bg=self._paned_bg())
        except Exception:
            pass

        self.refresh_list()

    def show_about_dialog(self):
        messagebox.showinfo(
            "About VisionVault",
            "VisionVault\n\nOffline movie and TV inventory manager."
        )

    def toggle_theme(self):
        mode = ctk.get_appearance_mode()
        new_mode = "Light" if str(mode).lower() == "dark" else "Dark"
        ctk.set_appearance_mode(new_mode)

        # keep paned bg in sync
        try:
            self.split.configure(bg=self._paned_bg())
        except Exception:
            pass

        # keep grid canvas bg in sync
        try:
            self.grid_canvas.configure(bg=self._paned_bg())
        except Exception:
            pass


    def toggle_view(self):
        vm = self.view_mode.get()
        new_vm = "grid" if vm == "list" else "list"
        self.view_mode.set(new_vm)
        self._show_view(new_vm)
        self.refresh_list() # repopulate according to current mode

    # -------------------- Context Menu --------------------
    def _build_context_menu(self):
        self.ctx_menu = tk.Menu(self, tearoff=0)
        self.ctx_menu.add_command(label="Play", command=self._ctx_play)
        self.ctx_menu.add_command(label="Edit", command=self._ctx_edit)
        self.ctx_menu.add_command(label="Delete", command=self._ctx_delete)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Mark watched", command=self._ctx_mark_watched)
        self.ctx_menu.add_command(label="Copy file path", command=self._ctx_copy_file_path)
        self.ctx_menu.add_command(label="Convert to 3D (VisionDepth3D)", command=self._ctx_convert_to_3d)

        # Track which id was right-clicked (so we don't depend on previous selection)
        self._ctx_target_id = None

    def _ctx_set_target(self, mid: int | None):
        self._ctx_target_id = int(mid) if mid else None

        # Enable/disable items depending on what was clicked
        can_act = bool(self._ctx_target_id)
        try:
            state = "normal" if can_act else "disabled"
            self.ctx_menu.entryconfigure("Play", state=state)
            self.ctx_menu.entryconfigure("Edit", state=state)
            self.ctx_menu.entryconfigure("Delete", state=state)
            self.ctx_menu.entryconfigure("Mark watched", state=state)
            self.ctx_menu.entryconfigure("Copy file path", state=state)
            self.ctx_menu.entryconfigure("Convert to 3D (VisionDepth3D)", state=state)
        except Exception:
            pass

        # If we have a target, check if it has a playable path (movies/episodes)
        # Shows have no file path, but Play should "enter show" which you already support.
        if can_act:
            mt = self._get_media_type(self._ctx_target_id)
            if mt in ("movie", "episode"):
                fpath = self._get_file_path(self._ctx_target_id)
                playable = bool(fpath and os.path.exists(fpath))
                try:
                    self.ctx_menu.entryconfigure("Play", state=("normal" if playable else "disabled"))
                    self.ctx_menu.entryconfigure("Copy file path", state=("normal" if fpath else "disabled"))
                    self.ctx_menu.entryconfigure("Convert to 3D (VisionDepth3D)", state=("normal" if playable else "disabled"))
                except Exception:
                    pass
            else:
                try:
                    self.ctx_menu.entryconfigure("Convert to 3D (VisionDepth3D)", state="disabled")
                except Exception:
                    pass

    def _get_file_path(self, mid: int) -> Optional[str]:
        try:
            con = db()
            row = con.execute("SELECT file_path FROM movies WHERE id=?", (int(mid),)).fetchone()
            con.close()
            if row and row[0]:
                return str(row[0])
        except Exception:
            pass
        return None

    def _find_vd3d_executable(self) -> Optional[str]:
        candidates = [
            "VisionDepth3D.exe",
            os.path.join(os.getcwd(), "VisionDepth3D.exe"),
            os.path.join(os.getcwd(), "VisionDepth3D", "VisionDepth3D.exe"),
            os.path.join(os.path.dirname(sys.executable), "VisionDepth3D.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "VisionDepth3D.exe"),
        ]

        for path in candidates:
            try:
                if path and os.path.exists(path):
                    return os.path.abspath(path)
            except Exception:
                pass

        return None

    def _popup_context_menu(self, event):
        # display menu at cursor
        try:
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.ctx_menu.grab_release()
            except Exception:
                pass

    # ---- Context menu actions ----
    def _ctx_play(self):
        if not self._ctx_target_id:
            return
        self.selected_id = int(self._ctx_target_id)
        self.play_selected()

    def _ctx_edit(self):
        if not self._ctx_target_id:
            return
        self.selected_id = int(self._ctx_target_id)
        self.edit_selected()

    def _ctx_delete(self):
        if not self._ctx_target_id:
            return
        self.selected_id = int(self._ctx_target_id)
        self.delete_selected()

    def _ctx_mark_watched(self):
        if not self._ctx_target_id:
            return
        self.selected_id = int(self._ctx_target_id)
        self.mark_watched()

    def _ctx_copy_file_path(self):
        if not self._ctx_target_id:
            return
        fpath = self._get_file_path(int(self._ctx_target_id))
        if not fpath:
            self.set_status("No file path to copy.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(fpath)
            self.update()  # keeps clipboard after app loses focus
            self.set_status("Copied file path to clipboard.")
        except Exception as e:
            self.set_status(f"Clipboard error: {e}")

    # -------- UI actions --------
    def refresh_list(self):
        if self.view_mode.get() == "grid":
            # ensure correct pane visible
            self._show_view("grid")
            self.refresh_grid()
            # also refresh genre filter values
            genres = ["All"] + get_genres()
            self.genre_opt.configure(values=genres)
            return

        # list mode
        self._show_view("list")

        self.listbox.configure(state="normal")        # <- allow updates
        self.listbox.delete("1.0", "end")
        self.line_to_id = {}
        

        search_term = self.search_entry.get()
        filter_val  = self.filter_opt.get().lower()
        genre_val   = self.genre_opt.get()
        sort_key    = self._sort_key_from_label(self.sort_opt.get())

        rows = list_movies(
            filter_mode=filter_val,
            search_term=search_term,
            genre=genre_val,
            sort_key=sort_key,
            nav_mode=self.nav_mode,
            nav_show_id=self.nav_show_id
        )

        for idx, (mid, title, year, count, genres, fpath, media_type, show_id, season, episode) in enumerate(rows, start=1):
            file_mark = " • file" if fpath else ""
            if self.nav_mode == "show":
                # episode line format
                s = int(season or 0)
                e = int(episode or 0)
                se = f"S{s:02d}E{e:02d}" if (s or e) else ""
                prefix = (se + " - ") if se else ""
                self.listbox.insert("end", f"{idx}: {prefix}{title} - Watched {count}x{file_mark}\n")
            else:
                # root: movie or show
                if media_type == "show":
                    # show summary: watched episodes / total
                    w, t = self._show_progress(mid)
                    prog = f" • {w}/{t} watched" if t else ""
                    self.listbox.insert("end", f"{idx}: {title} [{genres}]{prog}\n")
                else:
                    self.listbox.insert("end", f"{idx}: {title} ({year}) [{genres}] - Watched {count}x{file_mark}\n")
            self.line_to_id[idx] = mid
            
        self._highlight_selected_id_in_list()
        self.listbox.configure(state="disabled", cursor="arrow")  # <- lock it again

        genres = ["All"] + get_genres()
        self.genre_opt.configure(values=genres)

        # show/hide Back button in list mode too (in case user switched views)
        if self.nav_mode == "show":
            try:
                self.back_btn.pack(side="left", padx=(0, 6))
            except Exception:
                pass
        else:
            try:
                self.back_btn.pack_forget()
            except Exception:
                pass


    def import_encoded_tv_folder(self):
        folder = filedialog.askdirectory(title="Select encoded TV folder")
        if not folder:
            return

        exts = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv"}
        files = []
        for fn in os.listdir(folder):
            p = os.path.join(folder, fn)
            if os.path.isfile(p) and os.path.splitext(fn)[1].lower() in exts:
                files.append(p)

        if not files:
            messagebox.showinfo("Import", "No video files found in that folder.")
            return

        imported = 0
        skipped = 0
        show_ids = {}  # cache show_title -> show_id

        for path in sorted(files, key=lambda x: os.path.basename(x).lower()):
            parsed = self.parse_encoded_episode_filename(path)
            if not parsed:
                skipped += 1
                continue

            show_title, season, episode, ep_title = parsed

            # create/find show row once
            if show_title not in show_ids:
                show_id = self._ensure_show_row(show_title)
                if not show_id:
                    skipped += 1
                    continue
                show_ids[show_title] = int(show_id)

            show_id = show_ids[show_title]

            minutes, res = ffprobe_info(path)

            values = {
                "title": ep_title,   # ✅ use filename episode title
                "year": None,
                "genres": "",
                "overview": "",
                "poster_path": None,
                "file_path": path,
                "runtime_minutes": minutes,
                "resolution": res,
                "media_type": "episode",
                "show_id": int(show_id),
                "season": int(season),
                "episode": int(episode),
            }

            upsert_movie(values)
            imported += 1

        self.refresh_list()
        self.refresh_stats()
        self.set_status(f"Imported {imported} episodes. Skipped {skipped}.")
        messagebox.showinfo("Import done", f"Imported {imported} episodes.\nSkipped {skipped}.")


    def select_movie(self, event=None):
        try:
            if event is not None:
                idx = self.listbox.index(f"@{event.x},{event.y}")
            else:
                idx = self.listbox.index("insert")
            line_no = int(str(idx).split(".")[0])
        except Exception:
            return

        mid = self.line_to_id.get(line_no)
        if not mid:
            return

        self._highlight_list_line(line_no)

        mt = self._get_media_type(mid)

        if self.nav_mode == "root" and mt == "show":
            self.enter_show(mid)
            self.focus_set()
            return

        self._load_details(mid)
        self.focus_set()

    def _on_list_right_click(self, event):
        # Determine which line was right-clicked
        try:
            idx = self.listbox.index(f"@{event.x},{event.y}")
            line_no = int(str(idx).split(".")[0])
        except Exception:
            self._ctx_set_target(None)
            self._popup_context_menu(event)
            return

        mid = self.line_to_id.get(line_no)
        if not mid:
            self._ctx_set_target(None)
            self._popup_context_menu(event)
            return

        # Select it (so the UI details match the user's click)
        self._highlight_list_line(line_no)

        mt = self._get_media_type(mid)
        if self.nav_mode == "root" and mt == "show":
            # Don’t auto-enter show on right-click, just select it
            self.selected_id = mid
        else:
            self._load_details(mid)

        self._ctx_set_target(mid)
        self._popup_context_menu(event)

    def add_by_title(self):
        title = (self.add_title_entry.get() or "").strip()
        if not title:
            self.set_status("Enter a title first.")
            return

        # If we are inside a show, "Add" means add an episode to that show
        if self.nav_mode == "show" and self.nav_show_id:
            season = simpledialog.askinteger("Season", "Season number?", parent=self, minvalue=1, maxvalue=999)
            if season is None:
                self.set_status("Add canceled.")
                return
            episode = simpledialog.askinteger("Episode", "Episode number?", parent=self, minvalue=1, maxvalue=9999)
            if episode is None:
                self.set_status("Add canceled.")
                return

            values = {
                "title": title,
                "year": None,
                "genres": "",
                "overview": "",
                "poster_path": None,
                "file_path": None,
                "runtime_minutes": None,
                "resolution": None,
                "media_type": "episode",
                "show_id": int(self.nav_show_id),
                "season": int(season),
                "episode": int(episode),
            }

            dlg = EditDialog(self, values)
            self.wait_window(dlg)

            if dlg.saved:
                # keep episode linkage even if dialog does not expose these fields
                dlg.values["media_type"] = "episode"
                dlg.values["show_id"] = int(self.nav_show_id)
                dlg.values["season"] = int(season)
                dlg.values["episode"] = int(episode)

                upsert_movie(dlg.values)
                self._maybe_set_show_poster_from_episode(int(self.nav_show_id), dlg.values.get("poster_path"))
                self.add_title_entry.delete(0, "end")
                self.refresh_list()
                self.refresh_stats()
                self.set_status("Added episode.")

            else:
                self.set_status("Add canceled.")
            return

        # Root mode: ask if this is a movie or a show entry
        choice = messagebox.askyesnocancel(
            "Add item",
            "Add this as a Show?\n\nYes = Show\nNo = Movie\nCancel = abort"
        )
        if choice is None:
            self.set_status("Add canceled.")
            return

        media_type = "show" if choice else "movie"

        values = {
            "title": title,
            "year": None,
            "genres": "",
            "overview": "",
            "poster_path": None,
            "file_path": None,
            "runtime_minutes": None,
            "resolution": None,
            "media_type": media_type,
            "show_id": None,
            "season": None,
            "episode": None,
        }

        dlg = EditDialog(self, values)
        self.wait_window(dlg)

        if dlg.saved:
            dlg.values["media_type"] = media_type
            dlg.values["show_id"] = None
            dlg.values["season"] = None
            dlg.values["episode"] = None

            upsert_movie(dlg.values)
            self.add_title_entry.delete(0, "end")
            self.refresh_list()
            self.refresh_stats()
            self.set_status(f"Added {media_type}.")
        else:
            self.set_status("Add canceled.")

    def add_by_file(self):
        filetypes = [("Video files","*.mp4 *.mkv *.avi *.mov *.m4v *.wmv"), ("All files","*.*")]
        path = filedialog.askopenfilename(title="Select Video File", filetypes=filetypes)
        if not path:
            return

        minutes, res = ffprobe_info(path)

        ep = self._parse_episode_tag(path)
        if ep:
            season, episode, show_guess = ep
            add_as_ep = messagebox.askyesno(
                "TV Episode detected",
                f"Detected episode tag in filename:\nS{season:02d}E{episode:02d}\n\nAdd as TV episode?"
            )
            if add_as_ep:
                if not show_guess:
                    show_guess = simpledialog.askstring("Show Title", "Show title?", parent=self) or ""
                    show_guess = show_guess.strip()

                show_id = self._ensure_show_row(show_guess)
                if not show_id:
                    self.set_status("Could not create or find show.")
                    return

                # default episode title: keep guessed title, user can edit in dialog
                guess_title, guess_year = guess_title_year_from_filename(path)

                values = {
                    "title": guess_title or f"Episode {episode}",
                    "year": guess_year,
                    "genres": "",
                    "overview": "",
                    "poster_path": None,
                    "file_path": path,
                    "runtime_minutes": minutes,
                    "resolution": res,
                    "media_type": "episode",
                    "show_id": int(show_id),
                    "season": int(season),
                    "episode": int(episode),
                }

                dlg = EditDialog(self, values)
                self.wait_window(dlg)

                if not dlg.saved:
                    self.set_status("Add canceled.")
                    return

                # keep linkage even if dialog does not expose these fields
                dlg.values["media_type"] = "episode"
                dlg.values["show_id"] = int(show_id)
                dlg.values["season"] = int(season)
                dlg.values["episode"] = int(episode)

                upsert_movie(dlg.values)
                self._maybe_set_show_poster_from_episode(int(show_id), dlg.values.get("poster_path"))
                self._maybe_fill_episode_posters_from_show(int(show_id), dlg.values.get("poster_path"))
                self.refresh_list()
                self.refresh_stats()
                self.set_status("Added TV episode from file.")
                return

        # Otherwise, treat as a movie file
        guess_title, guess_year = guess_title_year_from_filename(path)
        values = {
            "title": guess_title or "",
            "year": guess_year,
            "genres": "",
            "overview": "",
            "poster_path": None,
            "file_path": path,
            "runtime_minutes": minutes,
            "resolution": res,
            "media_type": "movie",
            "show_id": None,
            "season": None,
            "episode": None,
        }

        dlg = EditDialog(self, values)
        self.wait_window(dlg)

        if not dlg.saved:
            self.set_status("Add canceled.")
            return

        dlg.values["media_type"] = "movie"
        dlg.values["show_id"] = None
        dlg.values["season"] = None
        dlg.values["episode"] = None

        upsert_movie(dlg.values)
        self.refresh_list()
        self.refresh_stats()
        self.set_status("Added movie from file.")

    def edit_selected(self):
        if not self.selected_id:
            return

        con = db()
        row = con.execute("""
            SELECT title,year,genres,overview,poster_path,
                   file_path,runtime_minutes,resolution,
                   media_type,show_id,season,episode
            FROM movies WHERE id=?
        """, (self.selected_id,)).fetchone()
        con.close()

        values = {
            "title": row[0],
            "year": row[1],
            "genres": row[2],
            "overview": row[3],
            "poster_path": row[4],
            "file_path": row[5],
            "runtime_minutes": row[6],
            "resolution": row[7],
            "media_type": row[8],
            "show_id": row[9],
            "season": row[10],
            "episode": row[11],
        }

        dlg = EditDialog(self, values)
        self.wait_window(dlg)

        if not dlg.saved:
            self.set_status("Edit canceled.")
            return

        dlg.values["id"] = self.selected_id
        upsert_movie(dlg.values)

        if values.get("media_type") == "episode":
            show_id = int(values.get("show_id") or 0)
            poster_path = dlg.values.get("poster_path")

            self._maybe_set_show_poster_from_episode(show_id, poster_path)
            self._maybe_fill_episode_posters_from_show(show_id, poster_path)

        self.refresh_list()
        self.refresh_stats()
        self.set_status("Saved changes.")

    def mark_watched(self):
        if self.selected_id:
            increment_watch(self.selected_id)
            self.refresh_list(); self.refresh_stats()
            self.set_status("Marked as watched.")

    def play_selected(self):
        if not self.selected_id:
            return

        con = db()
        row = con.execute("SELECT file_path, media_type FROM movies WHERE id=?", (self.selected_id,)).fetchone()
        con.close()
        if not row:
            return

        fpath, mt = row[0], (row[1] or "movie")

        # If user hits Play on a show entry, treat it like open
        if mt == "show" and self.nav_mode == "root":
            self.enter_show(self.selected_id)
            return

        if not fpath or not os.path.exists(fpath):
            self.set_status("No valid file path on this item.")
            return

        path = fpath

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(
                    f'start "" "{path}"',
                    shell=True
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

            increment_watch(self.selected_id)
            self.refresh_list()
            self.refresh_stats()
            self.set_status("Played and marked as watched.")

        except Exception as e:
            self.set_status(f"Could not open file: {e}")

    def refresh_stats(self):
        s = get_stats()

        self.lbl_totals.configure(
            text=(
                f"Movies: {s['movies_total']}\n"
                f"Movies watched at least once: {s['movies_watched']}\n"
                f"Movies unwatched: {s['movies_unwatched']}\n"
                f"Movie watch count total: {s['movies_watch_total']}\n\n"
                f"TV shows: {s['shows_total']}\n"
                f"Episodes: {s['episodes_total']}\n"
                f"Episodes watched at least once: {s['episodes_watched']}\n"
                f"Episodes unwatched: {s['episodes_unwatched']}\n"
                f"Episode watch count total: {s['episodes_watch_total']}"
            )
        )

        # Left column: top watched movies and top watched episodes
        self.col_top.delete("1.0", "end")
        self.col_top.insert("end", "Top watched movies\n\n")
        if s["top_movies"]:
            for title, count in s["top_movies"]:
                self.col_top.insert("end", f"{count}x  {title}\n")
        else:
            self.col_top.insert("end", "No movie watch data yet\n")

        self.col_top.insert("end", "\nTop watched episodes\n\n")
        if s["top_episodes"]:
            for show_title, season, episode, ep_title, count in s["top_episodes"]:
                se = ""
                if season is not None and episode is not None:
                    se = f"S{int(season):02d}E{int(episode):02d} "
                self.col_top.insert("end", f"{count}x  {show_title}  {se}{ep_title}\n")
        else:
            self.col_top.insert("end", "No episode watch data yet\n")

        # Middle column: genres (movies only)
        self.col_genres.delete("1.0", "end")
        self.col_genres.insert("end", "Top genres (movies)\n\n")
        if s["top_genres"]:
            for g, n in s["top_genres"]:
                self.col_genres.insert("end", f"{g}: {n}\n")
        else:
            self.col_genres.insert("end", "No genre data yet\n")

        # Right column: recently added (all)
        self.col_recent.delete("1.0", "end")
        self.col_recent.insert("end", "Recently added\n\n")
        if s["recent"]:
            for media_type, title, year, added, show_title, season, episode in s["recent"]:
                if media_type == "episode":
                    se = ""
                    if season is not None and episode is not None:
                        se = f"S{int(season):02d}E{int(episode):02d}"
                    st = show_title or "Unknown Show"
                    self.col_recent.insert("end", f"{st}  {se}  {title}  •  {added}\n")
                elif media_type == "show":
                    self.col_recent.insert("end", f"{title} (Show)  •  {added}\n")
                else:
                    y = f" ({year})" if year else ""
                    self.col_recent.insert("end", f"{title}{y}  •  {added}\n")
        else:
            self.col_recent.insert("end", "No recent items\n")

    def refresh_grid(self):
        # keep grid for root only. If inside show, we auto-list mode anyway.
        if self.nav_mode == "show":
            self.view_mode.set("list")
            self._show_view("list")
            self.refresh_list()
            return
            
        # clear previous tiles
        for child in self.grid_inner.winfo_children():
            child.destroy()

        search_term = self.search_entry.get()
        filter_val  = self.filter_opt.get().lower()
        genre_val   = self.genre_opt.get()
        sort_key    = self._sort_key_from_label(self.sort_opt.get())

        rows = list_movies(
            filter_mode=filter_val,
            search_term=search_term,
            genre=genre_val,
            sort_key=sort_key,
            nav_mode=self.nav_mode,
            nav_show_id=self.nav_show_id
        )

        # layout parameters (bigger posters)
        COLS = 3
        self.grid_cols = COLS
        PADX, PADY = 5, 7
        TILE_W, TILE_H = 185, 275

        self.grid_ids = []
        self.grid_tile_frames = {}

        # keep references so images aren’t GC’d
        if not hasattr(self, "_tile_buttons"):
            self._tile_buttons = []
        self._tile_buttons.clear()

        for idx, (mid, title, year, count, genres, fpath, media_type, show_id, season, episode) in enumerate(rows):
            r = idx // COLS
            c = idx % COLS

            poster_path = None
            try:
                con = db()
                pp = con.execute("SELECT poster_path FROM movies WHERE id=?", (mid,)).fetchone()
                con.close()
                poster_path = pp[0] if pp else None
            except Exception:
                poster_path = None

            img = self._load_tile_image(poster_path, max_w=TILE_W, max_h=TILE_H)

            TEXT_H = 44  # space for 2-ish lines
            OUTER_W = TILE_W + 14
            OUTER_H = TILE_H + TEXT_H + 14

            colors = self._grid_tile_colors()

            tile_frame = ctk.CTkFrame(
                self.grid_inner,
                width=OUTER_W,
                height=OUTER_H,
                fg_color=colors["normal_fg"],
                border_width=0,
                border_color=colors["normal_border"]
            )
            tile_frame.grid(row=r, column=c, padx=PADX, pady=PADY, sticky="n")
            tile_frame.grid_propagate(False)

            # image-only button
            img_btn = ctk.CTkButton(
                tile_frame,
                image=img,
                text="",
                width=TILE_W,
                height=TILE_H,
                fg_color="transparent",
                hover_color=self._theme()["accent_hover"],
                command=partial(self.select_by_id, mid)
            )
            img_btn.pack(padx=7, pady=(7, 4))

            # label text (wrapped/clamped, cannot change frame width)
            base = f"{title} ({year})" if year else f"{title}"
            label_text = self._clamp_lines(base, max_chars_per_line=28, max_lines=2)

            if media_type == "show":
                w, t = self._show_progress(mid)
                if t:
                    label_text = self._clamp_lines(title, 28, 2) + f"\n{w}/{t} watched"

            lbl = ctk.CTkLabel(
                tile_frame,
                text=label_text,
                justify="center",
                wraplength=TILE_W
            )
            lbl.pack(padx=8, pady=(0, 7))

            # hover effect across full tile
            self._bind_tile_hover(tile_frame, mid)
            self._bind_tile_hover(img_btn, mid)
            self._bind_tile_hover(lbl, mid)

            # right-click context menu (bind all so it works anywhere on the tile)
            img_btn.bind("<Button-3>", lambda e, m=mid: self._on_grid_right_click(e, m))
            img_btn.bind("<Control-Button-1>", lambda e, m=mid: self._on_grid_right_click(e, m))
            lbl.bind("<Button-3>", lambda e, m=mid: self._on_grid_right_click(e, m))
            lbl.bind("<Control-Button-1>", lambda e, m=mid: self._on_grid_right_click(e, m))
            tile_frame.bind("<Button-3>", lambda e, m=mid: self._on_grid_right_click(e, m))
            tile_frame.bind("<Control-Button-1>", lambda e, m=mid: self._on_grid_right_click(e, m))

            # keep references (not strictly needed for frame/label, but fine to track)
            self._tile_buttons.append(img_btn)
            self.grid_ids.append(mid)
            self.grid_tile_frames[mid] = tile_frame
            
        # update scrollregion
        self.grid_inner.update_idletasks()
        self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        self._highlight_selected_grid_tile()

        if self.selected_id in self.grid_ids:
            self.after(10, self._ensure_selected_tile_visible_smooth)

    def _sort_key_from_label(self, label):
        return {
            "Title A→Z": "title_asc",
            "Title Z→A": "title_desc",
            "Year ↑": "year_asc",
            "Year ↓": "year_desc",
            "Watched ↑": "watched_asc",
            "Watched ↓": "watched_desc",
            "Recently added": "added_desc",
            "Oldest added": "added_asc",
        }.get(label, "title_asc")

    def _show_view(self, mode: str):
        if mode == "grid":
            self.listbox.pack_forget()
            self.grid_scroll.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        else:
            self.grid_scroll.pack_forget()
            self.listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)


    def delete_selected(self):
        if not self.selected_id:
            return

        mid = int(self.selected_id)
        mt = self._get_media_type(mid)

        # ---- SHOW: only delete if empty ----
        if mt == "show":
            try:
                con = db()
                total = con.execute(
                    "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND show_id=?",
                    (mid,)
                ).fetchone()[0]
                con.close()
            except Exception:
                total = 0

            if int(total) > 0:
                messagebox.showinfo(
                    "Show not empty",
                    "This show still has episodes. Delete the episodes first, and the show will disappear when empty."
                )
                return

            confirm = messagebox.askyesno("Delete Show", "Delete this empty show entry from your library?")
            if not confirm:
                return

            delete_movie(mid)

        # ---- EPISODE: delete, then cleanup empty show ----
        elif mt == "episode":
            # get show_id before deleting episode
            try:
                con = db()
                row = con.execute("SELECT show_id FROM movies WHERE id=?", (mid,)).fetchone()
                con.close()
                show_id = int(row[0]) if row and row[0] else None
            except Exception:
                show_id = None

            confirm = messagebox.askyesno("Delete Episode", "Delete this episode entry?")
            if not confirm:
                return

            delete_movie(mid)

            # if that was the last episode, remove the show row too
            if show_id:
                try:
                    self._maybe_delete_orphan_show(show_id)
                except Exception:
                    pass

        # ---- MOVIE ----
        else:
            confirm = messagebox.askyesno("Delete Movie", "Are you sure you want to delete this movie from your library?")
            if not confirm:
                return
            delete_movie(mid)

        # ---- UI refresh / clear ----
        self.selected_id = None
        self.refresh_list()
        self.refresh_stats()
        self.set_status("Deleted.")

        try:
            self.desc_box.configure(state="normal")
            self.desc_box.delete("1.0", "end")
            self.desc_box.configure(state="disabled")
        except Exception:
            pass

        try:
            self.poster_label.configure(image=self._blank_img, text="No poster")
        except Exception:
            pass

    def on_close(self):
        # make sure geometry is up to date
        self.update_idletasks()

        settings = getattr(self, "settings", {}) or {}

        # window size and position, e.g. "1200x850+100+100"
        settings["window_geometry"] = self.geometry()

        # sash position (x coordinate)
        try:
            x, y = self.split.sash_coord(0)
            settings["split_sash_x"] = int(x)
        except Exception:
            pass

        # optional: remember current view mode (list/grid)
        try:
            settings["view_mode"] = self.view_mode.get()
        except Exception:
            pass
            
        # remember last selected movie
        try:
            settings["last_selected_id"] = int(self.selected_id) if self.selected_id else None
        except Exception:
            settings["last_selected_id"] = None
            
        # remember theme (Dark / Light / System)
        try:
            settings["appearance_mode"] = str(ctk.get_appearance_mode())
        except Exception:
            pass

        try:
            settings["nav_mode"] = self.nav_mode
            settings["nav_show_id"] = self.nav_show_id
        except Exception:
            pass

        try:
            settings["theme_name"] = self.current_theme_name
        except Exception:
            pass

        save_settings(settings)
        self.destroy()

    # --- TV helpers ---
    def _show_progress(self, show_id: int) -> Tuple[int, int]:
        try:
            con = db()
            total = con.execute(
                "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND show_id=?",
                (int(show_id),)
            ).fetchone()[0]
            watched = con.execute(
                "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND show_id=? AND watch_count>0",
                (int(show_id),)
            ).fetchone()[0]
            con.close()
            return int(watched), int(total)
        except Exception:
            return (0, 0)

    def _maybe_set_show_poster_from_episode(self, show_id: int, episode_poster: str | None):
        if not show_id or not episode_poster or not os.path.exists(episode_poster):
            return
        try:
            con = db()
            cur = con.cursor()

            # only set it if the show currently has no poster
            row = cur.execute(
                "SELECT poster_path FROM movies WHERE id=? AND media_type='show'",
                (int(show_id),)
            ).fetchone()

            cur_poster = (row[0] if row else None)
            if cur_poster and os.path.exists(cur_poster):
                con.close()
                return

            cur.execute(
                "UPDATE movies SET poster_path=? WHERE id=? AND media_type='show'",
                (episode_poster, int(show_id))
            )
            con.commit()
            con.close()
        except Exception:
            pass

    def _maybe_fill_episode_posters_from_show(self, show_id: int, poster_path: str | None):
        """
        Fill missing episode posters for a show using the provided poster.
        Does NOT overwrite episodes that already have their own poster.
        """
        if not show_id or not poster_path or not os.path.exists(poster_path):
            return

        try:
            con = db()
            cur = con.cursor()

            cur.execute(
                """
                UPDATE movies
                SET poster_path=?
                WHERE media_type='episode'
                  AND show_id=?
                  AND (poster_path IS NULL OR TRIM(poster_path)='')
                """,
                (poster_path, int(show_id))
            )

            con.commit()
            con.close()
        except Exception:
            pass

# -------------------- main --------------------
if __name__ == "__main__":
    init_db()
    app = MovieApp()
    app.mainloop()