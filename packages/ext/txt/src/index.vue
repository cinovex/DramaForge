<template>
  <section class="textDocument" @keydown="onKeydown">
    <header class="textToolbar">
      <el-button text size="small" @click="openSearch(false)">查找</el-button>
      <el-button text size="small" @click="openSearch(true)">替换</el-button>
    </header>
    <div v-if="searchVisible" class="searchPanel">
      <div class="searchRow">
        <el-input ref="searchInput" v-model="query" size="small" placeholder="查找文本" aria-label="查找文本" @keydown.enter.prevent="findNext(($event as KeyboardEvent).shiftKey ? -1 : 1)" />
        <el-checkbox v-model="caseSensitive" size="small">区分大小写</el-checkbox>
        <span class="searchStatus" aria-live="polite">{{ matches.length ? `${selectedIndex + 1} / ${matches.length}` : '无匹配' }}</span>
        <el-button text size="small" :disabled="!matches.length" @click="findNext(-1)">上一个</el-button>
        <el-button text size="small" :disabled="!matches.length" @click="findNext(1)">下一个</el-button>
        <el-button text size="small" aria-label="关闭查找" @click="searchVisible = false">关闭</el-button>
      </div>
      <div v-if="replaceVisible" class="searchRow">
        <el-input v-model="replacement" size="small" placeholder="替换为" aria-label="替换为" @keydown.enter.prevent="replaceCurrent" />
        <el-button size="small" :disabled="context.loading || !matches.length" @click="replaceCurrent">替换</el-button>
        <el-button size="small" :disabled="context.loading || !matches.length" @click="replaceAll">全部替换</el-button>
      </div>
    </div>
    <textarea ref="textarea" class="textEditor" :value="context.text" :disabled="context.loading" :aria-label="context.resource.label" :spellcheck="false"
      :wrap="context.config.wordWrap === false ? 'off' : 'soft'" :style="{ fontSize: `${fontSize}px` }" @input="updateText" />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { ElButton, ElCheckbox, ElInput, type InputInstance } from "element-plus";
import type { ExtContext } from "@toonflow/ext-scaffold/runtime";

const props = defineProps<{ context: ExtContext }>();
const textarea = ref<HTMLTextAreaElement>();
const searchInput = ref<InputInstance>();
const searchVisible = ref(false);
const replaceVisible = ref(false);
const query = ref("");
const replacement = ref("");
const caseSensitive = ref(false);
const selectedIndex = ref(-1);
const fontSize = computed(() => {
  const size = props.context.config.fontSize;
  return typeof size === "number" && size >= 10 && size <= 32 ? size : 14;
});
const matches = computed(() => {
  if (!searchVisible.value || !props.context.active || !query.value) return [];
  // 转义后仅作字面量查找，索引来自原文，避免 Unicode 大小写转换改变字符长度。
  const pattern = new RegExp(query.value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), caseSensitive.value ? "g" : "gi");
  return Array.from(props.context.text.matchAll(pattern), match => ({ start: match.index, end: match.index + match[0].length }));
});
watch(matches, () => { selectedIndex.value = -1; });
watch(() => props.context.location, async location => {
  if (!location) return;
  await nextTick();
  if (props.context.location !== location || !textarea.value) return;
  const lines = textarea.value.value.split("\n");
  const row = Math.min(Math.max(0, location.line - 1), lines.length - 1);
  const start = lines.slice(0, row).reduce((length, line) => length + line.length + 1, 0) + Math.min(Math.max(0, location.column - 1), lines[row]!.length);
  textarea.value?.focus();
  textarea.value?.setSelectionRange(start, start + location.query.length);
  if (textarea.value) textarea.value.scrollTop = Math.max(0, row * fontSize.value * 1.7 - textarea.value.clientHeight / 2);
}, { immediate: true });

function updateText(event: Event) {
  props.context.updateText((event.target as HTMLTextAreaElement).value);
}
async function openSearch(replace: boolean) {
  searchVisible.value = true;
  replaceVisible.value = replace;
  const input = textarea.value;
  const selected = input && input.value.slice(input.selectionStart, input.selectionEnd);
  if (selected && !selected.includes("\n")) query.value = selected;
  await nextTick();
  searchInput.value?.focus();
}
function findNext(direction = 1) {
  if (!matches.value.length || !textarea.value) return;
  selectedIndex.value = selectedIndex.value < 0 ? (direction < 0 ? matches.value.length - 1 : 0)
    : (selectedIndex.value + direction + matches.value.length) % matches.value.length;
  const match = matches.value[selectedIndex.value]!;
  // textarea 的偏移以规范为 LF 的显示文本为准；替换仍使用原始偏移，保留其余 CRLF。
  const before = props.context.text.slice(0, match.start).replace(/\r\n?/g, "\n");
  const selected = props.context.text.slice(match.start, match.end).replace(/\r\n?/g, "\n");
  textarea.value.focus();
  textarea.value.setSelectionRange(before.length, before.length + selected.length);
  const line = before.split("\n").length - 1;
  textarea.value.scrollTop = Math.max(0, line * fontSize.value * 1.7 - textarea.value.clientHeight / 2);
}
async function replaceCurrent() {
  if (props.context.loading || !matches.value.length) return;
  const match = matches.value[Math.max(selectedIndex.value, 0)]!;
  props.context.updateText(props.context.text.slice(0, match.start) + replacement.value + props.context.text.slice(match.end));
  await nextTick();
  const next = matches.value.findIndex(item => item.start >= match.start + replacement.value.length);
  selectedIndex.value = next < 0 ? -1 : next - 1;
  findNext();
}
function replaceAll() {
  if (props.context.loading || !matches.value.length) return;
  let position = 0;
  let result = "";
  for (const match of matches.value) {
    result += props.context.text.slice(position, match.start) + replacement.value;
    position = match.end;
  }
  props.context.updateText(result + props.context.text.slice(position));
}
function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && ["f", "h"].includes(event.key.toLowerCase())) {
    event.preventDefault(); event.stopPropagation();
    void openSearch(event.key.toLowerCase() === "h");
  } else if (event.key === "Escape" && searchVisible.value) {
    event.preventDefault(); event.stopPropagation(); searchVisible.value = false; textarea.value?.focus();
  }
}
</script>

<style scoped>
.textDocument {
  display: flex; flex-direction: column; height: 100%; min-height: 0;
  .textToolbar { display: flex; padding: 4px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
  .searchPanel {
    display: flex; flex-direction: column; gap: 6px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-lighter);
    .searchRow { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; :deep(.el-input) { flex: 1; min-width: 150px; } }
    .searchStatus { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
  }
  .textEditor {
  box-sizing: border-box;
  display: block;
  width: 100%;
  flex: 1;
  min-height: 0;
  padding: 20px 24px;
  resize: none;
  border: 0;
  outline: none;
  color: var(--el-text-color-primary);
  background: transparent;
  font: 14px/1.7 Consolas, "SFMono-Regular", monospace;
  tab-size: 2;
  }
}
</style>
