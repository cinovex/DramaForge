import { readdir } from "@toonflow/file";
import { Router } from "express";
import u from "@/utils";
import { success } from "@/lib/responseFormat";
import { translateMessage } from "@/lib/i18n";

export default Router().get("/", async (req, res) => {
  const canManage = u.workspace.isLocalWorkspaceRequest(req) === true;
  const files = await readdir(u.extPlugins.extDirectory, { withFileTypes: true }).catch((error: NodeJS.ErrnoException) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  const extensions = await Promise.all(files.filter(file => file.isFile() && /^ext-[a-z][a-zA-Z0-9]*\.umd\.js$/.test(file.name))
    .sort((left, right) => left.name.localeCompare(right.name)).map(async file => {
      const name = file.name.slice(0, -7);
      const metadata = await u.extPlugins.readExt(name).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return null;
        return { name, id: name, displayName: name, extensions: [], resourceKind: "file", version: "", readme: "", author: "", github: "", configRules: [],
          loadError: translateMessage(error instanceof Error ? error.message : "文件扩展无法读取") };
      });
      return metadata && { loadError: "", ...metadata, canManage, canConfigure: canManage, config: canManage ? u.extPlugins.getExtConfig(metadata) : {},
        enabled: !files.some(entry => entry.name === `${name}.disabled`), url: `/api/ext/read?name=${name}` };
    }));
  res.set("Cache-Control", "no-store").json(success(extensions.filter(Boolean)));
});
