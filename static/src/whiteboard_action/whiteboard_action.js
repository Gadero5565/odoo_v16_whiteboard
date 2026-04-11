/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";

export class WhiteboardAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.canvasRef = useRef("canvas");
        this.wrapRef = useRef("wrap");
        const params = this.props.action?.params || {};
        this.initialBoardId = params.board_id || null;
        this.state = useState({
            loading: true,
            boardId: null,
            boardName: "My Whiteboard",
            color: "#111111",
            width: 4,
            mode: "pen",
            boards: [],
        });

        this.undoStack = [];
        this.redoStack = [];
        this._isApplyingHistory = false;

        // Load Fabric from CDN (you can replace with any CDN/library)
        onWillStart(async () => {
            await loadJS("https://cdn.jsdelivr.net/npm/fabric@5.3.0/dist/fabric.min.js");
            await this._loadBoardsList();
        });

        onMounted(async () => {
            await this._initFabric();
            await this._loadBoardFromServer();

            this.state.loading = false;
            this._resizeCanvas();
            window.addEventListener("resize", this._resizeCanvas);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._resizeCanvas);
            if (this.canvas) this.canvas.dispose();
        });

        this._resizeCanvas = this._resizeCanvas.bind(this);
    }

    // ---------- Fabric init ----------
    async _initFabric() {
        const fabric = window.fabric;
        if (!fabric) {
            this.notification.add("Fabric.js failed to load from CDN.", { type: "danger" });
            return;
        }

        const canvasEl = this.canvasRef.el;
        this.canvas = new fabric.Canvas(canvasEl, {
            backgroundColor: "white",
            preserveObjectStacking: true,
            selection: true,
            enablePointerEvents: true,
        });

        // Helps ensure we still get pointerup even if cursor leaves the canvas while drawing
        const upper = this.canvas.upperCanvasEl;
        upper.style.touchAction = "none";

        upper.addEventListener("pointerdown", (ev) => {
            try { upper.setPointerCapture(ev.pointerId); } catch {}
        });
        upper.addEventListener("pointerup", (ev) => {
            try { upper.releasePointerCapture(ev.pointerId); } catch {}
        });
        upper.addEventListener("pointercancel", (ev) => {
            try { upper.releasePointerCapture(ev.pointerId); } catch {}
        });

        // Drawing mode by default
        this.canvas.isDrawingMode = true;
        this._applyBrush();

        // History hooks
        this.canvas.on("path:created", () => this._pushHistory());
        this.canvas.on("object:modified", () => this._pushHistory());
        this.canvas.on("object:removed", () => this._pushHistory());

        // object:added fires a lot (including loadFromJSON). We guard with flag.
        this.canvas.on("object:added", () => {
            if (!this._isApplyingHistory) this._pushHistory();
        });

        // Initial empty state
        this._pushHistory(true);
    }

    _resizeCanvas() {
        if (!this.canvas || !this.wrapRef.el) return;

        const rect = this.wrapRef.el.getBoundingClientRect();
        const w = Math.max(300, Math.floor(rect.width));
        const h = Math.max(300, Math.floor(rect.height));

        // use setDimensions + calcOffset (better with scrolling containers)
        this.canvas.setDimensions({ width: w, height: h });
        this.canvas.calcOffset();
        this.canvas.requestRenderAll();
    }

    _applyBrush() {
        const fabric = window.fabric;
        if (!this.canvas || !fabric) return;

        const brush = new fabric.PencilBrush(this.canvas);
        brush.width = Number(this.state.width) || 4;

        // Simple eraser: draw with background color
        brush.color = this.state.mode === "eraser" ? "#ffffff" : this.state.color;

        this.canvas.freeDrawingBrush = brush;
    }

    // ---------- UI handlers ----------
    setColor(ev) {
        this.state.color = ev.target.value;
        if (this.state.mode === "pen") this._applyBrush();
    }

    setWidth(ev) {
        this.state.width = parseInt(ev.target.value || "4", 10);
        this._applyBrush();
    }

    setPen() {
        this.state.mode = "pen";
        this.canvas.isDrawingMode = true;
        this._applyBrush();
    }

    setEraser() {
        this.state.mode = "eraser";
        this.canvas.isDrawingMode = true;
        this._applyBrush();
    }

    addText() {
        const fabric = window.fabric;
        if (!fabric || !this.canvas) return;

        this.canvas.isDrawingMode = false;

        const text = new fabric.IText("Type here", {
            left: 80,
            top: 80,
            fontSize: 28,
            fill: this.state.color,
        });

        this.canvas.add(text);
        this.canvas.setActiveObject(text);
        this.canvas.requestRenderAll();
        this._pushHistory();
    }

    clearCanvas() {
        if (!this.canvas) return;
        this.canvas.getObjects().forEach((obj) => this.canvas.remove(obj));
        this.canvas.requestRenderAll();
        this._pushHistory(true);
    }

    undo() {
        if (this.undoStack.length <= 1 || !this.canvas) return;

        const current = this.undoStack.pop();
        this.redoStack.push(current);

        const prev = this.undoStack[this.undoStack.length - 1];
        this._applyJSON(prev, { pushHistory: false });
    }

    redo() {
        if (!this.redoStack.length || !this.canvas) return;

        const next = this.redoStack.pop();
        this.undoStack.push(next);
        this._applyJSON(next, { pushHistory: false });
    }

    exportPNG() {
        if (!this.canvas) return;
        const url = this.canvas.toDataURL({ format: "png" });

        const a = document.createElement("a");
        a.href = url;
        a.download = (this.state.boardName || "whiteboard").replace(/[^\w\-]+/g, "_") + ".png";
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    async _loadBoardsList() {
        const boards = await this.orm.call("whiteboard.board", "get_user_boards", []);
        this.state.boards = boards;
        // If we have an initial board ID, make sure it's in the list
        if (this.state.boardId && !boards.find(b => b.id === this.state.boardId)) {
            this.state.boardId = null;
        }
    }

    onSelectBoard(ev) {
        const boardId = parseInt(ev.target.value, 10);
        if (!boardId) return;
        this.state.boardId = boardId;
        this._loadBoardFromServer(boardId);
    }

    // ---------- Save/load (server) ----------
    async _loadBoardFromServer(boardId = null) {
        let res;
        if (boardId) {
            res = await this.orm.call("whiteboard.board", "get_board_data", [boardId]);
            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
                return;
            }
        } else {
            res = await this.orm.call("whiteboard.board", "get_my_board", []);
        }

        this.state.boardId = res.id;
        this.state.boardName = res.name || "My Whiteboard";

        if (res.data_json) {
            await this._applyJSON(res.data_json, { pushHistory: true, resetRedo: true });
        } else {
            // Clear canvas for new empty board
            this.canvas?.clear();
            this._pushHistory(true);
        }
    }

    async save() {
            if (!this.canvas) return;

            const data_json = JSON.stringify(this.canvas.toDatalessJSON());
            const thumbnail = this.canvas.toDataURL({ format: "png", multiplier: 0.2 });

            // Use current boardId or fallback to get_my_board
            let boardId = this.state.boardId;
            if (!boardId) {
                // Ensure we have a board created
                const myBoard = await this.orm.call("whiteboard.board", "get_my_board", []);
                boardId = myBoard.id;
                this.state.boardId = boardId;
                this.state.boardName = myBoard.name;
            }

            await this.orm.call(
                "whiteboard.board",
                "save_my_board",
                [boardId, data_json, thumbnail, this.state.boardName]
            );

            this.notification.add("Whiteboard saved.", { type: "success" });
            // Refresh board list in case name changed
            await this._loadBoardsList();
        }

    // ---------- History helpers ----------
    _pushHistory(resetRedo = false) {
        if (!this.canvas || this._isApplyingHistory) return;

        const json = JSON.stringify(this.canvas.toDatalessJSON());
        this.undoStack.push(json);

        if (resetRedo) this.redoStack = [];
        else this.redoStack = [];

        // keep history bounded
        if (this.undoStack.length > 50) this.undoStack.shift();
    }

    async _applyJSON(json, { pushHistory = true, resetRedo = false } = {}) {
        if (!this.canvas) return;

        let obj = json;
        try {
            if (typeof json === "string") obj = JSON.parse(json);
        } catch (e) {
            this.notification.add("Saved board data is not valid JSON.", { type: "danger" });
            return;
        }

        this._isApplyingHistory = true;
        await new Promise((resolve) => {
            this.canvas.loadFromJSON(obj, () => {
                this.canvas.requestRenderAll();
                this._isApplyingHistory = false;
                if (pushHistory) this._pushHistory(resetRedo);
                resolve();
            });
        });
    }
}

WhiteboardAction.template = "odoo_whiteboard.WhiteboardAction";
registry.category("actions").add("odoo_whiteboard.whiteboard_action", WhiteboardAction);