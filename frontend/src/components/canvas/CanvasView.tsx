import { useCallback, useRef, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  ReactFlow,
  Background,
  Controls,
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
  type Viewport,
  type ReactFlowInstance,
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
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const setEdges = useCanvasStore((s) => s.setEdges);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const setViewport = useCanvasStore((s) => s.setViewport);
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const theme = useThemeStore((s) => s.theme);
  const isDark = theme === "dark";

  const propertiesOpen = selectedNodeId !== null;

  // Re-fit view when overlay panels open/close so nodes stay visible
  // in the remaining canvas area. Delay matches the container transition.
  useEffect(() => {
    const instance = rfInstanceRef.current;
    if (!instance) return;

    const timeout = setTimeout(() => {
      instance.fitView({ duration: 300, padding: 0.05 });
    }, 350);

    return () => clearTimeout(timeout);
  }, [propertiesOpen]);

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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (_event: any, node: any) => {
      selectNode(node.id);
    },
    [selectNode],
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  const onMoveEnd = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (_event: any, viewport: Viewport) => {
      setViewport(viewport);
    },
    [setViewport],
  );

  const onInit = useCallback(
    (instance: ReactFlowInstance) => {
      rfInstanceRef.current = instance;
      // Capture viewport after fitView completes
      setTimeout(() => {
        setViewport(instance.getViewport());
      }, 100);
    },
    [setViewport],
  );

  return (
    <div ref={containerRef} className="w-full h-full bg-[var(--color-inset)]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onPaneClick={onPaneClick}
        onNodeClick={onNodeClick}
        onMoveEnd={onMoveEnd}
        onInit={onInit}
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
      </ReactFlow>
    </div>
  );
}