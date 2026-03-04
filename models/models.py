from odoo import api, fields, models, _
import re


class WhiteboardBoard(models.Model):
    _name = "whiteboard.board"
    _description = "Whiteboard Board"
    _order = "write_date desc"

    name = fields.Char(required=True, default="My Whiteboard")
    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    data_json = fields.Text()
    thumbnail = fields.Binary(attachment=True)

    @api.model
    def get_my_board(self):
        """Return (and create if missing) a single board per user."""
        board = self.search([("user_id", "=", self.env.uid)], limit=1)
        if not board:
            board = self.create({"name": _("My Whiteboard")})
        return {
            "id": board.id,
            "name": board.name,
            "data_json": board.data_json or False,
        }

    @api.model
    def save_my_board(self, board_id, data_json, thumbnail_data_url=None, name=None):
        """Save current user's board safely."""
        board = self.browse(board_id).exists()
        if not board or board.user_id.id != self.env.uid:
            # Fallback to user's own board (never write another user's record)
            board = self.search([("user_id", "=", self.env.uid)], limit=1)
            if not board:
                board = self.create({"name": name or _("My Whiteboard")})

        vals = {"data_json": data_json}
        if name:
            vals["name"] = name

        if thumbnail_data_url:
            # expected: "data:image/png;base64,AAA..."
            m = re.match(r"^data:image/\w+;base64,(.*)$", thumbnail_data_url)
            if m:
                vals["thumbnail"] = m.group(1)

        board.write(vals)
        return True