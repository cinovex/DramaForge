<template>
  <el-dialog
    :modelValue="modelValue"
    title="Pippit AI 创作"
    width="min(760px, calc(100vw - 32px))"
    alignCenter
    appendToBody
    :closeOnClickModal="!busy"
    :closeOnPressEscape="!busy"
    :showClose="!busy"
    @update:modelValue="$emit('update:modelValue', $event)">
    <div class="pippitCreator">
      <div class="capabilityGrid" aria-label="Pippit API 能力状态">
        <div class="capabilityItem">
          <span>API 连接</span>
          <el-tag size="small" :type="status?.connected ? 'success' : status?.connected === false ? 'danger' : 'info'">
            {{ status?.connected ? '已连接' : status?.connected === false ? '未连接' : '状态未知' }}
          </el-tag>
        </div>
        <div class="capabilityItem"><span>积分余额</span><strong>API 未提供</strong></div>
        <div class="capabilityItem"><span>单步费用</span><strong>API 未提供</strong></div>
        <div class="capabilityItem"><span>模型与技能</span><strong>由 Pippit 自动选择</strong></div>
      </div>
      <p class="capabilityNote">官方海外接口支持提交创作、上传图片/视频参考、查询进度和取回生成结果；当前接口没有余额、逐步费用、模型或技能目录与手动选择功能。</p>

      <el-input
        v-model="prompt"
        type="textarea"
        :rows="8"
        resize="vertical"
        :disabled="busy"
        aria-label="Pippit 创作描述"
        placeholder="描述想生成的图片或视频。内容会原样提交给 Pippit Nest，由它决定具体制作流程。" />

      <div class="referenceHeader">
        <div><strong>参考素材</strong><span>图片或视频，可不添加</span></div>
        <el-button :disabled="busy || referenceFiles.length >= 32" @click="fileInput?.click()">添加图片 / 视频</el-button>
        <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm" multiple hidden @change="selectReferenceFiles" />
      </div>
      <div v-if="referenceFiles.length" class="referenceList">
        <div v-for="(item, index) in referenceFiles" :key="`${item.file.name}-${index}`" class="referenceItem">
          <span class="referenceName" :title="item.file.name">{{ item.file.name }}</span>
          <el-tag v-if="item.assetId" size="small" type="success">已上传</el-tag>
          <el-tag v-else-if="item.uploading" size="small">上传中</el-tag>
          <el-button text type="danger" size="small" :disabled="busy" aria-label="移除参考素材" @click="referenceFiles.splice(index, 1)">移除</el-button>
        </div>
      </div>

      <div v-if="runStatus !== 'idle'" class="runStatus" role="status" aria-live="polite">
        <div class="runStatusHeader">
          <strong>{{ statusLabel }}</strong>
          <el-button v-if="threadLink" tag="a" :href="threadLink" target="_blank" rel="noopener noreferrer" text type="primary">在 Pippit 查看</el-button>
        </div>
        <p v-if="latestMessage" class="latestMessage">{{ latestMessage }}</p>
        <el-alert v-if="runError" type="error" :title="runError" :closable="false" showIcon />
        <div v-if="resultAssets.length" class="resultAssets">
          <div v-for="asset in resultAssets" :key="asset.url" class="resultAsset">
            <video v-if="asset.kind === 'video'" :src="asset.url" controls preload="metadata" />
            <el-image v-else :src="asset.url" fit="contain" :alt="asset.name" :preview-src-list="[asset.url]" />
            <span :title="asset.name">{{ asset.name }}</span>
            <el-button size="small" @click="$emit('insertAssets', [asset])">放入画布</el-button>
          </div>
          <el-button v-if="resultAssets.length > 1" type="primary" plain @click="$emit('insertAssets', resultAssets)">全部放入画布</el-button>
        </div>
        <div v-if="runStatus === 'requires_action'" class="replyBox">
          <el-input v-model="replyText" type="textarea" :rows="3" resize="vertical" :disabled="busy" aria-label="回复 Pippit 的问题" placeholder="补充回答后继续同一个创作任务" />
          <el-button type="primary" :disabled="!replyText.trim() || busy" :loading="submitting" @click="submitRun(true)">回复并继续</el-button>
        </div>
      </div>

      <el-alert v-if="status?.message && !status.connected" class="connectionError" :type="status.connected === false ? 'error' : 'info'" :title="status.message" :closable="false" showIcon />
      <el-alert v-if="pageError" class="connectionError" type="error" :title="pageError" :closable="false" showIcon />
    </div>
    <template #footer>
      <div class="dialogFooter">
        <span>提交生成可能消耗 Pippit 积分；当前接口无法提前报价。</span>
        <el-button type="primary" :disabled="!prompt.trim() || status?.connected === false || busy" :loading="submitting && !threadId" @click="submitRun(false)">提交创作</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

type PippitStatus = { connected: boolean | null; message: string; capabilities?: Record<string, unknown> };
type PippitAsset = { url: string; name: string; mime?: string; kind: "image" | "video"; assetId?: string };
type ReferenceFile = { file: File; assetId?: string; uploading?: boolean };
type PippitResult = {
  status?: string;
  messages?: { role?: string; content?: { type?: string; data?: unknown }[] }[];
  downloads?: Record<string, unknown>[];
  download_urls?: string[];
  generated_assets?: Record<string, unknown>[];
  interactions?: Record<string, unknown>[];
};

const props = defineProps<{ modelValue: boolean }>();
defineEmits<{
  (event: "update:modelValue", value: boolean): void;
  (event: "insertAssets", assets: PippitAsset[]): void;
}>();

const prompt = ref("");
const replyText = ref("");
const status = ref<PippitStatus>();
const pageError = ref("");
const runError = ref("");
const fileInput = ref<HTMLInputElement>();
const referenceFiles = ref<ReferenceFile[]>([]);
const threadId = ref("");
const runId = ref("");
const threadLink = ref("");
const runStatus = ref<"idle" | "running" | "completed" | "failed" | "canceled" | "requires_action">("idle");
const latestMessage = ref("");
const resultAssets = ref<PippitAsset[]>([]);
const submitting = ref(false);
const uploading = ref(false);
const busy = computed(() => submitting.value || uploading.value || runStatus.value === "running");
const statusLabel = computed(() => ({ idle: "", running: "Pippit 正在创作…", completed: "创作完成", failed: "创作失败", canceled: "任务已取消", requires_action: "Pippit 需要补充信息" })[runStatus.value]);
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let pollController: AbortController | undefined;

function dramaForgeApiUrl(path: string) {
  return new URL(`api/${path.replace(/^\/+/, "")}`, `${window.location.origin}/`).toString();
}

watch(() => props.modelValue, visible => {
  if (visible) void checkConnection();
});

onScopeDispose(() => {
  if (pollTimer) clearTimeout(pollTimer);
  pollController?.abort();
});

async function checkConnection() {
  pageError.value = "";
  try {
    const response = await fetch(dramaForgeApiUrl("pippit/status"), { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (response.status === 404) {
      status.value = { connected: null, message: "当前本地服务尚未提供连接状态检查；提交前仍会再次确认。" };
      return;
    }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Pippit API 状态检查失败");
    status.value = data as PippitStatus;
  } catch (error) {
    status.value = { connected: null, message: "连接状态暂时无法读取；提交前仍会再次确认。" };
  }
}

function selectReferenceFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = Array.from(input.files ?? []);
  const remaining = 32 - referenceFiles.value.length;
  if (selected.length > remaining) ElMessage.warning("参考素材最多添加 32 个");
  referenceFiles.value.push(...selected.slice(0, remaining).map(file => ({ file })));
  input.value = "";
}

async function uploadReferences() {
  uploading.value = true;
  const assetIds: string[] = [];
  try {
    for (const item of referenceFiles.value) {
      if (item.assetId) {
        assetIds.push(item.assetId);
        continue;
      }
      item.uploading = true;
      const form = new FormData();
      form.append("file", item.file);
      const response = await fetch(dramaForgeApiUrl("pippit/upload"), { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || typeof data.asset_id !== "string") throw new Error(typeof data.detail === "string" ? data.detail : `参考素材“${item.file.name}”上传失败`);
      item.assetId = data.asset_id;
      assetIds.push(item.assetId!);
      item.uploading = false;
    }
    return assetIds;
  } finally {
    for (const item of referenceFiles.value) item.uploading = false;
    uploading.value = false;
  }
}

async function submitRun(isReply: boolean) {
  if (submitting.value || uploading.value) return;
  const message = isReply ? replyText.value : prompt.value;
  if (!message.trim()) return;
  const confirmed = await ElMessageBox.confirm(
    "Pippit 创作会提交到海外 API，可能消耗积分。当前接口不能查询余额或预估本次费用。仍要继续吗？",
    "确认提交 Pippit 创作",
    { confirmButtonText: "继续提交", cancelButtonText: "返回修改", type: "warning", closeOnClickModal: false },
  ).then(() => true, () => false);
  if (!confirmed) return;

  submitting.value = true;
  pageError.value = "";
  runError.value = "";
  try {
    const assetIds = isReply ? [] : await uploadReferences();
    const response = await fetch(dramaForgeApiUrl("pippit/submit"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: isReply ? threadId.value : "", asset_ids: assetIds }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || typeof data.thread_id !== "string" || typeof data.run_id !== "string") throw new Error(typeof data.detail === "string" ? data.detail : "Pippit 未返回有效任务编号");
    threadId.value = data.thread_id;
    runId.value = data.run_id;
    threadLink.value = typeof data.web_thread_link === "string" ? data.web_thread_link : "";
    runStatus.value = "running";
    replyText.value = "";
    resultAssets.value = [];
    latestMessage.value = "任务已提交，正在等待 Pippit 返回进度。";
    if (!isReply) referenceFiles.value = referenceFiles.value.filter(item => !item.assetId);
    void pollRun();
  } catch (error) {
    runError.value = error instanceof Error ? error.message : "Pippit 提交失败";
    if (!threadId.value) runStatus.value = "failed";
  } finally {
    submitting.value = false;
  }
}

async function pollRun() {
  if (!threadId.value || !runId.value) return;
  pollController?.abort();
  const controller = new AbortController();
  pollController = controller;
  try {
    const response = await fetch(dramaForgeApiUrl("pippit/thread"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId.value, run_id: runId.value, after_seq: 0 }),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({})) as PippitResult & { detail?: string };
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "读取 Pippit 任务进度失败");
    runStatus.value = normalizeStatus(data.status);
    latestMessage.value = getLatestMessage(data.messages ?? []);
    resultAssets.value = normalizeAssets(data);
    runError.value = runStatus.value === "failed" ? latestMessage.value || "Pippit 返回任务失败" : "";
    if (runStatus.value === "requires_action") replyText.value = "";
    if (runStatus.value === "running") pollTimer = setTimeout(() => void pollRun(), 5000);
    else if (runStatus.value === "completed" && !resultAssets.value.length && !latestMessage.value) latestMessage.value = "Pippit 已完成任务，但没有返回可导入的媒体链接。";
  } catch (error) {
    if (controller.signal.aborted) return;
    runError.value = error instanceof Error ? error.message : "读取 Pippit 任务进度失败";
    runStatus.value = "failed";
  }
}

function normalizeStatus(value: unknown): "running" | "completed" | "failed" | "canceled" | "requires_action" {
  const statusValue = String(value ?? "").toLowerCase();
  if (["completed", "complete", "succeeded", "success", "done"].includes(statusValue)) return "completed";
  if (["failed", "failure", "error"].includes(statusValue)) return "failed";
  if (["canceled", "cancelled"].includes(statusValue)) return "canceled";
  if (["requires_action", "requires_user_input", "interaction_required"].includes(statusValue)) return "requires_action";
  return "running";
}

function getLatestMessage(messages: NonNullable<PippitResult["messages"]>) {
  const assistant = [...messages].reverse().find(message => message.role === "assistant");
  const text = assistant?.content?.map(item => {
    if (typeof item.data === "string") {
      try {
        const parsed: unknown = JSON.parse(item.data);
        return typeof parsed === "string" ? parsed : JSON.stringify(parsed);
      } catch { return item.data; }
    }
    return item.data && typeof item.data === "object" ? JSON.stringify(item.data) : "";
  }).filter(Boolean).join("\n");
  return text || "";
}

function normalizeAssets(data: PippitResult): PippitAsset[] {
  const values: Record<string, unknown>[] = [
    ...(data.downloads ?? []),
    ...(data.generated_assets ?? []),
    ...(data.download_urls ?? []).map(url => ({ url })),
  ];
  const seen = new Set<string>();
  return values.flatMap((asset, index) => {
    const url = [asset.download_url, asset.url, asset.uri].find(value => typeof value === "string" && /^https?:\/\//i.test(value)) as string | undefined;
    if (!url || seen.has(url)) return [];
    seen.add(url);
    const mime = String(asset.mime ?? asset.format ?? "").toLowerCase();
    const extension = url.split(/[?#]/, 1)[0]?.split(".").at(-1)?.toLowerCase() ?? "";
    const path = String(asset.path ?? "").toLowerCase();
    const kind = mime.startsWith("video/") || ["mp4", "mov", "webm"].includes(extension) || path.includes("video") ? "video" : "image";
    const normalizedMime = mime.includes("/") ? mime : kind === "video" ? ({ mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm" } as Record<string, string>)[mime] || "video/mp4" : ({ png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" } as Record<string, string>)[mime] || "image/jpeg";
    return [{ url, name: String(asset.name ?? asset.caption ?? `${kind === "video" ? "视频" : "图片"} ${index + 1}`), mime: normalizedMime, kind, assetId: String(asset.pippit_asset_id ?? asset.asset_id ?? "") }];
  });
}
</script>

<style scoped lang="scss">
.pippitCreator {
  display: grid;
  gap: 16px;

  .capabilityGrid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .capabilityItem {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    min-height: 40px;
    padding: 8px 10px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: var(--el-border-radius-base);
    color: var(--el-text-color-secondary);
    font-size: 12px;

    strong { color: var(--el-text-color-primary); font-weight: 500; text-align: right; }
  }

  .capabilityNote { margin: -4px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }

  .referenceHeader, .runStatusHeader, .dialogFooter {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .referenceHeader > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
  .referenceHeader span, .dialogFooter > span { color: var(--el-text-color-secondary); font-size: 12px; }
  .referenceList { display: grid; gap: 6px; }
  .referenceItem { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .referenceName { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .runStatus { display: grid; gap: 12px; padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: var(--el-border-radius-base); }
  .latestMessage { max-height: 180px; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.6; }
  .resultAssets { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
  .resultAsset { display: grid; gap: 6px; min-width: 0; }
  .resultAsset video, .resultAsset :deep(.el-image) { width: 100%; height: 144px; border-radius: 8px; background: var(--el-fill-color-light); object-fit: contain; }
  .resultAsset > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--el-text-color-secondary); font-size: 12px; }
  .replyBox { display: grid; justify-items: end; gap: 8px; }
  .connectionError { margin-top: 2px; }

  @media (max-width: 560px) {
    .capabilityGrid { grid-template-columns: 1fr; }
    .dialogFooter { align-items: flex-end; }
  }
}
</style>
