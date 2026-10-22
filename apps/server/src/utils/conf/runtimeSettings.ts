import conf from "./index";
import { z } from "zod";

export default async function readRuntimeSettings(): Promise<Record<string, unknown>> {
  const source = process.env.DRAMAFORGE_SETTINGS_URL;
  if (!source) return conf.get("settings", {});
  try {
    const response = await fetch(source, { signal: AbortSignal.timeout(10000), cache: "no-store" });
    if (!response.ok) throw new Error("Settings service unavailable");
    const payload = z.object({ code: z.literal(200), data: z.record(z.string(), z.unknown()) }).parse(await response.json());
    return payload.data;
  } catch {
    throw Object.assign(new Error("无法读取全局模型配置，请确认项目服务已启动后重试"), { status: 503 });
  }
}
