# Changelog

All notable changes to OWL Whiteboard are documented here.

## 16.0.1.0.0 — 2026-07-23

### Security

- Added strict Fabric JSON validation.
- Added JSON size, object, text, path, group, and numeric limits.
- Rejected external image sources, clip paths, and unsafe JSON properties.
- Enforced per-user board ownership and record rules.
- Added board-creation quotas.
- Added thumbnail decoding and validation.
- Added optimistic concurrency protection.
- Prevented saved-content modification on archived boards.

### Data protection

- Added dirty-state tracking.
- Added browser and Odoo navigation protection.
- Added debounced autosave.
- Preserved unsaved edits after failed saves.
- Added conflict detection for multiple tabs and sessions.

### Performance

- Added byte-bounded undo and redo history.
- Added paginated board loading.
- Added client and server thumbnail normalization.
- Added client canvas complexity limits.
- Added large-board loading feedback.

### User experience

- Added explicit save-status feedback.
- Added a real object and path eraser.
- Added responsive tablet and mobile layouts.
- Added keyboard shortcuts.
- Added empty-board feedback.
- Added accessibility improvements.
- Added RTL layout support.
- Renamed the saved-board menu to “My Boards.”

### Packaging

- Declared the LGPL-3 license.
- Declared Pillow as an external Python dependency.
- Removed the unused controller scaffold.
- Documented local Fabric.js usage.
