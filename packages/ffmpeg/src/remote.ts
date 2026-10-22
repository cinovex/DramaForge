import { msg } from "@toonflow/i18n";
import { messageError } from "@toonflow/i18n/errors";
import { chainMethods, queryMethods, runMethods } from "./browserTypes";
import type { BrowserFfmpegRequest, FfmpegCall, FfmpegRemoteEvent } from "./browserTypes";
import type { FfmpegCommand, FfmpegFactory } from "./types";

export { chainMethods, queryMethods, runMethods } from "./browserTypes";

const chainNames = new Set<string>(chainMethods);
const queryNames = new Set<string>(queryMethods);
const runNames = new Set<string>(runMethods);
const inputNames = new Set(["input", "addInput", "mergeAdd"]);
const outputNames = new Set(["output", "addOutput", "save", "saveToFile", "concat", "concatenate", "mergeToFile"]);

function serializeError(error: unknown) {
  return error instanceof Error
    ? { name: error.name, message: error.message, ...("code" in error ? { code: error.code } : {}), ...("i18nMessage" in error ? { i18nMessage: error.i18nMessage } : {}) }
    : { name: "Error", message: String(error) };
}

function invoke(command: FfmpegCommand, call: FfmpegCall, extra: unknown[] = []) {
  if ((inputNames.has(call.method) || outputNames.has(call.method)) && typeof call.args[0] !== "string") {
    throw new Error("浏览器 FFmpeg 输入、输出必须使用工作区文件路径");
  }
  const args = call.args.map((value, index) => call.undefinedArgs?.includes(index) ? undefined : value);
  return Reflect.apply((command as unknown as Record<string, (...args: unknown[]) => unknown>)[call.method]!, command, [...args, ...extra]);
}

/** 浏览器只传链式调用数据，执行及显式路径检查仍使用原生工作区工厂。 */
export async function executeRemoteFfmpeg(
  factory: FfmpegFactory,
  request: BrowserFfmpegRequest,
  emit: (event: FfmpegRemoteEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  try {
    signal.throwIfAborted();
    for (const call of request.calls) {
      if (!chainNames.has(call.method)) throw messageError(msg`FFmpeg 配置方法不可用：${call.method}`);
    }
    const operation = request.operation;
    if (!queryNames.has(operation.method) && !runNames.has(operation.method)) {
      throw messageError(msg`FFmpeg 执行方法不可用：${operation.method}`);
    }
    let command = factory(request.options);
    for (const call of request.calls) command = invoke(command, call) as FfmpegCommand;
    await new Promise<void>(resolve => {
      let finished = false;
      const send = (event: string, args: unknown[]) => { if (!finished) emit({ event, args }); };
      const finish = (event: string, args: unknown[]) => {
        if (finished) return;
        if (signal.aborted) {
          event = "error";
          args = [serializeError(signal.reason ?? new DOMException("FFmpeg 已取消", "AbortError"))];
        }
        send(event, args);
        finished = true;
        signal.removeEventListener("abort", cancel);
        resolve();
      };
      const fail = (error: unknown, ...args: unknown[]) => finish("error", [serializeError(error), ...args]);
      const cancel = () => {
        // ACT: kill 只发送信号；等原生完成事件再返回，调用方才能安全清理输出文件。
        if (!queryNames.has(operation.method)) command.kill("SIGKILL");
      };
      signal.addEventListener("abort", cancel, { once: true });
      // ACT: 取消可能早于 spawn；保留监听，准备阶段结束后立即终止，且接住迟到的 error。
      command.on("start", (...args) => {
        if (signal.aborted) command.kill("SIGKILL");
        else send("start", args);
      });
      command.on("error", fail);
      command.on("end", (...args) => finish("end", args));
      for (const event of ["progress", "stderr", "codecData", "filenames"] as const) {
        command.addListener(event, (...args: unknown[]) => send(event, args));
      }
      try {
        signal.throwIfAborted();
        if (queryNames.has(operation.method)) {
          // ACT: fluent 未公开查询子进程；取消后等查询回调释放文件，不等待查询不会触发的 start。
          invoke(command, operation, [(error: unknown, data: unknown) => error ? fail(error) : finish("result", [data])]);
        } else {
          invoke(command, operation);
        }
      } catch (error) {
        fail(error);
      }
    });
  } catch (error) {
    emit({ event: "error", args: [serializeError(error)] });
  }
}
