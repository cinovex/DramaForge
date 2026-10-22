<template>
  <section class="skillLibrary">
    <h1>技能</h1>
    <div class="skillToolbar"><el-input v-model="query" placeholder="搜索已安装技能" clearable aria-label="搜索技能" /><el-button :loading="loading" @click="loadSkills">刷新</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-if="loading" role="status">正在读取技能…</div>
    <p v-else-if="!filtered.length" class="skillEmpty">{{ query ? '没有匹配的技能' : '尚未安装全局技能' }}</p>
    <div class="skillGrid"><article v-if="'pippit 海外创作 视频重制'.includes(query.toLowerCase())" class="skillCard"><span class="skillIcon">✧</span><h2>Pippit 海外创作</h2><p>通过 API 进行创作、视频重制和同会话修改，保存生成素材到资产库。</p><footer><span>{{ pippitConnected === null ? '正在检查连接…' : pippitConnected ? 'API 已连接' : pippitConnectionMessage }}</span><el-button @click="$emit('select', 'pippit-skill')">用于创作</el-button></footer></article><article v-for="skill in filtered" :key="skill.name" class="skillCard"><span class="skillIcon">✧</span><h2>{{ skill.displayName || skill.name }}</h2><p>{{ skill.description }}</p><footer><span>{{ skill.enabled ? '已启用' : '已停用' }}</span><el-button :disabled="!skill.enabled" @click="$emit('select', skill.name)">用于创作</el-button></footer></article></div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import axios from "axios";
defineEmits<{ select: [name: string] }>();
type InstalledSkill = { name: string; displayName: string; description: string; enabled: boolean };
const skills = ref<InstalledSkill[]>([]);
const pippitConnected = ref<boolean | null>(null);
const pippitConnectionMessage = ref("暂时无法连接，请重试");
const query = ref("");
const loading = ref(false);
const error = ref("");
const filtered = computed(() => skills.value.filter(item => item.name !== "pippit-skill").filter(item => `${item.name} ${item.displayName} ${item.description}`.toLowerCase().includes(query.value.toLowerCase())));
async function loadSkills() {
  if (loading.value) return;
  loading.value = true; error.value = "";
  pippitConnected.value = null;
  const statusRequest = fetch(new URL("api/pippit/status", `${window.location.origin}/`)).then(response => response.ok ? response.json() : null).then(result => { pippitConnected.value = result?.connected === true; pippitConnectionMessage.value = typeof result?.message === "string" ? result.message : "暂时无法连接，请重试"; }).catch(() => { pippitConnected.value = false; });
  try {
    const { data } = await axios.get("/api/skills/get");
    if (data.code !== 200 || !Array.isArray(data.data)) throw new Error(data.message || "技能读取失败");
    skills.value = data.data;
  } catch { error.value = "技能读取失败，请检查画布服务是否启动后重试"; }
  finally { await statusRequest; loading.value = false; }
}
onMounted(loadSkills);
</script>

<style lang="scss" scoped>
.skillLibrary {
  max-width: 1200px; margin: 0 auto; padding: 32px 16px;
  h1 { font-size: 28px; margin: 0 0 28px; }
  .skillToolbar { display: flex; gap: 12px; margin-bottom: 28px; .el-input { max-width: 420px; } }
  .skillGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }
  .skillCard { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter); border-radius: 22px; padding: 24px; display: flex; flex-direction: column;
    .skillIcon { font-size: 26px; }
    h2 { font-size: 17px; margin: 18px 0 8px; }
    p { font-size: 13px; color: var(--el-text-color-secondary); line-height: 1.7; overflow-wrap: anywhere; }
    footer { margin-top: auto; padding-top: 20px; display: flex; align-items: center; justify-content: space-between; font-size: 12px; }
  }
  .skillEmpty { padding: 60px 0; color: var(--el-text-color-secondary); }
}
</style>
