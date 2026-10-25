<template>
  <section class="dreaminaCanvasPage" aria-label="即梦画布">
    <header><div><h1>即梦画布</h1><p>{{ localProject ? `为「${localProject.name}」连接即梦官网画布` : '从工作台创建、查看并打开即梦官网画布' }}</p></div><el-button round :loading="busy" @click="refreshStatus">检查连接</el-button></header>
    <div class="connectionBar"><span :class="{ connected: connection?.loggedIn }">● {{ connection?.loggedIn ? '即梦账号已授权' : connection ? '尚未授权' : '正在检查连接' }}</span><small v-if="connection?.version">工具版本 {{ connection.version }}</small><span v-if="linkedCanvas" class="linkedName">已关联：{{ linkedCanvas.name }}</span></div>
    <div v-if="connection && !connection.loggedIn" class="canvasToolbar"><el-button round :loading="busy" @click="authorize">连接即梦账号</el-button><a v-if="authorizationUrl" :href="safeUrl(authorizationUrl)" target="_blank" rel="noopener noreferrer">打开官方授权页 ↗</a></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" showIcon />
    <div v-if="linkedCanvas" class="linkedCanvas"><div><strong>{{ linkedCanvas.name }}</strong><p>此关联不会替换本地画布，也不会自动复制两边的节点。</p></div><a :href="safeUrl(linkedCanvas.webUrl)" target="_blank" rel="noopener noreferrer" class="openCanvasLink">打开即梦画布 ↗</a><el-button v-if="localProjectId" round @click="router.push(`/workspace?dramaforgeProjectId=${localProjectId}`)">返回本地项目</el-button></div>
    <div class="canvasToolbar"><el-button round :loading="busy" :disabled="!connection?.loggedIn" @click="loadCanvases(false)">载入画布</el-button><el-button type="primary" round :disabled="!connection?.loggedIn || busy || accessDenied" @click="createVisible = true">创建即梦画布</el-button></div>
    <p v-if="!loaded && !error" class="pageHint">点击“载入画布”读取当前账号可访问的官网画布。</p>
    <div class="cloudCanvasGrid"><article v-for="canvas in canvases" :key="canvas.projectId"><icon-layout-grid :size="30" :strokeWidth="1.2" /><h2>{{ canvas.name }}</h2><div class="canvasActions"><a :href="safeUrl(canvas.webUrl)" target="_blank" rel="noopener noreferrer">官网打开 ↗</a><el-button text :disabled="busy" @click="readNodes(canvas)">查看节点</el-button><el-button v-if="localProjectId" text :disabled="busy" @click="linkCanvas(canvas)">关联当前项目</el-button></div></article></div>
    <p v-if="loaded && !canvases.length && !error" class="pageHint">当前账号还没有返回可访问的画布，可以创建一张新画布。</p>
    <el-button v-if="nextCursor" round :loading="busy" @click="loadCanvases(true)">加载更多画布</el-button>
    <section v-if="selectedCanvas" class="cloudNodes"><h2>{{ selectedCanvas.name }} · 节点</h2><div v-for="node in nodes" :key="node.nodeId" class="cloudNode"><span>{{ nodeLabels[node.type] || node.type }}</span><strong>{{ node.title || '未命名节点' }}</strong><small>{{ node.status }}</small></div><p v-if="!nodes.length && !busy">这张画布没有返回节点。</p><el-button v-if="nodesHaveMore && nodes.length < 1000" :loading="busy" @click="readNodes(selectedCanvas, true)">加载更多节点</el-button></section>
    <el-dialog v-model="createVisible" title="创建即梦画布" width="min(460px, calc(100vw - 32px))" :closeOnClickModal="!busy"><el-input v-model="canvasName" maxlength="120" placeholder="画布名称" aria-label="画布名称" :disabled="busy || !!createRequestId" /><p class="pageHint">只创建空白画布，不生成素材；创建后可在即梦官网继续编辑。未确认结果的创建会保留名称和编号，重试不会另起一张画布。</p><template #footer><el-button :disabled="busy" @click="createVisible = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!canvasName.trim()" @click="createCanvas">创建</el-button></template></el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconLayoutGrid } from "@tabler/icons-vue";
const props = defineProps<{ localProjectId?: number }>();
const router = useRouter();
type CloudCanvas = { projectId: string; name: string; webUrl: string };
type CloudNode = { nodeId: string; title: string; type: string; status: string };
const connection = ref<{ installed: boolean; loggedIn: boolean; version: string; authPending?: boolean }>();
const authorizationUrl = ref("");
let authorizationTimer: ReturnType<typeof setTimeout> | undefined;
onScopeDispose(() => { if (authorizationTimer) clearTimeout(authorizationTimer); });
const localProject = ref<{ name: string; generation_settings?: { dreaminaCanvas?: CloudCanvas } }>();
const linkedCanvas = computed(() => localProject.value?.generation_settings?.dreaminaCanvas);
const canvases = ref<CloudCanvas[]>([]);
const selectedCanvas = ref<CloudCanvas>();
const nodes = ref<CloudNode[]>([]);
const nodesHaveMore = ref(false);
const nextCursor = ref("");
const busy = ref(false);
const error = ref("");
const accessDenied = ref(false);
const loaded = ref(false);
const createVisible = ref(false);
const canvasName = ref("");
const createRequestId = ref("");
const pendingCreateKey = "dreaminaCanvasPendingCreate";
try {
  const pending = JSON.parse(localStorage.getItem(pendingCreateKey) || "null");
  if (pending?.requestId && pending?.name) { createRequestId.value = pending.requestId; canvasName.value = pending.name; }
} catch { /* A damaged local draft must not prevent opening the page. */ }
const nodeLabels: Record<string, string> = { text: "文本", image: "图片", video: "视频", audio: "音频", element: "主体", timeline: "时间轴" };
function apiUrl(path: string) { return new URL(`api/${path}`, `${window.location.origin}/`).toString(); }
function safeUrl(value: string) { try { const url = new URL(value); return url.protocol === "https:" && url.hostname === "jimeng.jianying.com" ? url.href : undefined; } catch { return undefined; } }
async function request(path: string, options?: RequestInit) {
  const response = await fetch(apiUrl(path), options);
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    if (response.status === 403) accessDenied.value = true;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "即梦请求失败");
  }
  return result;
}
async function refreshStatus() {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try { connection.value = await request("dreamina-canvas/status"); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "连接检查失败"; }
  finally { busy.value = false; }
  if (connection.value?.authPending && !connection.value.loggedIn) authorizationTimer = setTimeout(() => void refreshStatus(), 5000);
}
async function authorize() {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try { const data = await request("dreamina-canvas/authorize", { method: "POST" }); authorizationUrl.value = data.url || ""; if (safeUrl(authorizationUrl.value)) window.open(authorizationUrl.value, "_blank", "noopener,noreferrer"); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "授权启动失败"; }
  finally { busy.value = false; }
  await refreshStatus();
}
async function loadCanvases(more: boolean) {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try {
    const data = await request(`dreamina-canvas/canvases${more && nextCursor.value ? `?cursor=${encodeURIComponent(nextCursor.value)}` : ""}`);
    const items = data.items as CloudCanvas[];
    canvases.value = [...new Map([...(more ? canvases.value : []), ...items].map(item => [item.projectId, item])).values()];
    nextCursor.value = data.hasMore ? data.nextCursor || "" : "";
    accessDenied.value = false; loaded.value = true;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "读取画布失败"; }
  finally { busy.value = false; }
}
async function createCanvas() {
  if (busy.value || !canvasName.value.trim()) return;
  busy.value = true; error.value = "";
  createRequestId.value ||= crypto.randomUUID();
  localStorage.setItem(pendingCreateKey, JSON.stringify({ name: canvasName.value.trim(), requestId: createRequestId.value }));
  try {
    const data = await request("dreamina-canvas/canvases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: canvasName.value.trim(), requestId: createRequestId.value }) });
    const canvas = data.project as CloudCanvas;
    canvases.value = [canvas, ...canvases.value.filter(item => item.projectId !== canvas.projectId)];
    createVisible.value = false; canvasName.value = ""; createRequestId.value = ""; loaded.value = true;
    localStorage.removeItem(pendingCreateKey);
    if (safeUrl(canvas.webUrl)) window.open(canvas.webUrl, "_blank", "noopener,noreferrer");
    ElMessage.success("即梦画布已创建");
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "创建失败；再次提交将复用原编号"; }
  finally { busy.value = false; }
}
async function readNodes(canvas: CloudCanvas, more = false) {
  if (busy.value) return;
  busy.value = true; error.value = "";
  if (!more) { selectedCanvas.value = canvas; nodes.value = []; }
  try { const data = await request(`dreamina-canvas/canvases/${encodeURIComponent(canvas.projectId)}/nodes?offset=${more ? nodes.value.length : 0}`); nodes.value = [...(more ? nodes.value : []), ...data.items]; nodesHaveMore.value = !!data.hasMore; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "读取节点失败"; }
  finally { busy.value = false; }
}
async function linkCanvas(canvas: CloudCanvas) {
  if (!props.localProjectId || busy.value) return;
  if (linkedCanvas.value && linkedCanvas.value.projectId !== canvas.projectId) {
    try { await ElMessageBox.confirm("是否将当前项目关联到这张即梦画布？原本的两张画布内容都不会删除。", "更换关联"); } catch { return; }
  }
  busy.value = true; error.value = "";
  try { await request(`dreamina-canvas/projects/${props.localProjectId}/link`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(canvas) }); localProject.value = await request(`projects/${props.localProjectId}`); ElMessage.success("已关联当前项目"); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "关联失败"; }
  finally { busy.value = false; }
}
onMounted(async () => {
  await refreshStatus();
  if (props.localProjectId) { try { localProject.value = await request(`projects/${props.localProjectId}`); } catch (cause) { error.value = cause instanceof Error ? cause.message : "本地项目读取失败"; } }
});
</script>

<style scoped lang="scss">
.dreaminaCanvasPage { max-width: 1200px; margin: 36px auto; color: var(--el-text-color-primary); > header { display: flex; align-items: center; justify-content: space-between; gap: 20px; h1 { font-size: 28px; font-weight: 500; margin: 0 0 12px; } p { font-size: 13px; color: var(--el-text-color-secondary); } } .connectionBar { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; padding: 18px 0; font-size: 13px; .connected { color: var(--el-color-success); } small, .linkedName { color: var(--el-text-color-secondary); } } .canvasToolbar { display: flex; gap: 12px; margin: 24px 0; } .pageHint { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.8; } .cloudCanvasGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; article { border: 1px solid var(--el-border-color-lighter); border-radius: 20px; padding: 24px; background: var(--el-bg-color); h2 { font-size: 16px; font-weight: 500; margin: 20px 0 12px; } } } .canvasActions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 12px; a { color: var(--el-color-primary); } } .linkedCanvas { display: flex; flex-wrap: wrap; align-items: center; gap: 18px; padding: 20px; border: 1px solid var(--el-border-color); border-radius: 16px; margin-top: 18px; p { color: var(--el-text-color-secondary); font-size: 12px; } .openCanvasLink { margin-left: auto; color: var(--el-color-primary); font-size: 13px; } } .cloudNodes { margin-top: 32px; h2 { font-size: 18px; font-weight: 500; } } .cloudNode { display: flex; gap: 20px; padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); font-size: 13px; strong { flex: 1; font-weight: 500; } span, small { color: var(--el-text-color-secondary); } } }
</style>
