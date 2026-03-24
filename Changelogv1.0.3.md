# VisionVault Changelog v1.0.3

## Improvements

### VisionVault TV Mode

* Added a built-in **TV Mode** that lets users browse and stream their library through a web browser
* The desktop app can now launch the TV interface directly from the main program
* Added **TV Mode controls** to the menu bar:

  * **Start TV Mode**
  * **Stop TV Mode**
  * **Open TV Mode in Browser**
  * **Show TV URL**
* Makes it easier to use VisionVault as both a desktop organizer and a TV-friendly media browser

---

### Desktop App and TV UI Integration

* Improved the connection between the main desktop app and the TV web interface
* TV Mode now reads from the same shared library/core system as the main application
* Changes made in the desktop app can now flow properly into the TV browsing experience
* Helps keep VisionVault more unified instead of feeling like two separate apps

---

### Browser-Based Video Playback

* Added direct **in-browser playback** for movies through the TV web UI
* Users can now open a title from the VisionVault TV interface and stream it directly in the browser
* Playback supports high-quality local media streaming with proper range requests
* Creates a more complete TV-style experience without needing external playback apps

---

### Resume Playback Support

* Added **resume playback** support for streamed movies in the TV interface
* VisionVault now stores the last known playback position while watching in the browser
* Movie detail pages can now show a **Resume** option when saved progress exists
* Added a **Start Over** option to clear saved playback position and restart the movie from the beginning
* Helps users return to unfinished movies more naturally

---

### Continue Watching Flow

* Improved the **Continue Watching** experience in the TV UI
* Resume-aware movie items now better support picking up from where the user left off
* Makes the TV browsing experience feel more like a full media platform

---

### Shared Watch Progress Behavior

* Browser playback can now tie back into VisionVault’s tracking workflow more cleanly
* Added API handling for playback progress updates and resume clearing
* Improves consistency between streamed playback and the main library system

---

### All Movies Page Access

* Added a dedicated **All Movies** page to the TV interface
* Users can now access the full movie library instead of only seeing the limited home row selection
* Helps larger collections feel more complete and easier to browse

---

## Fixes

### Core/Desktop Separation Cleanup

* Refactored parts of the project so duplicated logic could be removed from the desktop script
* Reduced overlap between `visionvault.py` and `vault_core.py`
* Improves maintainability and makes the app structure cleaner going forward

---

### Grid and Library Data Compatibility

* Fixed issues caused by differences between row-based data and dictionary-based data returned from the shared core
* Resolved unpacking and lookup errors that appeared after moving functionality into `vault_core.py`
* Helps desktop and web interfaces use the same backend more reliably

---

### Poster and Path Handling Reliability

* Improved path handling while consolidating shared logic into the core module
* Helped prevent broken references during the desktop/web integration process
* Improves consistency when loading posters and media files across VisionVault components

