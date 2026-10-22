import type { ExtDefinition } from "@toonflow/ext-scaffold/runtime";

export default {
  id: "ext-md",
  displayName: "Markdown",
  icon: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#7aa2f7" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M5 16V8l4 4 4-4v8M18 8v8m-2-2 2 2 2-2"/></svg>'),
  extensions: ["md", "markdown"],
  resourceKind: "file",
  text: true,
} satisfies Omit<ExtDefinition, "load">;
