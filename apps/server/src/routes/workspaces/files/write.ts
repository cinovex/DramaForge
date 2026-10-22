import { Router } from "express";
import { readFile } from "@toonflow/file";
import { createHash } from "node:crypto";
import { z } from "zod";
import u from "@/utils";
import { validateFields } from "@/lib/middleware";
import { success } from "@/lib/responseFormat";

const router = Router();

export default router.put("/", validateFields({ directory: z.string().min(1).max(4096), path: z.string().max(4096), exclusive: z.enum(["true", "false"]).optional(), expectedRevision: z.string().regex(/^[a-f0-9]{64}$/).optional(), encoding: z.enum(["utf-8", "utf-8-bom", "utf-16le", "utf-16be"]).optional() }, "query"), async (req, res) => {
  if (!req.is("application/octet-stream") || (req.body !== undefined && !Buffer.isBuffer(req.body))) {
    throw Object.assign(new Error("请发送文件原始内容"), { status: 400 });
  }
  const { directory, path } = await u.workspaceFile.resolveWorkspaceFile(req, req.query.directory as string, req.query.path as string);
  u.workspaceFile.protectWorkspaceRoot(directory, path);
  const release = u.workspaceFile.lockWorkspaceFiles([path]);
  let revision: string | undefined;
  try {
    let bytes = req.body ?? Buffer.alloc(0);
    if (req.query.expectedRevision) {
      const previous = await readFile(path).catch(error => {
        if (error.code === "ENOENT") throw Object.assign(new Error("文件已被删除或移动，未覆盖磁盘内容"), { status: 409, code: "ESTALE" });
        throw error;
      });
      if (createHash("sha256").update(previous).digest("hex") !== req.query.expectedRevision) {
        throw Object.assign(new Error("文件已被其他编辑器修改，当前修改已保留，请重新载入磁盘版本或另存副本"), { status: 409, code: "ESTALE" });
      }
    }
    if (req.query.encoding && req.query.encoding !== "utf-8") {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      if (req.query.encoding === "utf-8-bom") bytes = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(text)]);
      else {
        const encoded = Buffer.from(text, "utf16le");
        if (req.query.encoding === "utf-16be") encoded.swap16();
        bytes = Buffer.concat([Buffer.from(req.query.encoding === "utf-16be" ? [0xfe, 0xff] : [0xff, 0xfe]), encoded]);
      }
    }
    await u.workspaceFile.writeWorkspaceFile(path, bytes, req.query.exclusive === "true");
    if (req.query.expectedRevision) revision = createHash("sha256").update(bytes).digest("hex");
  }
  finally { release(); }
  res.json(success(revision ? { revision } : undefined));
});
