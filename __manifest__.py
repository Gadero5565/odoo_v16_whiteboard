{
    "name": "OWL Whiteboard",
    "version": "1.0.0",
    "category": "Tools",
    "summary": "Backend whiteboard (OWL client action) using CDN JS library (Fabric.js)",
    "depends": ["web"],
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
}

