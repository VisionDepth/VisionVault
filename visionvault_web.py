from pathlib import Path
from datetime import datetime

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_file, url_for, Response, stream_with_context
import mimetypes
import os

from vault_core import (
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
)

app = Flask(__name__)


PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ page_title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --bg: #0b0d11;
            --bg2: #10141b;
            --panel: rgba(15, 18, 24, 0.92);
            --card: #171b22;
            --card2: #1c2129;
            --text: #f3f6fb;
            --muted: #b6c0ce;
            --accent: #3a95ff;
            --accent2: #7fb9ff;
            --border: #2a3240;
            --shadow: rgba(0, 0, 0, 0.42);
        }

        * { box-sizing: border-box; }

        html, body {
            margin: 0;
            padding: 0;
            background:
                radial-gradient(circle at top, #162033 0%, #0d1118 30%, #090b0f 100%);
            color: var(--text);
            font-family: Arial, Helvetica, sans-serif;
            min-height: 100%;
        }

        body {
            overflow-x: hidden;
        }

        a {
            color: inherit;
            text-decoration: none;
        }

        .shell {
            min-height: 100vh;
        }

        .hero {
            position: relative;
            min-height: 560px;
            overflow: hidden;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }

        .hero-bg {
            position: absolute;
            inset: 0;
            background-size: cover;
            background-position: center 22%;
            filter: blur(0px);
            transform: scale(1.04);
            opacity: 0.28;
            transition: background-image 0.22s ease, opacity 0.22s ease;
        }

        .hero-overlay {
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, rgba(8,10,14,0.95) 0%, rgba(8,10,14,0.88) 34%, rgba(8,10,14,0.52) 58%, rgba(8,10,14,0.80) 100%),
                linear-gradient(180deg, rgba(7,9,13,0.25) 0%, rgba(7,9,13,0.70) 65%, rgba(7,9,13,0.98) 100%);
        }

        .topbar {
            position: relative;
            z-index: 3;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 18px;
            padding: 28px 38px 0 38px;
            flex-wrap: wrap;
        }

        .brand h1 {
            margin: 0;
            font-size: 56px;
            letter-spacing: -1.6px;
        }

        .brand p {
            margin: 8px 0 0 0;
            color: var(--muted);
            font-size: 18px;
        }

        .top-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .pill,
        .hero-btn,
        .nav-chip,
        .search-input,
        .search-btn {
            border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(20,24,31,0.86);
            color: var(--text);
            backdrop-filter: blur(10px);
        }

        .nav-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 12px 16px;
            font-size: 15px;
            min-width: 96px;
        }

        .nav-chip:hover {
            border-color: var(--accent);
        }

        .searchbar {
            position: relative;
            z-index: 3;
            display: flex;
            gap: 10px;
            align-items: center;
            padding: 20px 38px 0 38px;
            flex-wrap: wrap;
        }

        .search-input {
            width: min(720px, 100%);
            max-width: 720px;
            padding: 15px 16px;
            font-size: 17px;
            outline: none;
        }

        .search-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(58,149,255,0.18);
        }

        .search-btn {
            cursor: pointer;
            padding: 15px 18px;
            font-size: 16px;
        }

        .search-btn:hover {
            border-color: var(--accent);
        }

        .hero-content {
            position: relative;
            z-index: 3;
            display: grid;
            grid-template-columns: 280px 1fr;
            gap: 28px;
            align-items: end;
            padding: 26px 38px 42px 38px;
        }

        .hero-poster {
            width: 280px;
            aspect-ratio: 2 / 3;
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 18px 46px var(--shadow);
            background: #1c2129;
            border: 1px solid rgba(255,255,255,0.10);
        }

        .hero-poster img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .hero-copy {
            max-width: 920px;
        }

        .eyebrow {
            display: inline-block;
            color: #d1def0;
            font-size: 14px;
            letter-spacing: 1.6px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }

        .hero-title {
            margin: 0;
            font-size: 62px;
            line-height: 0.95;
            letter-spacing: -2px;
        }

        .hero-meta {
            margin-top: 18px;
            color: var(--muted);
            font-size: 20px;
            line-height: 1.7;
        }

        .hero-overview {
            margin-top: 18px;
            color: #edf2f8;
            font-size: 20px;
            line-height: 1.65;
            max-width: 900px;
        }

        .hero-actions {
            margin-top: 24px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .hero-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 150px;
            padding: 15px 18px;
            font-size: 17px;
            cursor: pointer;
            transition: 0.15s ease;
        }

        .hero-btn.primary {
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
        }

        .hero-btn.primary:hover {
            background: #2b86f5;
            border-color: #2b86f5;
        }

        .hero-btn.secondary:hover {
            border-color: var(--accent);
        }

        .main {
            padding: 18px 0 46px 0;
        }

        .row-section {
            margin-top: 22px;
        }

        .row-head {
            display: flex;
            justify-content: space-between;
            align-items: end;
            gap: 14px;
            padding: 0 38px;
            margin-bottom: 14px;
        }

        .row-head h2 {
            margin: 0;
            font-size: 30px;
            letter-spacing: -0.8px;
        }

        .row-sub {
            color: var(--muted);
            font-size: 15px;
        }

        .media-row-wrap {
            position: relative;
        }

        .media-row {
            display: flex;
            gap: 18px;
            overflow-x: auto;
            overflow-y: hidden;
            padding: 4px 38px 16px 38px;
            scroll-behavior: smooth;
            scrollbar-width: thin;
            scrollbar-color: #3a95ff #111827;
        }

        .media-row::-webkit-scrollbar {
            height: 10px;
        }

        .media-row::-webkit-scrollbar-track {
            background: #111827;
            border-radius: 999px;
        }

        .media-row::-webkit-scrollbar-thumb {
            background: #3a95ff;
            border-radius: 999px;
        }
        .card {
            flex: 0 0 230px;
            width: 230px;
            border-radius: 22px;
            overflow: hidden;
            background: linear-gradient(180deg, #1b2028 0%, #161a21 100%);
            border: 2px solid transparent;
            box-shadow: 0 12px 28px rgba(0,0,0,0.35);
            transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
            outline: none;
        }

        .card:hover,
        .card:focus,
        .card.tv-focused {
            transform: translateY(-3px) scale(1.02);
            border-color: var(--accent2);
            box-shadow: 0 18px 38px rgba(0,0,0,0.48), 0 0 0 2px rgba(127,185,255,0.12);
        }

        .card-poster {
            width: 100%;
            aspect-ratio: 2 / 3;
            background: #222831;
        }

        .card-poster img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .card-meta {
            padding: 14px 14px 16px 14px;
        }

        .card-title {
            font-size: 18px;
            font-weight: bold;
            line-height: 1.25;
            min-height: 44px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .card-sub {
            margin-top: 10px;
            color: var(--muted);
            font-size: 14px;
            line-height: 1.45;
        }

        .all-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
            gap: 20px;
            align-items: start;
        }

        .grid-card {
            width: 100%;
            flex: unset;
        }

        .details-page {
            padding: 30px 38px 50px 38px;
        }

        .back-link {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            color: #cde4ff;
            font-size: 17px;
            margin-bottom: 18px;
        }

        .detail-layout {
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 28px;
            align-items: start;
        }

        .detail-poster {
            width: 320px;
            aspect-ratio: 2 / 3;
            border-radius: 24px;
            overflow: hidden;
            background: #1b2028;
            box-shadow: 0 18px 46px var(--shadow);
            border: 1px solid rgba(255,255,255,0.10);
        }

        .detail-poster img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .detail-panel {
            background: linear-gradient(180deg, #171c24 0%, #12171e 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 24px;
            padding: 26px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.30);
        }

        .detail-title {
            margin: 0;
            font-size: 48px;
            letter-spacing: -1px;
        }

        .detail-meta {
            margin-top: 16px;
            color: var(--muted);
            font-size: 18px;
            line-height: 1.7;
        }

        .detail-overview {
            margin-top: 18px;
            font-size: 19px;
            line-height: 1.75;
            white-space: pre-wrap;
        }

        .detail-actions {
            margin-top: 22px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .episode-list {
            margin-top: 26px;
            display: grid;
            gap: 14px;
        }

        .episode-card {
            display: block;
            background: linear-gradient(180deg, #171c24 0%, #12171e 100%);
            border: 2px solid transparent;
            border-radius: 18px;
            padding: 18px;
            transition: 0.15s ease;
            outline: none;
        }

        .episode-card:hover,
        .episode-card:focus,
        .episode-card.tv-focused {
            border-color: var(--accent2);
            transform: translateY(-2px);
        }

        .episode-title {
            font-size: 21px;
            font-weight: bold;
        }

        .episode-sub {
            margin-top: 8px;
            color: var(--muted);
            font-size: 15px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 18px;
        }

        .stat-card {
            background: linear-gradient(180deg, #171c24 0%, #12171e 100%);
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 20px;
        }

        .stat-label {
            color: var(--muted);
            font-size: 14px;
        }

        .stat-value {
            margin-top: 10px;
            font-size: 36px;
            font-weight: bold;
        }

        .empty {
            margin: 18px 38px;
            padding: 24px;
            border-radius: 18px;
            background: linear-gradient(180deg, #171c24 0%, #12171e 100%);
            color: var(--muted);
            font-size: 18px;
        }

        .helper {
            padding: 0 38px;
            color: var(--muted);
            font-size: 14px;
        }

        @media (max-width: 1200px) {
            .hero-content {
                grid-template-columns: 240px 1fr;
            }

            .hero-poster {
                width: 240px;
            }

            .hero-title {
                font-size: 52px;
            }
        }

        @media (max-width: 900px) {
            .hero-content,
            .detail-layout {
                grid-template-columns: 1fr;
            }

            .hero-poster,
            .detail-poster {
                width: min(320px, 100%);
            }

            .hero-title {
                font-size: 44px;
            }

            .brand h1 {
                font-size: 42px;
            }
        }

        @media (max-width: 700px) {
            .topbar,
            .searchbar,
            .row-head,
            .media-row,
            .details-page,
            .helper {
                padding-left: 18px !important;
                padding-right: 18px !important;
            }

            .hero-content {
                padding-left: 18px;
                padding-right: 18px;
            }

            .card {
                flex-basis: 180px;
                width: 180px;
            }

            .hero-title {
                font-size: 38px;
            }
        }
    </style>
</head>
<body>
    <div class="shell">
        {{ body|safe }}
    </div>

    <script>
        const HERO_DATA = {{ hero_data|safe }};

        function byId(id) {
            return document.getElementById(id);
        }

        function updateHeroFromCard(card) {
            if (!card) return;
            const itemId = card.getAttribute("data-item-id");
            if (!itemId || !HERO_DATA[itemId]) return;

            const data = HERO_DATA[itemId];

            if (byId("hero-bg")) {
                byId("hero-bg").style.backgroundImage = `url("${data.poster_url}")`;
            }
            if (byId("hero-poster-img")) {
                byId("hero-poster-img").src = data.poster_url;
            }
            if (byId("hero-type")) {
                byId("hero-type").textContent = data.type_label;
            }
            if (byId("hero-title")) {
                byId("hero-title").textContent = data.title;
            }
            if (byId("hero-meta")) {
                byId("hero-meta").textContent = data.meta_line;
            }
            if (byId("hero-overview")) {
                byId("hero-overview").textContent = data.overview;
            }
            if (byId("hero-open")) {
                byId("hero-open").href = data.detail_url;
                byId("hero-open").setAttribute("data-item-id", itemId);
            }
            if (byId("hero-play")) {
                if (data.can_play) {
                    byId("hero-play").style.display = "inline-flex";
                    byId("hero-play").href = data.play_url;
                } else {
                    byId("hero-play").style.display = "none";
                    byId("hero-play").removeAttribute("href");
                }
            }
        }

        function getFocusable() {
            return Array.from(document.querySelectorAll("[data-tv-focus='1']"));
        }

        function getRows() {
            return Array.from(document.querySelectorAll(".media-row, .episode-list"));
        }

        function getRowItems(row) {
            if (!row) return [];
            return Array.from(row.querySelectorAll("[data-tv-focus='1']"));
        }

        function getCurrentFocused() {
            const active = document.activeElement;
            if (active && active.matches("[data-tv-focus='1']")) return active;
            return document.querySelector(".tv-focused");
        }

        function scrollRowToItem(row, el) {
            if (!row || !el) return;

            const elLeft = el.offsetLeft;
            const elRight = elLeft + el.offsetWidth;
            const viewLeft = row.scrollLeft;
            const viewRight = viewLeft + row.clientWidth;

            const pad = 24;

            if (elLeft - pad < viewLeft) {
                row.scrollTo({
                    left: Math.max(0, elLeft - pad),
                    behavior: "smooth"
                });
            } else if (elRight + pad > viewRight) {
                row.scrollTo({
                    left: elRight - row.clientWidth + pad,
                    behavior: "smooth"
                });
            }
        }

        function setFocus(el) {
            if (!el) return;

            getFocusable().forEach(x => x.classList.remove("tv-focused"));
            el.classList.add("tv-focused");
            el.focus({ preventScroll: true });

            const row = el.closest(".media-row, .episode-list");
            if (row && row.classList.contains("media-row")) {
                scrollRowToItem(row, el);
            }

            el.scrollIntoView({
                block: "nearest",
                inline: "nearest",
                behavior: "smooth"
            });

            if (el.hasAttribute("data-item-id")) {
                updateHeroFromCard(el);
            }
        }

        function focusFirstCard() {
            const auto = document.querySelector("[data-autofocus='1']");
            if (auto) {
                setFocus(auto);
                return;
            }
            const all = getFocusable();
            if (all.length) setFocus(all[0]);
        }

        function findRowIndexForElement(el) {
            const row = el.closest(".media-row, .episode-list");
            const rows = getRows();
            return rows.indexOf(row);
        }

        function moveHorizontal(direction) {
            const current = getCurrentFocused();
            if (!current) {
                focusFirstCard();
                return;
            }

            const row = current.closest(".media-row, .episode-list");
            if (row) {
                const items = getRowItems(row);
                if (!items.length) return;

                const idx = items.indexOf(current);
                if (idx === -1) {
                    setFocus(items[0]);
                    return;
                }

                const nextIdx = idx + direction;
                if (nextIdx >= 0 && nextIdx < items.length) {
                    setFocus(items[nextIdx]);
                }
                return;
            }

            const grid = current.closest(".all-grid");
            if (grid) {
                const items = Array.from(grid.querySelectorAll("[data-tv-focus='1']"));
                const idx = items.indexOf(current);
                if (idx === -1) return;

                const nextIdx = idx + direction;
                if (nextIdx >= 0 && nextIdx < items.length) {
                    setFocus(items[nextIdx]);
                }
            }
        }

        function moveVertical(direction) {
            const current = getCurrentFocused();
            if (!current) {
                focusFirstCard();
                return;
            }

            const currentRow = current.closest(".media-row, .episode-list");
            if (currentRow) {
                const rows = getRows();
                const rowIndex = rows.indexOf(currentRow);
                if (rowIndex === -1) return;

                const currentItems = getRowItems(currentRow);
                const currentIdx = Math.max(0, currentItems.indexOf(current));

                const targetRowIndex = rowIndex + direction;
                if (targetRowIndex < 0 || targetRowIndex >= rows.length) return;

                const targetRow = rows[targetRowIndex];
                const targetItems = getRowItems(targetRow);
                if (!targetItems.length) return;

                const clampedIdx = Math.min(currentIdx, targetItems.length - 1);
                setFocus(targetItems[clampedIdx]);
                return;
            }

            const grid = current.closest(".all-grid");
            if (grid) {
                const items = Array.from(grid.querySelectorAll("[data-tv-focus='1']"));
                const idx = items.indexOf(current);
                if (idx === -1) return;

                const cols = Math.max(1, Math.floor(grid.clientWidth / 250));
                const nextIdx = idx + (direction * cols);

                if (nextIdx >= 0 && nextIdx < items.length) {
                    setFocus(items[nextIdx]);
                }
            }
        }

        document.addEventListener("focusin", function(e) {
            const target = e.target;
            if (target && target.matches("[data-tv-focus='1']")) {
                getFocusable().forEach(x => x.classList.remove("tv-focused"));
                target.classList.add("tv-focused");

                const row = target.closest(".media-row, .episode-list");
                if (row && row.classList.contains("media-row")) {
                    scrollRowToItem(row, target);
                }

                if (target.hasAttribute("data-item-id")) {
                    updateHeroFromCard(target);
                }
            }
        });

        document.addEventListener("keydown", function(e) {
            const active = document.activeElement;
            const isInput = active && (
                active.tagName === "INPUT" ||
                active.tagName === "TEXTAREA" ||
                active.tagName === "SELECT"
            );

            if (isInput && e.key !== "Escape") {
                return;
            }

            const all = getFocusable();
            if (!all.length) return;

            if (e.key === "ArrowRight") {
                e.preventDefault();
                moveHorizontal(1);
            } else if (e.key === "ArrowLeft") {
                e.preventDefault();
                moveHorizontal(-1);
            } else if (e.key === "ArrowDown") {
                e.preventDefault();
                moveVertical(1);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                moveVertical(-1);
            } else if (e.key === "Enter") {
                const current = getCurrentFocused();
                if (current && typeof current.click === "function") {
                    e.preventDefault();
                    current.click();
                }
            } else if (e.key === "Backspace" || e.key === "Escape") {
                const back = document.querySelector("[data-back-link='1']");
                if (back) {
                    e.preventDefault();
                    window.location.href = back.getAttribute("href");
                }
            } else if (e.key === "/") {
                const input = document.querySelector(".search-input");
                if (input) {
                    e.preventDefault();
                    input.focus();
                    input.select();
                }
            }
        });

        window.addEventListener("load", function() {
            focusFirstCard();
        });
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
    item_id = item["id"]
    media_type = item.get("media_type") or "movie"

    if media_type == "show":
        watched, total = get_show_progress(item_id)
        meta_parts = [
            "Show",
            f"{watched}/{total} watched"
        ]
        type_label = "Series"
        can_play = False
    else:
        meta_parts = [
            str(item.get("year") or "Unknown year"),
            f"Watched {item.get('watch_count', 0)}x"
        ]
        if item.get("runtime_minutes"):
            meta_parts.append(f"{item['runtime_minutes']} min")
        if item.get("resolution"):
            meta_parts.append(str(item["resolution"]))
        type_label = "Movie" if media_type == "movie" else "Episode"
        can_play = True

    if item.get("genres"):
        meta_parts.append(str(item["genres"]))

    return {
        "title": item.get("title") or "Unknown",
        "overview": truncate(item.get("overview")),
        "meta_line": " • ".join(meta_parts),
        "type_label": type_label,
        "poster_url": poster_url_for(item_id),
        "detail_url": url_for("item_page", item_id=item_id),
        "play_url": url_for("player_page", item_id=item_id),
        "can_play": can_play,
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

@app.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    all_items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))

    if q:
        all_items = [x for x in all_items if q in (x.get("title") or "").lower()]

    movies = [x for x in all_items if x.get("media_type") == "movie"]
    shows = [x for x in all_items if x.get("media_type") == "show"]

    continue_watching = [x for x in movies if int(x.get("watch_count") or 0) > 0]
    continue_watching.sort(key=lambda x: int(x.get("watch_count") or 0), reverse=True)

    recently_added = sorted(all_items, key=lambda x: safe_date(x.get("added_at")), reverse=True)

    continue_watching = continue_watching[:18]
    shows = shows[:18]
    movies = movies[:30]
    recently_added = recently_added[:18]

    hero_source = None
    for bucket in (continue_watching, shows, movies, recently_added):
        if bucket:
            hero_source = bucket[0]
            break

    hero_data = {}
    for bucket in (continue_watching, shows, movies, recently_added):
        for item in bucket:
            hero_data[str(item["id"])] = build_hero_entry(item)

    default_hero = build_hero_entry(hero_source) if hero_source else {
        "title": "VisionVault",
        "overview": "Browse your local movie and TV collection in a TV-first interface.",
        "meta_line": "Local library • TV mode",
        "type_label": "Library",
        "poster_url": "",
        "detail_url": "#",
        "play_url": "#",
        "can_play": False,
    }

    body = render_template_string(
        """
        <section class="hero">
            <div class="hero-bg" id="hero-bg"
                 {% if default_hero.poster_url %}style='background-image:url("{{ default_hero.poster_url }}")'{% endif %}></div>
            <div class="hero-overlay"></div>

            <div class="topbar">
                <div class="brand">
                    <h1>VisionVault TV</h1>
                    <p>Local movie and show library built for your TV</p>
                </div>

                <div class="top-actions">
                    <a class="nav-chip" href="{{ url_for('index') }}">Home</a>
                    <a class="nav-chip" href="{{ url_for('stats_page') }}">Stats</a>
                </div>
            </div>

            <form class="searchbar" method="get" action="{{ url_for('index') }}">
                <input class="search-input" type="text" name="q" value="{{ query }}" placeholder="Search title...">
                <button class="search-btn" type="submit">Search</button>
            </form>

            <div class="helper">Arrow keys navigate rows. Enter opens. Backspace or Escape goes back. Press / to jump to search.</div>

            <div class="hero-content">
                <div class="hero-poster">
                    <img id="hero-poster-img"
                         src="{{ default_hero.poster_url if default_hero.poster_url else '' }}"
                         alt="">
                </div>

                <div class="hero-copy">
                    <div class="eyebrow" id="hero-type">{{ default_hero.type_label }}</div>
                    <h2 class="hero-title" id="hero-title">{{ default_hero.title }}</h2>
                    <div class="hero-meta" id="hero-meta">{{ default_hero.meta_line }}</div>
                    <div class="hero-overview" id="hero-overview">{{ default_hero.overview }}</div>

                    <div class="hero-actions">
                        <a id="hero-open" class="hero-btn primary" href="{{ default_hero.detail_url }}">Open Details</a>
                        <a id="hero-play"
                           class="hero-btn secondary"
                           href="{{ default_hero.play_url }}"
                           {% if not default_hero.can_play %}style="display:none"{% endif %}>Play</a>
                    </div>
                </div>
            </div>
        </section>

        <main class="main">
            {% if continue_watching %}
            <section class="row-section">
                <div class="row-head">
                    <div>
                        <h2>Continue Watching</h2>
                        <div class="row-sub">{{ continue_watching|length }} title{{ '' if continue_watching|length == 1 else 's' }}</div>
                    </div>
                </div>
                <div class="media-row-wrap">
                    <div class="media-row">
                        {% for item in continue_watching %}
                        <a class="card"
                           href="{{ url_for('item_page', item_id=item['id']) }}"
                           data-tv-focus="1"
                           data-item-id="{{ item['id'] }}"
                           {% if loop.first %}data-autofocus="1"{% endif %}>
                            <div class="card-poster">
                                <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                            </div>
                            <div class="card-meta">
                                <div class="card-title">{{ item['title'] }}</div>
                                <div class="card-sub">
                                    {{ item['year'] or 'Unknown year' }} • Watched {{ item['watch_count'] }}x
                                </div>
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </section>
            {% endif %}

            {% if shows %}
            <section class="row-section">
                <div class="row-head">
                    <div>
                        <h2>Shows</h2>
                        <div class="row-sub">{{ shows|length }} series</div>
                    </div>
                </div>
                <div class="media-row-wrap">
                    <div class="media-row">
                        {% for item in shows %}
                        <a class="card"
                           href="{{ url_for('item_page', item_id=item['id']) }}"
                           data-tv-focus="1"
                           data-item-id="{{ item['id'] }}">
                            <div class="card-poster">
                                <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                            </div>
                            <div class="card-meta">
                                <div class="card-title">{{ item['title'] }}</div>
                                <div class="card-sub">
                                    Show • {{ get_show_progress(item['id'])[0] }}/{{ get_show_progress(item['id'])[1] }} watched
                                </div>
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </section>
            {% endif %}

            {% if movies %}
            <section class="row-section">
                <div class="row-head">
                    <div>
                        <h2>Movies</h2>
                        <div class="row-sub">{{ movies|length }} movie{{ '' if movies|length == 1 else 's' }}</div>
                    </div>

                    <div>
                        <a class="nav-chip" href="{{ url_for('movies_page') }}">View All</a>
                    </div>
                </div>
                <div class="media-row-wrap">
                    <div class="media-row">
                        {% for item in movies %}
                        <a class="card"
                           href="{{ url_for('item_page', item_id=item['id']) }}"
                           data-tv-focus="1"
                           data-item-id="{{ item['id'] }}">
                            <div class="card-poster">
                                <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                            </div>
                            <div class="card-meta">
                                <div class="card-title">{{ item['title'] }}</div>
                                <div class="card-sub">
                                    {{ item['year'] or 'Unknown year' }} • Watched {{ item['watch_count'] }}x
                                </div>
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </section>
            {% endif %}

            {% if recently_added %}
            <section class="row-section">
                <div class="row-head">
                    <div>
                        <h2>Recently Added</h2>
                        <div class="row-sub">{{ recently_added|length }} recent item{{ '' if recently_added|length == 1 else 's' }}</div>
                    </div>
                </div>
                <div class="media-row-wrap">
                    <div class="media-row">
                        {% for item in recently_added %}
                        <a class="card"
                           href="{{ url_for('item_page', item_id=item['id']) }}"
                           data-tv-focus="1"
                           data-item-id="{{ item['id'] }}">
                            <div class="card-poster">
                                <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                            </div>
                            <div class="card-meta">
                                <div class="card-title">{{ item['title'] }}</div>
                                <div class="card-sub">
                                    {% if item['media_type'] == 'show' %}
                                        Show
                                    {% else %}
                                        {{ item['year'] or 'Unknown year' }}
                                    {% endif %}
                                </div>
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </section>
            {% endif %}

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
        query=request.args.get("q", ""),
        get_show_progress=get_show_progress,
    )

    return render_page("VisionVault TV", body, hero_data=hero_data)


@app.route("/movies")
def movies_page():
    q = (request.args.get("q") or "").strip().lower()
    all_items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))
    movies = [x for x in all_items if x.get("media_type") == "movie"]

    if q:
        movies = [x for x in movies if q in (x.get("title") or "").lower()]

    hero_data = {}
    for item in movies:
        hero_data[str(item["id"])] = build_hero_entry(item)

    body = render_template_string(
        """
        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1">← Back to Home</a>

            <div class="row-head" style="padding-left:0;padding-right:0; margin-bottom:18px;">
                <div>
                    <h2>All Movies</h2>
                    <div class="row-sub">{{ movies|length }} movie{{ '' if movies|length == 1 else 's' }}</div>
                </div>
            </div>

            <form class="searchbar" method="get" action="{{ url_for('movies_page') }}" style="padding-left:0;padding-right:0; padding-top:0; margin-bottom:22px;">
                <input class="search-input" type="text" name="q" value="{{ query }}" placeholder="Search movies...">
                <button class="search-btn" type="submit">Search</button>
            </form>

            {% if movies %}
            <div class="all-grid">
                {% for item in movies %}
                <a class="card grid-card"
                   href="{{ url_for('item_page', item_id=item['id']) }}"
                   data-tv-focus="1"
                   data-item-id="{{ item['id'] }}"
                   {% if loop.first %}data-autofocus="1"{% endif %}>
                    <div class="card-poster">
                        <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                    </div>
                    <div class="card-meta">
                        <div class="card-title">{{ item['title'] }}</div>
                        <div class="card-sub">
                            {{ item['year'] or 'Unknown year' }} • Watched {{ item['watch_count'] }}x
                        </div>
                    </div>
                </a>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty">No movies found.</div>
            {% endif %}
        </div>
        """,
        movies=movies,
        query=request.args.get("q", "")
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

    body = render_template_string(
        """
        <div class="details-page">
            <a class="back-link" href="{{ url_for('index') }}" data-back-link="1">← Back to Home</a>

            <div class="detail-layout">
                <div class="detail-poster">
                    <img src="{{ url_for('poster_for_item', item_id=item['id']) }}" alt="">
                </div>

                <div class="detail-panel">
                    <h1 class="detail-title">{{ item['title'] }}</h1>
                    <div class="detail-meta">
                        Type: {{ item['media_type'] }}<br>
                        Year: {{ item['year'] or 'Unknown' }}<br>
                        Genres: {{ item['genres'] or 'None' }}<br>
                        Runtime: {{ item['runtime_minutes'] or 'Unknown' }}{% if item['runtime_minutes'] %} min{% endif %}<br>
                        Resolution: {{ item['resolution'] or 'Unknown' }}<br>
                        Watched: {{ item['watch_count'] }}x
                        {% if progress %}
                            <br>Show progress: {{ progress['watched'] }}/{{ progress['total'] }} watched
                        {% endif %}
                        {% if resume_seconds > 5 %}
                            <br>Resume position: {{ resume_label }}
                        {% endif %}
                    </div>

                    <div class="detail-overview">{{ item['overview'] or 'No overview yet.' }}</div>

                    <div class="detail-actions">
                        {% if item['media_type'] != 'show' %}
                            {% if resume_seconds > 5 %}
                                <a class="hero-btn primary" href="{{ url_for('player_page', item_id=item['id']) }}" data-tv-focus="1" data-autofocus="1">
                                    Resume
                                </a>
                                <a class="hero-btn secondary" href="{{ url_for('restart_route', item_id=item['id']) }}" data-tv-focus="1">
                                    Start Over
                                </a>
                            {% else %}
                                <a class="hero-btn primary" href="{{ url_for('player_page', item_id=item['id']) }}" data-tv-focus="1" data-autofocus="1">
                                    Play
                                </a>
                            {% endif %}
                            <a class="hero-btn secondary" href="{{ url_for('watch_route', item_id=item['id']) }}" data-tv-focus="1">Mark Watched</a>
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
                    <a class="episode-card"
                       href="{{ url_for('item_page', item_id=ep['id']) }}"
                       data-tv-focus="1"
                       data-item-id="{{ ep['id'] }}"
                       {% if item['media_type'] == 'show' and loop.first %}data-autofocus="1"{% endif %}>
                        <div class="episode-title">
                            S{{ "%02d"|format(ep['season'] or 0) }}E{{ "%02d"|format(ep['episode'] or 0) }} — {{ ep['title'] }}
                        </div>
                        <div class="episode-sub">
                            Watched {{ ep['watch_count'] }}x
                            {% if ep['resolution'] %} • {{ ep['resolution'] }}{% endif %}
                            {% if ep['runtime_minutes'] %} • {{ ep['runtime_minutes'] }} min{% endif %}
                        </div>
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
    return jsonify({"ok": True, "seconds": seconds})

@app.route("/play/<int:item_id>")
def play_route(item_id: int):
    ok, msg = play_item(item_id)
    if ok:
        return redirect(url_for("item_page", item_id=item_id))
    return f"<h1>Playback error</h1><p>{msg}</p><p><a href='{url_for('item_page', item_id=item_id)}'>Back</a></p>", 400

@app.route("/stream/<int:item_id>")
def stream_route(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return "No playable file found for this item.", 404

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

@app.route("/player/<int:item_id>")
def player_page(item_id: int):
    item, file_path = get_streamable_file(item_id)
    if not item:
        abort(404)

    if not file_path:
        return f"<h1>Playback error</h1><p>No playable file found for this item.</p><p><a href='{url_for('item_page', item_id=item_id)}'>Back</a></p>", 404

    hero_data = {}
    resume_seconds = int(get_resume_position(item_id) or 0)

    body = render_template_string(
        """
        <div class="details-page">
            <a class="back-link" href="{{ url_for('item_page', item_id=item['id']) }}" data-back-link="1">← Back to Details</a>

            <h1 class="detail-title" style="margin-bottom:16px;">{{ item['title'] }}</h1>

            <div style="background: linear-gradient(180deg, #171c24 0%, #12171e 100%); border: 1px solid rgba(255,255,255,0.08); border-radius: 24px; padding: 18px; box-shadow: 0 12px 30px rgba(0,0,0,0.30);">
                <video
                    id="vv-player"
                    controls
                    autoplay
                    playsinline
                    style="width:100%; max-height:78vh; background:#000; border-radius:16px; outline:none;"
                    data-tv-focus="1"
                    data-autofocus="1">
                    <source src="{{ url_for('stream_route', item_id=item['id']) }}" type="{{ mime_type }}">
                    Your browser does not support video playback.
                </video>
            </div>

            <div class="detail-meta" style="margin-top:18px;">
                {% if item['resolution'] %}Resolution: {{ item['resolution'] }}<br>{% endif %}
                {% if item['runtime_minutes'] %}Runtime: {{ item['runtime_minutes'] }} min<br>{% endif %}
                File: {{ item['file_path'] or 'Unknown' }}
            </div>
        </div>

        <script>
            window.addEventListener("load", function() {
                const player = document.getElementById("vv-player");
                if (!player) return;

                const itemId = {{ item['id'] }};
                const resumeSeconds = {{ resume_seconds }};
                let lastSavedSecond = -1;
                let completed = false;
                let resumeApplied = false;

                player.focus();

                function applyResume() {
                    if (resumeApplied) return;
                    if (!(resumeSeconds > 5)) return;
                    if (!player.duration || !isFinite(player.duration)) return;
                    if (resumeSeconds >= (player.duration - 10)) return;

                    try {
                        player.currentTime = resumeSeconds;
                        resumeApplied = true;
                        console.log("Resume applied at", resumeSeconds);
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
                    })
                    .then(r => r.json())
                    .then(data => console.log("Saved progress:", data))
                    .catch(err => console.log("Save progress failed:", err));
                }

                function markComplete() {
                    if (completed) return;
                    completed = true;

                    fetch(`/api/progress/${itemId}/clear`, {
                        method: "POST"
                    })
                    .then(r => r.json())
                    .then(data => console.log("Cleared progress:", data))
                    .catch(err => console.log("Clear progress failed:", err));
                }

                setInterval(function() {
                    if (!player.paused && !player.ended) {
                        saveProgress();

                        if (player.duration > 0) {
                            const pct = player.currentTime / player.duration;
                            if (pct >= 0.95) {
                                markComplete();
                            }
                        }
                    }
                }, 5000);

                player.addEventListener("pause", saveProgress);
                player.addEventListener("ended", function() {
                    markComplete();
                });
                window.addEventListener("beforeunload", saveProgress);
            });

            document.addEventListener("keydown", function(e) {
                const player = document.getElementById("vv-player");
                if (!player) return;

                if (e.key === "Escape" || e.key === "Backspace") {
                    e.preventDefault();
                    window.location.href = "{{ url_for('item_page', item_id=item['id']) }}";
                }
            });
        </script>
        """,
        item=item,
        mime_type=guess_mime_type(file_path),
        resume_seconds=resume_seconds,
    )

    return render_page(f"Playing {item['title']}", body, hero_data=hero_data)

@app.route("/poster/<int:item_id>")
def poster_for_item(item_id: int):
    item = get_item(item_id)
    if not item:
        abort(404)

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

@app.route("/restart/<int:item_id>")
def restart_route(item_id: int):
    clear_resume_position(item_id)
    return redirect(url_for("player_page", item_id=item_id))

@app.route("/api/library")
def api_library():
    items = enrich_items(list_movies(sort_key="title_asc", nav_mode="root"))
    return jsonify(items)


@app.route("/api/item/<int:item_id>")
def api_item(item_id: int):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
