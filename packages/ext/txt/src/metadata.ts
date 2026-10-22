import type { ExtDefinition } from "@toonflow/ext-scaffold/runtime";

export default {
  id: "ext-txt",
  displayName: "文本编辑器",
  icon: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#4e9fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/></svg>'),
  configRules: [
    { type: "inputNumber", field: "fontSize", title: "字号", value: 14, props: { min: 10, max: 32, step: 1 } },
    { type: "switch", field: "wordWrap", title: "自动换行", value: true },
  ],
  extensions: ["txt", "log", "json", "jsonc", "csv", "tsv", "yaml", "yml", "xml", "toml", "ini"],
  resourceKind: "file",
  text: true,
} satisfies Omit<ExtDefinition, "load">;
