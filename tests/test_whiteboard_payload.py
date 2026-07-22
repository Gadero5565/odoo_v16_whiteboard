import base64
from io import BytesIO
import json
from unittest.mock import patch

from PIL import Image
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models import models as whiteboard_models
from ..models.models import (
    MAX_CANVAS_OBJECTS,
    MAX_JSON_BYTES,
    MAX_PATH_COMMANDS,
    MAX_TEXT_LENGTH,
    MAX_THUMBNAIL_BYTES,
    MAX_THUMBNAIL_WIDTH,
)


class TestWhiteboardPayloadValidation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Board = self.env["whiteboard.board"]

    def _validate(self, payload):
        return self.Board._validate_data_json(json.dumps(payload))

    def _png_base64(self, width=32, height=32):
        buffer = BytesIO()

        Image.new(
            "RGB",
            (width, height),
            color="white",
        ).save(
            buffer,
            format="PNG",
        )

        return base64.b64encode(
            buffer.getvalue()
        ).decode("ascii")

    def _valid_payload(self):
        return {
            "version": "5.3.0",
            "background": "white",
            "objects": [
                {
                    "type": "path",
                    "path": [["M", 0, 0], ["Q", 10, 10, 20, 20]],
                    "fill": None,
                    "stroke": "#111111",
                    "strokeWidth": 4,
                },
                {
                    "type": "i-text",
                    "text": "Type here",
                    "left": 80,
                    "top": 80,
                    "fontSize": 28,
                    "fill": "#111111",
                },
                {
                    "type": "rect",
                    "left": 160,
                    "top": 120,
                    "width": 190,
                    "height": 110,
                    "fill": "rgba(255, 255, 255, 0.96)",
                    "stroke": "#111111",
                    "strokeWidth": 2,
                    "wbId": "rectangle_1",
                    "wbType": "shape",
                    "wbShape": "rectangle",
                    "wbVersion": 1,
                },
                {
                    "type": "circle",
                    "left": 300,
                    "top": 120,
                    "radius": 62,
                    "fill": "white",
                    "stroke": "#111111",
                    "wbId": "circle_1",
                    "wbType": "shape",
                    "wbShape": "circle",
                    "wbVersion": 1,
                },
                {
                    "type": "polygon",
                    "points": [
                        {"x": 0, "y": -60},
                        {"x": 90, "y": 0},
                        {"x": 0, "y": 60},
                        {"x": -90, "y": 0},
                    ],
                    "fill": "white",
                    "stroke": "#111111",
                    "wbId": "diamond_1",
                    "wbType": "shape",
                    "wbShape": "diamond",
                    "wbVersion": 1,
                },
                {
                    "type": "line",
                    "x1": 0,
                    "y1": 0,
                    "x2": 220,
                    "y2": 0,
                    "fill": "#111111",
                    "stroke": "#111111",
                    "wbId": "line_1",
                    "wbType": "shape",
                    "wbShape": "line",
                    "wbVersion": 1,
                },
                {
                    "type": "group",
                    "left": 400,
                    "top": 300,
                    "objects": [
                        {
                            "type": "rect",
                            "left": -115,
                            "top": -42,
                            "width": 230,
                            "height": 84,
                            "fill": "rgba(255, 255, 255, 0.98)",
                            "stroke": "#111111",
                            "strokeWidth": 2,
                            "wbId": "node_background_1",
                            "wbRole": "node_background",
                            "wbVersion": 1,
                        },
                        {
                            "type": "textbox",
                            "text": "Main Idea",
                            "left": -95,
                            "top": -14,
                            "width": 190,
                            "fontSize": 18,
                            "fill": "#0f172a",
                            "wbId": "node_text_1",
                            "wbRole": "node_text",
                            "wbVersion": 1,
                        },
                    ],
                    "wbId": "mind_node_1",
                    "wbType": "mind_node",
                    "wbShape": "mind_node",
                    "wbNodeType": "mind_node",
                    "wbText": "Main Idea",
                    "wbVersion": 1,
                },
                {
                    "type": "path",
                    "path": [["M", -100, 0], ["L", 80, 0], ["L", 100, 0]],
                    "fill": None,
                    "stroke": "#111111",
                    "strokeWidth": 3,
                    "wbId": "connector_1",
                    "wbType": "connector",
                    "wbShape": "arrow",
                    "wbConnectorType": "straight_arrow",
                    "wbFromNodeId": "mind_node_1",
                    "wbToNodeId": "rectangle_1",
                    "wbVersion": 1,
                },
            ],
        }

    def test_valid_current_editor_payload_is_accepted(self):
        valid, normalized = self._validate(self._valid_payload())

        self.assertTrue(valid)
        self.assertEqual(json.loads(normalized), self._valid_payload())

    def test_empty_legacy_payload_is_accepted(self):
        for value in (None, False, "", "{}"):
            valid, normalized = self.Board._validate_data_json(value)
            self.assertTrue(valid)
            self.assertEqual(normalized, "{}")

    def test_direct_create_cannot_bypass_validation(self):
        with self.assertRaises(ValidationError):
            self.Board.create({
                "name": "Invalid board",
                "data_json": '{"objects":[{"type":"image","src":"https://example.com/a.png"}]}',
            })

    def test_direct_write_cannot_bypass_validation(self):
        board = self.Board.create({"name": "Validation test"})

        with self.assertRaises(ValidationError):
            board.write({
                "data_json": '{"objects":[{"type":"rect","clipPath":{"type":"circle"}}]}',
            })

    def test_direct_write_accepts_current_editor_payload(self):
        board = self.Board.create({"name": "Valid board", "data_json": False})
        valid_payload = self._valid_payload()

        board.write({"data_json": json.dumps(valid_payload)})

        self.assertEqual(json.loads(board.data_json), valid_payload)

    def test_unknown_object_type_is_rejected(self):
        payload = self._valid_payload()
        payload["objects"] = [{"type": "image", "src": "https://example.com/a.png"}]

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_external_fabric_content_is_rejected(self):
        payload = self._valid_payload()
        payload["objects"][0]["sourcePath"] = "https://example.com/path.json"

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_clip_path_is_rejected(self):
        payload = self._valid_payload()
        payload["objects"][2]["clipPath"] = {"type": "circle", "radius": 10}

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_gradient_or_pattern_fill_is_rejected(self):
        payload = self._valid_payload()
        payload["objects"][2]["fill"] = {
            "type": "linear",
            "colorStops": [{"offset": 0, "color": "#fff"}],
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_non_finite_json_number_is_rejected(self):
        valid, _error = self.Board._validate_data_json(
            '{"objects":[{"type":"rect","left":NaN}]}'
        )

        self.assertFalse(valid)

    def test_duplicate_json_keys_are_rejected(self):
        valid, _error = self.Board._validate_data_json(
            '{"objects":[],"objects":[]}'
        )

        self.assertFalse(valid)

    def test_prototype_pollution_key_is_rejected(self):
        valid, _error = self.Board._validate_data_json(
            '{"objects":[{"type":"rect","__proto__":{"polluted":true}}]}'
        )

        self.assertFalse(valid)

    def test_object_limit_is_enforced(self):
        payload = {
            "objects": [
                {"type": "rect", "fill": "white", "stroke": "black"}
                for _index in range(MAX_CANVAS_OBJECTS + 1)
            ]
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_text_limit_is_enforced(self):
        payload = {
            "objects": [
                {
                    "type": "i-text",
                    "text": "x" * (MAX_TEXT_LENGTH + 1),
                    "fill": "#111111",
                }
            ]
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_path_complexity_limit_is_enforced(self):
        payload = {
            "objects": [
                {
                    "type": "path",
                    "path": [["L", 1, 1] for _index in range(MAX_PATH_COMMANDS + 1)],
                    "fill": None,
                    "stroke": "#111111",
                }
            ]
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_group_depth_limit_is_enforced(self):
        nested = {"type": "rect", "fill": "white", "stroke": "black"}
        for _index in range(4):
            nested = {"type": "group", "objects": [nested]}

        valid, _error = self._validate({"objects": [nested]})

        self.assertFalse(valid)

    def test_extreme_scale_is_rejected(self):
        payload = {
            "objects": [
                {
                    "type": "rect",
                    "scaleX": 1000,
                    "scaleY": 1,
                    "fill": "white",
                }
            ]
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_metadata_type_mismatch_is_rejected(self):
        payload = {
            "objects": [
                {
                    "type": "circle",
                    "wbType": "shape",
                    "wbShape": "rectangle",
                }
            ]
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_canvas_image_property_is_rejected(self):
        payload = {
            "objects": [],
            "backgroundImage": {
                "type": "image",
                "src": "https://example.com/background.png",
            },
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)

    def test_json_byte_limit_is_enforced(self):
        valid, _error = self.Board._validate_data_json(
            " " * (MAX_JSON_BYTES + 1)
        )

        self.assertFalse(valid)

    def test_board_creation_quota_is_enforced(self):
        existing_count = (
            self.Board.sudo()
            .with_context(active_test=False)
            .search_count([
                ("user_id", "=", self.env.uid),
            ])
        )

        with patch.object(
                whiteboard_models,
                "MAX_BOARDS_PER_USER",
                existing_count + 2,
        ):
            self.Board.create({"name": "Quota 1"})
            self.Board.create({"name": "Quota 2"})

            with self.assertRaises(ValidationError):
                self.Board.create({"name": "Quota 3"})

    def test_board_creation_quota_counts_archived_boards(self):
        existing_count = (
            self.Board.sudo()
            .with_context(active_test=False)
            .search_count([
                ("user_id", "=", self.env.uid),
            ])
        )

        with patch.object(
                whiteboard_models,
                "MAX_BOARDS_PER_USER",
                existing_count + 1,
        ):
            board = self.Board.create({
                "name": "Archived quota board",
            })

            board.write({"active": False})

            with self.assertRaises(ValidationError):
                self.Board.create({
                    "name": "Quota bypass attempt",
                })

    def test_multi_create_cannot_bypass_board_quota(self):
        existing_count = (
            self.Board.sudo()
            .with_context(active_test=False)
            .search_count([
                ("user_id", "=", self.env.uid),
            ])
        )

        with patch.object(
                whiteboard_models,
                "MAX_BOARDS_PER_USER",
                existing_count + 1,
        ):
            with self.assertRaises(ValidationError):
                self.Board.create([
                    {"name": "Batch 1"},
                    {"name": "Batch 2"},
                ])

    def test_board_list_result_limit_is_enforced(self):
        first = self.Board.create({
            "name": "List limit 1",
        })
        second = self.Board.create({
            "name": "List limit 2",
        })
        third = self.Board.create({
            "name": "List limit 3",
        })

        with patch.object(
                whiteboard_models,
                "MAX_BOARD_LIST_RESULTS",
                2,
        ):
            boards = self.Board.get_user_boards()

        board_ids = [
            board["id"]
            for board in boards
        ]

        self.assertEqual(
            board_ids,
            [third.id, second.id],
        )
        self.assertNotIn(first.id, board_ids)

    def test_valid_thumbnail_data_url_is_accepted(self):
        thumbnail_b64 = self._png_base64()

        valid, normalized = (
            self.Board._extract_thumbnail_base64(
                "data:image/png;base64,%s"
                % thumbnail_b64
            )
        )

        self.assertTrue(valid)
        self.assertEqual(
            normalized,
            thumbnail_b64,
        )

    def test_thumbnail_must_be_a_real_image(self):
        fake_image = base64.b64encode(
            b"not an image"
        ).decode("ascii")

        valid, _error = (
            self.Board._extract_thumbnail_base64(
                fake_image
            )
        )

        self.assertFalse(valid)

    def test_thumbnail_byte_limit_is_enforced(self):
        oversized = base64.b64encode(
            b"x" * (MAX_THUMBNAIL_BYTES + 1)
        ).decode("ascii")

        valid, _error = (
            self.Board._extract_thumbnail_base64(
                oversized
            )
        )

        self.assertFalse(valid)

    def test_thumbnail_dimension_limit_is_enforced(self):
        oversized_dimensions = self._png_base64(
            width=MAX_THUMBNAIL_WIDTH + 1,
            height=1,
        )

        valid, _error = (
            self.Board._extract_thumbnail_base64(
                oversized_dimensions
            )
        )

        self.assertFalse(valid)

    def test_direct_create_cannot_bypass_thumbnail_validation(self):
        fake_image = base64.b64encode(
            b"not an image"
        ).decode("ascii")

        with self.assertRaises(ValidationError):
            self.Board.create({
                "name": "Invalid thumbnail",
                "thumbnail": fake_image,
            })

    def test_direct_write_cannot_bypass_thumbnail_validation(self):
        board = self.Board.create({
            "name": "Thumbnail validation",
        })

        fake_image = base64.b64encode(
            b"not an image"
        ).decode("ascii")

        with self.assertRaises(ValidationError):
            board.write({
                "thumbnail": fake_image,
            })

    def test_text_object_accepts_fabric_null_path_property(self):
        payload = {
            "objects": [
                {
                    "type": "textbox",
                    "text": "Flowchart node",
                    "path": None,
                    "fill": "#0f172a",
                    "fontSize": 16,
                }
            ],
        }

        valid, error = self._validate(payload)

        self.assertTrue(valid, error)

    def test_non_path_object_with_real_path_data_is_rejected(self):
        payload = {
            "objects": [
                {
                    "type": "textbox",
                    "text": "Unsafe text path",
                    "path": [
                        ["M", 0, 0],
                        ["L", 100, 100],
                    ],
                    "fill": "#0f172a",
                }
            ],
        }

        valid, _error = self._validate(payload)

        self.assertFalse(valid)
