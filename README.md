<h1 align="center"> VisionVault — Offline Movie & TV Library Manager</h1>

<p align="center">
 <img width="700" alt="VisionVault Grid Layout" src="https://github.com/user-attachments/assets/101c80de-3620-439b-aaf6-7b039bdf224c" />
</p>

<p align="center">
  <a href="https://github.com/VisionDepth/VisionVault/releases">
    <img src="https://img.shields.io/github/downloads/VisionDepth/VisionVault/total?style=for-the-badge&logo=github&color=8A2BE2" alt="Total Downloads">
  </a>
</p>

<p align="center">
<strong>VisionVault</strong> is a sleek, fast, fully <strong>offline movie & TV library manager</strong> built with <strong>CustomTkinter + SQLite</strong>.<br>
Organize your collection, browse cinematic poster grids, track watch history, and launch media from one clean interface.
</p>

<p align="center"> No accounts • No cloud • No subscriptions • 100% local
</p>

<p align="center">
Optional <strong>Wikipedia-powered metadata & posters</strong> instantly enrich your library while keeping everything private.
</p>

<p align="center">
Your personal media vault — fully under your control.
</p>

---

## Key Features

### Library Management
- Add movies by **title** or **file**
- Automatic title & year detection from filenames
- Local SQLite database storage (`movies.db`)
- Edit everything:
  - Title, year, genres
  - Runtime & resolution
  - Overview & poster
  - File path
- Delete entries cleanly
- Track watch history
- Launch movies directly from the app

---

### TV Show Support
- Import entire TV show folders
- Automatic show + episode structure
- Episode naming format:
  - `S01E01 - Episode Name`
  - `S01E02 - Episode Name`
- Manual editing of:
  - Episode posters
  - Descriptions
  - Metadata
- Progress tracking per show

---

### Grid View (Modern Media Wall)
- Poster-focused tiled layout
- Uniform sizing with clean alignment
- Clamped and wrapped titles (no stretching)
- Dense, directory-style browsing
- Fully integrated with:
  - Sorting
  - Filters
  - Show navigation
  - Right-click context menu

---

### List View
- Clean detailed list layout
- Highlighted selection
- Larger readable text spacing

---

### Search, Filter & Sort
- Live search by title
- Filter:
  - All
  - Watched
  - Unwatched
- Genre filter (auto-generated)
- Sort by:
  - Title A–Z / Z–A
  - Year ↑ / ↓
  - Watched ↑ / ↓
  - Recently added / Oldest

---

### Stats Dashboard
- Total movies, shows, and episodes
- Watched vs unwatched breakdown
- Total watch counts
- Top watched movies and episodes
- Most common genres
- Recently added items

---

### Quality of Life
VisionVault automatically remembers:
- Window size and position
- Split panel layout
- Dark / Light / System theme
- Last selected item
- Grid/List view mode
Saved locally in:

movie_inventory_settings.json

Posters are cached locally in:

posters/

---

## Getting Started

### Add by Title
1. Type into **Add by Title...**
2. Click **Add**
3. Optionally fetch:
   - Wikipedia metadata
   - Poster art
4. Save

---

### Add by File
1. Click **Add by File**
2. Select a video file
3. VisionVault will:
   - Guess title and year
   - Detect runtime and resolution (via ffprobe if installed)
4. Edit if needed and save

---

### Watching and Playing
- **Play** opens your movie in the default OS player  
- If playback launches successfully, watch count increments automatically  
- Or manually use **Mark as Watched**

---

### Grid Browsing
Switch to **Grid View** to browse your collection visually like a media wall.  
Click any poster to view full details.

---

## Notes
- Internet is only required for Wikipedia metadata fetching
- The app works fully offline otherwise
- All posters are stored locally for fast loading
- If you move files, update the file path in **Edit Details**

---

## Built With
- CustomTkinter  
- SQLite  
- Wikipedia Action API  

---

## Download
Grab the standalone Windows `.exe` from:  
https://github.com/VisionDepth/VisionVault/releases  

No Python required.
