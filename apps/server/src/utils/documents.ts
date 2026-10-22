import { createHash } from "node:crypto";
import { readFile } from "@toonflow/file";
import { decodeTextFile, getDocumentExtension, getReadableFileMimeType, getTextMimeType } from "@/lib/documentFormats";

async function loadDocumentParser() {
  try {
    const parser = await import("@firecrawl/anydoc");
    return (bytes: Uint8Array, extension: string) => parser.toMarkdownBytes(bytes,
      parser.formatFromBytes(bytes) ?? parser.formatFromExtension(extension), { ocr: "reject" });
  } catch {
    const parser = await import("@firecrawl/anydoc-wasm");
    parser.initSync({ module: await readFile(new URL(import.meta.resolve("@firecrawl/anydoc-wasm/anydoc_wasm_bg.wasm"))) });
    // ACT: 无原生包的平台使用同步 WASM；大文档会占用当前线程，后续可迁移到独立 Worker。
    return (bytes: Uint8Array, extension: string) => Promise.resolve(parser.toMarkdownBytes(bytes,
      parser.formatFromBytes(bytes) ?? parser.formatFromExtension(extension)));
  }
}

let parser: ReturnType<typeof loadDocumentParser> | undefined;
const pending = new Map<string, Promise<Buffer>>();
const cache = new Map<string, Buffer>();
let cacheBytes = 0;

/** 仅供模型读取使用；写入、编辑、复制等文件操作始终保留原始字节。 */
export async function readDocument(name: string, bytes: Buffer, mimeType?: string): Promise<Buffer> {
  const normalized = getReadableFileMimeType(name, mimeType);
  if (!normalized) return bytes;
  if (bytes.byteLength > 100 * 1024 * 1024) throw new Error("文件不能超过 100 MB");
  const extension = getDocumentExtension(name) ?? (getTextMimeType(name) ? undefined : getDocumentExtension("", normalized));
  if (!extension) return Buffer.from(decodeTextFile(bytes));
  if (!bytes.length) throw new Error("文档不能为空");
  const key = createHash("sha256").update(extension).update(bytes).digest("hex");
  const cached = cache.get(key);
  if (cached) {
    cache.delete(key);
    cache.set(key, cached);
    return cached;
  }
  const existing = pending.get(key);
  if (existing) return existing;
  const conversion = (async () => {
    try {
      parser ??= loadDocumentParser().catch(error => { parser = undefined; throw error; });
      const markdown = await (await parser)(bytes, extension);
      if (!markdown.trim()) throw new Error("文档中未提取到可读文本");
      const content = Buffer.from(markdown);
      // ACT: 分页复用解析结果，最多缓存 128 份、32 MiB 正文；更大的文档按次解析。
      if (content.byteLength <= 32 * 1024 * 1024) {
        while (cache.size >= 128 || cacheBytes + content.byteLength > 32 * 1024 * 1024) {
          const oldest = cache.keys().next().value!;
          cacheBytes -= cache.get(oldest)!.byteLength;
          cache.delete(oldest);
        }
        cache.set(key, content);
        cacheBytes += content.byteLength;
      }
      return content;
    } catch (error) {
      const failure = error as { code?: string; pages?: number[]; message?: string };
      const messages: Record<string, string> = {
        needsOcr: `此 PDF 包含需要 OCR 的页面${failure.pages?.length ? `（${failure.pages.join(", ")}）` : ""}，本地解析无法提取完整内容，请先进行 OCR 后重试`,
        encrypted: "文档已加密，请先解除密码保护后重试",
        malformed: "文档内容损坏或无法解析",
        resourceLimit: "文档超过解析器的安全资源限制",
        missingPart: "文档缺少必要内容，无法完整解析",
        unsupported: "不支持此文档的实际格式",
      };
      throw new Error(`读取文档 ${name} 失败：${messages[failure.code ?? ""] ?? failure.message ?? String(error)}`, { cause: error });
    }
  })();
  pending.set(key, conversion);
  try { return await conversion; }
  finally { pending.delete(key); }
}
