<h1 align="center"> VisionVault — Offline Movie & TV Library Manager</h1>

<p align="center">
  <img width="700" alt="VisionVault UI" src="assets/VisionVault-UI.gif" />
</p>

<p align="center">
  <a href="https://github.com/VisionDepth/VisionVault/releases">
    <img src="https://img.shields.io/github/downloads/VisionDepth/VisionVault/total?style=for-the-badge&logo=github&color=8A2BE2" alt="Total Downloads">
  </a>
</p>

<p align="center">
<strong>VisionVault</strong> is a modern <strong>offline movie &amp; TV library manager</strong> built with <strong>CustomTkinter, Flask, and SQLite</strong>.<br>
Manage your personal collection, browse cinematic poster grids, track watch history, launch local files, and access your library through the built-in <strong>Web UI / TV Mode</strong> for browser and TV playback.
</p>

<p align="center">
No accounts • No cloud • No subscriptions • 100% local
</p>

<p align="center">
Optional <strong>Wikipedia-powered metadata and posters</strong> make it easy to enrich your collection while keeping everything private and under your control.
</p>

<p align="center">
A personal media vault designed for collectors who want a clean desktop experience with the flexibility of local web playback.
</p>

---

## Key Features

### Library Management
- Add movies by **title** or **file**
- Import movie folders with **recursive subfolder scanning**
- Automatic title and year detection from filenames
- Local SQLite database storage (`movies.db`)
- Edit full metadata:
  - Title
  - Year
  - Genres
  - Runtime
  - Resolution
  - Overview
  - Poster
  - Animated poster
  - File path
- Delete entries cleanly
- Track watch history
- Launch movies directly from the desktop app

---

### Animated Poster Support
- Add **animated posters** alongside standard poster art
- Supports animated artwork formats including **`.gif`**
- Animated posters only play when a title is **selected**
- Helps keep the library visually clean while still adding motion to focused items
- Animated poster controls are built directly into the **Edit Details** dialog

---

### TV Show Support
- Import entire TV show folders
- Automatic show and episode structure
- Recursive subfolder support for organized TV libraries
- Episode naming format:
  - `S01E01 - Episode Name`
  - `S01E02 - Episode Name`
- Manual editing of:
  - Episode posters
  - Descriptions
  - Metadata
- Progress tracking per show
- Automatic show poster inheritance from episode artwork
- Optional poster propagation across episodes that do not already have artwork

---

### TV Mode Web Interface
- Launch a browser-based **VisionVault TV** interface directly from the desktop app
- Browse your library from another device on your local network
- Stream movies directly in-browser
- TV-friendly navigation layout for couch or remote-style use
- Dedicated sections for:
  - Continue Watching
  - Movies
  - Shows
  - Recently Added
- Built-in movie detail pages, stats page, and full movie library page
- Branded VisionVault TV layout with logo support and a polished featured hero section

---

### Browser Playback and Subtitles
- Stream movies directly in the VisionVault TV web player
- Resume movies from your last saved position
- **Resume** and **Start Over** options appear on supported items
- Completed playback clears saved progress automatically
- Subtitle support for matching subtitle files during browser playback
- Supports subtitle lookup beside the movie file and in common subtitle subfolders

---

### Resume and Watch Tracking
- Browser playback saves watch progress
- Desktop and web playback share the same core watch tracking system
- Recent watch activity can be reflected more cleanly across connected clients
- Successful desktop playback increments watch count automatically
- You can also manually use **Mark as Watched**

---

### Grid View (Modern Media Wall)
- Poster-focused tiled layout
- Uniform sizing with clean alignment
- Clamped and wrapped titles without stretching
- Dense, directory-style browsing
- Animated posters can be previewed on selected items
- Fully integrated with:
  - Sorting
  - Filters
  - Show navigation
  - Right-click context menu
  - Keyboard navigation

---

### List View
- Clean detailed list layout
- Highlighted selection
- Larger readable text spacing
- Fast keyboard-friendly browsing

---

### Search, Filter & Sort
- Live search by title
- Filter by:
  - All
  - Watched
  - Unwatched
- Genre filter (auto-generated)
- Sort by:
  - Title A-Z / Z-A
  - Year up / down
  - Watched up / down
  - Recently added / oldest added

---

### Stats Dashboard
- Total movies, shows, and episodes
- Watched vs unwatched breakdown
- Total watch counts
- Top watched movies and episodes
- Most common genres
- Recently added items

---

### Keyboard Navigation
- Full keyboard navigation support in the desktop app
- Shortcuts include:
  - **Enter** to play
  - **Space** to mark watched
  - **E** to edit
  - **Delete** to remove selected item
  - **Backspace / Escape** to return from show episode view
- Smooth auto-scroll keeps selected items visible while browsing

---

### Themes and Interface Customization
- Multiple accent color themes
- Supports **Dark / Light / System** appearance modes
- Theme styling updates buttons, highlights, borders, and dialog accents
- Cleaner desktop-style menu bar for app controls

---

### Quality of Life
VisionVault automatically remembers:
- Window size and position
- Split panel layout
- Dark / Light / System appearance
- Active theme
- Last selected item
- Grid or List view mode

Saved locally in:

`movie_inventory_settings.json`

Posters are cached locally in:

`posters/`

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
   - Detect runtime and resolution using ffprobe if installed
4. Edit if needed and save

---

### Import Movie Folders
1. Click **Import Movie Folder**
2. Select your main movie folder
3. VisionVault can scan supported video files in **subfolders automatically**
4. Imported titles can then be edited normally if needed

---

### Import TV Shows
1. Click **Import TV Show**
2. Select a folder of encoded episode files
3. VisionVault can scan organized episode folders and subfolders automatically
4. VisionVault will build the show and episode structure automatically
5. Edit posters or metadata if needed

---

### Watching and Playing
- **Play** opens your movie in the default OS player from the desktop app
- Successful desktop playback increments watch count automatically
- In **TV Mode**, movies can be streamed directly in-browser
- Browser playback supports saved resume progress
- Matching subtitle files can be used during supported web playback
- You can also manually use **Mark as Watched**

---

### TV Mode
1. Open the **TV Mode** menu from the desktop app
2. Start the TV web interface
3. Open the provided local network URL on your browser or TV
4. Browse and stream your collection from the web interface

---

## Notes
- Internet is only required for Wikipedia metadata fetching
- The desktop app works fully offline otherwise
- TV Mode works over your local network
- All posters are stored locally for fast loading
- If you move files, update the file path in **Edit Details**
- Subtitle support in web playback works best with matching text subtitle files such as `.srt` or `.vtt`

---

## Built With
- CustomTkinter
- Flask
- SQLite
- Wikipedia Action API

---

## Download

Grab the standalone Windows `.exe` from the Releases page when a new version becomes available.

## Manual Install

### 1. Clone the repository

```bash
git clone https://github.com/VisionDepth/VisionVault.git
cd VisionVault
```

### 2. Create and activate a Conda environment

```bash
conda create -n VisionVault python=3.13
conda activate VisionVault
```

### 3. Or create a standard virtual environment

```bash
python -m venv venv
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Launch VisionVault

```bash
python visionvault.py
```

## Notes for Manual Install

- `vault_core.py`, `visionvault.py`, and `visionvault_web.py` should stay in the same project folder
- TV Mode uses the same local database as the desktop app
- Posters are stored locally in the `posters/` folder
- Settings are stored in `movie_inventory_settings.json`
- `ffprobe` is recommended for automatic runtime and resolution detection

