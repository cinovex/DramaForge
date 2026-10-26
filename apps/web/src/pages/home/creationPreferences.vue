<template>
  <div class="creationPreferences">
    <el-popover placement="top-start" width="min(480px, calc(100vw - 32px))" trigger="click" :disabled="disabled">
      <template #reference><el-button text :disabled="disabled" aria-label="选择创作风格"><icon-palette :size="17" />{{ selectedStyleName }}⌄</el-button></template>
      <section class="styleLibrary" aria-label="风格库"><header><strong>风格库</strong><span>本地风格预设</span></header><el-input v-model="search" placeholder="搜索风格" clearable aria-label="搜索风格" /><nav><button v-for="item in ['全部', '真人实拍', '2D', '3D']" :key="item" type="button" :class="{ active: category === item }" @click="category = item">{{ item }}</button></nav>
        <div class="styleGrid"><button v-for="style in filteredStyles" :key="style.id" type="button" :class="{ selected: modelValue.styleId === style.id }" :aria-pressed="modelValue.styleId === style.id" @click="update('styleId', style.id)"><svg viewBox="0 0 180 106" aria-hidden="true"><defs><linearGradient :id="`stylePreview-${style.id}`" x2="0" y2="1"><stop :stop-color="style.colors[0]" /><stop offset="1" :stop-color="style.colors[1]" /></linearGradient></defs><rect width="180" height="106" :fill="`url(#stylePreview-${style.id})`" /><circle cx="135" cy="28" r="16" :fill="style.colors[0]" opacity="0.8" /><path d="M0 82L43 39L91 80L125 55L180 89V106H0Z" :fill="style.colors[2]" opacity="0.45" /><path d="M65 106L69 68Q80 60 91 68L96 106M75 58A9 11 0 1 0 75 36A9 11 0 1 0 75 58" :fill="style.colors[2]" /><path d="M106 106L111 75Q120 69 129 75L135 106M115 65A8 10 0 1 0 115 45A8 10 0 1 0 115 65" :fill="style.colors[2]" opacity="0.8" /></svg><strong>{{ style.name }}</strong><small>{{ style.description }}</small></button></div>
        <button type="button" class="customStyleButton" @click="update('styleId', 'custom')">自定义风格 →</button><el-input v-if="modelValue.styleId === 'custom'" :modelValue="modelValue.customStyle" type="textarea" maxlength="2000" placeholder="填写自己的画风、色彩、摄影和材质要求" @update:modelValue="update('customStyle', $event)" /><p>缩略图为色调示意；所选风格作为创作要求保存并传递。</p><p v-if="error" role="alert">{{ error }}</p>
      </section>
    </el-popover>
    <el-select class="ratioChoice" :modelValue="modelValue.aspectRatio" :disabled="disabled" aria-label="创作比例" @change="update('aspectRatio', $event)"><el-option v-for="ratio in ['9:16', '16:9', '1:1', '3:4', '4:3', '21:9']" :key="ratio" :value="ratio" :label="ratio" /></el-select>
    <el-select v-if="mode === 'writer'" class="episodeChoice" :modelValue="modelValue.episodes" :disabled="disabled" aria-label="剧本集数" @change="update('episodes', $event)"><el-option v-for="count in [1, 3, 5, 10, 20, 30, 50, 100]" :key="count" :value="count" :label="`${count} 集`" /></el-select>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { IconPalette } from '@tabler/icons-vue';
const props = defineProps<{ modelValue: { styleId: string; customStyle: string; aspectRatio: string; episodes: number }; mode: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: typeof props.modelValue] }>();
type StylePreset = { id: string; name: string; category: string; description: string; colors: string[] };
const styles = ref<StylePreset[]>([]);
const category = ref('全部');
const search = ref('');
const error = ref('');
const selectedStyleName = computed(() => props.modelValue.styleId === 'none' ? '风格库' : props.modelValue.styleId === 'custom' ? '自定义风格' : styles.value.find(item => item.id === props.modelValue.styleId)?.name || '风格库');
const filteredStyles = computed(() => styles.value.filter(item => (category.value === '全部' || item.category === category.value || item.id === 'none') && `${item.name}${item.description}`.includes(search.value.trim())));
function update(key: string, value: string | number) { emit('update:modelValue', { ...props.modelValue, [key]: value }); }
onMounted(async () => { try { const response = await fetch(new URL('api/pippit/creative-options', `${window.location.origin}/`)); if (!response.ok) throw new Error('风格库读取失败'); styles.value = (await response.json()).styles; } catch (cause) { error.value = cause instanceof Error ? cause.message : '风格库不可用'; } });
</script>

<style scoped lang="scss">
.creationPreferences { display: flex; align-items: center; gap: 8px; .ratioChoice { width: 94px; } .episodeChoice { width: 92px; } :deep(.el-select__wrapper) { box-shadow: none; background: transparent; } }
.styleLibrary { header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; span { font-size: 11px; color: var(--el-text-color-secondary); } } nav { display: flex; gap: 18px; margin: 16px 0; button { padding: 6px 0; border: 0; border-bottom: 2px solid transparent; color: inherit; background: none; cursor: pointer; &.active { border-color: var(--el-color-primary); } } } .styleGrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; max-height: min(260px, 40vh); overflow-y: auto; button { display: flex; flex-direction: column; gap: 6px; padding: 5px; text-align: left; border: 1px solid transparent; border-radius: 12px; color: inherit; background: none; cursor: pointer; &.selected { border-color: var(--el-color-primary); background: var(--el-fill-color-light); } svg { width: 100%; border-radius: 8px; } strong { font-size: 12px; font-weight: 500; } small { font-size: 10px; color: var(--el-text-color-secondary); } } } .customStyleButton { margin: 14px 0; padding: 0; background: none; border: 0; color: var(--el-color-primary); cursor: pointer; } p { font-size: 11px; color: var(--el-text-color-secondary); } }
</style>
