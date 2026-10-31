<template>
  <el-dialog v-model="visible" title="Pippit 账号池" width="min(620px, calc(100vw - 32px))" appendToBody @open="loadAccounts">
    <p>后台队列按启用顺序使用账号。只有原任务明确积分不足才接力；超时、网络和查询异常不会切换。每个账号分别上传同一套本地参考资产。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-for="account in accounts" :key="account.id" class="accountRow"><div><strong>{{ account.label }}</strong><small>{{ account.exhausted ? '积分不足 · 充值后可解除标记' : '待使用 · 未预查余额' }}</small></div><el-button size="small" :disabled="busy" @click="updateAccount(account, !account.enabled)">{{ account.enabled ? '停用' : '启用' }}</el-button><el-button v-if="account.exhausted" size="small" :disabled="busy" @click="updateAccount(account, account.enabled, true)">已充值，解除标记</el-button></div>
    <el-form labelPosition="top" @submit.prevent="addAccount"><el-form-item label="账号名称"><el-input v-model="label" maxlength="80" placeholder="例如：账号 B" /></el-form-item><el-form-item label="Pippit API Key"><el-input v-model="apiKey" type="password" showPassword autocomplete="off" placeholder="只保存在本机，不上传 GitHub" /></el-form-item><el-button type="primary" :loading="busy" :disabled="!label.trim() || !apiKey.trim()" @click="addAccount">加密保存账号</el-button></el-form>
    <p class="accountHint">这里不共享账号积分，也不能保证跨账号生成质量完全一致。旧任务继续使用提交时的账号，停用账号不会取消其远端任务。</p>
  </el-dialog>
</template>
<script setup lang="ts">
import { ref } from "vue";
const visible = defineModel<boolean>({ default: false });
type Account = { id: string; label: string; enabled: boolean; exhausted: boolean };
const accounts = ref<Account[]>([]);
const label = ref("");
const apiKey = ref("");
const busy = ref(false);
const error = ref("");
async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`/api/pippit/accounts${path}`, { method, ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "账号操作失败");
  return data;
}
async function loadAccounts() { try { accounts.value = await request(""); error.value = ""; } catch (cause) { error.value = cause instanceof Error ? cause.message : "读取失败"; } }
async function addAccount() {
  if (busy.value) return;
  busy.value = true;
  try { await request("", "POST", { label: label.value.trim(), apiKey: apiKey.value.trim(), enabled: true }); apiKey.value = ""; label.value = ""; await loadAccounts(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "保存失败"; }
  finally { busy.value = false; }
}
async function updateAccount(account: Account, enabled: boolean, resetCredits = false) {
  busy.value = true;
  try { await request(`/${account.id}`, "PUT", { label: account.label, enabled, resetCredits }); await loadAccounts(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "修改失败"; }
  finally { busy.value = false; }
}
</script>
<style scoped lang="scss">
p { font-size: 13px; line-height: 1.8; color: var(--el-text-color-secondary); }
.accountRow { display: flex; align-items: center; gap: 8px; padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); > div { flex: 1; } small { display: block; margin-top: 6px; color: var(--el-text-color-secondary); } }
.el-form { margin-top: 24px; }
.accountHint { margin-top: 20px; }
</style>
