<template>
  <section class="assetLibrary">
    <h1>资产库</h1>
    <nav class="libraryTabs" aria-label="资产分类"><button v-for="tab in categories" :key="tab.id" :class="{ active: category === tab.id }" @click="category = tab.id">{{ tab.label }}</button></nav>
    <div class="libraryToolbar">
      <button v-for="item in mediaTypes" :key="item.id" :class="{ active: mediaType === item.id }" @click="mediaType = item.id">{{ item.label }}</button>
      <button @click="descending = !descending">{{ descending ? '时间 ↓' : '时间 ↑' }}</button>
      <button @click="listView = !listView">{{ listView ? '网格视图' : '列表视图' }}</button>
      <el-input v-model="query" placeholder="搜索素材或项目" clearable aria-label="搜索素材" />
      <el-button :loading="loading" @click="loadAssets">刷新</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-if="loading" role="status">正在读取项目素材…</div>
    <div v-else-if="!filtered.length" class="libraryEmpty">{{ query ? '没有匹配的素材' : '此分类暂无素材；项目生成的角色、场景、关键帧与视频会出现在这里。' }}</div>
    <div class="assetGrid" :class="{ listView }">
      <article v-for="item in filtered" :key="item.id" class="assetCard">
        <div class="assetPreview"><video v-if="item.kind === 'video'" :src="item.url" controls preload="metadata" /><img v-else :src="item.url" :alt="item.name" loading="lazy" /></div>
        <div class="assetInfo"><strong :title="item.name">{{ item.name }}</strong><small>{{ item.projectName }}</small>
          <div class="assetActions"><a :href="item.url" target="_blank" rel="noopener noreferrer">打开素材</a><button @click="$emit('openProject', item.projectId)">进入画布</button><button v-if="item.prompt" @click="copyPrompt(item.prompt)">复制提示词</button></div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
type MediaAsset = { id: string; url: string; name: string; kind: string; category: string; projectId: number; projectName: string; prompt: string; createdAt: string };
defineEmits<{ openProject: [id: number] }>();
const categories = [{ id: "all", label: "全部素材" }, { id: "works", label: "作品" }, { id: "characters", label: "角色" }, { id: "scenes", label: "场景" }, { id: "props", label: "道具" }];
const mediaTypes = [{ id: "all", label: "全部" }, { id: "image", label: "图片" }, { id: "video", label: "视频" }, { id: "audio", label: "音频" }];
const category = ref("all");
const mediaType = ref("all");
const query = ref("");
const descending = ref(true);
const listView = ref(false);
const loading = ref(false);
const error = ref("");
const assets = ref<MediaAsset[]>([]);
const filtered = computed(() => assets.value.filter(item => (category.value === "all" || item.category === category.value) && (mediaType.value === "all" || item.kind === mediaType.value) && `${item.name} ${item.projectName}`.toLowerCase().includes(query.value.toLowerCase())).sort((a, b) => (descending.value ? -1 : 1) * a.createdAt.localeCompare(b.createdAt)));
async function loadAssets() {
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch(new URL("api/library", `${window.location.origin}/`));
    if (!response.ok) throw new Error("素材读取失败，请检查项目服务是否启动");
    const result = await response.json();
    assets.value = result.items;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "素材读取失败"; }
  finally { loading.value = false; }
}
async function copyPrompt(text: string) {
  try { await navigator.clipboard.writeText(text); ElMessage.success("提示词已复制"); }
  catch { ElMessage.error("无法复制，请允许浏览器使用剪贴板"); }
}
onMounted(loadAssets);
</script>

<style lang="scss" scoped>
.assetLibrary {
  max-width: 1200px; margin: 0 auto; padding: 32px 16px;
  h1 { margin: 0 0 28px; font-size: 28px; font-weight: 600; }
  button { color: inherit; font: inherit; cursor: pointer; }
  .libraryTabs { display: flex; gap: 28px; border-bottom: 1px solid var(--el-border-color-lighter); margin-bottom: 20px;
    button { border: 0; border-bottom: 2px solid transparent; padding: 12px 0; background: transparent; color: var(--el-text-color-secondary); &.active { border-bottom-color: var(--el-text-color-primary); color: var(--el-text-color-primary); } }
  }
  .libraryToolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 24px;
    > button { border: 1px solid var(--el-border-color); padding: 7px 16px; border-radius: 24px; background: transparent; &.active { background: var(--el-fill-color-dark); } }
    .el-input { max-width: 250px; margin-left: auto; }
  }
  .libraryEmpty { padding: 70px 20px; text-align: center; color: var(--el-text-color-secondary); }
  .assetGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: 26px;
    &.listView { grid-template-columns: 1fr; .assetCard { display: flex; gap: 20px; } .assetPreview { width: 200px; flex-shrink: 0; } }
  }
  .assetCard { min-width: 0; }
  .assetPreview { aspect-ratio: 16 / 10; padding: 10px; box-sizing: border-box; background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter); border-radius: 24px; overflow: hidden;
    img, video { width: 100%; height: 100%; object-fit: contain; border-radius: 16px; }
  }
  .assetInfo { padding: 12px 4px; strong, small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } small { color: var(--el-text-color-secondary); margin-top: 6px; } }
  .assetActions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; font-size: 12px;
    a, button { color: var(--el-text-color-regular); text-decoration: none; background: transparent; border: 0; padding: 0; &:hover { color: var(--el-color-primary); } }
  }
}
</style>
