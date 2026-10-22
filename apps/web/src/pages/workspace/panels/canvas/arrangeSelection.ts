import type { GraphNode, useVueFlow } from "@vue-flow/core";
import { fitGroupBounds, getSelectionRoots } from "./selectionNodes";

export type ArrangeSelectionMode = "horizontal" | "vertical" | "grid";

export function arrangeSelection(flow: ReturnType<typeof useVueFlow>, selection: GraphNode[], mode: ArrangeSelectionMode) {
  const nodes = flow.getNodes.value;
  const roots = getSelectionRoots(selection, nodes);
  if (roots.length < 2) return;
  const byId = new Map(nodes.map(node => [node.id, node]));
  const affected = new Set<GraphNode>();
  const items = roots.map(node => {
    if (byId.get(node.id) !== node) throw new Error("节点已变化，请重新选择后整理");
    if (node.draggable === false) throw new Error(`节点 ${node.id} 不允许移动`);
    const { width, height } = node.dimensions;
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error(`节点 ${node.id} 尚未完成尺寸测量，请等待节点显示后重试`);
    }
    const position = { ...node.position };
    const parentPosition = { x: 0, y: 0 };
    const visited = new Set([node.id]);
    let parentId = node.parentNode;
    while (parentId) {
      const parent = byId.get(parentId);
      if (!parent || visited.has(parentId)) throw new Error(`节点 ${node.id} 的分组关系无效`);
      visited.add(parentId);
      parentPosition.x += parent.position.x;
      parentPosition.y += parent.position.y;
      if (parent.type === "canvasGroup") affected.add(parent);
      parentId = parent.parentNode;
    }
    position.x += parentPosition.x;
    position.y += parentPosition.y;
    if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) throw new Error(`节点 ${node.id} 的位置无效`);
    return { node, position, parentPosition };
  });
  items.sort((a, b) => mode === "horizontal"
    ? a.position.x - b.position.x || a.position.y - b.position.y
    : a.position.y - b.position.y || a.position.x - b.position.x);
  const origin = { x: Math.min(...items.map(item => item.position.x)), y: Math.min(...items.map(item => item.position.y)) };
  const columns = mode === "horizontal" ? items.length : mode === "vertical" ? 1 : Math.ceil(Math.sqrt(items.length));
  const columnWidths = Array<number>(columns).fill(0);
  const rowHeights = Array<number>(Math.ceil(items.length / columns)).fill(0);
  items.forEach(({ node }, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    columnWidths[column] = Math.max(columnWidths[column]!, node.dimensions.width);
    rowHeights[row] = Math.max(rowHeights[row]!, node.dimensions.height);
  });
  let x = origin.x;
  const columnPositions = columnWidths.map(width => {
    const position = x;
    x += width + 80;
    return position;
  });
  let y = origin.y;
  const rowPositions = rowHeights.map(height => {
    const position = y;
    y += height + 80;
    return position;
  });
  const positions = items.map(({ node, parentPosition }, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const position = {
      x: columnPositions[column]! + (mode === "vertical" ? (columnWidths[column]! - node.dimensions.width) / 2 : 0) - parentPosition.x,
      y: rowPositions[row]! + (mode === "horizontal" ? (rowHeights[row]! - node.dimensions.height) / 2 : 0) - parentPosition.y,
    };
    if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) throw new Error(`节点 ${node.id} 的排列位置无效`);
    return { node, position };
  });
  positions.forEach(({ node, position }) => { node.position = position; });
  // ACT: 整理只贴合原分组边界，不执行拖动结束时按相交关系重新归组。
  fitGroupBounds(nodes, affected);
}
