# VisionVault Changelog v1.0.4

## Improvements

### Animated Poster Support

* Added support for **animated posters** in VisionVault
* Users can now assign animated poster media alongside standard posters for supported titles
* Added support for **`.gif` animated posters** in the desktop app
* Added animated poster controls to the Edit dialog for easier poster management
* Added support for prioritizing animated poster artwork in supported views when both static and animated artwork exist

---

### Selected-Only Animated Poster Playback

* Added selected-only animated poster playback in the desktop app
* Animated poster artwork now plays only when a title is selected
* Helps keep the library view cleaner while still giving selected titles a more dynamic animated effect

---

### VisionVault TV Web UI Expansion

* Continued expanding the built-in **TV web interface** into a more complete browser-based frontend
* Added a more polished home screen with a featured hero section, branded layout, and TV-style content rows
* Added logo support in the web UI for a stronger **VisionVault-branded** presentation
* Added animated poster support in the web UI, including better poster priority handling
* Added support for **subtitle playback** in the web-based player
* Added more flexible subtitle lookup support, including matching subtitle files beside the movie and in common subtitle subfolders
* Added a dedicated **All Movies** page for browsing the full movie library outside the limited home rows
* Added more complete movie and show detail support for the web interface
* Expanded browser-based playback and resume support to make the web UI feel more like a full media platform

---

### Recursive Folder Import

* Added support for **recursive folder importing** in VisionVault
* Movie and TV folder imports can now scan **subfolders automatically**
* Users no longer need to manually add every nested folder one by one
* Makes it much easier to import larger, organized media libraries

---

### Android TV Foundation Work

* Continued backend and interface groundwork for the upcoming **VisionVault TV Android app**
* Added support in the shared system for cleaner TV-oriented browsing, playback flow, and server connection handling
* Expanded backend support for features that will be used by the Android TV app, including improved detail handling for movies and shows
* Continued shaping VisionVault’s shared architecture so desktop, web, and future Android TV experiences can work from the same core system

---

## Fixes

---

### Web UI and TV Layout Stability

* Improved layout behavior in TV-oriented views to better support featured hero sections, browsing rows, and poster presentation
* Reduced oversized visual elements in supported TV-style layouts so content fits the screen more cleanly
* Improved spacing and presentation for a more polished couch-friendly experience

---

### Shared Watch and Recent Activity Flow

* Added backend support for exposing more recent watch information to connected clients
* Improved groundwork for sharing playback-related state between the desktop/server side and future TV-facing clients
* Helps move VisionVault toward more accurate cross-device playback and watch flow behavior