import { Router } from "express";
import { z } from "zod";
import u from "@/utils";
import { validateFields } from "@/lib/middleware";
import { error, success } from "@/lib/responseFormat";

const router = Router();

export default router.post("/", validateFields({ directory: z.string().min(1).max(4096), path: z.string().min(1).max(4096), target: z.string().min(1).max(4096) }), async (req, res) => {
  const source = await u.workspaceFile.resolveWorkspaceFile(req, req.body.directory, req.body.path);
  const target = await u.workspaceFile.resolveWorkspacePath(source.directory, req.body.target);
  u.workspaceFile.protectWorkspaceRoot(source.directory, source.path);
  u.workspaceFile.protectWorkspaceRoot(target.directory, target.path);
  const release = u.workspaceFile.lockWorkspaceFiles([source.path, target.path]);
  try { await u.workspaceFile.copyWorkspaceFile(source.path, target.path); }
  catch (cause) {
    if (!(cause instanceof Error) || (cause as NodeJS.ErrnoException).code !== "ECOPYINCOMPLETE") throw cause;
    return res.status(500).json(error(cause.message, { code: "ECOPYINCOMPLETE", partial: true, target: req.body.target }, 500));
  } finally { release(); }
  res.json(success());
});
