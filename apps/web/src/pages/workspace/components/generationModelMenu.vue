<template>
  <el-popover v-model:visible="visible" trigger="click" placement="bottom-end" :width="320" :showArrow="false" :disabled="disabled" popperClass="generationModelPopover">
    <template #reference><button type="button" class="modelMenuTrigger" :disabled="disabled" aria-label="选择生成模型"><icon-sparkles :size="17" /><span>{{ options.find(item => item.id === modelValue)?.label || defaultLabel }}</span><span class="modelMenuChevron">⌄</span></button></template>
    <div class="modelMenuList" role="menu" aria-label="生成模型">
      <button v-for="item in options" :key="item.id" type="button" role="menuitemradio" :aria-checked="modelValue === item.id" @click="selectModel(item.id)"><icon-sparkles :size="24" :strokeWidth="1.4" /><span><strong>{{ item.label }}</strong><small>{{ item.description || item.id }}</small></span><span v-if="modelValue === item.id" class="selectedMark">✓</span></button>
      <button v-if="modelValue" type="button" class="defaultModel" @click="selectModel('')">使用默认模型</button>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { IconSparkles } from "@tabler/icons-vue";
defineProps<{ modelValue: string; options: { id: string; label: string; description?: string }[]; defaultLabel: string; disabled?: boolean }>();
const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();
const visible = ref(false);
function selectModel(value: string) { emit("update:modelValue", value); visible.value = false; }
</script>

<style scoped lang="scss">
.modelMenuTrigger { display: inline-flex; align-items: center; justify-content: center; gap: 8px; max-width: 300px; border: 0; border-radius: 8px; background: transparent; color: var(--el-text-color-primary); padding: 8px; cursor: pointer; font-size: 12px; font-weight: 500; > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } &:hover { background: var(--el-fill-color-light); } &:disabled { opacity: .5; cursor: default; } .modelMenuChevron { color: var(--el-text-color-secondary); } }
.modelMenuList { display: grid; gap: 4px; max-height: 420px; overflow-y: auto; > button { display: flex; align-items: center; gap: 14px; width: 100%; padding: 12px; border: 0; border-radius: 10px; background: transparent; color: var(--el-text-color-primary); text-align: left; cursor: pointer; &:hover { background: var(--el-fill-color-light); } > span { min-width: 0; } strong { display: block; font-size: 13px; font-weight: 600; } small { display: block; margin-top: 5px; font-size: 11px; line-height: 1.5; color: var(--el-text-color-secondary); overflow-wrap: anywhere; } .selectedMark { margin-left: auto; color: var(--el-color-primary); } } .defaultModel { font-size: 11px; color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter); border-radius: 0; } }
</style>
