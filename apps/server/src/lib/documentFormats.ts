// 前后端共用文件类型与文本解码；文档扩展与 anydoc 的映射保持一致。
export const documentFormats: Record<string, string> = {
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  docm: "application/vnd.ms-word.document.macroenabled.12",
  xls: "application/vnd.ms-excel",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xlsm: "application/vnd.ms-excel.sheet.macroenabled.12",
  xlsb: "application/vnd.ms-excel.sheet.binary.macroenabled.12",
  ppt: "application/vnd.ms-powerpoint",
  pps: "application/vnd.ms-powerpoint",
  pot: "application/vnd.ms-powerpoint",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  pptm: "application/vnd.ms-powerpoint.presentation.macroenabled.12",
  ppsx: "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
  ppsm: "application/vnd.ms-powerpoint.slideshow.macroenabled.12",
  odt: "application/vnd.oasis.opendocument.text",
  ods: "application/vnd.oasis.opendocument.spreadsheet",
  odp: "application/vnd.oasis.opendocument.presentation",
  rtf: "application/rtf",
  epub: "application/epub+zip",
  csv: "text/csv",
  pdf: "application/pdf",
};

export const documentAccept = Object.keys(documentFormats).map(extension => `.${extension}`).join(",");

export function getDocumentExtension(name: string, mimeType = ""): string | undefined {
  const extension = name.split(/[\\/]/).pop()?.match(/\.([^.]+)$/)?.[1].toLowerCase() ?? "";
  if (Object.hasOwn(documentFormats, extension)) return extension;
  const normalized = mimeType.split(";")[0].trim().toLowerCase();
  if (normalized === "text/rtf") return "rtf";
  if (normalized === "application/csv") return "csv";
  return Object.keys(documentFormats).find(extension => documentFormats[extension] === normalized);
}

export function getDocumentMimeType(name: string, mimeType = ""): string | undefined {
  const extension = getDocumentExtension(name, mimeType);
  return extension ? documentFormats[extension] : undefined;
}

export const textFormats: Record<string, string> = {
  txt: "text/plain", text: "text/plain", log: "text/x-log",
  html: "text/html", htm: "text/html", xhtml: "application/xhtml+xml",
  md: "text/markdown", markdown: "text/markdown", mdx: "text/mdx", rst: "text/x-rst", adoc: "text/asciidoc",
  json: "application/json", jsonc: "application/jsonc", json5: "application/json5", jsonl: "application/x-ndjson", ndjson: "application/x-ndjson",
  xml: "application/xml", xsl: "application/xslt+xml", xslt: "application/xslt+xml", xsd: "application/xml",
  yaml: "application/yaml", yml: "application/yaml", toml: "application/toml", ini: "text/x-ini", cfg: "text/x-ini", conf: "text/x-config", env: "text/x-env", properties: "text/x-properties",
  js: "text/javascript", mjs: "text/javascript", cjs: "text/javascript", jsx: "text/jsx",
  ts: "text/typescript", mts: "text/typescript", cts: "text/typescript", tsx: "text/tsx",
  vue: "text/x-vue", svelte: "text/x-svelte", astro: "text/x-astro", css: "text/css", scss: "text/x-scss", sass: "text/x-sass", less: "text/x-less",
  py: "text/x-python", pyw: "text/x-python", java: "text/x-java", kt: "text/x-kotlin", kts: "text/x-kotlin", cs: "text/x-csharp",
  c: "text/x-c", h: "text/x-c", cpp: "text/x-c++", cxx: "text/x-c++", cc: "text/x-c++", hpp: "text/x-c++",
  go: "text/x-go", rs: "text/x-rust", rb: "text/x-ruby", php: "text/x-php", swift: "text/x-swift", m: "text/x-objectivec", mm: "text/x-objectivec",
  sh: "text/x-shellscript", bash: "text/x-shellscript", zsh: "text/x-shellscript", ps1: "text/x-powershell", psm1: "text/x-powershell", bat: "text/x-bat", cmd: "text/x-bat",
  sql: "application/sql", graphql: "application/graphql", gql: "application/graphql", proto: "text/x-protobuf", lua: "text/x-lua", r: "text/x-r", dart: "text/x-dart", ipynb: "application/json",
  tex: "text/x-tex", bib: "text/x-bibtex", srt: "application/x-subrip", vtt: "text/vtt", tsv: "text/tab-separated-values", diff: "text/x-diff", patch: "text/x-diff",
};

const textMimeAliases: Record<string, string> = {
  "application/javascript": "text/javascript", "application/x-javascript": "text/javascript",
  "application/typescript": "text/typescript", "application/x-typescript": "text/typescript",
  "application/python": "text/x-python", "application/x-python": "text/x-python",
  "application/sh": "text/x-shellscript", "application/x-sh": "text/x-shellscript", "application/shellscript": "text/x-shellscript", "application/x-shellscript": "text/x-shellscript",
  "application/php": "text/x-php", "application/x-php": "text/x-php", "application/x-httpd-php": "text/x-php",
  "text/xml": "application/xml", "text/yaml": "application/yaml", "text/x-yaml": "application/yaml", "application/x-yaml": "application/yaml",
};

export function getTextMimeType(name: string, mimeType = ""): string | undefined {
  const filename = name.split(/[\\/]/).pop()?.toLowerCase() ?? "";
  if (/^(?:readme|license|licence|notice|changelog|authors|copying)$/.test(filename)) return "text/plain";
  if (/^(?:dockerfile|makefile|gemfile|\.gitignore|\.gitattributes|\.editorconfig|\.npmrc|\.env(?:\..+)?)$/.test(filename)) return "text/x-config";
  const extension = filename.match(/\.([^.]+)$/)?.[1] ?? "";
  if (Object.hasOwn(textFormats, extension)) return textFormats[extension];
  const raw = mimeType.split(";")[0].trim().toLowerCase();
  const normalized = Object.hasOwn(textMimeAliases, raw) ? textMimeAliases[raw] : raw;
  if (/^text\/[\w.+-]+$/.test(normalized) || /^application\/(?:[\w.-]+\+(?:json|xml)|(?:x-)?(?:json|jsonc|json5|ndjson|xml|yaml|toml|javascript|typescript|sql|graphql|sh|shellscript|python|php|subrip))$/.test(normalized)) return normalized;
}

export function getReadableFileMimeType(name: string, mimeType = ""): string | undefined {
  return getDocumentMimeType(name) ?? getTextMimeType(name) ?? getDocumentMimeType("", mimeType) ?? getTextMimeType("", mimeType);
}

export function getReadableFileExtension(name: string, mimeType = ""): string | undefined {
  const documentExtension = getDocumentExtension(name);
  if (documentExtension) return documentExtension;
  const textMimeType = getTextMimeType(name);
  const extension = name.split(/[\\/]/).pop()?.match(/\.([^.]+)$/)?.[1].toLowerCase() ?? "";
  if (textMimeType && Object.hasOwn(textFormats, extension)) return extension;
  const inferredDocumentExtension = textMimeType ? undefined : getDocumentExtension("", mimeType);
  if (inferredDocumentExtension) return inferredDocumentExtension;
  const normalized = textMimeType ?? getTextMimeType("", mimeType);
  return normalized ? Object.keys(textFormats).find(extension => textFormats[extension] === normalized) ?? "txt" : undefined;
}

export const readableFileAccept = `${documentAccept},${Object.keys(textFormats).map(extension => `.${extension}`).join(",")},text/*,application/json,application/xml,application/yaml`;

export function decodeTextFile(bytes: Uint8Array): string {
  const encoding = bytes[0] === 0xff && bytes[1] === 0xfe ? "utf-16le"
    : bytes[0] === 0xfe && bytes[1] === 0xff ? "utf-16be" : "utf-8";
  try {
    const text = new TextDecoder(encoding, { fatal: true }).decode(bytes);
    if (text.includes("\0")) throw new Error("binary");
    return text;
  } catch {
    throw new Error("文件不是受支持的 UTF-8 或带 BOM 的 UTF-16 文本，请先转换编码后重试");
  }
}
