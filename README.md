# VisionVault (Offline Movie Inventory) 

<p align="center">
  <img width="450" alt="VisionVaultLogo" src="https://github.com/user-attachments/assets/4d2aeb39-014d-4134-b434-8dd16ca97089" />
</p>

<p align="center">
VisionVault is a sleek, lightweight <strong>offline movie library manager</strong> built with <strong>CustomTkinter + SQLite</strong>.<br>
Organize your entire collection, track watch history, browse beautiful poster grids, and launch your movies directly from one clean interface.
</p>

<p align="center">
Designed to be fast, private, and distraction-free: <strong>no accounts, no subscriptions, no cloud storage</strong>.<br>
Everything lives locally on your machine, with optional <strong>Wikipedia-powered metadata and posters</strong> to instantly enrich your library.
</p>

<p align="center">
Your personal movie vault, fully under your control.
</p>

---

## Features

### Library Management
- **Add movies by title** (manual entry)
- **Add movies by file** (auto guesses title + year from filename)
- Stores everything in a local **SQLite database** (`movies.db`)
- **Edit details** anytime: title, year, genres, runtime, resolution, overview, poster, file path
- **Delete** entries cleanly
- **Mark as watched** (increments watch counter)
- **Play movie file** from the app (and auto-increments watch count if the file successfully launches)

### Views & Filters
- **List View** and **Grid View** (poster tiles)
- Search by title (live filtering)
- Filter:
  - All
  - Unwatched
  - Watched
- Genre filter (auto-generated from your library)
- Sorting:
  - Title A→Z / Z→A
  - Year ↑ / ↓
  - Watched ↑ / ↓
  - Recently added / Oldest added

### Discover Tab (Wikipedia)
- Search Wikipedia for a movie title
- Click results to preview:
  - Short overview
  - Poster image (if available)
  - Detected year (optional manual override)
- Add the selected result to your Library in one click

### Stats Tab
- Total movies
- Watched vs Unwatched
- Total watch count
- Top watched titles
- Top genres
- Recently added

### Quality-of-Life
- **Remembers your layout and preferences** using `movie_inventory_settings.json`:
  - Window size/position
  - Split panel sash position
  - Theme (Dark/Light/System)
  - Last selected movie
  - List/Grid view mode
- Posters are saved locally to `posters/`

---

## How To Use

### Add by Title
1. Type a title into **Add by Title...**
2. Click **Add**
3. In the Edit dialog you can optionally:
   - Fetch metadata + poster from Wikipedia
   - Set year/genres/overview manually
4. Click **Save**

### Add by File
1. Click **Add by File**
2. Select your movie file (`.mkv`, `.mp4`, `.avi`, etc.)
3. The app will:
   - Guess title + year from filename
   - Try to detect runtime + resolution via ffprobe (if available)
4. Adjust anything in the Edit dialog and click **Save**

### Watching & Playing
- **Mark as Watched** increments the watch counter
- **Play** opens the file using your OS default player  
  If the player successfully launches, the app also increments watch count

### Grid View
Use **Grid View** to browse posters as tiles. Click a tile to load details.

---

## Notes / Behavior Details

- Wikipedia features require internet access, but the app works fine without it.
- Posters downloaded from Wikipedia are stored locally so Grid View stays fast.
- If no movie poster is found when adding wiki info, just add a movie poster manually 
- If you move movie files, update the **File path** field in **Edit Details**.

---

## Credits

Built with:
- CustomTkinter
- SQLite (built-in to Python)
- Wikipedia Action API (for metadata & posters)
