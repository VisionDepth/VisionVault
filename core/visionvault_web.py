from pathlib import Path
from datetime import datetime
import json
import mimetypes
import os
import sys
import random
import threading

import ssl
from flask import (
    Flask, abort, jsonify, redirect, render_template_string,
    request, send_file, url_for, Response, stream_with_context,
    make_response
)
from werkzeug.serving import make_server

def bundle_base() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def brand_logo_path() -> Path | None:
    candidates = [
        bundle_base() / "visionvault_logo.png",
        bundle_base() / "logo.png",
        bundle_base().parent / "visionvault_logo.png",
        bundle_base().parent / "logo.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None

from core.vault_core import (
    POSTERS,
    get_item,
    get_show_progress,
    get_stats,
    increment_watch,
    init_db,
    list_movies,
    list_show_episodes,
    play_item,
    resolve_existing_path,
    get_resume_position,
    save_resume_position,
    clear_resume_position,
    touch_last_watched,
)

app = Flask(__name__)

def api_base_url() -> str:
    return request.host_url.rstrip("/")


def absolute_url(path: str) -> str:
    return f"{api_base_url()}{path}"

def start_tv_server_thread_https(host="0.0.0.0", port=5051):
    """Start HTTPS server for DeoVR and other VR browsers"""
    global _server, _server_thread
    
    cert_file = "server.crt"
    key_file = "server.key"
    
    # Generate self-signed certs if they don't exist
    if not Path(cert_file).exists() or not Path(key_file).exists():
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        
        # Generate key
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        
        # Generate cert
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"visionvault.local")
        ])
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(u"visionvault.local"),
                x509.DNSName(u"localhost"),
            ]),
            critical=False,
        ).sign(key, hashes.SHA256())
        
        # Write files
        with open(key_file, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    try:
        # FIX: Use (host, port) tuple correctly - make_server expects host as string, not tuple
        # The ssl_context parameter expects a tuple of (cert_file, key_file)
        _server = make_server(
            host,           # string like "0.0.0.0" - this is fine
            port,           # int
            app,
            threaded=True,
            ssl_context=(cert_file, key_file)
        )
        _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _server_thread.start()
        return True, f"HTTPS TV server started on {host}:{port}"
    except Exception as e:
        return False, f"Could not start HTTPS server: {e}"

def can_play_item(item: dict) -> bool:
    if not item:
        return False
    if item.get("media_type") == "show":
        return False
    file_path = resolve_existing_path(item.get("file_path"))
    return bool(file_path and Path(file_path).exists())


def serialize_item(item: dict) -> dict:
    if not item:
        return {}

    item_id = int(item["id"])
    media_type = item.get("media_type") or "movie"
    poster_url = absolute_url(url_for("poster_for_item", item_id=item_id))
    animated_poster_url = absolute_url(url_for("animated_poster_for_item", item_id=item_id))
    detail_url = absolute_url(url_for("api_item", item_id=item_id))

    can_play = can_play_item(item)

    if can_play:
        stream_url = absolute_url(url_for("stream_item", item_id=item_id))
    else:
        stream_url = None

    subtitle_url = None
    if can_play:
        subtitle_path = find_subtitle_file_for_video(item.get("file_path"))
        if subtitle_path:
            subtitle_url = absolute_url(url_for("subtitles_route", item_id=item_id))

    out = {
        "id": item_id,
        "title": item.get("title"),
        "year": item.get("year"),
        "genres": item.get("genres") or "",
        "overview": item.get("overview") or "",
        "poster_url": poster_url,
        "animated_poster_url": animated_poster_url,
        "watch_count": int(item.get("watch_count") or 0),
        "runtime_minutes": item.get("runtime_minutes"),
        "resolution": item.get("resolution"),
        "media_type": media_type,
        "show_id": item.get("show_id"),
        "season": item.get("season"),
        "episode": item.get("episode"),
        "resume_seconds": float(item.get("resume_seconds") or 0),
        "last_watched_at": item.get("last_watched_at"),
        "detail_url": detail_url,
        "can_play": can_play,
        "stream_url": stream_url,
        "subtitle_url": subtitle_url,
    }

    if media_type == "show":
        watched, total = get_show_progress(item_id)
        out["episode_progress"] = {
            "watched": int(watched),
            "total": int(total),
        }

    return out


def serialize_items(items: list[dict]) -> list[dict]:
    return [serialize_item(item) for item in items]

def continue_watching_items() -> list[dict]:
    items = list_movies(sort_key="title_asc", nav_mode="root")
    out = []

    for item in items:
        full = get_item(int(item["id"])) or item
        if full.get("media_type") == "show":
            continue

        resume = float(full.get("resume_seconds") or 0)
        if resume > 5:
            out.append(full)

    out.sort(key=lambda x: float(x.get("resume_seconds") or 0), reverse=True)
    return out[:20]

def has_animated_poster(item: dict) -> bool:
    if not item:
        return False
    animated_path = resolve_existing_path(item.get("animated_poster_path"))
    return bool(animated_path and Path(animated_path).exists())


def animated_media_ext(item: dict) -> str:
    animated_path = resolve_existing_path((item or {}).get("animated_poster_path"))
    if not animated_path:
        return ""
    return Path(animated_path).suffix.lower()


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ page_title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg: #070a10;
            --bg2: #0d1320;
            --panel: rgba(13, 18, 28, 0.86);
            --panel2: rgba(20, 27, 40, 0.76);
            --card: #131a25;
            --card2: #1b2433;
            --text: #f5f8ff;
            --muted: #aeb9cb;
            --soft: #dbe8ff;
            --accent: #3a95ff;
            --accent2: #78c6ff;
            --accent3: #8b5cf6;
            --good: #2dd4bf;
            --warn: #f59e0b;
            --border: rgba(255,255,255,0.10);
            --border2: rgba(120,198,255,0.34);
            --shadow: rgba(0, 0, 0, 0.52);
            --rail-w: 92px;
        }

        * { box-sizing: border-box; }

        html, body {
            margin: 0;
            padding: 0;
            min-height: 100%;
            background:
                radial-gradient(circle at 18% 4%, rgba(58,149,255,0.24), transparent 30%),
                radial-gradient(circle at 86% 12%, rgba(139,92,246,0.20), transparent 28%),
                linear-gradient(180deg, #0b101a 0%, #070a10 62%, #05070b 100%);
            color: var(--text);
            font-family: Inter, Segoe UI, Arial, Helvetica, sans-serif;
            overflow-x: hidden;
        }

        a { color: inherit; text-decoration: none; }
        button, input { font: inherit; }

        .shell { min-height: 100vh; }

        .app-frame {
            min-height: 100vh;
            display: grid;
            grid-template-columns: var(--rail-w) minmax(0, 1fr);
        }

        .side-rail {
            position: sticky;
            top: 0;
            height: 100vh;
            z-index: 20;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 14px;
            padding: 20px 12px;
            background: linear-gradient(180deg, rgba(9,13,20,0.96), rgba(9,13,20,0.78));
            border-right: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(18px);
        }

        .rail-logo {
            width: 54px;
            height: 54px;
            border-radius: 18px;
            object-fit: contain;
            filter: drop-shadow(0 0 18px rgba(58,149,255,0.26));
        }

        .rail-links {
            display: flex;
            flex-direction: column;
            gap: 10px;
            width: 100%;
            margin-top: 12px;
        }

        .rail-link {
            width: 100%;
            min-height: 62px;
            border-radius: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 5px;
            color: var(--muted);
            border: 1px solid transparent;
            background: transparent;
            outline: none;
            transition: 0.16s ease;
        }

        .rail-link:hover,
        .rail-link:focus,
        .rail-link.tv-focused {
            color: var(--text);
            border-color: var(--border2);
            background: rgba(58,149,255,0.12);
            box-shadow: 0 0 0 2px rgba(58,149,255,0.10);
            transform: translateY(-1px);
        }

        .rail-icon { font-size: 22px; line-height: 1; }
        .rail-label { font-size: 11px; letter-spacing: 0.2px; }

        .content-shell {
            min-width: 0;
            position: relative;
        }

        .hero {
            position: relative;
            min-height: 650px;
            overflow: hidden;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }

        .hero-bg {
            position: absolute;
            inset: -20px;
            background-size: cover;
            background-position: center 18%;
            transform: scale(1.06);
            opacity: 0.32;
            filter: saturate(1.1);
            transition: background-image 0.24s ease, opacity 0.24s ease;
        }

        .hero-bg::after {
            content: "";
            position: absolute;
            inset: 0;
            backdrop-filter: blur(12px);
            background: rgba(5,7,11,0.18);
        }

        .hero-overlay {
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, rgba(5,7,11,0.98) 0%, rgba(5,7,11,0.88) 36%, rgba(5,7,11,0.56) 68%, rgba(5,7,11,0.94) 100%),
                linear-gradient(180deg, rgba(5,7,11,0.12) 0%, rgba(5,7,11,0.74) 72%, rgba(5,7,11,1) 100%);
        }

        .topbar {
            position: relative;
            z-index: 3;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 18px;
            padding: 30px 44px 0 44px;
            flex-wrap: wrap;
        }

        .brand { display: flex; align-items: center; gap: 14px; }
        .brand-logo { width: 104px; height: 104px; object-fit: contain; display: block; flex: 0 0 auto; filter: drop-shadow(0 0 20px rgba(77,182,255,0.25)); }
        .brand-copy h1 { margin: 0; font-size: clamp(38px, 5vw, 64px); letter-spacing: -2px; }
        .brand-copy p { margin: 8px 0 0 0; color: var(--muted); font-size: 18px; }

        .top-actions, .hero-actions, .detail-actions, .player-actions { display: flex; gap: 12px; flex-wrap: wrap; }

        .pill,
        .hero-btn,
        .nav-chip,
        .search-input,
        .search-btn,
        .filter-chip {
            border-radius: 16px;
            border: 1px solid var(--border);
            background: rgba(18,24,35,0.82);
            color: var(--text);
            backdrop-filter: blur(12px);
        }

        .nav-chip, .filter-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 100px;
            padding: 12px 16px;
            font-size: 15px;
            outline: none;
            transition: 0.16s ease;
        }

        .nav-chip:hover, .nav-chip:focus, .filter-chip:hover, .filter-chip:focus,
        .nav-chip.tv-focused, .filter-chip.tv-focused {
            border-color: var(--accent2);
            background: rgba(58,149,255,0.14);
        }

        .searchbar {
            position: relative;
            z-index: 3;
            display: flex;
            gap: 10px;
            align-items: center;
            padding: 22px 44px 0 44px;
            flex-wrap: wrap;
        }

        .search-input {
            width: min(760px, 100%);
            max-width: 760px;
            padding: 16px 18px;
            font-size: 17px;
            outline: none;
        }

        .search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(58,149,255,0.18); }
        .search-btn { cursor: pointer; padding: 16px 20px; font-size: 16px; outline: none; }
        .search-btn:hover, .search-btn:focus { border-color: var(--accent2); }

        .helper { position: relative; z-index: 3; padding: 10px 44px 0 44px; color: var(--muted); font-size: 14px; }

        .hero-content {
            position: relative;
            z-index: 3;
            display: grid;
            grid-template-columns: 300px minmax(0, 1fr);
            gap: 34px;
            align-items: end;
            padding: 30px 44px 54px 44px;
        }

        .hero-poster, .detail-poster {
            aspect-ratio: 2 / 3;
            border-radius: 28px;
            overflow: hidden;
            background: #121722;
            border: 1px solid rgba(255,255,255,0.12);
            box-shadow: 0 22px 58px var(--shadow), 0 0 0 1px rgba(120,198,255,0.08);
        }

        .hero-poster { width: 300px; }
        .hero-poster img, .detail-poster img, .card-poster img { width: 100%; height: 100%; object-fit: cover; display: block; }

        .hero-copy { max-width: 980px; }
        .eyebrow { display: inline-block; color: var(--accent2); font-size: 13px; letter-spacing: 1.8px; text-transform: uppercase; margin-bottom: 10px; font-weight: 700; }
        .hero-title { margin: 0; font-size: clamp(44px, 6vw, 76px); line-height: 0.94; letter-spacing: -2.4px; text-shadow: 0 14px 40px rgba(0,0,0,0.6); }
        .hero-meta { margin-top: 18px; color: var(--soft); font-size: 20px; line-height: 1.65; }
        .hero-overview { margin-top: 18px; color: #eef5ff; font-size: 20px; line-height: 1.62; max-width: 960px; }

        .hero-progress { margin-top: 20px; max-width: 520px; }
        .progress-caption { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 14px; margin-bottom: 8px; }
        .progress-track { height: 8px; border-radius: 999px; background: rgba(255,255,255,0.14); overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), var(--good)); border-radius: 999px; }

        .hero-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 150px;
            padding: 15px 18px;
            font-size: 17px;
            cursor: pointer;
            transition: 0.16s ease;
            outline: none;
        }

        .hero-btn.primary { background: linear-gradient(135deg, var(--accent), #2563eb); border-color: rgba(120,198,255,0.55); color: #fff; }
        .hero-btn.primary:hover, .hero-btn.primary:focus, .hero-btn.primary.tv-focused { transform: translateY(-1px); box-shadow: 0 10px 26px rgba(58,149,255,0.28); }
        .hero-btn.secondary:hover, .hero-btn.secondary:focus, .hero-btn.secondary.tv-focused { border-color: var(--accent2); background: rgba(58,149,255,0.13); }
        .hero-btn.danger:hover, .hero-btn.danger:focus { border-color: #fb7185; background: rgba(251,113,133,0.13); }

        .main { padding: 18px 0 54px 0; }
        .row-section { margin-top: 28px; }
        .row-head { display: flex; justify-content: space-between; align-items: end; gap: 14px; padding: 0 44px; margin-bottom: 14px; }
        .row-head h2 { margin: 0; font-size: 31px; letter-spacing: -0.8px; }
        .row-sub { color: var(--muted); font-size: 15px; }
        .media-row-wrap { position: relative; }
        .media-row { display: flex; gap: 18px; overflow-x: auto; overflow-y: hidden; padding: 5px 44px 20px 44px; scroll-behavior: smooth; scrollbar-width: thin; scrollbar-color: var(--accent) #111827; }
        .media-row::-webkit-scrollbar { height: 10px; }
        .media-row::-webkit-scrollbar-track { background: #111827; border-radius: 999px; }
        .media-row::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 999px; }

        .card {
            position: relative;
            flex: 0 0 232px;
            width: 232px;
            border-radius: 24px;
            overflow: hidden;
            background: linear-gradient(180deg, rgba(29,38,54,0.96) 0%, rgba(18,24,35,0.96) 100%);
            border: 2px solid transparent;
            box-shadow: 0 14px 32px rgba(0,0,0,0.38);
            transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
            outline: none;
        }

        .card:hover, .card:focus, .card.tv-focused {
            transform: translateY(-5px) scale(1.025);
            border-color: var(--accent2);
            box-shadow: 0 22px 48px rgba(0,0,0,0.54), 0 0 0 2px rgba(120,198,255,0.16);
        }

        .card-poster { position: relative; width: 100%; aspect-ratio: 2 / 3; background: #222831; overflow: hidden; }
        .card-poster::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, transparent 42%, rgba(0,0,0,0.55) 100%);
            opacity: 0;
            transition: 0.16s ease;
        }
        .card:hover .card-poster::after, .card:focus .card-poster::after, .card.tv-focused .card-poster::after { opacity: 1; }

        .card-overlay {
            position: absolute;
            left: 12px;
            right: 12px;
            bottom: 12px;
            z-index: 2;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            opacity: 0;
            transform: translateY(8px);
            transition: 0.16s ease;
        }
        .card:hover .card-overlay, .card:focus .card-overlay, .card.tv-focused .card-overlay { opacity: 1; transform: translateY(0); }
        .mini-badge { border-radius: 999px; padding: 6px 8px; background: rgba(4,8,14,0.75); border: 1px solid rgba(255,255,255,0.18); color: #fff; font-size: 12px; backdrop-filter: blur(8px); }
        .resume-badge { color: #dffcff; border-color: rgba(45,212,191,0.45); }

        .card-progress { position: absolute; left: 0; right: 0; bottom: 0; height: 6px; background: rgba(255,255,255,0.15); z-index: 3; }
        .card-progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--good)); }
        .card-meta { padding: 14px 14px 16px 14px; }
        .card-title { font-size: 18px; font-weight: 800; line-height: 1.25; min-height: 44px; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .card-sub { margin-top: 10px; color: var(--muted); font-size: 14px; line-height: 1.45; }

        .all-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(222px, 1fr)); gap: 22px; align-items: start; }
        .grid-card, .all-grid .card { width: 100%; flex: unset; }

        .details-page { padding: 34px 44px 56px 44px; }
        .back-link { display: inline-flex; align-items: center; gap: 10px; color: #cde4ff; font-size: 17px; margin-bottom: 18px; outline: none; }
        .back-link:hover, .back-link:focus, .back-link.tv-focused { color: #fff; }

        .detail-hero-bg { position: fixed; inset: 0; opacity: 0.14; background-size: cover; background-position: center; filter: blur(18px); transform: scale(1.08); pointer-events: none; }
        .detail-layout { position: relative; z-index: 2; display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 30px; align-items: start; }
        .detail-poster { width: 340px; }
        .detail-panel { background: linear-gradient(180deg, rgba(23,28,38,0.92) 0%, rgba(13,18,27,0.92) 100%); border: 1px solid rgba(255,255,255,0.10); border-radius: 28px; padding: 28px; box-shadow: 0 14px 36px rgba(0,0,0,0.34); backdrop-filter: blur(16px); }
        .detail-title { margin: 0; font-size: clamp(38px, 5vw, 58px); line-height: 1; letter-spacing: -1.5px; }
        .detail-meta { margin-top: 16px; color: var(--muted); font-size: 18px; line-height: 1.7; }
        .detail-overview { margin-top: 20px; font-size: 19px; line-height: 1.75; white-space: pre-wrap; color: #edf4ff; }
        .chip-line { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 18px; }
        .detail-chip { padding: 8px 11px; border-radius: 999px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.10); color: #dce9fb; font-size: 14px; }

        .episode-list { margin-top: 26px; display: grid; gap: 14px; }
        .episode-card { display: block; background: linear-gradient(180deg, rgba(23,28,38,0.94) 0%, rgba(13,18,27,0.94) 100%); border: 2px solid transparent; border-radius: 20px; padding: 18px; transition: 0.15s ease; outline: none; }
        .episode-card:hover, .episode-card:focus, .episode-card.tv-focused { border-color: var(--accent2); transform: translateY(-2px); }
        .episode-title { font-size: 21px; font-weight: 800; }
        .episode-sub { margin-top: 8px; color: var(--muted); font-size: 15px; }

        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 18px; }
        .stat-card { background: linear-gradient(180deg, rgba(23,28,38,0.94) 0%, rgba(13,18,27,0.94) 100%); border-radius: 22px; border: 1px solid rgba(255,255,255,0.10); padding: 20px; }
        .stat-label { color: var(--muted); font-size: 14px; }
        .stat-value { margin-top: 10px; font-size: 36px; font-weight: 800; }
        .empty { margin: 18px 44px; padding: 24px; border-radius: 20px; background: linear-gradient(180deg, rgba(23,28,38,0.94) 0%, rgba(13,18,27,0.94) 100%); color: var(--muted); font-size: 18px; }

        .player-page { min-height: 100vh; padding: 22px; display: flex; flex-direction: column; gap: 14px; background: #030509; }
        .player-top { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
        .player-title { font-size: 24px; font-weight: 800; }
        .player-frame { position: relative; flex: 1; min-height: 420px; border-radius: 26px; overflow: hidden; background: #000; border: 1px solid rgba(255,255,255,0.10); box-shadow: 0 22px 60px rgba(0,0,0,0.55); }
        .player-frame video { width: 100%; height: 100%; max-height: calc(100vh - 160px); min-height: 420px; background: #000; display: block; outline: none; }
        .player-actions { align-items: center; }
        .next-episode-card { display: none; position: absolute; right: 24px; bottom: 24px; width: min(420px, calc(100% - 48px)); background: rgba(8,12,20,0.92); border: 1px solid rgba(120,198,255,0.38); border-radius: 22px; padding: 18px; box-shadow: 0 18px 48px rgba(0,0,0,0.55); backdrop-filter: blur(14px); z-index: 5; }
        .next-episode-card.show { display: block; }
        .next-title { font-size: 20px; font-weight: 800; margin-bottom: 8px; }
        .next-sub { color: var(--muted); line-height: 1.45; margin-bottom: 14px; }

        @media (max-width: 1200px) {
            .hero-content { grid-template-columns: 250px 1fr; }
            .hero-poster { width: 250px; }
            .detail-layout { grid-template-columns: 300px 1fr; }
            .detail-poster { width: 300px; }
        }

        @media (max-width: 920px) {
            :root { --rail-w: 0px; }
            .app-frame { display: block; }
            .side-rail { position: fixed; left: 12px; right: 12px; bottom: 12px; top: auto; height: 72px; flex-direction: row; justify-content: center; padding: 8px; border-radius: 24px; border: 1px solid rgba(255,255,255,0.10); z-index: 50; }
            .rail-logo { display: none; }
            .rail-links { flex-direction: row; margin: 0; gap: 6px; }
            .rail-link { min-height: 54px; border-radius: 18px; }
            .rail-label { font-size: 10px; }
            .content-shell { padding-bottom: 92px; }
            .hero-content, .detail-layout { grid-template-columns: 1fr; }
            .hero-poster, .detail-poster { width: min(320px, 100%); }
        }

        @media (max-width: 700px) {
            .topbar, .searchbar, .row-head, .media-row, .details-page, .helper { padding-left: 18px !important; padding-right: 18px !important; }
            .hero-content { padding-left: 18px; padding-right: 18px; }
            .brand-logo { width: 76px; height: 76px; }
            .card { flex-basis: 180px; width: 180px; }
            .all-grid { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; }
        }
    </style>
</head>
<body>
    <div class="shell">
        <div class="app-frame">
            <nav class="side-rail" aria-label="VisionVault navigation">
                <img class="rail-logo" src="{{ url_for('brand_logo') }}" alt="VisionVault">
                <div class="rail-links">
                    <a class="rail-link" href="{{ url_for('index') }}" data-tv-focus="1"><span class="rail-icon">⌂</span><span class="rail-label">Home</span></a>
                    <a class="rail-link" href="{{ url_for('movies_page') }}" data-tv-focus="1"><span class="rail-icon">▣</span><span class="rail-label">Movies</span></a>
                    <a class="rail-link" href="{{ url_for('shows_page') }}" data-tv-focus="1"><span class="rail-icon">▤</span><span class="rail-label">Shows</span></a>
                    <a class="rail-link" href="{{ url_for('random_route') }}" data-tv-focus="1"><span class="rail-icon">🎲</span><span class="rail-label">Random</span></a>
                    <a class="rail-link" href="{{ url_for('stats_page') }}" data-tv-focus="1"><span class="rail-icon">◌</span><span class="rail-label">Stats</span></a>
                </div>
            </nav>
            <div class="content-shell">
                {{ body|safe }}
            </div>
        </div>
    </div>

    <script>
        const HERO_DATA = {{ hero_data|tojson }};

        function byId(id) { return document.getElementById(id); }

        function updateHeroFromCard(card) {
            if (!card) return;
            const itemId = card.getAttribute("data-item-id");
            if (!itemId || !HERO_DATA[itemId]) return;

            const data = HERO_DATA[itemId];

            if (byId("hero-bg")) {
                const bgUrl = data.animated_poster_url || data.poster_url || "";
                byId("hero-bg").style.backgroundImage = bgUrl ? `url("${bgUrl}")` : "";
            }

            const heroPosterImg = byId("hero-poster-img");
            const existingAnimatedImg = byId("hero-poster-animated");
            const existingVideo = byId("hero-poster-video");

            if (existingAnimatedImg) existingAnimatedImg.remove();
            if (existingVideo) {
                try { existingVideo.pause(); } catch (err) {}
                existingVideo.remove();
            }

            if (heroPosterImg) {
                heroPosterImg.src = data.poster_url || "";
                heroPosterImg.style.display = "block";
            }

            if (data.animated_poster_url) {
                const heroPoster = document.querySelector(".hero-poster");
                if (heroPoster) {
                    if ([".mp4", ".webm", ".m4v"].includes(data.animated_poster_ext)) {
                        const video = document.createElement("video");
                        video.id = "hero-poster-video";
                        video.autoplay = true;
                        video.muted = true;
                        video.loop = true;
                        video.playsInline = true;
                        video.style.width = "100%";
                        video.style.height = "100%";
                        video.style.objectFit = "cover";
                        video.style.display = "block";
                        const source = document.createElement("source");
                        source.src = data.animated_poster_url;
                        source.type = data.animated_poster_ext === ".webm" ? "video/webm" : "video/mp4";
                        video.appendChild(source);
                        heroPoster.appendChild(video);
                        if (heroPosterImg) heroPosterImg.style.display = "none";
                    } else {
                        const animImg = document.createElement("img");
                        animImg.id = "hero-poster-animated";
                        animImg.src = data.animated_poster_url;
                        animImg.alt = "";
                        animImg.style.width = "100%";
                        animImg.style.height = "100%";
                        animImg.style.objectFit = "cover";
                        animImg.style.display = "block";
                        heroPoster.appendChild(animImg);
                        if (heroPosterImg) heroPosterImg.style.display = "none";
                    }
                }
            }

            if (byId("hero-type")) byId("hero-type").textContent = data.type_label || "Library";
            if (byId("hero-title")) byId("hero-title").textContent = data.title || "Untitled";
            if (byId("hero-meta")) byId("hero-meta").textContent = data.meta_line || "";
            if (byId("hero-overview")) byId("hero-overview").textContent = data.overview || "No overview yet.";

            const heroOpen = byId("hero-open");
            if (heroOpen) {
                heroOpen.href = data.detail_url || "#";
                heroOpen.setAttribute("data-item-id", itemId);
            }

            const heroPlay = byId("hero-play");
            if (heroPlay) {
                if (data.can_play) {
                    heroPlay.style.display = "inline-flex";
                    heroPlay.href = data.play_url || "#";
                    heroPlay.textContent = data.resume_seconds > 5 ? "Resume" : "Play";
                } else {
                    heroPlay.style.display = "none";
                    heroPlay.removeAttribute("href");
                }
            }

            const heroProgress = byId("hero-progress");
            const heroProgressFill = byId("hero-progress-fill");
            const heroProgressLabel = byId("hero-progress-label");
            if (heroProgress && heroProgressFill && heroProgressLabel) {
                const pct = Number(data.progress_percent || 0);
                if (pct > 0) {
                    heroProgress.style.display = "block";
                    heroProgressFill.style.width = `${Math.min(99, Math.max(1, pct))}%`;
                    heroProgressLabel.textContent = data.resume_label ? `Resume at ${data.resume_label}` : "Resume available";
                } else {
                    heroProgress.style.display = "none";
                    heroProgressFill.style.width = "0%";
                }
            }
        }

        function getFocusable() { return Array.from(document.querySelectorAll("[data-tv-focus='1']")); }
        function getRows() { return Array.from(document.querySelectorAll(".media-row, .episode-list, .all-grid")); }
        function getRowItems(row) { return row ? Array.from(row.querySelectorAll("[data-tv-focus='1']")) : []; }
        function getCurrentFocused() {
            const active = document.activeElement;
            if (active && active.matches("[data-tv-focus='1']")) return active;
            return document.querySelector(".tv-focused");
        }

        function scrollRowToItem(row, el) {
            if (!row || !el || !row.classList.contains("media-row")) return;
            const elLeft = el.offsetLeft;
            const elRight = elLeft + el.offsetWidth;
            const viewLeft = row.scrollLeft;
            const viewRight = viewLeft + row.clientWidth;
            const pad = 28;
            if (elLeft - pad < viewLeft) row.scrollTo({ left: Math.max(0, elLeft - pad), behavior: "smooth" });
            else if (elRight + pad > viewRight) row.scrollTo({ left: elRight - row.clientWidth + pad, behavior: "smooth" });
        }

        function setFocus(el) {
            if (!el) return;
            getFocusable().forEach(x => x.classList.remove("tv-focused"));
            el.classList.add("tv-focused");
            el.focus({ preventScroll: true });
            const row = el.closest(".media-row, .episode-list, .all-grid");
            scrollRowToItem(row, el);
            el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
            if (el.hasAttribute("data-item-id")) updateHeroFromCard(el);
        }

        function focusFirstCard() {
            const auto = document.querySelector("[data-autofocus='1']");
            if (auto) return setFocus(auto);
            const all = getFocusable();
            if (all.length) setFocus(all[0]);
        }

        function moveHorizontal(direction) {
            const current = getCurrentFocused();
            if (!current) return focusFirstCard();
            const row = current.closest(".media-row, .episode-list, .all-grid, .rail-links");
            const items = getRowItems(row);
            if (!items.length) return;
            const idx = items.indexOf(current);
            const nextIdx = idx + direction;
            if (nextIdx >= 0 && nextIdx < items.length) setFocus(items[nextIdx]);
        }

        function moveVertical(direction) {
            const current = getCurrentFocused();
            if (!current) return focusFirstCard();

            const grid = current.closest(".all-grid");
            if (grid) {
                const items = getRowItems(grid);
                const idx = items.indexOf(current);
                const cols = Math.max(1, Math.floor(grid.clientWidth / 245));
                const nextIdx = idx + direction * cols;
                if (nextIdx >= 0 && nextIdx < items.length) setFocus(items[nextIdx]);
                return;
            }

            const currentRow = current.closest(".media-row, .episode-list, .rail-links");
            if (!currentRow) return;
            const rows = getRows();
            const rowIndex = rows.indexOf(currentRow);
            if (rowIndex === -1) return;
            const currentItems = getRowItems(currentRow);
            const currentIdx = Math.max(0, currentItems.indexOf(current));
            const targetRow = rows[rowIndex + direction];
            if (!targetRow) return;
            const targetItems = getRowItems(targetRow);
            if (!targetItems.length) return;
            setFocus(targetItems[Math.min(currentIdx, targetItems.length - 1)]);
        }

        document.addEventListener("focusin", function(e) {
            const target = e.target;
            if (target && target.matches("[data-tv-focus='1']")) {
                getFocusable().forEach(x => x.classList.remove("tv-focused"));
                target.classList.add("tv-focused");
                const row = target.closest(".media-row, .episode-list, .all-grid");
                scrollRowToItem(row, target);
                if (target.hasAttribute("data-item-id")) updateHeroFromCard(target);
            }
        });

        document.addEventListener("keydown", function(e) {
            const active = document.activeElement;
            const isInput = active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName);
            if (isInput && e.key !== "Escape") return;

            if (e.key === "ArrowRight") { e.preventDefault(); moveHorizontal(1); }
            else if (e.key === "ArrowLeft") { e.preventDefault(); moveHorizontal(-1); }
            else if (e.key === "ArrowDown") { e.preventDefault(); moveVertical(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); moveVertical(-1); }
            else if (e.key === "Enter") {
                const current = getCurrentFocused();
                if (current && typeof current.click === "function") { e.preventDefault(); current.click(); }
            } else if (e.key === "Backspace" || e.key === "Escape") {
                const back = document.querySelector("[data-back-link='1']");
                if (back) { e.preventDefault(); window.location.href = back.getAttribute("href"); }
            } else if (e.key === "/") {
                const input = document.querySelector(".search-input");
                if (input) { e.preventDefault(); input.focus(); input.select(); }
            } else if (e.key.toLowerCase() === "r") {
                const randomLink = document.querySelector("a[href*='/random']");
                if (randomLink && !isInput) { e.preventDefault(); window.location.href = randomLink.href; }
            }
        });

        window.addEventListener("load", focusFirstCard);
    </script>
</body>
</html>
"""


def render_page(page_title: str, body_html: str, hero_data: dict | None = None):
    return render_template_string(
        PAGE_TEMPLATE,
        page_title=page_title,
        body=body_html,
        hero_data=hero_data or {},
    )


def safe_date(value):
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return datetime.min


def truncate(text: str | None, max_len: int = 260) -> str:
    text = (text or "").strip()
    if not text:
        return "No overview yet."
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def poster_url_for(item_id: int) -> str:
    return url_for("poster_for_item", item_id=item_id)

def build_hero_entry(item: dict) -> dict:
    item_id = int(item["id"])
    media_type = item.get("media_type") or "movie"
    resume_seconds = 0
    progress_percent = 0
    resume_label = ""

    if media_type == "show":
        watched, total = get_show_progress(item_id)
        meta_parts = ["Series", f"{watched}/{total} watched"]
        type_label = "Series"
        play_url = "#"
    else:
        try:
            resume_seconds = int(get_resume_position(item_id) or item.get("resume_seconds") or 0)
        except Exception:
            resume_seconds = int(item.get("resume_seconds") or 0)

        runtime_seconds = int(item.get("runtime_minutes") or 0) * 60
        if resume_seconds > 5 and runtime_seconds > 0:
            progress_percent = max(1, min(99, int((resume_seconds / runtime_seconds) * 100)))
            resume_label = format_seconds_label(resume_seconds)

        meta_parts = [
            str(item.get("year") or "Unknown year"),
            f"Watched {item.get('watch_count', 0)}x"
        ]
        if item.get("runtime_minutes"):
            meta_parts.append(f"{item['runtime_minutes']} min")
        if item.get("resolution"):
            meta_parts.append(str(item["resolution"]))
        type_label = "Movie" if media_type == "movie" else "Episode"
        play_url = url_for("player_page", item_id=item_id)

    if item.get("genres"):
        meta_parts.append(str(item["genres"]))

    animated_url = absolute_url(url_for("animated_poster_for_item", item_id=item_id)) if has_animated_poster(item) else ""
    animated_ext = animated_media_ext(item)
    poster_url = absolute_url(url_for("poster_for_item", item_id=item_id))
    preferred_visual_url = animated_url if animated_url else poster_url

    return {
        "title": item.get("title") or "Untitled",
        "overview": item.get("overview") or "No overview yet.",
        "meta_line": " • ".join(meta_parts) if meta_parts else type_label,
        "type_label": type_label,
        "poster_url": poster_url,
        "animated_poster_url": animated_url,
        "animated_poster_ext": animated_ext,
        "preferred_visual_url": preferred_visual_url,
        "detail_url": url_for("item_page", item_id=item_id),
        "play_url": play_url,
        "can_play": can_play_item(item),
        "resume_seconds": resume_seconds,
        "resume_label": resume_label,
        "progress_percent": progress_percent,
    }


def enrich_items(items: list[dict]) -> list[dict]:
    enriched = []
    for item in items:
        full = get_item(item["id"])
        if full:
            enriched.append(full)
        else:
            enriched.append(item)
    return enriched


def get_streamable_file(item_id: int) -> tuple[dict | None, str | None]:
    item = get_item(item_id)
    if not item:
        return None, None

    if (item.get("media_type") or "") == "show":
        return item, None

    file_path = item.get("file_path")
    if not file_path:
        return item, None

    if not os.path.exists(file_path):
        return item, None

    return item, file_path


def parse_range_header(range_header: str, file_size: int):
    """
    Parse a Range header like: bytes=0-1023
    Returns (start, end) inclusive, or None if invalid.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None

    try:
        range_value = range_header.split("=", 1)[1].strip()
        start_str, end_str = range_value.split("-", 1)

        if start_str == "":
            # suffix bytes: bytes=-500
            length = int(end_str)
            if length <= 0:
                return None
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1

        if start < 0 or end < start or start >= file_size:
            return None

        end = min(end, file_size - 1)
        return start, end
    except Exception:
        return None

def format_seconds_label(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"



def item_resume_seconds(item: dict) -> int:
    if not item or item.get("media_type") == "show":
        return 0
    try:
        return int(get_resume_position(int(item["id"])) or item.get("resume_seconds") or 0)
    except Exception:
        try:
            return int(item.get("resume_seconds") or 0)
        except Exception:
            return 0


def item_progress_percent(item: dict) -> int:
    resume = item_resume_seconds(item)
    runtime_seconds = int(item.get("runtime_minutes") or 0) * 60
    if resume > 5 and runtime_seconds > 0:
        return max(1, min(99, int((resume / runtime_seconds) * 100)))
    return 0


def item_resume_label(item: dict) -> str:
    resume = item_resume_seconds(item)
    return format_seconds_label(resume) if resume > 5 else ""


def card_subtitle(item: dict) -> str:
    media_type = item.get("media_type") or "movie"
    if media_type == "show":
        watched, total = get_show_progress(int(item["id"]))
        return f"Series • {watched}/{total} watched"

    parts = []
    if media_type == "episode":
        season = item.get("season") or 0
        episode = item.get("episode") or 0
        parts.append(f"S{int(season):02d}E{int(episode):02d}")
    else:
        parts.append(str(item.get("year") or "Unknown year"))

    if item.get("resolution"):
        parts.append(str(item["resolution"]))
    if item.get("runtime_minutes"):
        parts.append(f"{item['runtime_minutes']} min")
    if int(item.get("watch_count") or 0) > 0:
        parts.append(f"Watched {item.get('watch_count')}x")
    return " • ".join(parts)


def unique_by_id(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        if not item or "id" not in item:
            continue
        item_id = int(item["id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        out.append(item)
    return out


def is_hd_item(item: dict) -> bool:
    res = str(item.get("resolution") or "").lower()
    return any(token in res for token in ["4k", "2160", "1080", "uhd", "hd"])


def is_vd3d_candidate(item: dict) -> bool:
    if not can_play_item(item):
        return False
    res = str(item.get("resolution") or "").lower()
    genres = str(item.get("genres") or "").lower()
    title = str(item.get("title") or "").lower()
    return any(token in res + " " + genres + " " + title for token in ["4k", "2160", "1080", "action", "sci-fi", "adventure", "fantasy"])


def genre_rows_from_movies(movies: list[dict], limit: int = 4, per_row: int = 18) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for item in movies:
        raw = item.get("genres") or ""
        for genre in [g.strip() for g in str(raw).split(",") if g.strip()]:
            buckets.setdefault(genre, []).append(item)

    rows = []
    for genre, items in sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True):
        clean_items = unique_by_id(items)[:per_row]
        if len(clean_items) >= 2:
            rows.append({"name": genre, "items": clean_items})
        if len(rows) >= limit:
            break
    return rows


def next_episode_for(item: dict) -> dict | None:
    if not item or item.get("media_type") != "episode":
        return None
    show_id = item.get("show_id")
    if not show_id:
        return None

    episodes = list_show_episodes(int(show_id))
    episodes = sorted(episodes, key=lambda x: (int(x.get("season") or 0), int(x.get("episode") or 0), int(x.get("id") or 0)))

    for idx, ep in enumerate(episodes):
        if int(ep.get("id") or 0) == int(item.get("id") or 0):
            if idx + 1 < len(episodes):
                return get_item(int(episodes[idx + 1]["id"])) or episodes[idx + 1]
            return None
    return None


def iter_file_chunks(path: str, start: int, end: int, chunk_size: int = 1024 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1

        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            yield data
            remaining -= len(data)


def guess_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"
    
def find_subtitle_file_for_video(video_path: str) -> str | None:
    if not video_path:
        return None

    p = Path(video_path)
    if not p.exists():
        return None

    movie_folder = p.parent
    movie_named_folder = movie_folder / p.stem
    parent_folder = movie_folder.parent if movie_folder.parent != movie_folder else None

    search_dirs = [
        movie_folder,
        movie_folder / "Subtitles",
        movie_folder / "subtitles",
        movie_named_folder,
        movie_named_folder / "Subtitles",
        movie_named_folder / "subtitles",
    ]

    if parent_folder:
        search_dirs.extend([
            parent_folder / "Subtitles",
            parent_folder / "subtitles",
        ])

    candidate_names = []

    for ext in [".vtt", ".srt"]:
        candidate_names.append(f"{p.stem}{ext}")

    for ext in [".vtt", ".srt"]:
        candidate_names.append(f"{p.stem}.en{ext}")
        candidate_names.append(f"{p.stem}.eng{ext}")
        candidate_names.append(f"{p.stem}.english{ext}")

    seen = set()

    for folder in search_dirs:
        try:
            folder_key = str(folder.resolve())
        except Exception:
            folder_key = str(folder)

        if folder_key in seen:
            continue
        seen.add(folder_key)

        if not folder.exists():
            continue

        for name in candidate_names:
            candidate = folder / name
            if candidate.exists():
                return str(candidate)

    return None


def srt_to_vtt_text(srt_text: str) -> str:
    text = (srt_text or "").replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    out_lines = ["WEBVTT", ""]

    for line in lines:
        if "-->" in line:
            line = line.replace(",", ".")
        out_lines.append(line)

    return "\n".join(out_lines)
    
def build_stream_response(file_path: str):
    file_size = os.path.getsize(file_path)
    mime_type = guess_mime_type(file_path)
    range_header = request.headers.get("Range", None)

    if range_header:
        parsed = parse_range_header(range_header, file_size)
        if not parsed:
            return Response(status=416)

        start, end = parsed
        content_length = end - start + 1

        response = Response(
            stream_with_context(iter_file_chunks(file_path, start, end)),
            status=206,
            mimetype=mime_type,
            direct_passthrough=True,
        )
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(content_length)
        return response

    response = Response(
        stream_with_context(iter_file_chunks(file_path, 0, file_size - 1)),
        status=200,
        mimetype=mime_type,
        direct_passthrough=True,
    )
    response.headers["Content-Length"] = str(file_size)
    response.headers["Accept-Ranges"] = "bytes"
    return response

@app.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    all_items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))

    if q:
        all_items = [x for x in all_items if q in (x.get("title") or "").lower()]

    movies_all = [x for x in all_items if (x.get("media_type") or "movie") == "movie"]
    shows_all = [x for x in all_items if x.get("media_type") == "show"]

    continue_watching = continue_watching_items()
    if q:
        continue_watching = [x for x in continue_watching if q in (x.get("title") or "").lower()]

    recently_added = sorted(all_items, key=lambda x: safe_date(x.get("added_at")), reverse=True)
    most_watched = sorted(movies_all, key=lambda x: int(x.get("watch_count") or 0), reverse=True)
    most_watched = [x for x in most_watched if int(x.get("watch_count") or 0) > 0]
    unwatched = [x for x in movies_all if int(x.get("watch_count") or 0) == 0]
    hd_collection = [x for x in movies_all if is_hd_item(x)]
    vd3d_ready = [x for x in movies_all if is_vd3d_candidate(x)]
    genre_rows = genre_rows_from_movies(movies_all, limit=4, per_row=18)

    continue_watching = continue_watching[:18]
    shows = shows_all[:18]
    movies = movies_all[:30]
    recently_added = recently_added[:18]
    most_watched = most_watched[:18]
    unwatched = unwatched[:18]
    hd_collection = hd_collection[:18]
    vd3d_ready = vd3d_ready[:18]

    random_pool = [x for x in movies_all if can_play_item(x)]
    random_pick = random.choice(random_pool) if random_pool else None

    hero_source = None
    for bucket in (continue_watching, recently_added, movies, shows):
        if bucket:
            hero_source = bucket[0]
            break

    hero_items = unique_by_id(
        continue_watching + shows + movies + recently_added + most_watched + unwatched + hd_collection + vd3d_ready +
        [item for row in genre_rows for item in row["items"]] + ([random_pick] if random_pick else [])
    )
    hero_data = {str(item["id"]): build_hero_entry(item) for item in hero_items}

    default_hero = build_hero_entry(hero_source) if hero_source else {
        "title": "VisionVault",
        "overview": "Browse your local movie and TV collection in a TV-first interface.",
        "meta_line": "Local library • TV mode",
        "type_label": "Library",
        "poster_url": "",
        "animated_poster_url": "",
        "animated_poster_ext": "",
        "preferred_visual_url": "",
        "detail_url": "#",
        "play_url": "#",
        "can_play": False,
        "resume_seconds": 0,
        "resume_label": "",
        "progress_percent": 0,
    }

    body = render_template_string(
        """
        
{% macro media_card(item, autofocus=False) %}
<a class="card"
   href="{{ url_for('item_page', item_id=item['id']) }}"
   data-tv-focus="1"
   data-item-id="{{ item['id'] }}"
   {% if autofocus %}data-autofocus="1"{% endif %}>
    <div class="card-poster">
        <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
        <div class="card-overlay">
            {% if item['media_type'] == 'show' %}
                <span class="mini-badge">Open</span>
            {% elif item_progress_percent(item) > 0 %}
                <span class="mini-badge resume-badge">Resume {{ item_resume_label(item) }}</span>
            {% else %}
                <span class="mini-badge">Play</span>
            {% endif %}
            {% if item['resolution'] %}<span class="mini-badge">{{ item['resolution'] }}</span>{% endif %}
        </div>
        {% if item_progress_percent(item) > 0 %}
        <div class="card-progress"><div class="card-progress-fill" style="width: {{ item_progress_percent(item) }}%;"></div></div>
        {% endif %}
    </div>
    <div class="card-meta">
        <div class="card-title">{{ item['title'] }}</div>
        <div class="card-sub">{{ card_subtitle(item) }}</div>
    </div>
</a>
{% endmacro %}

        <section class="hero">
            <div class="hero-bg" id="hero-bg"
                 {% if default_hero.preferred_visual_url %}style='background-image:url("{{ default_hero.preferred_visual_url }}")'{% endif %}></div>
            <div class="hero-overlay"></div>

            <div class="topbar">
                <div class="brand">
                    <img class="brand-logo" src="{{ url_for('brand_logo') }}" alt="VisionVault logo">
                    <div class="brand-copy">
                        <h1>VisionVault TV</h1>
                        <p>Your private cinematic hub for local movies, shows, and VR viewing.</p>
                    </div>
                </div>

                <div class="top-actions">
                    <a class="nav-chip" href="{{ url_for('movies_page') }}" data-tv-focus="1">Movies</a>
                    <a class="nav-chip" href="{{ url_for('shows_page') }}" data-tv-focus="1">Shows</a>
                    <a class="nav-chip" href="{{ url_for('random_route') }}" data-tv-focus="1">Random Pick</a>
                </div>
            </div>

            <form class="searchbar" method="get" action="{{ url_for('index') }}">
                <input class="search-input" type="text" name="q" value="{{ query }}" placeholder="Search your library...">
                <button class="search-btn" type="submit" data-tv-focus="1">Search</button>
            </form>

            <div class="helper">Arrow keys navigate. Enter opens. Backspace or Escape goes back. Press / to search. Press R for random.</div>

            <div class="hero-content">
                <div class="hero-poster">
                    <img id="hero-poster-img"
                         src="{{ default_hero.poster_url if default_hero.poster_url else '' }}"
                         alt=""
                         {% if default_hero.animated_poster_url %}style="display:none"{% endif %}>
                    {% if default_hero.animated_poster_url and default_hero.animated_poster_ext in ['.mp4', '.webm', '.m4v'] %}
                    <video id="hero-poster-video" autoplay muted loop playsinline style="width:100%;height:100%;object-fit:cover;display:block;">
                        <source src="{{ default_hero.animated_poster_url }}" type="{{ 'video/webm' if default_hero.animated_poster_ext == '.webm' else 'video/mp4' }}">
                    </video>
                    {% elif default_hero.animated_poster_url %}
                    <img id="hero-poster-animated" src="{{ default_hero.animated_poster_url }}" alt="" style="width:100%;height:100%;object-fit:cover;display:block;">
                    {% endif %}
                </div>

                <div class="hero-copy">
                    <div class="eyebrow" id="hero-type">{{ default_hero.type_label }}</div>
                    <h2 class="hero-title" id="hero-title">{{ default_hero.title }}</h2>
                    <div class="hero-meta" id="hero-meta">{{ default_hero.meta_line }}</div>
                    <div class="hero-overview" id="hero-overview">{{ default_hero.overview }}</div>

                    <div class="hero-progress" id="hero-progress" {% if not default_hero.progress_percent %}style="display:none"{% endif %}>
                        <div class="progress-caption">
                            <span id="hero-progress-label">{% if default_hero.resume_label %}Resume at {{ default_hero.resume_label }}{% endif %}</span>
                            <span>Progress</span>
                        </div>
                        <div class="progress-track"><div class="progress-fill" id="hero-progress-fill" style="width: {{ default_hero.progress_percent or 0 }}%;"></div></div>
                    </div>

                    <div class="hero-actions">
                        <a id="hero-open" class="hero-btn primary" href="{{ default_hero.detail_url }}" data-tv-focus="1">Open Details</a>
                        <a id="hero-play" class="hero-btn secondary" href="{{ default_hero.play_url }}" data-tv-focus="1" {% if not default_hero.can_play %}style="display:none"{% endif %}>{% if default_hero.resume_seconds > 5 %}Resume{% else %}Play{% endif %}</a>
                    </div>
                </div>
            </div>
        </section>

        <main class="main">
            {% if random_pick %}
            <section class="row-section">
                <div class="row-head">
                    <div><h2>Tonight's Pick</h2><div class="row-sub">Let VisionVault choose for you</div></div>
                    <a class="nav-chip" href="{{ url_for('random_route') }}" data-tv-focus="1">Pick Again</a>
                </div>
                <div class="media-row-wrap"><div class="media-row">{{ media_card(random_pick, autofocus=(not continue_watching)) }}</div></div>
            </section>
            {% endif %}

            {% if continue_watching %}
            <section class="row-section">
                <div class="row-head"><div><h2>Continue Watching</h2><div class="row-sub">Resume titles with saved progress</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in continue_watching %}{{ media_card(item, autofocus=loop.first) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if recently_added %}
            <section class="row-section">
                <div class="row-head"><div><h2>Recently Added</h2><div class="row-sub">Fresh from your local library</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in recently_added %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if shows %}
            <section class="row-section">
                <div class="row-head"><div><h2>Shows</h2><div class="row-sub">{{ shows|length }} series</div></div><a class="nav-chip" href="{{ url_for('shows_page') }}" data-tv-focus="1">View All</a></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in shows %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if movies %}
            <section class="row-section">
                <div class="row-head"><div><h2>Movies</h2><div class="row-sub">{{ movies|length }} featured movie{{ '' if movies|length == 1 else 's' }}</div></div><a class="nav-chip" href="{{ url_for('movies_page') }}" data-tv-focus="1">View All</a></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in movies %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if vd3d_ready %}
            <section class="row-section">
                <div class="row-head"><div><h2>VisionDepth3D Ready</h2><div class="row-sub">Playable titles that could make strong 3D candidates</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in vd3d_ready %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if hd_collection %}
            <section class="row-section">
                <div class="row-head"><div><h2>HD / 4K Collection</h2><div class="row-sub">Higher resolution files in your vault</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in hd_collection %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if most_watched %}
            <section class="row-section">
                <div class="row-head"><div><h2>Most Watched</h2><div class="row-sub">Your replay favorites</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in most_watched %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% if unwatched %}
            <section class="row-section">
                <div class="row-head"><div><h2>Unwatched Gems</h2><div class="row-sub">Movies you have not played yet</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in unwatched %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endif %}

            {% for row in genre_rows %}
            <section class="row-section">
                <div class="row-head"><div><h2>{{ row.name }}</h2><div class="row-sub">Genre collection</div></div></div>
                <div class="media-row-wrap"><div class="media-row">{% for item in row['items'] %}{{ media_card(item) }}{% endfor %}</div></div>
            </section>
            {% endfor %}

            {% if not continue_watching and not shows and not movies and not recently_added %}
            <div class="empty">No library items found.</div>
            {% endif %}
        </main>
        """,
        default_hero=default_hero,
        continue_watching=continue_watching,
        shows=shows,
        movies=movies,
        recently_added=recently_added,
        most_watched=most_watched,
        unwatched=unwatched,
        hd_collection=hd_collection,
        vd3d_ready=vd3d_ready,
        genre_rows=genre_rows,
        random_pick=random_pick,
        query=request.args.get("q", ""),
        card_subtitle=card_subtitle,
        item_progress_percent=item_progress_percent,
        item_resume_label=item_resume_label,
    )

    return render_page("VisionVault Theater", body, hero_data=hero_data)


@app.route("/random")
def random_route():
    items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))
    playable = [x for x in items if can_play_item(x)]
    if not playable:
        return redirect(url_for("index"))
    pick = random.choice(playable)
    return redirect(url_for("item_page", item_id=int(pick["id"])))


@app.route("/shows")
def shows_page():
    q = (request.args.get("q") or "").strip().lower()
    all_items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))
    shows = [x for x in all_items if x.get("media_type") == "show"]

    if q:
        shows = [x for x in shows if q in (x.get("title") or "").lower()]

    hero_data = {str(item["id"]): build_hero_entry(item) for item in shows}

    body = render_template_string(
        """
        
{% macro media_card(item, autofocus=False) %}
<a class="card"
   href="{{ url_for('item_page', item_id=item['id']) }}"
   data-tv-focus="1"
   data-item-id="{{ item['id'] }}"
   {% if autofocus %}data-autofocus="1"{% endif %}>
    <div class="card-poster">
        <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
        <div class="card-overlay">
            {% if item['media_type'] == 'show' %}
                <span class="mini-badge">Open</span>
            {% elif item_progress_percent(item) > 0 %}
                <span class="mini-badge resume-badge">Resume {{ item_resume_label(item) }}</span>
            {% else %}
                <span class="mini-badge">Play</span>
            {% endif %}
            {% if item['resolution'] %}<span class="mini-badge">{{ item['resolution'] }}</span>{% endif %}
        </div>
        {% if item_progress_percent(item) > 0 %}
        <div class="card-progress"><div class="card-progress-fill" style="width: {{ item_progress_percent(item) }}%;"></div></div>
        {% endif %}
    </div>
    <div class="card-meta">
        <div class="card-title">{{ item['title'] }}</div>
        <div class="card-sub">{{ card_subtitle(item) }}</div>
    </div>
</a>
{% endmacro %}

        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1" data-tv-focus="1">← Back to Home</a>
            <div class="row-head" style="padding-left:0;padding-right:0; margin-bottom:18px;">
                <div><h2>All Shows</h2><div class="row-sub">{{ shows|length }} series</div></div>
            </div>
            <form class="searchbar" method="get" action="{{ url_for('shows_page') }}" style="padding-left:0;padding-right:0; padding-top:0; margin-bottom:22px;">
                <input class="search-input" type="text" name="q" value="{{ query }}" placeholder="Search shows...">
                <button class="search-btn" type="submit" data-tv-focus="1">Search</button>
            </form>
            {% if shows %}
            <div class="all-grid">{% for item in shows %}{{ media_card(item, autofocus=loop.first) }}{% endfor %}</div>
            {% else %}
            <div class="empty" style="margin-left:0;margin-right:0;">No shows found.</div>
            {% endif %}
        </div>
        """,
        shows=shows,
        query=request.args.get("q", ""),
        card_subtitle=card_subtitle,
        item_progress_percent=item_progress_percent,
        item_resume_label=item_resume_label,
    )

    return render_page("All Shows - VisionVault", body, hero_data=hero_data)


@app.route("/movies")
def movies_page():
    q = (request.args.get("q") or "").strip().lower()
    all_items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))
    movies = [x for x in all_items if (x.get("media_type") or "movie") == "movie"]

    if q:
        movies = [x for x in movies if q in (x.get("title") or "").lower()]

    hero_data = {str(item["id"]): build_hero_entry(item) for item in movies}

    body = render_template_string(
        """
        
{% macro media_card(item, autofocus=False) %}
<a class="card"
   href="{{ url_for('item_page', item_id=item['id']) }}"
   data-tv-focus="1"
   data-item-id="{{ item['id'] }}"
   {% if autofocus %}data-autofocus="1"{% endif %}>
    <div class="card-poster">
        <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
        <div class="card-overlay">
            {% if item['media_type'] == 'show' %}
                <span class="mini-badge">Open</span>
            {% elif item_progress_percent(item) > 0 %}
                <span class="mini-badge resume-badge">Resume {{ item_resume_label(item) }}</span>
            {% else %}
                <span class="mini-badge">Play</span>
            {% endif %}
            {% if item['resolution'] %}<span class="mini-badge">{{ item['resolution'] }}</span>{% endif %}
        </div>
        {% if item_progress_percent(item) > 0 %}
        <div class="card-progress"><div class="card-progress-fill" style="width: {{ item_progress_percent(item) }}%;"></div></div>
        {% endif %}
    </div>
    <div class="card-meta">
        <div class="card-title">{{ item['title'] }}</div>
        <div class="card-sub">{{ card_subtitle(item) }}</div>
    </div>
</a>
{% endmacro %}

        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1" data-tv-focus="1">← Back to Home</a>

            <div class="row-head" style="padding-left:0;padding-right:0; margin-bottom:18px;">
                <div>
                    <h2>All Movies</h2>
                    <div class="row-sub">{{ movies|length }} movie{{ '' if movies|length == 1 else 's' }}</div>
                </div>
                <a class="nav-chip" href="{{ url_for('random_route') }}" data-tv-focus="1">Random Pick</a>
            </div>

            <form class="searchbar" method="get" action="{{ url_for('movies_page') }}" style="padding-left:0;padding-right:0; padding-top:0; margin-bottom:22px;">
                <input class="search-input" type="text" name="q" value="{{ query }}" placeholder="Search movies...">
                <button class="search-btn" type="submit" data-tv-focus="1">Search</button>
            </form>

            {% if movies %}
            <div class="all-grid">
                {% for item in movies %}{{ media_card(item, autofocus=loop.first) }}{% endfor %}
            </div>
            {% else %}
            <div class="empty" style="margin-left:0;margin-right:0;">No movies found.</div>
            {% endif %}
        </div>
        """,
        movies=movies,
        query=request.args.get("q", ""),
        card_subtitle=card_subtitle,
        item_progress_percent=item_progress_percent,
        item_resume_label=item_resume_label,
    )

    return render_page("All Movies - VisionVault", body, hero_data=hero_data)

@app.route("/item/<int:item_id>")
def item_page(item_id: int):
    item = get_item(item_id)
    if not item:
        abort(404)

    episodes = []
    progress = None
    hero_data = {}
    resume_seconds = 0
    next_episode = None

    if item["media_type"] == "show":
        episodes = list_show_episodes(item_id)
        watched, total = get_show_progress(item_id)
        progress = {"watched": watched, "total": total}

        for ep in episodes:
            full = get_item(ep["id"]) or ep
            hero_data[str(full["id"])] = build_hero_entry(full)
    else:
        resume_seconds = int(get_resume_position(item_id) or 0)
        item["resume_seconds"] = resume_seconds
        next_episode = next_episode_for(item)

    chips = []
    if item.get("media_type"):
        chips.append(str(item["media_type"]).title())
    if item.get("year"):
        chips.append(str(item["year"]))
    if item.get("runtime_minutes"):
        chips.append(f"{item['runtime_minutes']} min")
    if item.get("resolution"):
        chips.append(str(item["resolution"]))
    if item.get("genres"):
        chips.extend([g.strip() for g in str(item["genres"]).split(",") if g.strip()][:5])

    body = render_template_string(
        """
        <div class="detail-hero-bg" style="background-image:url('{{ url_for('poster_for_item', item_id=item['id']) }}')"></div>
        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1" data-tv-focus="1">← Back to Home</a>

            <div class="detail-layout">
                <div class="detail-poster">
                    <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                </div>

                <div class="detail-panel">
                    <div class="eyebrow">Vault Details</div>
                    <h1 class="detail-title">{{ item['title'] }}</h1>

                    <div class="chip-line">
                        {% for chip in chips %}<span class="detail-chip">{{ chip }}</span>{% endfor %}
                        {% if progress %}<span class="detail-chip">{{ progress['watched'] }}/{{ progress['total'] }} watched</span>{% endif %}
                        <span class="detail-chip">Watched {{ item['watch_count'] }}x</span>
                    </div>

                    {% if resume_seconds > 5 %}
                    <div class="hero-progress" style="display:block;">
                        <div class="progress-caption"><span>Resume at {{ resume_label }}</span><span>{{ item_progress_percent(item) }}%</span></div>
                        <div class="progress-track"><div class="progress-fill" style="width: {{ item_progress_percent(item) }}%;"></div></div>
                    </div>
                    {% endif %}

                    <div class="detail-overview">{{ item['overview'] or 'No overview yet.' }}</div>

                    <div class="detail-actions">
                        {% if item['media_type'] != 'show' %}
                            {% if resume_seconds > 5 %}
                                <a class="hero-btn primary" href="{{ url_for('player_page', item_id=item['id']) }}" data-tv-focus="1" data-autofocus="1">Resume</a>
                                <a class="hero-btn secondary" href="{{ url_for('restart_route', item_id=item['id']) }}" data-tv-focus="1">Start Over</a>
                            {% else %}
                                <a class="hero-btn primary" href="{{ url_for('player_page', item_id=item['id']) }}" data-tv-focus="1" data-autofocus="1">Play</a>
                            {% endif %}
                            <a class="hero-btn secondary" href="{{ url_for('watch_route', item_id=item['id']) }}" data-tv-focus="1">Mark Watched</a>
                            {% if next_episode %}
                                <a class="hero-btn secondary" href="{{ url_for('item_page', item_id=next_episode['id']) }}" data-tv-focus="1">Next Episode</a>
                            {% endif %}
                        {% endif %}
                    </div>
                </div>
            </div>

            {% if episodes %}
            <section class="row-section">
                <div class="row-head" style="padding-left:0;padding-right:0;">
                    <div>
                        <h2>Episodes</h2>
                        <div class="row-sub">{{ episodes|length }} episode{{ '' if episodes|length == 1 else 's' }}</div>
                    </div>
                </div>

                <div class="episode-list">
                    {% for ep in episodes %}
                    <a class="episode-card" href="{{ url_for('item_page', item_id=ep['id']) }}" data-tv-focus="1" data-item-id="{{ ep['id'] }}" {% if loop.first %}data-autofocus="1"{% endif %}>
                        <div class="episode-title">S{{ "%02d"|format(ep['season'] or 0) }}E{{ "%02d"|format(ep['episode'] or 0) }} • {{ ep['title'] }}</div>
                        <div class="episode-sub">
                            Watched {{ ep['watch_count'] }}x
                            {% if ep['resolution'] %} • {{ ep['resolution'] }}{% endif %}
                            {% if ep['runtime_minutes'] %} • {{ ep['runtime_minutes'] }} min{% endif %}
                            {% if item_progress_percent(ep) > 0 %} • Resume {{ item_resume_label(ep) }}{% endif %}
                        </div>
                        {% if item_progress_percent(ep) > 0 %}
                        <div class="progress-track" style="margin-top:12px;"><div class="progress-fill" style="width: {{ item_progress_percent(ep) }}%;"></div></div>
                        {% endif %}
                    </a>
                    {% endfor %}
                </div>
            </section>
            {% endif %}
        </div>
        """,
        item=item,
        episodes=episodes,
        progress=progress,
        resume_seconds=resume_seconds,
        resume_label=format_seconds_label(resume_seconds),
        chips=chips,
        next_episode=next_episode,
        item_progress_percent=item_progress_percent,
        item_resume_label=item_resume_label,
    )

    return render_page(f"{item['title']} - VisionVault", body, hero_data=hero_data)

@app.route("/stats")
def stats_page():
    stats = get_stats()

    body = render_template_string(
        """
        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1">← Back to Home</a>

            <h1 class="detail-title" style="margin-bottom:12px;">Library Stats</h1>
            <div class="detail-meta">Quick totals for your local collection.</div>

            <div class="stats-grid">
                <div class="stat-card"><div class="stat-label">Movies</div><div class="stat-value">{{ stats.movies_total }}</div></div>
                <div class="stat-card"><div class="stat-label">Shows</div><div class="stat-value">{{ stats.shows_total }}</div></div>
                <div class="stat-card"><div class="stat-label">Episodes</div><div class="stat-value">{{ stats.episodes_total }}</div></div>
                <div class="stat-card"><div class="stat-label">Movies Watched</div><div class="stat-value">{{ stats.movies_watched }}</div></div>
                <div class="stat-card"><div class="stat-label">Episodes Watched</div><div class="stat-value">{{ stats.episodes_watched }}</div></div>
                <div class="stat-card"><div class="stat-label">Movie Watch Total</div><div class="stat-value">{{ stats.movies_watch_total }}</div></div>
                <div class="stat-card"><div class="stat-label">Episode Watch Total</div><div class="stat-value">{{ stats.episodes_watch_total }}</div></div>
            </div>
        </div>
        """,
        stats=stats,
    )

    return render_page("VisionVault Stats", body, hero_data={})

def empty_options_response():
    response = make_response("", 204)
    return response

@app.route("/watch/<int:item_id>")
def watch_route(item_id: int):
    increment_watch(item_id)
    return redirect(url_for("item_page", item_id=item_id))

@app.route("/api/watch-progress/<int:item_id>", methods=["POST"])
def watch_progress_route(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Item not found"}), 404

    if (item.get("media_type") or "") == "show":
        return jsonify({"ok": False, "error": "Shows are not directly watchable"}), 400

    increment_watch(item_id)
    return jsonify({"ok": True})
    
@app.route("/api/progress/<int:item_id>/clear", methods=["POST"])
def clear_progress_route(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404

    clear_resume_position(item_id)
    increment_watch(item_id)
    return jsonify({"ok": True})

@app.route("/brand-logo")
def brand_logo():
    logo_path = brand_logo_path()
    if not logo_path:
        abort(404)
    return send_file(logo_path)

@app.route("/api/progress/<int:item_id>", methods=["POST"])
def save_progress_route(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Item not found"}), 404

    if (item.get("media_type") or "") == "show":
        return jsonify({"ok": False, "error": "Shows are not directly watchable"}), 400

    data = request.get_json(silent=True) or {}
    seconds = int(data.get("seconds") or 0)

    if seconds < 0:
        seconds = 0

    save_resume_position(item_id, seconds)

    if seconds > 5:
        touch_last_watched(item_id)

    return jsonify({"ok": True, "seconds": seconds})

@app.route("/play/<int:item_id>")
def play_route(item_id: int):
    ok, msg = play_item(item_id)
    if ok:
        return redirect(url_for("item_page", item_id=item_id))
    return f"<h1>Playback error</h1><p>{msg}</p><p><a href='{url_for('item_page', item_id=item_id)}'>Back</a></p>", 400

@app.route("/subtitles/<int:item_id>")
def subtitles_route(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return ("", 404)

    subtitle_path = find_subtitle_file_for_video(file_path)
    if not subtitle_path:
        return ("", 404)

    ext = Path(subtitle_path).suffix.lower()

    try:
        if ext == ".vtt":
            return send_file(
                subtitle_path,
                mimetype="text/vtt",
                as_attachment=False
            )

        if ext == ".srt":
            with open(subtitle_path, "r", encoding="utf-8-sig", errors="replace") as f:
                srt_text = f.read()

            vtt_text = srt_to_vtt_text(srt_text)
            return Response(vtt_text, mimetype="text/vtt")

    except Exception:
        return ("", 500)

    return ("", 404)

@app.route("/stream/<int:item_id>")
def stream_route(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return "No playable file found for this item.", 404

    return build_stream_response(file_path)

@app.route("/player/<int:item_id>")
def player_page(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return f"<h1>Playback error</h1><p>No playable file found for this item.</p><p><a href='{url_for('item_page', item_id=item_id)}'>Back</a></p>", 404

    hero_data = {}
    resume_seconds = int(get_resume_position(item_id) or 0)
    subtitle_path = find_subtitle_file_for_video(file_path)
    has_subtitles = bool(subtitle_path)
    next_episode = next_episode_for(item)

    body = render_template_string(
        """
        <div class="player-page">
            <div class="player-top">
                <div>
                    <a class="back-link" href="{{ url_for('item_page', item_id=item['id']) }}" data-back-link="1" data-tv-focus="1">← Back to Details</a>
                    <div class="player-title">{{ item['title'] }}</div>
                </div>
                <div class="player-actions">
                    <button class="hero-btn secondary" id="restart-btn" type="button" data-tv-focus="1">Restart</button>
                    <button class="hero-btn secondary" id="back10-btn" type="button" data-tv-focus="1">-10s</button>
                    <button class="hero-btn secondary" id="forward30-btn" type="button" data-tv-focus="1">+30s</button>
                    {% if next_episode %}<a class="hero-btn primary" href="{{ url_for('player_page', item_id=next_episode['id']) }}" data-tv-focus="1">Next Episode</a>{% endif %}
                </div>
            </div>

            <div class="player-frame">
                <video id="vv-player" controls autoplay playsinline data-tv-focus="1" data-autofocus="1">
                    <source src="{{ url_for('stream_route', item_id=item['id']) }}" type="{{ mime_type }}">
                    {% if has_subtitles %}
                    <track kind="subtitles" src="{{ url_for('subtitles_route', item_id=item['id']) }}" srclang="en" label="English" default>
                    {% endif %}
                    Your browser does not support video playback.
                </video>

                {% if next_episode %}
                <div class="next-episode-card" id="next-card">
                    <div class="next-title">Next Episode</div>
                    <div class="next-sub">S{{ "%02d"|format(next_episode['season'] or 0) }}E{{ "%02d"|format(next_episode['episode'] or 0) }} • {{ next_episode['title'] }}</div>
                    <div class="player-actions">
                        <a class="hero-btn primary" href="{{ url_for('player_page', item_id=next_episode['id']) }}" data-tv-focus="1">Play Now</a>
                        <button class="hero-btn secondary" id="cancel-next-btn" type="button" data-tv-focus="1">Cancel</button>
                    </div>
                </div>
                {% endif %}
            </div>

            <div class="detail-meta">
                {% if item['resolution'] %}Resolution: {{ item['resolution'] }} • {% endif %}
                {% if item['runtime_minutes'] %}Runtime: {{ item['runtime_minutes'] }} min • {% endif %}
                {% if has_subtitles %}Subtitles detected • {% endif %}
                Progress saves automatically.
            </div>
        </div>

        <script>
            window.addEventListener("load", function() {
                const player = document.getElementById("vv-player");
                if (!player) return;

                const itemId = {{ item['id'] }};
                const resumeSeconds = {{ resume_seconds }};
                const nextUrl = {% if next_episode %}"{{ url_for('player_page', item_id=next_episode['id']) }}"{% else %}""{% endif %};
                let lastSavedSecond = -1;
                let completed = false;
                let resumeApplied = false;
                let nextCountdownStarted = false;

                player.focus();

                function applyResume() {
                    if (resumeApplied) return;
                    if (!(resumeSeconds > 5)) return;
                    if (!player.duration || !isFinite(player.duration)) return;
                    if (resumeSeconds >= (player.duration - 10)) return;
                    try {
                        player.currentTime = resumeSeconds;
                        resumeApplied = true;
                    } catch (err) {
                        console.log("Resume seek failed", err);
                    }
                }

                player.addEventListener("loadedmetadata", applyResume);
                player.addEventListener("canplay", applyResume);
                player.addEventListener("loadeddata", applyResume);

                function saveProgress() {
                    if (!player.duration || completed) return;
                    const current = Math.floor(player.currentTime || 0);
                    if (current < 1) return;
                    if (current === lastSavedSecond) return;
                    lastSavedSecond = current;
                    fetch(`/api/progress/${itemId}`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ seconds: current })
                    }).catch(err => console.log("Save progress failed:", err));
                }

                function markComplete() {
                    if (completed) return;
                    completed = true;
                    fetch(`/api/progress/${itemId}/clear`, { method: "POST" })
                        .catch(err => console.log("Clear progress failed:", err));
                }

                function showNextCard() {
                    if (!nextUrl || nextCountdownStarted) return;
                    nextCountdownStarted = true;
                    const card = document.getElementById("next-card");
                    if (card) card.classList.add("show");
                    setTimeout(function() {
                        if (nextCountdownStarted) window.location.href = nextUrl;
                    }, 10000);
                }

                setInterval(function() {
                    if (!player.paused && !player.ended) {
                        saveProgress();
                        if (player.duration > 0) {
                            const pct = player.currentTime / player.duration;
                            if (pct >= 0.95) {
                                markComplete();
                                showNextCard();
                            }
                        }
                    }
                }, 5000);

                player.addEventListener("pause", saveProgress);
                player.addEventListener("ended", function() {
                    markComplete();
                    showNextCard();
                });
                window.addEventListener("beforeunload", saveProgress);

                const restartBtn = document.getElementById("restart-btn");
                const back10Btn = document.getElementById("back10-btn");
                const forward30Btn = document.getElementById("forward30-btn");
                const cancelNextBtn = document.getElementById("cancel-next-btn");

                if (restartBtn) restartBtn.addEventListener("click", function() { player.currentTime = 0; player.play(); });
                if (back10Btn) back10Btn.addEventListener("click", function() { player.currentTime = Math.max(0, player.currentTime - 10); });
                if (forward30Btn) forward30Btn.addEventListener("click", function() { player.currentTime = Math.min(player.duration || player.currentTime + 30, player.currentTime + 30); });
                if (cancelNextBtn) cancelNextBtn.addEventListener("click", function() {
                    nextCountdownStarted = false;
                    const card = document.getElementById("next-card");
                    if (card) card.classList.remove("show");
                });
            });

            document.addEventListener("keydown", function(e) {
                const player = document.getElementById("vv-player");
                if (!player) return;

                if (e.key === "Escape" || e.key === "Backspace") {
                    e.preventDefault();
                    try {
                        player.pause();
                        player.removeAttribute("src");
                        const source = player.querySelector("source");
                        if (source) source.removeAttribute("src");
                        player.load();
                    } catch (err) {
                        console.log("Player cleanup failed:", err);
                    }
                    window.location.href = "{{ url_for('item_page', item_id=item['id']) }}";
                } else if (e.key === "ArrowLeft") {
                    player.currentTime = Math.max(0, player.currentTime - 10);
                } else if (e.key === "ArrowRight") {
                    player.currentTime = Math.min(player.duration || player.currentTime + 30, player.currentTime + 30);
                }
            });
        </script>
        """,
        item=item,
        mime_type=guess_mime_type(file_path),
        resume_seconds=resume_seconds,
        has_subtitles=has_subtitles,
        next_episode=next_episode,
    )

    return render_page(f"Playing {item['title']}", body, hero_data=hero_data)

@app.route("/poster/<int:item_id>")
def poster_for_item(item_id: int):
    item = get_item(item_id)
    if not item:
        abort(404)

    animated_path = resolve_existing_path(item.get("animated_poster_path"))
    if animated_path and Path(animated_path).exists():
        ext = Path(animated_path).suffix.lower()
        if ext in [".gif", ".webp", ".png", ".jpg", ".jpeg"]:
            return send_file(animated_path)

    poster_path = resolve_existing_path(item.get("poster_path"))
    if poster_path and Path(poster_path).exists():
        return send_file(poster_path)

    fallback = POSTERS / "__vv_placeholder__.jpg"
    if not fallback.exists():
        from PIL import Image, ImageDraw
        canvas = Image.new("RGB", (300, 450), (40, 40, 40))
        draw = ImageDraw.Draw(canvas)
        draw.text((90, 210), "No Poster", fill=(220, 220, 220))
        canvas.save(fallback, "JPEG", quality=90)

    return send_file(fallback)

@app.route("/animated_poster/<int:item_id>")
def animated_poster_for_item(item_id: int):
    item = get_item(item_id)
    if not item:
        abort(404)

    animated_path = resolve_existing_path(item.get("animated_poster_path"))
    if not animated_path or not Path(animated_path).exists():
        return ("", 404)

    return send_file(animated_path)

@app.route("/restart/<int:item_id>")
def restart_route(item_id: int):
    clear_resume_position(item_id)
    return redirect(url_for("player_page", item_id=item_id))

@app.route("/api/library")
def api_library():
    search_term = (request.args.get("q") or "").strip()
    items = list_movies(sort_key="title_asc", nav_mode="root", search_term=search_term)
    full_items = [(get_item(int(x["id"])) or x) for x in items]
    return jsonify(serialize_items(full_items))


@app.route("/api/item/<int:item_id>")
def api_item(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404

    data = serialize_item(item)

    if item.get("media_type") == "show":
        episodes = list_show_episodes(item_id)
        episodes_full = [(get_item(int(x["id"])) or x) for x in episodes]
        data["episodes"] = serialize_items(episodes_full)
    else:
        data["episodes"] = []

    return jsonify(data)

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "ok": True,
        "app": "VisionVault",
        "server_time": datetime.utcnow().isoformat() + "Z"
    })
    
@app.route("/api/home", methods=["GET"])
def api_home():
    root_items = list_movies(sort_key="title_asc", nav_mode="root")
    root_items_full = [(get_item(int(x["id"])) or x) for x in root_items]

    movies = [x for x in root_items_full if (x.get("media_type") or "movie") == "movie"]
    shows = [x for x in root_items_full if x.get("media_type") == "show"]
    continue_items = continue_watching_items()

    return jsonify({
        "continue_watching": serialize_items(continue_items),
        "movies": serialize_items(movies),
        "shows": serialize_items(shows),
    })
    
@app.route("/api/movies", methods=["GET"])
def api_movies():
    items = list_movies(sort_key="title_asc", nav_mode="root")
    full_items = [(get_item(int(x["id"])) or x) for x in items]
    movies = [x for x in full_items if (x.get("media_type") or "movie") == "movie"]
    return jsonify(serialize_items(movies))
    
@app.route("/api/shows", methods=["GET"])
def api_shows():
    items = list_movies(sort_key="title_asc", nav_mode="root")
    full_items = [(get_item(int(x["id"])) or x) for x in items]
    shows = [x for x in full_items if x.get("media_type") == "show"]
    return jsonify(serialize_items(shows))    
    
@app.route("/api/show/<int:show_id>/episodes", methods=["GET"])
def api_show_episodes(show_id: int):
    show_item = get_item(show_id)
    if not show_item or show_item.get("media_type") != "show":
        return jsonify({"error": "show not found"}), 404

    episodes = list_show_episodes(show_id)
    episodes_full = [(get_item(int(x["id"])) or x) for x in episodes]
    return jsonify(serialize_items(episodes_full))

@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(get_stats())

@app.route("/api/resume/<int:item_id>", methods=["GET"])
def api_resume(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404

    return jsonify({
        "item_id": item_id,
        "resume_seconds": float(get_resume_position(item_id) or 0)
    })

@app.route("/api/stream/<int:item_id>", methods=["GET"])
def stream_item(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return jsonify({"error": "media file missing"}), 404

    return build_stream_response(file_path)

_server = None
_server_thread = None


def start_tv_server_thread(host="0.0.0.0", port=5050):
    global _server, _server_thread

    if _server is not None:
        return True, f"TV server already running on {host}:{port}"

    try:
        _server = make_server(host, port, app, threaded=True)
        _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _server_thread.start()
        return True, f"TV server started on {host}:{port}"
    except Exception as e:
        _server = None
        _server_thread = None
        return False, f"Could not start TV server: {e}"


def stop_tv_server():
    global _server, _server_thread

    if _server is None:
        return False, "TV server is not running."

    try:
        _server.shutdown()
        _server.server_close()
        _server = None
        _server_thread = None
        return True, "TV server stopped."
    except Exception as e:
        return False, f"Could not stop TV server: {e}"
