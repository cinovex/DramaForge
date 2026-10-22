type RequestPart = Record<string, unknown>;
type InlineFile = { data: string; mimeType: string; source?: RequestPart; field?: "image_url" | "video_url" | "file_data" };

export type RequestFile = {
  id?: string;
  data: string;
  mimeType: string;
  readonly inlineBytes: number;
  replace(file: { data: string; mimeType: string }, note?: string): void;
  offload(text: string): void;
  useReference(part: Record<string, unknown>): void;
};

function inlineFile(part: RequestPart): InlineFile | undefined {
  const source = part.source as RequestPart | undefined;
  if (["image", "document"].includes(String(part.type)) && source?.type === "base64"
    && typeof source.media_type === "string" && typeof source.data === "string" && source.data) {
    return { data: source.data, mimeType: source.media_type, source };
  }
  const field = part.type === "input_file" ? "file_data"
    : part.type === "video_url" ? "video_url" : ["image_url", "input_image"].includes(String(part.type)) ? "image_url" : undefined;
  if (!field) return;
  const value = part[field];
  const url = typeof value === "string" ? value : value && typeof value === "object" ? (value as RequestPart).url : undefined;
  const match = typeof url === "string" ? url.match(/^data:([^;,]+);base64,(.+)$/is) : undefined;
  if (match) return { data: match[2], mimeType: match[1], field };
}

function visitRequestParts(payload: unknown, visit: (part: RequestPart, content: RequestPart[]) => void) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
  function visitContent(content: unknown) {
    if (!Array.isArray(content)) return;
    for (const part of content as RequestPart[]) {
      if (!part || typeof part !== "object" || Array.isArray(part)) continue;
      visit(part, content);
      delete part.toonflowImageId;
      if (part.type === "tool_result") visitContent(part.content);
    }
  }
  const body = payload as { messages?: unknown; input?: unknown };
  for (const messages of [body.messages, body.input]) {
    if (!Array.isArray(messages)) continue;
    for (const message of messages as RequestPart[]) {
      if (!message || typeof message !== "object" || Array.isArray(message)) continue;
      delete message.toonflowImageId;
      visitContent(message.content);
      if (["function_call_output", "custom_tool_call_output"].includes(String(message.type))) visitContent(message.output);
    }
  }
}

export function getRequestFileReferences(payload: unknown): { readonly fileId: string; replace(fileId: string): void }[] {
  const references: { readonly fileId: string; replace(fileId: string): void }[] = [];
  visitRequestParts(payload, part => {
    const source = part.source as RequestPart | undefined;
    const reference = ["file", "input_image", "input_file"].includes(String(part.type)) ? part
      : ["image", "document"].includes(String(part.type)) && source?.type === "file" ? source : undefined;
    if (typeof reference?.file_id === "string") references.push({
      get fileId() { return reference.file_id as string; },
      replace(fileId) { reference.file_id = fileId; },
    });
  });
  return references;
}

export function getRequestFiles(payload: unknown): RequestFile[] {
  const files: RequestFile[] = [];
  visitRequestParts(payload, (part, content) => {
    const id = typeof part.toonflowImageId === "string" ? part.toonflowImageId : undefined;
    const inline = inlineFile(part);
    if (!inline) return;
    let { data, mimeType } = inline;
    const textType = ["input_image", "input_file"].includes(String(part.type)) ? "input_text" : "text";
    files.push({
      id,
      get data() { return data; },
      get mimeType() { return mimeType; },
      get inlineBytes() {
        const current = content.includes(part) ? inlineFile(part) : undefined;
        return current ? Buffer.byteLength(current.data, "utf8") : 0;
      },
      replace(file, note) {
        const current = inlineFile(part);
        if (!current || !content.includes(part)) return;
        data = file.data;
        mimeType = file.mimeType;
        if (current.source) {
          current.source.data = data;
          current.source.media_type = mimeType;
        } else {
          const nextUrl = `data:${mimeType};base64,${data}`;
          const value = part[current.field!];
          if (typeof value === "object" && value) (value as RequestPart).url = nextUrl;
          else part[current.field!] = nextUrl;
        }
        const position = content.indexOf(part);
        const previous = content[position - 1];
        if (note && (previous?.type !== textType || previous.text !== note)) content.splice(position, 0, { type: textType, text: note });
      },
      offload(text) {
        if (!content.includes(part)) return;
        const cacheControl = part.cache_control;
        for (const key of Object.keys(part)) delete part[key];
        Object.assign(part, { type: textType, text }, cacheControl === undefined ? {} : { cache_control: cacheControl });
      },
      useReference(reference) {
        if (!content.includes(part)) return;
        for (const key of ["image_url", "video_url", "file_data", "source", "filename", "toonflowImageId"]) delete part[key];
        Object.assign(part, reference);
      },
    });
  });
  return files;
}
