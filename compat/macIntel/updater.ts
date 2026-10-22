import { Updater, Utils } from "electrobun/bun";
import { execFile, spawn } from "node:child_process";
import { basename, dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { lstatSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeAtomicSync } from "@toonflow/file";

const execFileAsync = promisify(execFile);
type preparedUpdate = { version: string; hash: string; archivePath: string };
let prepared: preparedUpdate | undefined;
let updateError = "";
let installError = "";
let activeHelper: ReturnType<typeof spawn> | undefined;
let startupConfirmed = false;
// 在本进程启动时固定身份，旧进程完成目录交换后不能用新磁盘元数据确认启动成功。
const startupInfo = Updater.getLocalInfo().then(info => ({ ...info }));

// ACT: 1.18.1 launcher 与其 Bun 子进程共享进程组；先验证独立组，再允许旧进程退出。
// 原生事务只操作本次同卷目录；新版未确认就绪时，先确认其进程组停止，再恢复旧应用。
const supervisorScript = `
transactionDirectory=$1
bundlePath=$2
stagedPath=$3
parentPid=$4
oldLauncherPid=$5
transactionId=$6
targetVersion=$7
targetHash=$8
quitDeadline=$9
previousPath="$transactionDirectory/previous.app"
groupSafe=0
handoff=0
previousMoved=0
launchPid=
writeFailure() { printf '%s\\n' "$1" > "$transactionDirectory/failure"; }
groupAlive() { kill -0 -- "-$launchPid" 2>/dev/null; }
stopLaunch() {
  /bin/rm -f "$transactionDirectory/ready"
  [ -n "$launchPid" ] || return 0
  if [ "$groupSafe" != 1 ]; then kill -TERM "$launchPid" 2>/dev/null; return 1; fi
  groupAlive || return 0
  kill -TERM -- "-$launchPid" 2>/dev/null
  count=0
  while groupAlive && [ "$count" -lt 20 ]; do /bin/sleep 0.1; count=$((count + 1)); done
  if groupAlive; then kill -KILL -- "-$launchPid" 2>/dev/null; fi
  count=0
  while groupAlive && [ "$count" -lt 20 ]; do /bin/sleep 0.1; count=$((count + 1)); done
  ! groupAlive
}
rollback() {
  writeFailure "$1"
  if ! stopLaunch; then
    writeFailure "无法确认本次新版进程已停止，未启动旧版本；备份保留在 $previousPath。"
    exit 1
  fi
  if [ "$previousMoved" = 1 ] && [ ! -d "$previousPath" ]; then
    writeFailure "旧版本备份已丢失或不可访问，未再次启动新版；请下载完整安装包。"; exit 1
  fi
  if [ -d "$previousPath" ]; then
    if [ -e "$bundlePath" ]; then
      if [ -e "$stagedPath" ] || ! /bin/mv "$bundlePath" "$stagedPath"; then
        writeFailure "新版已停止，但无法移开新版；旧版本保留在 $previousPath。"; exit 1
      fi
    fi
    if ! /bin/mv "$previousPath" "$bundlePath"; then
      writeFailure "新版已停止，但恢复旧应用失败；旧版本保留在 $previousPath。"; exit 1
    fi
  fi
  trap - HUP INT TERM
  unset TOONFLOW_INTEL_UPDATE_TRANSACTION TOONFLOW_INTEL_UPDATE_LAUNCHER
  cd "$bundlePath/Contents/MacOS" || exit 1
  exec ./launcher
}
trap 'trap - HUP INT TERM; if [ "$handoff" = 1 ]; then rollback "更新监督进程中断，已尝试恢复旧版本。"; fi; stopLaunch; exit 1' HUP INT TERM
set -m || exit 1
(
  count=0
  while [ ! -f "$transactionDirectory/launch" ]; do
    [ ! -f "$transactionDirectory/cancel" ] && [ "$count" -lt 1800 ] || exit 1
    /bin/sleep 0.1; count=$((count + 1))
  done
  read launchOwner < "$transactionDirectory/launch" || exit 1
  case "$launchOwner" in ''|*[!0-9]*) exit 1;; esac
  export TOONFLOW_INTEL_UPDATE_TRANSACTION="$transactionId"
  export TOONFLOW_INTEL_UPDATE_LAUNCHER="$launchOwner"
  cd "$bundlePath/Contents/MacOS" || exit 1
  exec ./launcher
) </dev/null >/dev/null 2>&1 &
launchPid=$!
launchGroup=$(/bin/ps -p "$launchPid" -o pgid= | /usr/bin/tr -d ' ')
supervisorGroup=$(/bin/ps -p "$$" -o pgid= | /usr/bin/tr -d ' ')
if [ "$launchGroup" != "$launchPid" ] || [ "$launchGroup" = "$supervisorGroup" ]; then
  writeFailure "无法隔离更新启动进程，已取消更新。"
  stopLaunch; exit 1
fi
groupSafe=1
printf '%s %s\\n' "$transactionId" "$quitDeadline" > "$transactionDirectory/ready" || { stopLaunch; exit 1; }
count=0
while kill -0 "$parentPid" 2>/dev/null || { [ "$oldLauncherPid" != 0 ] && kill -0 "$oldLauncherPid" 2>/dev/null; }; do
  if [ -f "$transactionDirectory/cancel" ] || [ "$count" -ge 600 ] || [ "$(( $(/bin/date +%s) * 1000 ))" -ge "$quitDeadline" ]; then
    writeFailure "旧应用尚未退出，已取消更新。"; stopLaunch; exit 1
  fi
  /bin/sleep 0.1; count=$((count + 1))
done
if [ -f "$transactionDirectory/cancel" ]; then stopLaunch; exit 1; fi
handoff=1
if [ ! -d "$bundlePath" ] || [ -L "$bundlePath" ] || [ ! -d "$stagedPath" ] || [ -L "$stagedPath" ] || [ -e "$previousPath" ]; then
  writeFailure "应用目录已变化，未替换旧应用。"; stopLaunch; exit 1
fi
if ! /bin/mv "$bundlePath" "$previousPath"; then rollback "无法备份旧应用，更新未完成。"; fi
previousMoved=1
if ! /bin/mv "$stagedPath" "$bundlePath"; then rollback "无法替换应用，已尝试恢复旧版本。"; fi
printf '%s\\n' "$launchPid" > "$transactionDirectory/launch.pending" && /bin/mv "$transactionDirectory/launch.pending" "$transactionDirectory/launch" || rollback "无法发布新版启动指令，已尝试恢复旧版本。"
count=0
while [ "$count" -lt 1200 ]; do
  if [ -f "$transactionDirectory/started" ]; then
    read ackId ackVersion ackHash ackSuccess ackPid extra < "$transactionDirectory/started"
    case "$ackPid" in ''|*[!0-9]*) ackPid=0;; esac
    ackGroup=$(/bin/ps -p "$ackPid" -o pgid= 2>/dev/null | /usr/bin/tr -d ' ')
    if [ "$ackId" = "$transactionId" ] && [ "$ackVersion" = "$targetVersion" ] && [ "$ackHash" = "$targetHash" ] && [ "$ackGroup" = "$launchPid" ] && [ -z "$extra" ]; then
      if [ "$ackSuccess" != 1 ]; then rollback "新版报告启动失败，已尝试恢复旧版本。"; fi
      trap - HUP INT TERM
      /bin/rm -rf "$transactionDirectory"
      wait "$launchPid"
      exit 0
    fi
  fi
  groupAlive || rollback "新版启动进程提前退出，已尝试恢复旧版本。"
  /bin/sleep 0.1; count=$((count + 1))
done
rollback "新版启动确认超时，已尝试恢复旧版本。"
`;

function readSmallFile(path: string) {
  const stat = lstatSync(path, { throwIfNoEntry: false });
  return stat?.isFile() && stat.size <= 16384 ? readFileSync(path, "utf8") : "";
}

async function readTransaction() {
  const source = readSmallFile(join(await Updater.appDataFolder(), "toonflowUpdate.json"));
  if (!source) return;
  const record = JSON.parse(source);
  const bundlePath = realpathSync(resolve(dirname(process.execPath), "../.."));
  if (!/^[a-f0-9]{32}$/.test(record.transactionId) || !/^\d+\.\d+\.\d+$/.test(record.version) || !/^[a-zA-Z0-9]{1,64}$/.test(record.hash)
    || record.bundlePath !== bundlePath || typeof record.transactionDirectory !== "string"
    || dirname(record.transactionDirectory) !== dirname(bundlePath) || !/^\.toonflowUpdate-[a-zA-Z0-9]+$/.test(basename(record.transactionDirectory))) return;
  const stat = lstatSync(record.transactionDirectory, { throwIfNoEntry: false });
  if (!stat?.isDirectory() || realpathSync(record.transactionDirectory) !== record.transactionDirectory) return;
  return record as { transactionId: string; identifier: string; channel: string; version: string; hash: string; transactionDirectory: string };
}

async function verifyArchive(target: preparedUpdate) {
  const local = await Updater.getLocalInfo();
  if (!/^[a-zA-Z0-9_-]+$/.test(local.name) || !lstatSync(target.archivePath, { throwIfNoEntry: false })?.isFile()) {
    throw new Error("更新包路径无效，请重新下载。");
  }
  try {
    const { stdout } = await execFileAsync("/usr/bin/tar", ["-xOf", target.archivePath, `${local.name}.app/Contents/Resources/version.json`], {
      timeout: 60000, maxBuffer: 65536,
    });
    verifyIdentity(JSON.parse(stdout), local, target);
  } catch (error) {
    // 旧 SDK 只凭 tar 文件名复用缓存，移除无效包后重试才会真正重新下载。
    try { rmSync(target.archivePath, { force: true }); }
    catch (cleanupError) { console.warn("无效更新包暂时无法清理：", cleanupError); }
    throw error;
  }
}

function verifyIdentity(info: Record<string, unknown>, local: { identifier: string; channel: string }, target: preparedUpdate) {
  if (!info || info.identifier !== local.identifier || info.channel !== local.channel || info.version !== target.version || info.hash !== target.hash) {
    throw new Error("更新包版本与已下载的更新不一致，请重新下载。");
  }
}

const updater = {
  ...Updater,
  async getLocalInfo() {
    const local = await Updater.getLocalInfo();
    try {
      const record = await readTransaction();
      const failure = record && readSmallFile(join(record.transactionDirectory, "failure")).trim();
      const currentTransaction = record?.transactionId === process.env.TOONFLOW_INTEL_UPDATE_TRANSACTION;
      const recovered = record && (local.version === record.version && local.hash === record.hash || Bun.semver.order(local.version, record.version) > 0);
      installError = record?.identifier === local.identifier && record.channel === local.channel && failure && (currentTransaction || !recovered) ? failure : "";
    } catch (error) { console.warn("读取更新监督结果失败：", error); }
    return local;
  },
  async confirmStartup(failed = false) {
    const transactionId = process.env.TOONFLOW_INTEL_UPDATE_TRANSACTION;
    if (!transactionId || startupConfirmed) return;
    const local = await startupInfo;
    const record = await readTransaction();
    if (record?.transactionId !== transactionId || String(process.ppid) !== process.env.TOONFLOW_INTEL_UPDATE_LAUNCHER) {
      throw new Error("更新启动事务不匹配，无法确认启动成功。");
    }
    const matches = record.identifier === local.identifier && record.channel === local.channel && record.version === local.version && record.hash === local.hash;
    writeAtomicSync(join(record.transactionDirectory, "started"), `${transactionId} ${record.version} ${record.hash} ${!failed && matches ? 1 : 0} ${process.pid}\n`, { exclusive: true, mode: 0o600 });
    startupConfirmed = true;
  },
  updateInfo() {
    const state = Updater.updateInfo();
    return { ...state, error: updateError || state?.error || "", installError, updateReady: !!prepared && state?.hash === prepared.hash && state.version === prepared.version };
  },
  async checkForUpdate() {
    if (activeHelper) throw new Error("更新交接仍在执行，请稍后重试。");
    updateError = "";
    try {
      const state = await Updater.checkForUpdate();
      if (state.error || !state.updateAvailable || state.hash !== prepared?.hash || state.version !== prepared?.version) prepared = undefined;
      updateError = state.error || "";
      return { ...state, updateReady: !!prepared };
    } catch (error) {
      prepared = undefined;
      updateError = error instanceof Error ? error.message : String(error);
      throw error;
    }
  },
  async downloadUpdate() {
    if (activeHelper) throw new Error("更新交接仍在执行，请稍后重试。");
    prepared = undefined;
    updateError = "";
    try {
      await Updater.downloadUpdate();
      const state = Updater.updateInfo();
      if (state?.error || !state?.updateReady || !/^[a-zA-Z0-9]{1,64}$/.test(state.hash) || !/^\d+\.\d+\.\d+$/.test(state.version)) {
        throw new Error(state?.error || "更新包尚未准备完成，请重新下载。");
      }
      const target = { version: state.version, hash: state.hash, archivePath: join(await Updater.appDataFolder(), "self-extraction", `${state.hash}.tar`) };
      await verifyArchive(target);
      prepared = target;
    } catch (error) {
      updateError = error instanceof Error ? error.message : String(error);
      throw error;
    }
  },
  async applyUpdate() {
    if (activeHelper) throw new Error("更新交接仍在执行，请稍后重试。");
    if (!prepared || !updater.updateInfo().updateReady) throw new Error("请先下载当前版本的更新包。");
    const target = prepared;
    updateError = "";
    let transactionDirectory = "";
    let restart: ReturnType<typeof spawn> | undefined;
    const bundlePath = realpathSync(resolve(dirname(process.execPath), "../.."));
    try {
      // ACT: 应用已准备的固定版本，不在重启阶段再次请求可变的远程清单。
      await verifyArchive(target);
      const local = await Updater.getLocalInfo();
      verifyIdentity(JSON.parse(readFileSync(join(bundlePath, "Contents/Resources/version.json"), "utf8")), local, { ...target, version: local.version, hash: local.hash });
      // ACT: 暂存和备份都在安装卷，缓存与应用跨卷时也只在同卷内 rename。
      transactionDirectory = mkdtempSync(join(dirname(bundlePath), ".toonflowUpdate-"));
      const stagingDirectory = join(transactionDirectory, "staged");
      mkdirSync(stagingDirectory);
      const stagedPath = join(stagingDirectory, `${local.name}.app`);
      await execFileAsync("/usr/bin/tar", ["-xf", target.archivePath, "-C", stagingDirectory], { timeout: 120000 });
      if (!lstatSync(stagedPath, { throwIfNoEntry: false })?.isDirectory()
        || ["launcher", "bun"].some(name => {
          const stat = lstatSync(join(stagedPath, "Contents/MacOS", name), { throwIfNoEntry: false });
          return !stat?.isFile() || !(stat.mode & 0o111);
        }) || !lstatSync(join(stagedPath, "Contents/Resources/main.js"), { throwIfNoEntry: false })?.isFile()) {
        throw new Error("更新包缺少可运行的应用，请重新下载。");
      }
      verifyIdentity(JSON.parse(readFileSync(join(stagedPath, "Contents/Resources/version.json"), "utf8")), local, target);
      // 保留旧 SDK 的 quarantine 处理；没有该属性时 xattr 会返回非零。
      await execFileAsync("/usr/bin/xattr", ["-r", "-d", "com.apple.quarantine", stagedPath]).catch(() => {});
      const transactionId = crypto.randomUUID().replaceAll("-", "");
      const quitDeadline = Date.now() + 60000;
      const quitMonotonicDeadline = performance.now() + 60000;
      const recordPath = join(await Updater.appDataFolder(), "toonflowUpdate.json");
      writeAtomicSync(recordPath, JSON.stringify({ transactionId, identifier: local.identifier, channel: local.channel, version: target.version, hash: target.hash, bundlePath, transactionDirectory }), { mode: 0o600 });
      const { stdout } = await execFileAsync("/bin/ps", ["-p", String(process.ppid), "-o", "comm="], { timeout: 5000 });
      const oldLauncherPid = stdout.trim() === join(bundlePath, "Contents/MacOS/launcher") ? process.ppid : 0;
      // 所有路径经独立参数传递；helper 在旧进程退出前只准备监督组，不移动应用。
      restart = spawn("/bin/sh", ["-c", supervisorScript, "toonflowUpdate", transactionDirectory, bundlePath, stagedPath,
        String(process.pid), String(oldLauncherPid), transactionId, target.version, target.hash, String(quitDeadline)], {
        cwd: dirname(bundlePath), detached: true, stdio: "ignore",
      });
      activeHelper = restart;
      restart.once("exit", () => { if (activeHelper === restart) activeHelper = undefined; });
      restart.once("error", () => { if (!restart!.pid && activeHelper === restart) activeHelper = undefined; });
      await new Promise<void>((resolve, reject) => { restart!.once("spawn", resolve); restart!.once("error", reject); });
      const readyPath = join(transactionDirectory, "ready");
      const readyValue = `${transactionId} ${quitDeadline}`;
      for (let count = 0; readSmallFile(readyPath).trim() !== readyValue; count++) {
        if (restart.exitCode !== null || restart.signalCode !== null || count >= 50) {
          throw new Error(readSmallFile(join(transactionDirectory, "failure")).trim() || "更新监督进程未就绪，已取消更新。");
        }
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      // UTC 判断暂停过期，单调时钟防系统时间回拨；两种期限都必须留下完整退出时间。
      if (!restart.pid || restart.exitCode !== null || restart.signalCode !== null || Date.now() + 5000 >= quitDeadline
        || performance.now() + 5000 >= quitMonotonicDeadline
        || readSmallFile(readyPath).trim() !== readyValue) throw new Error("更新交接已失效，已保留旧版本，请重试。");
      process.kill(restart.pid, 0);
      restart.unref();
      // 1.18.1 成功退出不会返回；若被取消，helper 尚未换包，取消放行即可。
      Utils.quit();
      throw new Error("更新重启已取消，已保留旧版本。");
    } catch (error) {
      prepared = undefined;
      if (restart && activeHelper === restart) {
        try { writeAtomicSync(join(transactionDirectory, "cancel"), "1", { mode: 0o600 }); }
        catch (cancelError) { console.warn("写入更新取消指令失败：", cancelError); }
        restart.kill("SIGTERM");
        for (let count = 0; activeHelper === restart && count < 50; count++) await new Promise(resolve => setTimeout(resolve, 100));
        if (activeHelper === restart) {
          restart.kill("SIGKILL");
          for (let count = 0; activeHelper === restart && count < 20; count++) await new Promise(resolve => setTimeout(resolve, 100));
        }
      }
      updateError = error instanceof Error ? error.message : String(error);
      if (activeHelper) updateError += " 更新监督进程尚未确认停止，请勿再次更新。";
      throw error;
    } finally {
      // 本进程仍然存活时，helper 不会换包；仅在确认其停止后清理本次暂存目录。
      if (transactionDirectory && !activeHelper) {
        try { rmSync(transactionDirectory, { recursive: true }); }
        catch (error) { console.warn("更新暂存目录清理失败：", error); }
      }
    }
  },
};

export default updater;
