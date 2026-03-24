import sqlite3
import os
import re
import subprocess
import sys
import json
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple
import socket
import webbrowser
import requests
from PIL import Image


def app_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_base()
DB = str(BASE_DIR / "movies.db")
POSTERS = BASE_DIR / "posters"
POSTERS.mkdir(exist_ok=True)
SETTINGS_FILE = BASE_DIR / "movie_inventory_settings.json"


# -------------------- paths --------------------
def resolve_existing_path(path_value: str | None) -> str | None:
    if not path_value:
        return None

    p = Path(path_value)

    if p.is_absolute() and p.exists():
        return str(p)

    candidate = POSTERS / p.name
    if candidate.exists():
        return str(candidate)

    candidate = BASE_DIR / p
    if candidate.exists():
        return str(candidate)

    candidate = BASE_DIR / "posters" / p.name
    if candidate.exists():
        return str(candidate)

    return None


# -------------------- settings --------------------
def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# -------------------- DB helpers --------------------

def get_resume_position(item_id: int) -> float:
    con = db()
    row = con.execute(
        "SELECT COALESCE(resume_seconds, 0) FROM movies WHERE id=?",
        (item_id,)
    ).fetchone()
    con.close()
    if not row:
        return 0.0
    return float(row[0] or 0.0)


def save_resume_position(item_id: int, seconds: float) -> None:
    seconds = max(0.0, float(seconds or 0.0))
    con = db()
    con.execute(
        """
        UPDATE movies
        SET resume_seconds=?,
            last_position_seconds=?
        WHERE id=?
        """,
        (seconds, seconds, item_id)
    )
    con.commit()
    con.close()


def clear_resume_position(item_id: int) -> None:
    con = db()
    con.execute(
        """
        UPDATE movies
        SET resume_seconds=0,
            last_position_seconds=0
        WHERE id=?
        """,
        (item_id,)
    )
    con.commit()
    con.close()

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con
    
def init_db():
    con = db()
    con.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY,
        tmdb_id INTEGER,
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

    for col_def in [
        ("added_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("file_path", "TEXT"),
        ("runtime_minutes", "INTEGER"),
        ("resolution", "TEXT"),
        ("tmdb_id", "INTEGER"),
        ("media_type", "TEXT DEFAULT 'movie'"),
        ("show_id", "INTEGER"),
        ("season", "INTEGER"),
        ("episode", "INTEGER"),
        ("resume_seconds", "REAL DEFAULT 0"),
        ("last_position_seconds", "REAL DEFAULT 0"),
    ]:
        try:
            con.execute(f"ALTER TABLE movies ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_movies_media_type ON movies(media_type)")
    except Exception:
        pass

    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_movies_show_se_ep ON movies(show_id, season, episode)")
    except Exception:
        pass

    try:
        con.execute("UPDATE movies SET media_type='movie' WHERE media_type IS NULL OR media_type=''")
    except Exception:
        pass

    con.execute("UPDATE movies SET added_at = COALESCE(added_at, CURRENT_TIMESTAMP)")
    con.commit()
    con.close()


def delete_movie(movie_id: int):
    con = db()
    con.execute("DELETE FROM movies WHERE id=?", (movie_id,))
    con.commit()
    con.close()


def increment_watch(movie_id: int):
    con = db()
    con.execute("UPDATE movies SET watch_count = watch_count + 1 WHERE id=?", (movie_id,))
    con.commit()
    con.close()


def upsert_movie(values: dict) -> int:
    con = db()
    cur = con.cursor()

    row = None
    movie_id = values.get("id")

    if movie_id is not None:
        row = cur.execute("SELECT id FROM movies WHERE id=?", (movie_id,)).fetchone()

    if row is None and values.get("file_path"):
        row = cur.execute(
            "SELECT id FROM movies WHERE file_path=?",
            (values["file_path"],)
        ).fetchone()

    if row is None and values.get("title") and values.get("year"):
        row = cur.execute(
            "SELECT id FROM movies WHERE title=? AND year=?",
            (values["title"], values["year"])
        ).fetchone()

    if row is not None:
        movie_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
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
    return int(movie_id)


# -------------------- reads --------------------
def get_item(movie_id: int) -> Optional[dict]:
    con = db()
    row = con.execute("""
        SELECT id, title, year, genres, overview, poster_path, watch_count,
               added_at, file_path, runtime_minutes, resolution,
               media_type, show_id, season, episode,
               resume_seconds, last_position_seconds
        FROM movies
        WHERE id=?
    """, (movie_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def get_show_progress(show_id: int) -> Tuple[int, int]:
    con = db()
    total = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND show_id=?",
        (show_id,)
    ).fetchone()[0]
    watched = con.execute(
        "SELECT COUNT(*) FROM movies WHERE media_type='episode' AND show_id=? AND watch_count>0",
        (show_id,)
    ).fetchone()[0]
    con.close()
    return int(watched), int(total)


def list_movies(
    filter_mode: str = "all",
    search_term: str = "",
    genre: str = "All",
    sort_key: str = "title_asc",
    nav_mode: str = "root",
    nav_show_id: Optional[int] = None,
):
    con = db()

    base = """
        SELECT id, title, year, watch_count, genres, file_path,
               media_type, show_id, season, episode, poster_path
        FROM movies
    """
    clauses = []
    params = []

    if nav_mode == "show":
        clauses.append("media_type='episode'")
        clauses.append("show_id=?")
        params.append(int(nav_show_id or 0))
    else:
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
        "title_asc": "title COLLATE NOCASE ASC",
        "title_desc": "title COLLATE NOCASE DESC",
        "year_asc": "COALESCE(year, 9999) ASC, title COLLATE NOCASE ASC",
        "year_desc": "COALESCE(year, 0) DESC, title COLLATE NOCASE ASC",
        "watched_asc": "watch_count ASC, title COLLATE NOCASE ASC",
        "watched_desc": "watch_count DESC, title COLLATE NOCASE ASC",
        "added_desc": "datetime(added_at) DESC",
        "added_asc": "datetime(added_at) ASC",
    }

    if nav_mode == "show":
        base += " ORDER BY COALESCE(season, 0) ASC, COALESCE(episode, 0) ASC, title COLLATE NOCASE ASC"
    else:
        base += f" ORDER BY {order_map.get(sort_key, 'title COLLATE NOCASE ASC')}"

    rows = con.execute(base, params).fetchall()
    con.close()

    out = []
    for row in rows:
        item = dict(row)
        if item["media_type"] == "show":
            watched, total = get_show_progress(item["id"])
            item["episode_progress"] = {"watched": watched, "total": total}
        out.append(item)

    return out

def list_show_episodes(show_id: int):
    return list_movies(nav_mode="show", nav_show_id=show_id)


def get_genres():
    con = db()
    rows = con.execute("SELECT DISTINCT genres FROM movies").fetchall()
    con.close()

    genres = set()
    for r in rows:
        gstr = r[0]
        if gstr:
            for g in gstr.split(","):
                g = g.strip()
                if g:
                    genres.add(g)
    return sorted(genres)


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
    for row in rows:
        gstr = row[0]
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

        "top_movies": [tuple(r) for r in top_movies],
        "top_episodes": [tuple(r) for r in top_episodes],
        "recent": [tuple(r) for r in recent],
        "top_genres": top_genres,
    }

# -------------------- filename parsing --------------------
COMMON_TAGS = [
    r"\b\d{3,4}p\b", r"\b4k\b", r"\b8k\b", r"\buhd\b", r"\bhdr10(\+)?\b", r"\bdv\b",
    r"\bblu[- ]?ray\b", r"\bbrrip\b", r"\bwebrip\b", r"\bweb[- ]?dl\b", r"\bdvdrip\b",
    r"\bh264\b", r"\bh265\b", r"\bhevc\b", r"\bx264\b", r"\bx265\b",
    r"\bac3\b", r"\bdts\b", r"\batmos\b", r"\bremux\b", r"\bproper\b", r"\brepack\b",
    r"\bextended\b", r"\bdirectors[’']? cut\b", r"\bs0?\d{1,2}e\d{1,3}\b",
]


def guess_title_year_from_filename(path: str):
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


def parse_encoded_episode_filename(path: str):
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

    if not ep_title:
        ep_title = f"S{season:02d}E{episode:02d}"

    return show_title, season, episode, ep_title


def parse_episode_tag(path: str) -> Optional[Tuple[int, int, str]]:
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


def ensure_show_row(show_title: str, year: Optional[int] = None) -> Optional[int]:
    show_title = (show_title or "").strip()
    if not show_title:
        return None

    con = db()
    row = con.execute(
        "SELECT id FROM movies WHERE media_type='show' AND title=?",
        (show_title,)
    ).fetchone()
    con.close()

    if row:
        return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])

    return upsert_movie({
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
    })

_tv_server_process = None


def get_local_ip() -> str:
    """
    Best-effort LAN IP for showing the TV access URL.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_tv_mode_url(port: int = 5050) -> str:
    return f"http://{get_local_ip()}:{port}"


def _web_entry_path() -> Path:
    """
    Where visionvault_web.py lives beside the desktop app/core.
    """
    return BASE_DIR / "visionvault_web.py"


def is_tv_mode_running() -> bool:
    global _tv_server_process
    return _tv_server_process is not None and _tv_server_process.poll() is None


def start_tv_mode(port: int = 5050) -> tuple[bool, str]:
    """
    Launch the TV web server as a subprocess.
    """
    global _tv_server_process

    if is_tv_mode_running():
        return True, f"TV Mode already running at {get_tv_mode_url(port)}"

    web_script = _web_entry_path()
    if not web_script.exists():
        return False, f"Could not find {web_script.name}"

    try:
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NO_WINDOW

        _tv_server_process = subprocess.Popen(
            [sys.executable, str(web_script)],
            cwd=str(BASE_DIR),
            creationflags=creationflags
        )

        return True, f"TV Mode started at {get_tv_mode_url(port)}"
    except Exception as e:
        _tv_server_process = None
        return False, f"Could not start TV Mode: {e}"


def stop_tv_mode() -> tuple[bool, str]:
    """
    Stop the TV web server if running.
    """
    global _tv_server_process

    if not is_tv_mode_running():
        _tv_server_process = None
        return False, "TV Mode is not running."

    try:
        _tv_server_process.terminate()
        _tv_server_process.wait(timeout=5)
        _tv_server_process = None
        return True, "TV Mode stopped."
    except Exception as e:
        try:
            _tv_server_process.kill()
        except Exception:
            pass
        _tv_server_process = None
        return False, f"Forced stop after error: {e}"


def open_tv_mode_in_browser(port: int = 5050) -> tuple[bool, str]:
    url = get_tv_mode_url(port)
    try:
        webbrowser.open(url)
        return True, url
    except Exception as e:
        return False, f"Could not open browser: {e}"


# -------------------- ffprobe --------------------
def ffprobe_info(path: str):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.STDOUT, text=True, timeout=10
        ).strip()
        dur_s = float(out) if out else None
        minutes = int(round(dur_s / 60.0)) if dur_s else None
    except Exception:
        minutes = None

    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", path],
            stderr=subprocess.STDOUT, text=True, timeout=10
        ).strip()
        if out and "," in out:
            w, h = out.split(",", 1)
            res = f"{w}x{h}"
        else:
            res = None
    except Exception:
        res = None

    return minutes, res


# -------------------- playback --------------------
def play_item(movie_id: int) -> tuple[bool, str]:
    item = get_item(movie_id)
    if not item:
        return False, "Item not found"

    fpath = item.get("file_path")
    media_type = item.get("media_type") or "movie"

    if media_type == "show":
        return False, "Shows do not have direct file playback"

    if not fpath or not os.path.exists(fpath):
        return False, "No valid file path"

    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(f'start "" "{fpath}"', shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", fpath])
        else:
            subprocess.Popen(["xdg-open", fpath])

        increment_watch(movie_id)
        return True, "Playback launched"
    except Exception as e:
        return False, f"Could not launch playback: {e}"
