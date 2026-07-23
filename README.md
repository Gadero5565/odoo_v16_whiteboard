# OWL Whiteboard for Odoo 16

A secure multi-board whiteboard implemented as an OWL client action and powered by a locally bundled Fabric.js build.

## Features

- Freehand drawing
- Text objects
- Rectangles, circles, diamonds, lines, and arrows
- Object-to-object connectors
- Mind-map nodes
- Flowchart nodes
- Mind-map and workflow templates
- Multi-board selector with paginated loading
- Automatic and manual saving
- Optimistic concurrency protection
- Navigation protection for unsaved changes
- Byte-bounded undo and redo history
- Real object and path erasing
- Responsive desktop, tablet, and mobile layout
- RTL support
- Keyboard shortcuts and accessible save feedback

## Requirements

- Odoo 16
- Python Pillow package
- A local Fabric.js build at:

```text
static/src/lib/fabric.min.js
````

The module does not require a runtime CDN connection.

Install Pillow in the Python environment used by Odoo:

```bash
pip install Pillow
```

## Installation

1. Copy `odoo_v16_whiteboard` into an Odoo addons directory.
2. Confirm `static/src/lib/fabric.min.js` exists.
3. Restart Odoo.
4. Update the Apps list.
5. Install **OWL Whiteboard**.

Command-line upgrade example:

```powershell
python odoo-bin -c "C:\odoo\debian\odoo.conf" -d odoo_whiteboard -u odoo_v16_whiteboard --stop-after-init
```

## Security model

* Only internal Odoo users receive model access.
* Each user can access only their own boards.
* Client-supplied ownership and revision values are ignored.
* Archived boards cannot have their saved content modified.
* Saves use optimistic concurrency protection.
* Canvas JSON is validated before storage.
* External Fabric image sources, clip paths, and unsafe properties are rejected.
* Thumbnails are decoded, validated, resized, and recompressed on the server.

## Resource limits

| Resource                    |     Limit |
|-----------------------------| --------: |
| Boards per user             |       100 |
| Board name                  | 120 characters |        
| Backend canvas JSON         |     2 MiB |
| Backend Fabric objects      |     1,000 |
| Client Fabric objects       |       800 |
| Client canvas JSON          |   1.5 MiB |
| Undo/redo entries           |        50 |
| Undo/redo memory            |    12 MiB |
| Stored thumbnail dimensions | 480 × 320 |
| Stored thumbnail size       |   160 KiB |
| Board-list page size        |        25 |

## Keyboard shortcuts

| Action                 | Shortcut                                 |
| ---------------------- | ---------------------------------------- |
| Save                   | `Ctrl/Cmd + S`                           |
| Undo                   | `Ctrl/Cmd + Z`                           |
| Redo                   | `Ctrl/Cmd + Shift + Z` or `Ctrl/Cmd + Y` |
| Remove selected object | `Delete` or `Backspace`                  |
| Cancel current mode    | `Escape`                                 |

Shortcuts are suppressed while editing HTML inputs or Fabric text.

## Automated tests

Run:

```powershell
python odoo-bin -c "C:\odoo\debian\odoo.conf" -d odoo_whiteboard -u odoo_v16_whiteboard --test-enable --stop-after-init --log-level=test
```

Current expected result:

```text
58 tests
0 failures
0 errors
```

## Release verification

Before releasing:

1. Confirm `fabric.min.js` is bundled locally.
2. Confirm Pillow is installed.
3. Upgrade the module on a clean test database.
4. Run the full automated suite.
5. Test save, autosave, conflict handling, erasing, undo/redo, and pagination.
6. Test desktop, tablet, mobile, and RTL layouts.
7. Test installation without internet access.
