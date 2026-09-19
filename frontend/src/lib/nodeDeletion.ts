import { useCanvasStore } from "@/store/canvasStore";
import { confirm } from "@/store/confirmStore";

function nodeLabel(node: { data?: unknown } | undefined): string | undefined {
  const data = node?.data as { name?: string } | undefined;
  return data?.name;
}

/**
 * Removes a single node — and any edges attached to it — from the canvas
 * store, after the user confirms via the shared in-app confirm dialog.
 * Resolves `false` without changing anything if the node no longer exists
 * or the user cancels.
 */
export async function deleteNodeWithConfirm(nodeId: string): Promise<boolean> {
  const node = useCanvasStore.getState().nodes.find((n) => n.id === nodeId);
  if (!node) return false;

  const name = nodeLabel(node);
  const confirmed = await confirm({
    title: "Delete node",
    description: name
      ? `Are you sure you want to delete "${name}"? This will also remove its connections.`
      : "Are you sure you want to delete this node? This will also remove its connections.",
    confirmLabel: "Delete",
    danger: true,
  });
  if (!confirmed) return false;

  const state = useCanvasStore.getState();
  state.setNodes(state.nodes.filter((n) => n.id !== nodeId));
  state.setEdges(state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId));
  if (state.selectedNodeId === nodeId) state.selectNode(null);
  if (state.activeNodeId === nodeId) state.setActiveNodeId(null);
  return true;
}

/**
 * Deletes every currently-selected node (used by the Delete/Backspace
 * keyboard shortcut) after a single confirmation covering all of them.
 * Resolves `false` without changing anything if nothing is selected or the
 * user cancels.
 */
export async function deleteSelectedNodesWithConfirm(): Promise<boolean> {
  const selected = useCanvasStore.getState().nodes.filter((n) => n.selected);
  if (selected.length === 0) return false;

  const confirmed = await confirm({
    title: selected.length === 1 ? "Delete node" : `Delete ${selected.length} nodes`,
    description:
      selected.length === 1
        ? `Are you sure you want to delete "${nodeLabel(selected[0]) ?? "this node"}"? This will also remove its connections.`
        : `Are you sure you want to delete these ${selected.length} nodes? This will also remove their connections.`,
    confirmLabel: "Delete",
    danger: true,
  });
  if (!confirmed) return false;

  const idsToDelete = new Set(selected.map((n) => n.id));
  const state = useCanvasStore.getState();
  state.setNodes(state.nodes.filter((n) => !idsToDelete.has(n.id)));
  state.setEdges(
    state.edges.filter((e) => !idsToDelete.has(e.source) && !idsToDelete.has(e.target))
  );
  if (state.selectedNodeId && idsToDelete.has(state.selectedNodeId)) state.selectNode(null);
  if (state.activeNodeId && idsToDelete.has(state.activeNodeId)) state.setActiveNodeId(null);
  return true;
}
