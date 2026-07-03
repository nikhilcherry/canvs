import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type IsValidConnection,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback } from "react";
import { useStore } from "../store";
import type { NodeSpec } from "../types";
import { CanvsNode } from "./CanvsNode";
import { DRAG_MIME } from "./Palette";

const nodeTypes = { canvs: CanvsNode };

function CanvasInner() {
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const onNodesChange = useStore((s) => s.onNodesChange);
  const onEdgesChange = useStore((s) => s.onEdgesChange);
  const onConnect = useStore((s) => s.onConnect);
  const addNode = useStore((s) => s.addNode);
  const selectNode = useStore((s) => s.selectNode);
  const { screenToFlowPosition } = useReactFlow();

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const raw = e.dataTransfer.getData(DRAG_MIME);
      if (!raw) return;
      const spec: NodeSpec = JSON.parse(raw);
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addNode(spec, position);
    },
    [addNode, screenToFlowPosition]
  );

  const isValidConnection: IsValidConnection = useCallback(
    (edge) => {
      const connection = edge as Connection;
      if (!connection.targetHandle) return false;
      const alreadyFed = edges.some(
        (e) => e.target === connection.target && e.targetHandle === connection.targetHandle
      );
      return !alreadyFed;
    },
    [edges]
  );

  return (
    <div className="canvas-wrap" onDragOver={handleDragOver} onDrop={handleDrop}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onPaneClick={() => selectNode(null)}
        onNodeClick={(_, node) => selectNode(node.id)}
        fitView
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      </ReactFlow>
    </div>
  );
}

export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}
