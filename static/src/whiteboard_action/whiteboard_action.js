/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import {
    WHITEBOARD_OBJECT_PROPS,
    createWhiteboardShape,
    createWhiteboardArrow,
    createWhiteboardMindNode,
    createWhiteboardConnector,
    createWhiteboardFlowNode,
} from "./whiteboard_objects";

import {
    WHITEBOARD_TEMPLATES,
    buildWhiteboardTemplate,
} from "./whiteboard_templates";

export class WhiteboardAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.canvasRef = useRef("canvas");
        this.wrapRef = useRef("wrap");

        const rawBoardId = this.props.action?.params?.board_id;
        const parsedBoardId = rawBoardId ? parseInt(rawBoardId, 10) : null;

        this.initialBoardId = Number.isFinite(parsedBoardId) ? parsedBoardId : null;

        this.state = useState({
            loading: true,
            saving: false,
            boardId: this.initialBoardId,
            boardName: "My Whiteboard",
            boardRevision: null,
            dirty: false,

            sidebarOpen: false,

            color: "#111111",
            width: 4,
            mode: "pen",
            connectorFromNodeId: null,

            templates: WHITEBOARD_TEMPLATES,
            boards: [],
        });

        this.undoStack = [];
        this.redoStack = [];
        this._isApplyingHistory = false;
        this._historyTimer = null;

        this._resizeCanvas = this._resizeCanvas.bind(this);

        this._beforeUnload = (ev) => {
            if (!this.state.dirty) return;
            ev.preventDefault();
            ev.returnValue = "";
            return "";
        };

        this._handleKeyDown = (ev) => {
            const targetTag = ev.target?.tagName?.toLowerCase();
            const isTypingInHtmlInput = ["input", "textarea", "select"].includes(targetTag);

            if (isTypingInHtmlInput || ev.target?.isContentEditable) {
                return;
            }

            const activeObject = this.canvas?.getActiveObject();

            if (!activeObject || activeObject.isEditing) {
                return;
            }

            if (ev.key === "Delete" || ev.key === "Backspace") {
                ev.preventDefault();
                this.deleteSelectedObjects();
            }
        };

        onWillStart(async () => {
            await this._loadBoardsList();
        });

        onMounted(async () => {
            try {
                const ready = await this._initFabric();
                if (ready) {
                    await this._loadBoardFromServer(this.initialBoardId);
                    this._resizeCanvas();
                    window.addEventListener("resize", this._resizeCanvas);
                    window.addEventListener("beforeunload", this._beforeUnload);
                    window.addEventListener("keydown", this._handleKeyDown);
                }
            } finally {
                this.state.loading = false;
            }
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._resizeCanvas);
            window.removeEventListener("beforeunload", this._beforeUnload);
            window.removeEventListener("keydown", this._handleKeyDown);

            if (this._historyTimer) {
                clearTimeout(this._historyTimer);
                this._historyTimer = null;
            }

            if (this.canvas) {
                this.canvas.dispose();
            }
        });
    }

    // -------------------------------------------------------------------------
    // Fabric init
    // -------------------------------------------------------------------------

    async _initFabric() {
        const fabric = window.fabric;

        if (!fabric) {
            this.notification.add(
                "Fabric.js is not loaded. Add static/lib/fabric/fabric.min.js to web.assets_backend.",
                { type: "danger" }
            );
            return false;
        }

        const canvasEl = this.canvasRef.el;

        this.canvas = new fabric.Canvas(canvasEl, {
            backgroundColor: "white",
            preserveObjectStacking: true,
            selection: true,
            enablePointerEvents: true,
        });

        const upper = this.canvas.upperCanvasEl;
        upper.style.touchAction = "none";

        upper.addEventListener("pointerdown", (ev) => {
            try {
                upper.setPointerCapture(ev.pointerId);
            } catch {
                // ignored
            }
        });

        upper.addEventListener("pointerup", (ev) => {
            try {
                upper.releasePointerCapture(ev.pointerId);
            } catch {
                // ignored
            }
        });

        upper.addEventListener("pointercancel", (ev) => {
            try {
                upper.releasePointerCapture(ev.pointerId);
            } catch {
                // ignored
            }
        });

        this.canvas.isDrawingMode = true;
        this._applyBrush();

        /*
         * History strategy:
         * - do not listen to object:added globally because it duplicates path/text pushes
         * - path:created handles drawing
         * - object:modified handles move/resize/rotate
         * - object:removed handles object deletion
         * - text:changed is debounced so typing does not create a huge history stack
         */
        this.canvas.on("path:created", () => this._pushHistory());

        this.canvas.on("object:moving", (ev) => {
            this._updateConnectorsForObject(ev.target);
        });

        this.canvas.on("object:scaling", (ev) => {
            this._updateConnectorsForObject(ev.target);
        });

        this.canvas.on("object:rotating", (ev) => {
            this._updateConnectorsForObject(ev.target);
        });

        this.canvas.on("object:modified", (ev) => {
            this._updateConnectorsForObject(ev.target);
            this._pushHistory();
        });

        this.canvas.on("object:removed", () => this._pushHistory());
        this.canvas.on("text:changed", () => this._pushHistoryDebounced());

        this.canvas.on("mouse:dblclick", (ev) => {
            this._editNodeFromTarget(ev.target);
        });

        this.canvas.on("mouse:down", (ev) => {
            this._handleConnectorMouseDown(ev);
        });

        this._resetHistoryFromCanvas();

        return true;
    }

    _resizeCanvas() {
        if (!this.canvas || !this.wrapRef.el) return;

        const rect = this.wrapRef.el.getBoundingClientRect();
        const style = window.getComputedStyle(this.wrapRef.el);

        const paddingX =
            parseFloat(style.paddingLeft || "0") +
            parseFloat(style.paddingRight || "0");

        const paddingY =
            parseFloat(style.paddingTop || "0") +
            parseFloat(style.paddingBottom || "0");

        const width = Math.max(300, Math.floor(rect.width - paddingX));
        const height = Math.max(300, Math.floor(rect.height - paddingY));

        this.canvas.setDimensions({ width, height });
        this.canvas.calcOffset();
        this.canvas.requestRenderAll();
    }

    _applyBrush() {
        const fabric = window.fabric;
        if (!this.canvas || !fabric) return;

        const brush = new fabric.PencilBrush(this.canvas);
        brush.width = Number(this.state.width) || 4;

        /*
         * MVP eraser:
         * This draws white over content. It is not object-level erasing.
         * A true eraser can be added later with object/path deletion behavior.
         */
        brush.color = this.state.mode === "eraser" ? "#ffffff" : this.state.color;

        this.canvas.freeDrawingBrush = brush;
    }

    // -------------------------------------------------------------------------
    // SideBar
    // -------------------------------------------------------------------------

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        this._resizeCanvasAfterSidebarAnimation();
    }

    openSidebar() {
        this.state.sidebarOpen = true;
        this._resizeCanvasAfterSidebarAnimation();
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
        this._resizeCanvasAfterSidebarAnimation();
    }

    _resizeCanvasAfterSidebarAnimation() {
        if (!this.canvas) {
            return;
        }

        requestAnimationFrame(() => this._resizeCanvas());

        window.setTimeout(() => {
            this._resizeCanvas();
        }, 260);
    }

    /* -------------------------------------------------------------------------
     * Templates
     * ------------------------------------------------------------------------- */

    insertTemplate(templateCode) {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        this.setSelect();

        const point = this._getInsertPoint();

        const result = buildWhiteboardTemplate(fabric, templateCode, {
            centerX: point.x,
            centerY: point.y,
            color: this.state.color,
        });

        if (!result || !result.objects?.length) {
            this.notification.add("Template could not be inserted.", {
                type: "warning",
            });
            return;
        }

        this._runWithoutHistory(() => {
            for (const object of result.objects) {
                this.canvas.add(object);
            }

            for (const connector of result.connectors || []) {
                this.canvas.sendToBack(connector);
            }
        });

        if (result.activeObject) {
            this.canvas.setActiveObject(result.activeObject);
        }

        this._updateAllConnectors();
        this.canvas.requestRenderAll();

        this._pushHistory();

        const template = this.state.templates.find((item) => item.code === templateCode);
        const templateName = template?.name || "Template";

        this.notification.add(`${templateName} template inserted.`, {
            type: "success",
        });
    }

    insertMindMapTemplate() {
        this.insertTemplate("mind_map");
    }

    insertProjectPlanTemplate() {
        this.insertTemplate("project_plan");
    }

    insertBasicFlowchartTemplate() {
        this.insertTemplate("basic_flowchart");
    }

    insertProjectWorkflowTemplate() {
        this.insertTemplate("project_workflow");
    }

    // -------------------------------------------------------------------------
    // UI handlers
    // -------------------------------------------------------------------------

    setColor(ev) {
        this.state.color = ev.target.value;
        if (this.state.mode === "pen") {
            this._applyBrush();
        }
    }

    setWidth(ev) {
        this.state.width = parseInt(ev.target.value || "4", 10);
        this._applyBrush();
    }

    setSelect() {
        if (!this.canvas) return;

        this.state.mode = "select";
        this.state.connectorFromNodeId = null;

        this.canvas.isDrawingMode = false;
        this.canvas.selection = true;
        this.canvas.defaultCursor = "default";
    }

    setPen() {
        if (!this.canvas) return;

        this.state.mode = "pen";
        this.state.connectorFromNodeId = null;

        this.canvas.isDrawingMode = true;
        this.canvas.selection = false;
        this._applyBrush();
    }

    setEraser() {
        if (!this.canvas) return;

        this.state.mode = "eraser";
        this.state.connectorFromNodeId = null;

        this.canvas.isDrawingMode = true;
        this.canvas.selection = false;
        this._applyBrush();
    }

    setConnectorMode() {
        if (!this.canvas) return;

        this.state.mode = "connector";
        this.state.connectorFromNodeId = null;

        this.canvas.isDrawingMode = false;
        this.canvas.selection = false;
        this.canvas.discardActiveObject();
        this.canvas.defaultCursor = "crosshair";
        this.canvas.requestRenderAll();

        this.notification.add("Connector mode: click a source object, then a target object.", {
            type: "info",
        });
    }

    addText() {
    const fabric = window.fabric;
    if (!fabric || !this.canvas) return;

    this.state.mode = "text";
    this.state.connectorFromNodeId = null;

    this.canvas.isDrawingMode = false;
    this.canvas.selection = true;
    this.canvas.defaultCursor = "text";

    const point = this._getInsertPoint();

    const text = new fabric.IText("Type here", {
        left: point.x,
        top: point.y,
        originX: "center",
        originY: "center",
        fontSize: 28,
        fill: this.state.color,
    });

    text.on("editing:exited", () => {
        if (this.state.mode === "text") {
            this.setSelect();
        }
    });

    this.canvas.add(text);
    this.canvas.setActiveObject(text);
    this.canvas.requestRenderAll();

    text.enterEditing();
    text.selectAll();

    this._pushHistory();
}

    clearCanvas() {
        if (!this.canvas) return;

        const confirmed = window.confirm("Clear this whiteboard?");
        if (!confirmed) return;

        this._runWithoutHistory(() => {
            this._clearCanvasObjects();
        });

        this._pushHistory();
    }

    undo() {
        if (!this.canvas || this.undoStack.length <= 1) return;

        this._flushDebouncedHistory();

        const current = this.undoStack.pop();
        this.redoStack.push(current);

        const previous = this.undoStack[this.undoStack.length - 1];

        this._applyJSON(previous).then((ok) => {
            if (ok) {
                this.state.dirty = true;
            }
        });
    }

    redo() {
        if (!this.canvas || !this.redoStack.length) return;

        this._flushDebouncedHistory();

        const next = this.redoStack.pop();
        this.undoStack.push(next);

        this._applyJSON(next).then((ok) => {
            if (ok) {
                this.state.dirty = true;
            }
        });
    }

    exportPNG() {
        if (!this.canvas) return;

        const url = this.canvas.toDataURL({ format: "png" });

        const safeName = (this.state.boardName || "whiteboard")
            .replace(/[^\w\-]+/g, "_")
            .replace(/^_+|_+$/g, "");

        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeName || "whiteboard"}.png`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    async createBoard() {
        if (this.state.dirty) {
            const confirmed = window.confirm("You have unsaved changes. Create a new board and discard them?");
            if (!confirmed) return;
        }

        this.state.loading = true;

        try {
            const result = await this.orm.call(
                "whiteboard.board",
                "create_board",
                ["Untitled Board"]
            );

            if (result?.error) {
                this.notification.add(result.error, { type: "danger" });
                return;
            }

            await this._applyBoardPayload(result);
            await this._loadBoardsList();

            this.notification.add("New whiteboard created.", { type: "success" });
        } catch {
            this.notification.add("Could not create whiteboard.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onSelectBoard(ev) {
        const selectedBoardId = parseInt(ev.target.value, 10);

        if (!selectedBoardId || selectedBoardId === this.state.boardId) {
            return;
        }

        if (this.state.dirty) {
            const confirmed = window.confirm("You have unsaved changes. Switch boards and discard them?");
            if (!confirmed) {
                ev.target.value = this.state.boardId ? String(this.state.boardId) : "";
                return;
            }
        }

        this.state.loading = true;

        try {
            await this._loadBoardFromServer(selectedBoardId);
        } finally {
            this.state.loading = false;
        }
    }

    _getInsertPoint() {
        if (!this.canvas) {
            return { x: 160, y: 120 };
        }

        const canvasWidth = this.canvas.getWidth();
        const canvasHeight = this.canvas.getHeight();

        const canvasEl = this.canvas.upperCanvasEl;
        const bodyEl = this.wrapRef.el?.parentElement;

        if (!canvasEl || !bodyEl) {
            return {
                x: canvasWidth / 2,
                y: canvasHeight / 2,
            };
        }

        const canvasRect = canvasEl.getBoundingClientRect();
        const bodyRect = bodyEl.getBoundingClientRect();

        const visibleCenterX = bodyRect.left + bodyRect.width / 2;
        const visibleCenterY = bodyRect.top + bodyRect.height / 2;

        const x = visibleCenterX - canvasRect.left;
        const y = visibleCenterY - canvasRect.top;

        return {
            x: Math.max(80, Math.min(canvasWidth - 80, x)),
            y: Math.max(80, Math.min(canvasHeight - 80, y)),
        };
    }

    _addShape(shape) {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        this.setSelect();

        const point = this._getInsertPoint();

        const object = createWhiteboardShape(fabric, shape, {
            left: point.x,
            top: point.y,
            color: this.state.color,
            strokeWidth: this.state.width,
        });

        if (!object) {
            this.notification.add("Unsupported shape.", { type: "warning" });
            return;
        }

        this.canvas.add(object);
        this.canvas.setActiveObject(object);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    addRectangle() {
        this._addShape("rectangle");
    }

    addCircle() {
        this._addShape("circle");
    }

    addDiamond() {
        this._addShape("diamond");
    }

    addLine() {
        this._addShape("line");
    }

    /* -------------------------------------------------------------------------
     * Arrows
     * ------------------------------------------------------------------------- */

    addArrow() {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        this.setSelect();

        const point = this._getInsertPoint();

        const arrow = createWhiteboardArrow(fabric, {
            left: point.x,
            top: point.y,
            color: this.state.color,
            strokeWidth: this.state.width,
        });

        this.canvas.add(arrow);
        this.canvas.setActiveObject(arrow);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    /* -------------------------------------------------------------------------
     * Mind map nodes
     * ------------------------------------------------------------------------- */

    addMindNode() {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        this.setSelect();

        const point = this._getInsertPoint();

        const node = createWhiteboardMindNode(fabric, {
            left: point.x,
            top: point.y,
            color: this.state.color,
            text: "New idea",
        });

        this.canvas.add(node);
        this.canvas.setActiveObject(node);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    addMindChild() {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        const parentNode = this._getNodeFromTarget(this.canvas.getActiveObject());

        if (!parentNode || parentNode.wbType !== "mind_node") {
            this.notification.add("Select a mind-map node first.", { type: "warning" });
            return;
        }

        this.setSelect();

        const parentCenter = parentNode.getCenterPoint();

        const childNode = createWhiteboardMindNode(fabric, {
            left: parentCenter.x + 330,
            top: parentCenter.y,
            color: this.state.color,
            text: "New idea",
            parentNodeId: parentNode.wbId,
        });

        this.canvas.add(childNode);

        const connector = this._createConnectorBetweenObjects(parentNode, childNode, {
            connectorType: "mind_arrow",
        });

        if (connector) {
            this.canvas.add(connector);
            this.canvas.sendToBack(connector);
        }

        this.canvas.setActiveObject(childNode);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    /* -------------------------------------------------------------------------
     * Flowchart nodes
     * ------------------------------------------------------------------------- */

    _addFlowNode(nodeType) {
        const fabric = window.fabric;

        if (!fabric || !this.canvas) {
            return;
        }

        this.setSelect();

        const point = this._getInsertPoint();

        const node = createWhiteboardFlowNode(fabric, {
            left: point.x,
            top: point.y,
            color: this.state.color,
            nodeType,
        });

        this.canvas.add(node);
        this.canvas.setActiveObject(node);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    addFlowTerminator() {
        this._addFlowNode("terminator");
    }

    addFlowProcess() {
        this._addFlowNode("process");
    }

    addFlowDecision() {
        this._addFlowNode("decision");
    }

    addFlowData() {
        this._addFlowNode("data");
    }

    /* -------------------------------------------------------------------------
     * Generic node editing
     * ------------------------------------------------------------------------- */

    editSelectedNode() {
        const node = this._getNodeFromTarget(this.canvas?.getActiveObject());

        if (!node) {
            this.notification.add("Select a mind-map or flowchart node first.", { type: "warning" });
            return;
        }

        this._editNode(node);
    }

    // Keep backward compatibility with current XML if the old method name is still used.
    editSelectedMindNode() {
        this.editSelectedNode();
    }

    _editNodeFromTarget(target) {
        const node = this._getNodeFromTarget(target);

        if (node) {
            this._editNode(node);
        }
    }

    _editNode(node) {
        if (!node) return;

        const currentText = node.wbText || this._getNodeText(node) || "";
        const nextText = window.prompt("Node text", currentText);

        if (nextText === null) {
            return;
        }

        const cleanText = nextText.trim() || "New idea";

        this._setNodeText(node, cleanText);
        this.canvas.setActiveObject(node);
        this.canvas.requestRenderAll();

        this._pushHistory();
    }

    _getNodeFromTarget(target) {
        if (!target) {
            return null;
        }

        if (target.wbType === "mind_node" || target.wbType === "flow_node") {
            return target;
        }

        if (
            target.group
            && (
                target.group.wbType === "mind_node"
                || target.group.wbType === "flow_node"
            )
        ) {
            return target.group;
        }

        return null;
    }

    _getNodeText(node) {
        if (!node || !node.getObjects) {
            return "";
        }

        const textObject = node.getObjects().find((object) => object.wbRole === "node_text");

        return textObject?.text || "";
    }

    _setNodeText(node, text) {
        if (!node || !node.getObjects) {
            return;
        }

        const textObject = node.getObjects().find((object) => object.wbRole === "node_text");

        if (textObject) {
            textObject.set("text", text);
        }

        node.set("wbText", text);
        node.dirty = true;
        node.setCoords();
    }

    /* -------------------------------------------------------------------------
     * Connector mode
     * ------------------------------------------------------------------------- */

    _handleConnectorMouseDown(ev) {
        if (this.state.mode !== "connector" || !this.canvas) {
            return;
        }

        const target = this._getConnectableObjectFromTarget(ev.target);

        if (!target) {
            this.state.connectorFromNodeId = null;
            this.canvas.discardActiveObject();
            this.canvas.requestRenderAll();

            this.notification.add("Click a shape, mind-map node, or flowchart node to start a connector.", {
                type: "warning",
            });
            return;
        }

        if (!this.state.connectorFromNodeId) {
            this.state.connectorFromNodeId = target.wbId;
            this.canvas.setActiveObject(target);
            this.canvas.requestRenderAll();

            this.notification.add("Source selected. Click the target object.", {
                type: "info",
            });
            return;
        }

        const source = this._getObjectByWhiteboardId(this.state.connectorFromNodeId);

        if (!source) {
            this.state.connectorFromNodeId = null;
            this.notification.add("Source object was not found. Start connector again.", {
                type: "warning",
            });
            return;
        }

        if (source.wbId === target.wbId) {
            this.notification.add("Choose a different target object.", {
                type: "warning",
            });
            return;
        }

        const connector = this._createConnectorBetweenObjects(source, target, {
            connectorType: "straight_arrow",
        });

        if (!connector) {
            this.notification.add("Could not create connector.", {
                type: "warning",
            });
            return;
        }

        this.canvas.add(connector);
        this.canvas.sendToBack(connector);
        this.canvas.setActiveObject(target);
        this.canvas.requestRenderAll();

        this.state.connectorFromNodeId = null;

        this._pushHistory();
    }

    /* -------------------------------------------------------------------------
     * Generic connectable objects
     * ------------------------------------------------------------------------- */

    _getConnectableObjectFromTarget(target) {
        if (!target) {
            return null;
        }

        if (target.group) {
            return this._getConnectableObjectFromTarget(target.group);
        }

        if (target.type === "activeSelection") {
            return null;
        }

        if (target.wbType === "mind_node" || target.wbType === "flow_node") {
            return target;
        }

        if (
            target.wbType === "shape"
            && ["rectangle", "circle", "diamond"].includes(target.wbShape)
        ) {
            return target;
        }

        return null;
    }

    _createConnectorBetweenObjects(fromObject, toObject, options = {}) {
        const fabric = window.fabric;

        if (!fabric || !fromObject || !toObject) {
            return null;
        }

        const fromPoint = this._getObjectAnchorPoint(fromObject, toObject);
        const toPoint = this._getObjectAnchorPoint(toObject, fromObject);

        return createWhiteboardConnector(fabric, {
            fromPoint,
            toPoint,
            color: options.color || this.state.color,
            strokeWidth: options.strokeWidth || 3,
            wbId: options.wbId,
            fromNodeId: fromObject.wbId,
            toNodeId: toObject.wbId,
            connectorType: options.connectorType || "straight_arrow",
        });
    }

    _getObjectAnchorPoint(object, otherObject) {
        const center = object.getCenterPoint();
        const otherCenter = otherObject.getCenterPoint();
        const bounds = object.getBoundingRect();

        const dx = otherCenter.x - center.x;
        const dy = otherCenter.y - center.y;

        const halfWidth = Math.max(30, bounds.width / 2);
        const halfHeight = Math.max(24, bounds.height / 2);

        if (Math.abs(dx) >= Math.abs(dy)) {
            return {
                x: center.x + (dx >= 0 ? halfWidth : -halfWidth),
                y: center.y,
            };
        }

        return {
            x: center.x,
            y: center.y + (dy >= 0 ? halfHeight : -halfHeight),
        };
    }

    _getObjectByWhiteboardId(wbId) {
        if (!wbId || !this.canvas) {
            return null;
        }

        return this.canvas.getObjects().find((object) => object.wbId === wbId) || null;
    }

    _isConnector(object) {
        return object?.wbType === "connector";
    }

    _updateConnectorsForObject(object) {
        const connectableObject = this._getConnectableObjectFromTarget(object);

        if (!connectableObject || !this.canvas) {
            return;
        }

        const connectors = this.canvas
            .getObjects()
            .filter((candidate) => {
                return this._isConnector(candidate)
                    && (
                        candidate.wbFromNodeId === connectableObject.wbId
                        || candidate.wbToNodeId === connectableObject.wbId
                    );
            });

        for (const connector of connectors) {
            this._replaceConnectorWithUpdatedVersion(connector);
        }

        this.canvas.requestRenderAll();
    }

    _updateAllConnectors() {
        if (!this.canvas) {
            return;
        }

        const connectors = this.canvas
            .getObjects()
            .filter((object) => this._isConnector(object));

        for (const connector of connectors) {
            this._replaceConnectorWithUpdatedVersion(connector);
        }

        this.canvas.requestRenderAll();
    }

    _replaceConnectorWithUpdatedVersion(connector) {
        if (!connector || !this.canvas) {
            return;
        }

        const fromObject = this._getObjectByWhiteboardId(connector.wbFromNodeId);
        const toObject = this._getObjectByWhiteboardId(connector.wbToNodeId);

        if (!fromObject || !toObject) {
            return;
        }

        const updatedConnector = this._createConnectorBetweenObjects(fromObject, toObject, {
            wbId: connector.wbId,
            color: connector.stroke || this.state.color,
            strokeWidth: connector.strokeWidth || 3,
            connectorType: connector.wbConnectorType || "straight_arrow",
        });

        if (!updatedConnector) {
            return;
        }

        const index = this.canvas.getObjects().indexOf(connector);

        this._runWithoutHistory(() => {
            this.canvas.remove(connector);

            if (index >= 0) {
                this.canvas.insertAt(updatedConnector, index, false);
            } else {
                this.canvas.add(updatedConnector);
            }

            this.canvas.sendToBack(updatedConnector);
        });
    }

    deleteSelectedObjects() {
        if (!this.canvas) {
            return;
        }

        const activeObject = this.canvas.getActiveObject();

        if (!activeObject) {
            this.notification.add("Select an object to remove.", { type: "warning" });
            return;
        }

        // Do not delete while editing Fabric text.
        if (activeObject.isEditing) {
            return;
        }

        const selectedObjects = activeObject.type === "activeSelection"
            ? [...activeObject.getObjects()]
            : [activeObject];

        const objectsToRemove = this._getObjectsToRemoveWithConnectors(selectedObjects);

        this._runWithoutHistory(() => {
            this.canvas.discardActiveObject();

            for (const object of objectsToRemove) {
                if (this.canvas.getObjects().includes(object)) {
                    this.canvas.remove(object);
                }
            }
        });

        this.state.connectorFromNodeId = null;
        this.canvas.requestRenderAll();
        this._pushHistory();
    }

    _getObjectsToRemoveWithConnectors(objects) {
        if (!this.canvas) {
            return [];
        }

        const removeSet = new Set(objects);
        const selectedIds = objects
            .map((object) => object?.wbId)
            .filter(Boolean);

        if (!selectedIds.length) {
            return [...removeSet];
        }

        const attachedConnectors = this.canvas
            .getObjects()
            .filter((object) => {
                return object?.wbType === "connector"
                    && (
                        selectedIds.includes(object.wbFromNodeId)
                        || selectedIds.includes(object.wbToNodeId)
                    );
            });

        for (const connector of attachedConnectors) {
            removeSet.add(connector);
        }

        return [...removeSet];
    }

    // -------------------------------------------------------------------------
    // Server load/save
    // -------------------------------------------------------------------------

    async _loadBoardsList() {
        try {
            const boards = await this.orm.call(
                "whiteboard.board",
                "get_user_boards",
                []
            );

            this.state.boards = boards || [];
            return this.state.boards;
        } catch {
            this.state.boards = [];
            this.notification.add("Could not load whiteboard list.", { type: "danger" });
            return [];
        }
    }

    async _loadBoardFromServer(boardId = null) {
        try {
            let result;

            if (boardId) {
                result = await this.orm.call(
                    "whiteboard.board",
                    "get_board_data",
                    [boardId]
                );
            } else {
                result = await this.orm.call(
                    "whiteboard.board",
                    "get_or_create_latest_board",
                    []
                );
            }

            if (result?.error) {
                this.notification.add(result.error, { type: "danger" });
                return false;
            }

            await this._applyBoardPayload(result);
            await this._loadBoardsList();

            return true;
        } catch {
            this.notification.add("Could not load whiteboard.", { type: "danger" });
            return false;
        }
    }

    async _applyBoardPayload(payload) {
    if (!payload) return false;

    this.state.boardId = payload.id;
    this.state.boardName = payload.name || "Untitled Board";
    this.state.boardRevision = Number.isInteger(payload.revision)
        ? payload.revision
        : 0;

    let applied = true;

    if (payload.data_json) {
        applied = await this._applyJSON(payload.data_json);
    } else {
        this._runWithoutHistory(() => {
            this._clearCanvasObjects();
        });
    }

    if (!applied) return false;

    this._runWithoutHistory(() => {
        this._updateAllConnectors();
    });

    this._resetHistoryFromCanvas();
    this.state.dirty = false;

    this._resizeCanvas();

    return true;
}

    async save() {
    if (
        !this.canvas
        || !this.state.boardId
        || this.state.saving
    ) {
        return;
    }

    this._flushDebouncedHistory();

    this.state.saving = true;

    try {
        const dataJson = this._getCanvasJSON();

        const thumbnail = this.canvas.toDataURL({
            format: "png",
            multiplier: 0.2,
        });

        const result = await this.orm.call(
            "whiteboard.board",
            "save_my_board",
            [
                this.state.boardId,
                dataJson,
                thumbnail,
                this.state.boardName,
                this.state.boardRevision,
            ]
        );

        if (result?.error) {
            this.notification.add(result.error, {
                type: result.conflict
                    ? "warning"
                    : "danger",
            });

            // Keep dirty=true. The user must reload or resolve the
            // conflict instead of silently overwriting newer data.
            return;
        }

        if (result?.board) {
            this.state.boardId = result.board.id;
            this.state.boardName =
                result.board.name
                || this.state.boardName;

            if (
                Number.isInteger(
                    result.board.revision
                )
            ) {
                this.state.boardRevision =
                    result.board.revision;
            }
        }

        this.state.dirty = false;

        await this._loadBoardsList();

        this.notification.add(
            "Whiteboard saved.",
            {
                type: "success",
            }
        );
    } catch {
        // Dirty state remains true when the request fails.
        this.notification.add(
            "Could not save whiteboard.",
            {
                type: "danger",
            }
        );
    } finally {
        this.state.saving = false;
    }
}

    // -------------------------------------------------------------------------
    // History helpers
    // -------------------------------------------------------------------------

    _getCanvasJSON() {
        return JSON.stringify(this.canvas.toDatalessJSON(WHITEBOARD_OBJECT_PROPS));
    }

    _pushHistory(resetRedo = true, options = {}) {
        if (!this.canvas || this._isApplyingHistory) return;

        const markDirty = options.markDirty !== false;
        const json = this._getCanvasJSON();

        const latest = this.undoStack[this.undoStack.length - 1];
        if (latest === json) {
            return;
        }

        this.undoStack.push(json);

        if (resetRedo) {
            this.redoStack = [];
        }

        if (this.undoStack.length > 50) {
            this.undoStack.shift();
        }

        if (markDirty) {
            this.state.dirty = true;
        }
    }

    _pushHistoryDebounced() {
        if (this._historyTimer) {
            clearTimeout(this._historyTimer);
        }

        this._historyTimer = setTimeout(() => {
            this._historyTimer = null;
            this._pushHistory();
        }, 350);
    }

    _flushDebouncedHistory() {
        if (!this._historyTimer) return;

        clearTimeout(this._historyTimer);
        this._historyTimer = null;
        this._pushHistory();
    }

    _resetHistoryFromCanvas() {
        if (!this.canvas) return;

        this.undoStack = [];
        this.redoStack = [];

        this._pushHistory(true, { markDirty: false });
        this.state.dirty = false;
    }

    _runWithoutHistory(callback) {
        this._isApplyingHistory = true;

        try {
            callback();
        } finally {
            this._isApplyingHistory = false;
        }
    }

    _clearCanvasObjects() {
        if (!this.canvas) return;

        this.canvas.discardActiveObject();

        const objects = [...this.canvas.getObjects()];
        for (const object of objects) {
            this.canvas.remove(object);
        }

        this.canvas.backgroundColor = "white";
        this.canvas.requestRenderAll();
    }

    async _applyJSON(json) {
        if (!this.canvas) return false;

        let parsed = json;

        try {
            if (typeof json === "string") {
                parsed = JSON.parse(json);
            }
        } catch {
            this.notification.add("Saved board data is not valid JSON.", { type: "danger" });
            return false;
        }

        this._isApplyingHistory = true;

        try {
            await new Promise((resolve) => {
                this.canvas.loadFromJSON(parsed, () => {
                    this.canvas.requestRenderAll();
                    resolve();
                });
            });

            return true;
        } catch {
            this.notification.add("Could not render saved whiteboard data.", { type: "danger" });
            return false;
        } finally {
            this._isApplyingHistory = false;
        }
    }
}

WhiteboardAction.template = "odoo_whiteboard.WhiteboardAction";

registry.category("actions").add("odoo_whiteboard.whiteboard_action", WhiteboardAction);

