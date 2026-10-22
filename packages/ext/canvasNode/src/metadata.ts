import type { ExtDefinition } from "@toonflow/ext-scaffold/runtime";

export default {
  id: "ext-canvasNode",
  displayName: "画布节点",
  icon: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>'),
  extensions: [],
  resourceKind: "canvasNode",
} satisfies Omit<ExtDefinition, "load">;
