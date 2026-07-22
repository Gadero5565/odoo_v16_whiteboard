import json

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.models import (
    MAX_CANVAS_OBJECTS,
    MAX_PATH_COMMANDS,
    MAX_TEXT_LENGTH,
)


class TestWhiteboardPayloadValidation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Board = self.env["whiteboard.board"]

    def _validate(self, payload):
        return self.Board._validate_data_json(json.dumps(payload))

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
