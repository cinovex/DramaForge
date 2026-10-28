<template>
  <article class="productionMedia" :class="{ selected, hasAudio: data.audioUrl }">
    <header><span>{{ data.category }}</span><small>{{ data.url ? '已生成' : data.running ? '生成中' : '待生成' }}</small></header>
    <div class="mediaPreview">
      <video v-if="data.kind === 'video' && data.url" class="nodrag nopan nowheel" :src="data.url" controls preload="metadata" @pointerdown.stop />
      <img v-else-if="data.url || data.poster" :src="data.url || data.poster" :alt="data.label" loading="lazy" />
      <div v-else class="pendingMedia"><icon-movie v-if="data.kind === 'video'" :size="34" /><icon-photo v-else :size="34" /><span>{{ data.kind === 'video' ? '视频待生成' : '参考图待生成' }}</span></div>
      <span v-if="data.duration" class="duration">{{ data.duration }} 秒</span>
    </div>
    <audio v-if="data.audioUrl" class="nodrag nopan nowheel" :src="data.audioUrl" controls preload="metadata" @pointerdown.stop />
    <h3 :title="data.label">{{ data.label }}</h3>
    <p :title="data.prompt">{{ data.prompt || '专用提示词尚未完成' }}</p>
    <button type="button" class="nodrag nopan" @click.stop="openDetails">{{ data.kind === 'video' ? '编辑分镜与生成' : '提示词与生成设置' }} <span>↗</span></button>
  </article>
</template>
<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core';
import { IconMovie, IconPhoto } from '@tabler/icons-vue';
const props = defineProps<NodeProps>();
function openDetails() { window.dispatchEvent(new CustomEvent('dramaforge:open-production', { detail: { projectId: props.data.dramaforgeProjectId, kind: props.data.targetKind, id: props.data.targetId, episode: props.data.episode, variant: props.data.referenceVariant } })); }
</script>
<style scoped lang="scss">
.productionMedia { width: 250px; height: 330px; box-sizing: border-box; padding: 10px; border: 1px solid var(--el-border-color-lighter); border-radius: 18px; background: var(--el-bg-color-overlay); color: var(--el-text-color-primary); overflow: hidden; &.hasAudio .mediaPreview { height: 122px; } > audio { width: 100%; height: 36px; margin-top: 8px; } &.selected { outline: 2px solid var(--el-color-primary); } header { display: flex; align-items: center; justify-content: space-between; height: 24px; margin-bottom: 8px; font-size: 11px; color: var(--el-text-color-secondary); small { font-size: 10px; padding: 3px 7px; border-radius: 10px; background: var(--el-fill-color); } } .mediaPreview { position: relative; height: 166px; border-radius: 11px; overflow: hidden; background: var(--el-fill-color-light); img, video { width: 100%; height: 100%; object-fit: contain; } .pendingMedia { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; height: 100%; color: var(--el-text-color-placeholder); font-size: 11px; } .duration { position: absolute; left: 8px; bottom: 8px; padding: 3px 6px; border-radius: 5px; color: white; background: rgb(0 0 0 / 55%); font-size: 10px; pointer-events: none; } } h3 { margin: 10px 0 5px; font-size: 13px; line-height: 20px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } p { font-size: 11px; color: var(--el-text-color-secondary); margin: 0 0 10px; height: 30px; line-height: 15px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; } button { display: flex; align-items: center; justify-content: space-between; width: 100%; height: 28px; padding: 0 9px; border: 0; border-radius: 8px; color: inherit; background: var(--el-fill-color); font: inherit; font-size: 11px; cursor: pointer; &:hover { background: var(--el-fill-color-dark); } } }
</style>
