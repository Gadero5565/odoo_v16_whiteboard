{
    "name": "OWL Whiteboard",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "summary": (
        "Secure multi-board OWL whiteboard "
        "with bundled Fabric.js"
    ),
    "description": """
OWL Whiteboard for Odoo 16
==========================

A multi-board interactive whiteboard built as an OWL client action.

Main features
-------------
* Freehand drawing, text, shapes, arrows, and connectors
* Mind-map and flowchart nodes and templates
* Multi-board selector with paginated loading
* Debounced autosave with optimistic concurrency protection
* Dirty-state and navigation protection
* Byte-bounded undo and redo history
* Server-side JSON and thumbnail validation
* Responsive desktop, tablet, mobile, and RTL layouts
* Keyboard shortcuts and accessible status feedback

Fabric.js is bundled locally in the module assets. The module does not
depend on a third-party CDN at runtime.
""",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/whiteboard_rules.xml",
        "views/whiteboard_board_views.xml",
        "views/whiteboard_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odoo_v16_whiteboard/static/src/lib/fabric.min.js",
            "odoo_v16_whiteboard/static/src/whiteboard_action/whiteboard_action.scss",
            "odoo_v16_whiteboard/static/src/whiteboard_action/whiteboard_action.xml",
            "odoo_v16_whiteboard/static/src/whiteboard_action/whiteboard_objects.js",
            "odoo_v16_whiteboard/static/src/whiteboard_action/whiteboard_templates.js",
            "odoo_v16_whiteboard/static/src/whiteboard_action/whiteboard_action.js",
        ],
    },
    "application": True,
    "installable": True,
    "auto_install": False,
}
