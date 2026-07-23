# OWL Whiteboard for Odoo 16

A secure, responsive, multi-board whiteboard for Odoo 16, implemented as an OWL client action and powered by a locally bundled Fabric.js build.

## Features

- Freehand drawing
- Text objects
- Rectangles, circles, diamonds, lines, and arrows
- Object-to-object connectors
- Mind-map nodes
- Flowchart nodes
- Mind-map and workflow templates
- Multi-board management with paginated loading
- Automatic and manual saving
- Optimistic concurrency protection
- Navigation protection for unsaved changes
- Byte-bounded undo and redo history
- Object and path erasing
- PNG export
- Responsive desktop, tablet, and mobile layouts
- RTL support
- Keyboard shortcuts
- Accessible save-status and error feedback

## Version

Current release: `16.0.1.0.0`

## Requirements

- Odoo 16
- Python Pillow package
- A local Fabric.js build at:

```text
static/src/lib/fabric.min.js
```

The module does not require a runtime CDN connection.

Install Pillow in the Python environment used by Odoo:

```bash
pip install Pillow
```

## Installation

1. Copy the `odoo_v16_whiteboard` directory into an Odoo addons path.
2. Confirm that `static/src/lib/fabric.min.js` exists.
3. Restart Odoo.
4. Update the Apps list.
5. Install **OWL Whiteboard**.

Command-line installation example:

```powershell
python odoo-bin -c "<path-to-odoo.conf>" -d "<database>" -i odoo_v16_whiteboard --stop-after-init
```

## Usage

After installation, open:

```text
Whiteboard → Open Whiteboard
```

Saved boards are available under:

```text
Whiteboard → My Boards
```

The whiteboard supports drawing, text, shapes, connectors, mind maps, flowcharts, templates, board switching, undo/redo, erasing, saving, and PNG export.

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Save | `Ctrl/Cmd + S` |
| Undo | `Ctrl/Cmd + Z` |
| Redo | `Ctrl/Cmd + Shift + Z` or `Ctrl/Cmd + Y` |
| Remove selected object | `Delete` or `Backspace` |
| Cancel the current mode | `Escape` |

Shortcuts are suppressed while editing HTML inputs or Fabric text.

## Security model

- Only internal Odoo users receive model access.
- Each user can access only their own boards.
- Client-supplied ownership, company, and revision values are ignored.
- Archived boards cannot have their saved content modified.
- Saves use optimistic concurrency protection.
- Canvas JSON is validated before storage.
- External Fabric image sources, clip paths, and unsafe properties are rejected.
- Thumbnail files are decoded, validated, resized, and recompressed on the server.
- Board names and board identifiers are validated before use.
- Per-user board quotas are enforced.

## Data protection and failure recovery

- Unsaved changes are tracked and protected during navigation.
- Autosave retries after temporary failures.
- Failed saves preserve the current unsaved state.
- Multi-tab conflicts are detected before newer data can be overwritten.
- Invalid or incompatible board JSON does not replace the currently open board.
- Temporary board-list failures preserve existing selector contents.
- Thumbnail-generation failure does not prevent canvas JSON from being saved.
- PNG export failures are reported without causing an uncaught exception.
- A missing Fabric.js asset displays a recoverable error screen.

## Resource limits

| Resource | Limit |
|---|---:|
| Boards per user | 100 |
| Board name | 120 characters |
| Backend canvas JSON | 2 MiB |
| Backend Fabric objects | 1,000 |
| Client Fabric objects | 800 |
| Client canvas JSON | 1.5 MiB |
| Undo/redo entries | 50 |
| Undo/redo memory | 12 MiB |
| Stored thumbnail dimensions | 480 × 320 |
| Stored thumbnail size | 160 KiB |
| Board-list page size | 25 |

## Testing

Run the module test suite with:

```powershell
python odoo-bin -c "<path-to-odoo.conf>" -d "<database>" -u odoo_v16_whiteboard --test-enable --test-tags=/odoo_v16_whiteboard --stop-after-init --log-level=test
```

Expected result for the current release:

```text
64 test methods
0 failures
0 errors
```

Odoo may display a higher total in its statistics because subtests are counted separately.

## Troubleshooting

### Fabric.js is not loaded

Confirm that this file exists:

```text
static/src/lib/fabric.min.js
```

Then restart Odoo, upgrade the module, and rebuild or clear backend assets if necessary.

### Pillow import errors

Install Pillow in the same Python environment used to run Odoo:

```bash
pip install Pillow
```

### Assets appear outdated

Restart Odoo, upgrade the module, and clear the browser cache. In development, use Odoo asset-debug mode when inspecting JavaScript or SCSS changes.

### A board cannot be saved

Check the visible save-status message. Common causes include:

- A concurrent update from another tab or session
- Canvas complexity limits
- Invalid or unsupported saved data
- Temporary network or server errors

Unsaved changes remain in the current session when a save fails.

## License

This module is licensed under the LGPL-3 license.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.
