from odoo import api, fields, models, _
import base64
import json
import re


MAX_JSON_BYTES = 10 * 1024 * 1024       # 10 MB
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024   # 2 MB


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
        for vals in vals_list:
            vals["user_id"] = self.env.uid
            vals.setdefault("company_id", self.env.company.id)
        return super().create(vals_list)

    def write(self, vals):
        """
        Prevent ownership reassignment from frontend/RPC.
        """
        vals = dict(vals)
        vals.pop("user_id", None)
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

    def _validate_data_json(self, data_json):
        if data_json is None:
            data_json = "{}"

        if not isinstance(data_json, str):
            return False, _("Whiteboard data must be a JSON string.")

        if len(data_json.encode("utf-8")) > MAX_JSON_BYTES:
            return False, _("Whiteboard is too large to save.")

        try:
            parsed = json.loads(data_json or "{}")
        except Exception:
            return False, _("Whiteboard data is not valid JSON.")

        if not isinstance(parsed, dict):
            return False, _("Whiteboard data must be a JSON object.")

        return True, data_json

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

        board.write(vals)

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