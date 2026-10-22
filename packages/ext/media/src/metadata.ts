import type { ExtDefinition } from "@toonflow/ext-scaffold/runtime";

export default {
  id: "ext-media",
  displayName: "音视频",
  icon: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#4e9fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m10 8 6 4-6 4z"/></svg>'),
  extensions: ["mp4", "mp3", "wav", "pcm", "opus"],
  resourceKind: "file",
} satisfies Omit<ExtDefinition, "load">;
