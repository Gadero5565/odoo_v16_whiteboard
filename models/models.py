from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import json
import math
import re


MAX_JSON_BYTES = 10 * 1024 * 1024       # 10 MB
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024   # 2 MB

# Phase 1A payload limits. Storage quotas and lower byte limits belong to Phase 1B.
MAX_CANVAS_OBJECTS = 1000
MAX_GROUP_DEPTH = 3
MAX_JSON_DEPTH = 12
MAX_TEXT_LENGTH = 10_000
MAX_TOTAL_TEXT_LENGTH = 100_000
MAX_PATH_COMMANDS = 20_000
MAX_TOTAL_PATH_COMMANDS = 50_000
MAX_POLYGON_POINTS = 2_000
MAX_COLLECTION_ITEMS = 20_000
MAX_ABS_NUMBER = 100_000
MAX_SCALE = 100
MAX_STROKE_WIDTH = 200
MAX_FONT_SIZE = 1_000
MAX_STRING_LENGTH = 100_000
MAX_IDENTIFIER_LENGTH = 160

ALLOWED_FABRIC_TYPES = frozenset({
    "path", "i-text", "rect", "circle", "polygon", "line", "group", "textbox",
})
ALLOWED_PATH_COMMANDS = frozenset(
    "MLHVCSQTAZmlhvcsqtaz"
)
FORBIDDEN_JSON_KEYS = frozenset({"__proto__", "prototype", "constructor"})
FORBIDDEN_FABRIC_KEYS = frozenset({
    "src", "source", "sourcePath", "crossOrigin", "filters",
    "resizeFilter", "clipPath", "backgroundImage", "overlayImage",
})
COLOR_KEYS = frozenset({"fill", "stroke", "backgroundColor", "textBackgroundColor"})
WHITEBOARD_ENUMS = {
    "wbType": frozenset({"shape", "connector", "mind_node", "flow_node"}),
    "wbShape": frozenset({
        "rectangle", "circle", "diamond", "line", "arrow", "mind_node", "flow_node",
    }),
    "wbRole": frozenset({"node_background", "node_text"}),
    "wbNodeType": frozenset({
        "mind_node", "terminator", "process", "decision", "data",
    }),
    "wbConnectorType": frozenset({
        "straight_arrow", "template_arrow", "mind_arrow",
    }),
}


class WhiteboardBoard(models.Model):
    _name = "whiteboard.board"
    _description = "Whiteboard Board"
    _order = "write_date desc, id desc"

    name = fields.Char(
        required=True,
        default=lambda self: _("My Whiteboard"),
    )

    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        copy=False,
    )

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        index=True,
        copy=False,
    )

    active = fields.Boolean(default=True)

    data_json = fields.Text()

    thumbnail = fields.Binary(
        attachment=True,
        copy=False,
    )

    # -------------------------------------------------------------------------
    # Ownership hardening
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """
        Force board ownership to the current user.

        Do not trust user_id coming from the client, XML context, RPC, import, etc.
        Each user creates boards only for himself.
        """
        prepared_vals_list = []

        for vals in vals_list:
            vals = dict(vals)
            vals["user_id"] = self.env.uid
            vals.setdefault("company_id", self.env.company.id)

            if "data_json" in vals:
                vals["data_json"] = self._validated_data_json(vals["data_json"])

            prepared_vals_list.append(vals)

        return super().create(prepared_vals_list)

    def write(self, vals):
        """
        Prevent ownership reassignment and validate direct ORM writes.
        """
        vals = dict(vals)
        vals.pop("user_id", None)

        if "data_json" in vals:
            vals["data_json"] = self._validated_data_json(vals["data_json"])

        return self._write_validated_vals(vals)

    def _write_validated_vals(self, vals):
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_current_user_board(self, board_id):
        try:
            board_id = int(board_id)
        except (TypeError, ValueError):
            return self.browse()

        return self.search(
            [
                ("id", "=", board_id),
                ("user_id", "=", self.env.uid),
                ("active", "=", True),
            ],
            limit=1,
        )

    def _board_payload(self, board):
        board.ensure_one()
        return {
            "id": board.id,
            "name": board.name,
            "data_json": board.data_json or False,
            "write_date": fields.Datetime.to_string(board.write_date) if board.write_date else False,
        }

    def _validated_data_json(self, data_json):
        valid, result = self._validate_data_json(data_json)
        if not valid:
            raise ValidationError(result)
        return result

    def _validate_data_json(self, data_json):
        if data_json is None or data_json is False:
            data_json = "{}"

        if not isinstance(data_json, str):
            return False, _("Whiteboard data must be a JSON string.")

        if len(data_json.encode("utf-8")) > MAX_JSON_BYTES:
            return False, _("Whiteboard is too large to save.")

        def reject_constant(_value):
            raise ValueError("Non-finite JSON number")

        def reject_duplicate_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result

        try:
            parsed = json.loads(
                data_json or "{}",
                parse_constant=reject_constant,
                object_pairs_hook=reject_duplicate_keys,
            )
        except (TypeError, ValueError, RecursionError):
            return False, _("Whiteboard data is not valid JSON.")

        if not isinstance(parsed, dict):
            return False, _("Whiteboard data must be a JSON object.")

        error = self._validate_canvas_payload(parsed)
        if error:
            return False, error

        return True, json.dumps(
            parsed,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )

    def _validate_canvas_payload(self, payload):
        if set(payload) - {"version", "objects", "background"}:
            return _("Whiteboard data contains unsupported canvas properties.")

        version = payload.get("version")
        if version is not None and (not isinstance(version, str) or len(version) > 40):
            return _("Whiteboard Fabric version is invalid.")

        background = payload.get("background")
        if background is not None and not self._is_safe_color(background):
            return _("Whiteboard background must be a plain color.")

        objects = payload.get("objects", [])
        if not isinstance(objects, list):
            return _("Whiteboard objects must be a JSON array.")

        state = {"objects": 0, "text": 0, "path_commands": 0}
        for obj in objects:
            error = self._validate_fabric_object(obj, state, group_depth=0)
            if error:
                return error

        return False

    def _validate_fabric_object(self, obj, state, group_depth):
        if not isinstance(obj, dict):
            return _("Each whiteboard object must be a JSON object.")

        state["objects"] += 1
        if state["objects"] > MAX_CANVAS_OBJECTS:
            return _("Whiteboard contains too many objects.")

        object_type = obj.get("type")
        if object_type not in ALLOWED_FABRIC_TYPES:
            return _("Unsupported whiteboard object type: %s") % (object_type or _("missing"))

        for key, allowed_values in WHITEBOARD_ENUMS.items():
            value = obj.get(key)
            if value is not None and value not in allowed_values:
                return _("Whiteboard object metadata is invalid.")

        for key in ("wbId", "wbParentNodeId", "wbFromNodeId", "wbToNodeId"):
            value = obj.get(key)
            if value is not None and (
                not isinstance(value, str) or len(value) > MAX_IDENTIFIER_LENGTH
            ):
                return _("Whiteboard object metadata is invalid.")

        wb_text = obj.get("wbText")
        if wb_text is not None and (
            not isinstance(wb_text, str) or len(wb_text) > MAX_TEXT_LENGTH
        ):
            return _("Whiteboard object metadata is invalid.")

        expected_types = {
            "rectangle": "rect",
            "circle": "circle",
            "diamond": "polygon",
            "line": "line",
            "arrow": "path",
            "mind_node": "group",
            "flow_node": "group",
        }
        wb_shape = obj.get("wbShape")
        if wb_shape and object_type != expected_types[wb_shape]:
            return _("Whiteboard object type does not match its metadata.")

        if obj.get("wbType") == "connector" and (
            object_type != "path"
            or not obj.get("wbFromNodeId")
            or not obj.get("wbToNodeId")
        ):
            return _("Whiteboard connector metadata is invalid.")

        for key, value in obj.items():
            if key in {"scaleX", "scaleY"} and value is not None and (
                not self._is_safe_number(value) or abs(value) > MAX_SCALE
            ):
                return _("Whiteboard object scale is invalid.")
            if key == "strokeWidth" and value is not None and (
                not self._is_safe_number(value) or not 0 <= value <= MAX_STROKE_WIDTH
            ):
                return _("Whiteboard stroke width is invalid.")
            if key == "fontSize" and value is not None and (
                not self._is_safe_number(value) or not 0 < value <= MAX_FONT_SIZE
            ):
                return _("Whiteboard font size is invalid.")
            if key == "opacity" and value is not None and (
                not self._is_safe_number(value) or not 0 <= value <= 1
            ):
                return _("Whiteboard opacity is invalid.")
            if key in FORBIDDEN_JSON_KEYS:
                return _("Whiteboard data contains an unsafe property.")
            if key in FORBIDDEN_FABRIC_KEYS:
                return _("Whiteboard data contains unsupported external content.")
            if key == "path" and object_type != "path":
                return _("Whiteboard object contains unsupported path data.")
            if key == "points" and object_type != "polygon":
                return _("Whiteboard object contains unsupported polygon data.")
            if key in {"objects", "path", "points"}:
                continue
            error = self._validate_json_value(value, key=key, depth=0)
            if error:
                return error

        if object_type in {"i-text", "textbox"}:
            text = obj.get("text", "")
            if not isinstance(text, str) or len(text) > MAX_TEXT_LENGTH:
                return _("A whiteboard text object is invalid or too long.")
            state["text"] += len(text)
            if state["text"] > MAX_TOTAL_TEXT_LENGTH:
                return _("Whiteboard contains too much text.")

        if object_type == "path":
            error = self._validate_path(obj.get("path"), state)
            if error:
                return error

        if object_type == "polygon":
            error = self._validate_polygon_points(obj.get("points"))
            if error:
                return error

        children = obj.get("objects")
        if object_type == "group":
            if group_depth >= MAX_GROUP_DEPTH:
                return _("Whiteboard groups are nested too deeply.")
            if not isinstance(children, list) or not children:
                return _("Whiteboard group objects are invalid.")
            for child in children:
                error = self._validate_fabric_object(child, state, group_depth + 1)
                if error:
                    return error
        elif children is not None:
            return _("Only whiteboard groups may contain child objects.")

        return False

    def _validate_path(self, path, state):
        if not isinstance(path, list) or len(path) > MAX_PATH_COMMANDS:
            return _("Whiteboard path data is invalid or too complex.")

        state["path_commands"] += len(path)
        if state["path_commands"] > MAX_TOTAL_PATH_COMMANDS:
            return _("Whiteboard drawing paths are too complex.")

        for command in path:
            if (
                not isinstance(command, list)
                or not command
                or command[0] not in ALLOWED_PATH_COMMANDS
                or len(command) > 8
            ):
                return _("Whiteboard path data is invalid.")
            for number in command[1:]:
                if not self._is_safe_number(number):
                    return _("Whiteboard path data contains an invalid number.")

        return False

    def _validate_polygon_points(self, points):
        if not isinstance(points, list) or not points or len(points) > MAX_POLYGON_POINTS:
            return _("Whiteboard polygon points are invalid.")

        for point in points:
            if (
                not isinstance(point, dict)
                or set(point) != {"x", "y"}
                or not all(self._is_safe_number(value) for value in point.values())
            ):
                return _("Whiteboard polygon points are invalid.")

        return False

    def _validate_json_value(self, value, key=None, depth=0):
        if depth > MAX_JSON_DEPTH:
            return _("Whiteboard data is nested too deeply.")

        if key in COLOR_KEYS and value is not None and not self._is_safe_color(value):
            return _("Whiteboard colors must be plain color values.")

        if value is None or isinstance(value, bool):
            return False

        if isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                return _("Whiteboard contains a string value that is too long.")
            return False

        if isinstance(value, (int, float)):
            return False if self._is_safe_number(value) else _("Whiteboard contains an invalid number.")

        if isinstance(value, (list, dict)) and len(value) > MAX_COLLECTION_ITEMS:
            return _("Whiteboard contains an oversized collection.")

        if isinstance(value, list):
            for item in value:
                error = self._validate_json_value(item, depth=depth + 1)
                if error:
                    return error
            return False

        if isinstance(value, dict):
            for child_key, item in value.items():
                if child_key in FORBIDDEN_JSON_KEYS:
                    return _("Whiteboard data contains an unsafe property.")
                if child_key in FORBIDDEN_FABRIC_KEYS:
                    return _("Whiteboard data contains unsupported external content.")
                error = self._validate_json_value(
                    item,
                    key=child_key,
                    depth=depth + 1,
                )
                if error:
                    return error
            return False

        return _("Whiteboard data contains an unsupported value.")

    @api.model
    def _is_safe_number(self, value):
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and abs(value) <= MAX_ABS_NUMBER
        )

    @api.model
    def _is_safe_color(self, value):
        if not isinstance(value, str) or len(value) > 100:
            return False
        normalized = value.strip().lower()
        return not (
            re.match(r"^url\s*\(", normalized)
            or normalized.startswith("data:")
            or "://" in normalized
        )

    def _extract_thumbnail_base64(self, thumbnail_data_url):
        if not thumbnail_data_url:
            return True, False

        if not isinstance(thumbnail_data_url, str):
            return False, _("Thumbnail data is invalid.")

        match = re.match(
            r"^data:image/(png|jpg|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)$",
            thumbnail_data_url,
        )

        if not match:
            return False, _("Thumbnail must be a valid base64 image data URL.")

        thumbnail_b64 = re.sub(r"\s+", "", match.group(2))

        try:
            decoded = base64.b64decode(thumbnail_b64, validate=True)
        except Exception:
            return False, _("Thumbnail base64 data is invalid.")

        if len(decoded) > MAX_THUMBNAIL_BYTES:
            return False, _("Thumbnail is too large.")

        return True, thumbnail_b64

    # -------------------------------------------------------------------------
    # RPC API used by OWL action
    # -------------------------------------------------------------------------

    @api.model
    def get_user_boards(self):
        """
        Return all active boards belonging to the current user.
        """
        boards = self.search(
            [
                ("user_id", "=", self.env.uid),
                ("active", "=", True),
            ],
            order="write_date desc, id desc",
        )

        return [
            {
                "id": board.id,
                "name": board.name,
                "write_date": fields.Datetime.to_string(board.write_date) if board.write_date else False,
            }
            for board in boards
        ]

    @api.model
    def create_board(self, name=None):
        """
        Create a new board for the current user.
        """
        clean_name = (name or "").strip() or _("Untitled Board")
        board = self.create({"name": clean_name})
        return self._board_payload(board)

    @api.model
    def get_or_create_latest_board(self):
        """
        Used when opening the main Whiteboard menu.

        Multi-board behavior:
        - open latest board if user already has boards
        - otherwise create the first board
        """
        board = self.search(
            [
                ("user_id", "=", self.env.uid),
                ("active", "=", True),
            ],
            limit=1,
            order="write_date desc, id desc",
        )

        if not board:
            board = self.create({"name": _("My Whiteboard")})

        return self._board_payload(board)

    @api.model
    def get_my_board(self):
        """
        Backward-compatible alias.

        Old code expected one board per user.
        New behavior returns latest board or creates first board.
        """
        return self.get_or_create_latest_board()

    @api.model
    def get_board_data(self, board_id):
        """
        Return data for a specific board only if owned by current user.
        """
        board = self._get_current_user_board(board_id)

        if not board:
            return {"error": _("Board not found or access denied.")}

        return self._board_payload(board)

    @api.model
    def save_my_board(self, board_id, data_json, thumbnail_data_url=None, name=None):
        """
        Save a board owned by the current user.

        Important:
        - invalid board_id does not fallback to another board
        - user cannot write another user's board
        - JSON is validated server-side
        - thumbnail is validated server-side
        """
        board = self._get_current_user_board(board_id)

        if not board:
            return {"error": _("Board not found or access denied.")}

        json_ok, json_result = self._validate_data_json(data_json)
        if not json_ok:
            return {"error": json_result}

        thumb_ok, thumb_result = self._extract_thumbnail_base64(thumbnail_data_url)
        if not thumb_ok:
            return {"error": thumb_result}

        vals = {
            "data_json": json_result,
        }

        clean_name = (name or "").strip()
        if clean_name:
            vals["name"] = clean_name

        if thumb_result:
            vals["thumbnail"] = thumb_result

        board._write_validated_vals(vals)

        return {
            "ok": True,
            "board": self._board_payload(board),
        }

    def action_open_whiteboard(self):
        """
        Open this board in the whiteboard client action.
        """
        self.ensure_one()

        return {
            "type": "ir.actions.client",
            "tag": "odoo_whiteboard.whiteboard_action",
            "name": _("Whiteboard"),
            "params": {"board_id": self.id},
            "target": "current",
        }

