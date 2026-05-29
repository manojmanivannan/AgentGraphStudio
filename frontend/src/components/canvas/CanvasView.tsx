import { useCallback, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Connection,
  type Edge,
  BackgroundVariant,
  type Node,
  MarkerType,
  type OnNodesChange,
  type OnEdgesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode } from "./AgentNode";
import { ToolNode } from "./ToolNode";
import { CustomEdge } from "./CustomEdge";
import { useCanvasStore } from "@/store/canvasStore";
import { useCanvasPersistence } from "@/hooks/useCanvasPersistence";
import { useThemeStore } from "@/store/themeStore";

const nodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
};

const edgeTypes = {
  default: CustomEdge,
};

const defaultEdgeOptions = {
  animated: false,
  style: { strokeWidth: 2 },
  markerEnd: { type: MarkerType.ArrowClosed },
};

function isValidConnection(connection: Connection): boolean {
  if (!connection.source || !connection.target) return false;
  if (connection.source === connection.target) return false;

  const state = useCanvasStore.getState();
  const sourceNode = state.nodes.find((n) => n.id === connection.source);
  const targetNode = state.nodes.find((n) => n.id === connection.target);

  if (!sourceNode || !targetNode) return true;
  if (sourceNode.type === "agent" && targetNode.type === "tool") return true;
  if (sourceNode.type === "agent" && targetNode.type === "agent") return true;
  return false;
}

export function CanvasView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const theme = useThemeStore((s) => s.theme);
  const isDark = theme === "dark";

  useCanvasPersistence();

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      setNodes(applyNodeChanges(changes, nodes));
    },
    [nodes, setNodes]
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      setEdges(applyEdgeChanges(changes, edges));
    },
    [edges, setEdges]
  );

  const onConnect = useCallback(
    (params: Connection) => {
      const sourceNode = nodes.find((n) => n.id === params.source);
      const targetNode = nodes.find((n) => n.id === params.target);
      const edgeType =
        sourceNode?.type === "agent" && targetNode?.type === "agent"
          ? "handoff"
          : "tool_access";

      const newEdge: Edge = {
        ...params,
        id: uuidv4(),
        data: { edgeType },
        style:
          edgeType === "handoff"
            ? { strokeDasharray: "6 4", strokeWidth: 2 }
            : { strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed },
      };

      setEdges(addEdge(newEdge, edges));
    },
    [nodes, edges, setEdges]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  return (
    <div ref={containerRef} className="w-full h-full bg-[var(--color-inset)]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        isValidConnection={isValidConnection as any}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        attributionPosition="bottom-right"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color={isDark ? "#1e1e28" : "#d8d8e2"}
        />
        <Controls />
        <MiniMap
          nodeColor={(node) =>
            node.type === "agent" ? "var(--color-accent)" : "var(--color-secondary)"
          }
          maskColor={isDark ? "rgba(9,9,11,0.85)" : "rgba(247,247,249,0.85)"}
          style={{ border: "none" }}
        />
      </ReactFlow>
    </div>
  );
}