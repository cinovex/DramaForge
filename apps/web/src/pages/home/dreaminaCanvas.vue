<template>
  <section class="dreaminaCanvasPage" aria-label="即梦生成">
    <header><div><h1>即梦生成</h1><p>{{ localProject ? `为「${localProject.name}」连接即梦生成服务` : '授权后，在我们的项目里选择模型生成图片和视频' }}</p></div><el-button round :loading="busy" @click="refreshStatus">检查连接</el-button></header>
    <div class="connectionBar"><span :class="{ connected: connection?.loggedIn }">● {{ connection?.loggedIn ? '即梦账号已授权' : connection ? '尚未授权' : '正在检查连接' }}</span><small v-if="connection?.version">工具版本 {{ connection.version }}</small></div>
    <div v-if="connection && !connection.loggedIn" class="canvasToolbar"><el-button round :loading="busy" @click="authorize">连接即梦账号</el-button><a v-if="authorizationUrl" :href="safeUrl(authorizationUrl)" target="_blank" rel="noopener noreferrer">打开官方授权页 ↗</a></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" showIcon />
    <div class="linkedCanvas"><div><strong>在项目中选择即梦模型生成</strong><p>进入制作资产库或剧集编辑器，在模型菜单选择“即梦”，确认报价后提交。生成结果保存到我们的项目；无需操作官网画布。</p><p>使用当前授权账号权益；仅支持工具实际返回的模型。模型目录可读取不代表账号具备生成权限。</p></div><el-button round @click="router.push(localProjectId ? `/workspace?dramaforgeProjectId=${localProjectId}` : '/home?section=projects')">打开项目</el-button></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onScopeDispose, ref } from "vue";
import { useRouter } from "vue-router";


const props = defineProps<{ localProjectId?: number }>();
const router = useRouter();
const connection = ref<{ installed: boolean; loggedIn: boolean; version: string; authPending?: boolean }>();
const authorizationUrl = ref("");
let authorizationTimer: ReturnType<typeof setTimeout> | undefined;
onScopeDispose(() => { if (authorizationTimer) clearTimeout(authorizationTimer); });
const localProject = ref<{ name: string }>();
const busy = ref(false);
const error = ref("");
function apiUrl(path: string) { return new URL(`api/${path}`, `${window.location.origin}/`).toString(); }
function safeUrl(value: string) { try { const url = new URL(value); return url.protocol === "https:" && url.hostname === "jimeng.jianying.com" ? url.href : undefined; } catch { return undefined; } }
async function request(path: string, options?: RequestInit) {
  const response = await fetch(apiUrl(path), options);
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;

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
onMounted(async () => {
  await refreshStatus();
  if (props.localProjectId) {
    try { localProject.value = await request(`projects/${props.localProjectId}`); }
    catch (cause) { error.value = cause instanceof Error ? cause.message : "项目读取失败"; }
  }
});
</script>

<style scoped lang="scss">
.dreaminaCanvasPage { max-width: 1200px; margin: 36px auto; color: var(--el-text-color-primary); > header { display: flex; align-items: center; justify-content: space-between; gap: 20px; h1 { font-size: 28px; font-weight: 500; margin: 0 0 12px; } p { font-size: 13px; color: var(--el-text-color-secondary); } } .connectionBar { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; padding: 18px 0; font-size: 13px; .connected { color: var(--el-color-success); } small, .linkedName { color: var(--el-text-color-secondary); } } .canvasToolbar { display: flex; gap: 12px; margin: 24px 0; } .pageHint { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.8; } .cloudCanvasGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; article { border: 1px solid var(--el-border-color-lighter); border-radius: 20px; padding: 24px; background: var(--el-bg-color); h2 { font-size: 16px; font-weight: 500; margin: 20px 0 12px; } } } .canvasActions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 12px; a { color: var(--el-color-primary); } } .linkedCanvas { display: flex; flex-wrap: wrap; align-items: center; gap: 18px; padding: 20px; border: 1px solid var(--el-border-color); border-radius: 16px; margin-top: 18px; p { color: var(--el-text-color-secondary); font-size: 12px; } .openCanvasLink { margin-left: auto; color: var(--el-color-primary); font-size: 13px; } } .cloudNodes { margin-top: 32px; h2 { font-size: 18px; font-weight: 500; } } .cloudNode { display: flex; gap: 20px; padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); font-size: 13px; strong { flex: 1; font-weight: 500; } span, small { color: var(--el-text-color-secondary); } } }
</style>
