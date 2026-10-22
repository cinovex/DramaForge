import { Router } from "express";
import { z } from "zod";
import { validateFields } from "@/lib/middleware";
import u from "@/utils";

export default Router().get("/", validateFields({
  accountIds: z.string().max(6499).regex(/^[a-f0-9]{64}(,[a-f0-9]{64}){0,99}$/),
}, "query"), (req, res) => {
  // ACT: 原生 EventSource 无自定义请求头；沿用 FFmpeg 通知流的同源校验。
  u.mcpControl.getAppOrigin(req);
  u.mediaBilling.connectBalanceEvents((req.query.accountIds as string).split(","), res);
});
