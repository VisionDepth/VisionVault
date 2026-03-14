# VisionVault Changelog v1.0.2

## Improvements

### Keyboard Navigation & Library Interaction

* Added full keyboard navigation support for the library
* Users can now browse the collection using arrow keys
* Selecting items automatically scrolls the library view smoothly to keep the selection visible
* New keyboard shortcuts:

  * **Enter** → Play selected movie/episode
  * **Space** → Mark selected item as watched
  * **E** → Edit selected item
  * **Delete** → Remove selected item from the library
  * **Backspace / Escape** → Return from show episode view to the main library
* Improves navigation speed and overall desktop usability

---

### Menu Bar & Application Controls

* Added a full desktop-style **menu bar** to the application
* New top-level menus include:

  * **File**
  * **View**
  * **Themes**
  * **Help**
* Core application actions are now accessible through the menu bar
* Improves usability and gives VisionVault a more traditional desktop application layout

---

### Theme System

* Introduced a customizable **theme system**
* Users can now switch accent color themes directly from the menu bar
* Theme colors dynamically update:

  * Buttons
  * Selection highlights
  * Grid tile borders
  * Interface accents
* Dialog windows now automatically respect the active theme
* Cancel buttons use a neutral gray style for clearer UI hierarchy

---

### Library Highlight & Hover Improvements

* Improved poster tile highlighting in Grid View
* Selected items now use cleaner border highlighting instead of heavy outlines
* Hover interactions now subtly change tile appearance for better visual feedback
* Creates a more modern, media-library style browsing experience

---

### Interface Simplification

* Removed the **List View / Grid View toggle button** from the main toolbar
* View switching is now handled through the **View menu** in the menu bar
* Reduces visual clutter in the main interface
* Improves overall UI cleanliness

---

### TV Show Poster Auto-Propagation

* When a poster is added to a TV episode, VisionVault can now automatically populate that poster to other episodes in the same show that do not already have posters
* The show entry will also inherit the first available episode poster if the show does not yet have one
* Existing episode posters are never overwritten, allowing users to keep custom artwork

---

### VisionDepth3D Integration Shortcut

* Added a **Convert to 3D (VisionDepth3D)** option to the right-click context menu
* If `VisionDepth3D.exe` is found in the expected folder, VisionVault launches it directly
* If VisionDepth3D is not installed, VisionVault can direct users to the GitHub releases page instead
* Creates a stronger link between VisionVault and VisionDepth3D for users managing 2D and 3D movie libraries
* Helps promote the broader VisionDepth ecosystem without interrupting normal library use

---

## Fixes

### Cancel Dialog Creating Phantom Entries

* Fixed an issue where canceling the Add/Edit dialog could still create an empty library entry
* Database entries are now only written when the user explicitly saves changes

---

### Windows Playback Stability

* Replaced `os.startfile()` with a safer `subprocess` launch method when opening media files on Windows
* Prevents rare crashes that could occur when launching external media players from the GUI
* Improves reliability when playing files stored on external drives

---

### Minor Stability Fixes

* Improved metadata handling when Wikipedia or Wikidata responses are incomplete
* General reliability improvements when fetching external metadata