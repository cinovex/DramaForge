import type { AgentMention } from "@toonflow/server/agent/types";

export function mentionName(mention: AgentMention) {
  return `${mention.source.kind === "asset" ? "全局素材" : mention.source.canvasName} / ${mention.label}`;
}

export function mentionThumbnailProps(mention: AgentMention) {
  const value = mention.value as { url?: unknown; mimeType?: unknown } | null;
  return {
    thumbnail: ["IMAGE", "MASK", "VIDEO"].includes(mention.dataType) && typeof value?.url === "string" && typeof value.mimeType === "string"
      ? { url: value.url, mimeType: value.mimeType } : undefined,
    globalAsset: mention.source.kind === "asset" && value?.url === mention.source.path,
  };
}

export function mentionParts(content: string, mentions: AgentMention[] = []) {
  const byId = new Map(mentions.map(mention => [mention.id, mention]));
  return content.split(/(\{\{mention:[^{}]+\}\})/g).filter(Boolean).map(text => {
    const id = /^\{\{mention:([^{}]+)\}\}$/.exec(text)?.[1];
    return { text, mention: id ? byId.get(id) : undefined };
  });
}

export function mentionPlainText(content: string, mentions?: AgentMention[]) {
  return mentionParts(content, mentions).map(part => part.mention ? `@${mentionName(part.mention)}` : part.text).join("");
}
