<template>
  <el-dialog v-model="visible" title="快速打开" width="min(620px, 94vw)" top="12vh" :closeOnClickModal="false" @closed="cancel" @opened="input?.focus()">
    <div class="quickOpen" @keydown.down.prevent="step(1)" @keydown.up.prevent="step(-1)" @keydown.enter.prevent="choose(selected)">
      <el-input ref="input" v-model="query" placeholder="输入文件路径或节点名称" aria-label="快速打开文件" clearable />
      <p class="status" role="status">{{ loading ? '正在读取工作区…' : `已找到 ${entries.length} 个文件与节点` }}{{ results.length > 100 ? '，仅展示前 100 个匹配，请缩小范围' : '' }}</p>
      <el-alert v-if="error" :title="error" type="warning" :closable="false" />
      <div class="resultList" role="listbox" aria-label="快速打开结果">
        <button v-for="(item, index) in results.slice(0, 100)" :key="item.key" class="resultItem" :class="{ selected: selected === index }" role="option" :aria-selected="selected === index" @click="choose(index)">
          <img v-if="icon(item)" :src="icon(item)" alt="" />
          <span class="label">{{ item.selection.label }}</span><small>{{ item.path }}</small>
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import type { InputInstance } from "element-plus";
import useWorkspaceFiles from "@/lib/workspaceFiles";
import { isCanvasFile } from "@/pages/workspace/canvasFile";
import { documentError } from "../documentSession";
import { extensionIcon, listExtensions } from "../extensions";
import type { TreeSelection } from "./fileTree.vue";

type Entry = { key: string; path: string; selection: TreeSelection };
const props = defineProps<{ directory: string }>();
const emit = defineEmits<{ open: [selection: TreeSelection] }>();
const visible = ref(false);
const loading = ref(false);
const query = ref("");
const selected = ref(0);
const error = ref("");
const input = ref<InputInstance>();
const entries = shallowRef<Entry[]>([]);
let controller: AbortController | undefined;
const results = computed(() => {
  const words = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return entries.value.filter(item => words.every(word => `${item.selection.label} ${item.path}`.toLocaleLowerCase().includes(word)))
    .sort((left, right) => Number(right.selection.label.toLocaleLowerCase().startsWith(query.value.toLocaleLowerCase())) - Number(left.selection.label.toLocaleLowerCase().startsWith(query.value.toLocaleLowerCase()))
      || left.path.localeCompare(right.path, "zh-CN", { numeric: true }));
});
watch(query, () => { selected.value = 0; });
function icon(item: Entry) {
  return extensionIcon("filePath" in item.selection
    ? { kind: "file", directory: props.directory, path: item.path, label: item.selection.label }
    : { kind: "canvasNode", directory: props.directory, path: item.path, nodeId: item.selection.nodeId, label: item.selection.label });
}
function cancel() { controller?.abort(); loading.value = false; }
async function open() {
  cancel();
  const request = new AbortController();
  controller = request;
  visible.value = true; loading.value = true; query.value = ""; error.value = ""; selected.value = 0; entries.value = [];
  const files = useWorkspaceFiles(props.directory);
  const pending = [""];
  const found: Entry[] = [];
  let visited = 0;
  try {
    await listExtensions();
    // ACT: 按需扫描并限制 10000 个条目；更大项目可接服务端文件索引，不在浏览器保存全量索引。
    for (let index = 0; index < pending.length; index++) {
      request.signal.throwIfAborted();
      const { entries: children } = await files.list(pending[index]!, request.signal);
      for (const child of children) {
        request.signal.throwIfAborted();
        if (++visited > 10000) { error.value = "工作区超过 10000 个条目，仅搜索已读取部分；其余文件可从文件树打开。"; return; }
        if (child.type === "directory") { pending.push(child.path); continue; }
        if (/\.json$/i.test(child.path) && await isCanvasFile(files, child.path, request.signal)) {
          const canvas = await files.readJson<{ nodes?: { id: string; data?: { label?: string } }[] }>(child.path, request.signal);
          if (Array.isArray(canvas.nodes)) for (const node of canvas.nodes) {
            if (typeof node.id !== "string") continue;
            found.push({ key: JSON.stringify([child.path, node.id]), path: child.path,
              selection: { canvasPath: child.path, nodeId: node.id, label: typeof node.data?.label === "string" ? node.data.label : node.id } });
          }
        } else found.push({ key: child.path, path: child.path, selection: { filePath: child.path, label: child.name } });
      }
      request.signal.throwIfAborted();
      entries.value = [...found];
    }
  } catch (cause) { if (!request.signal.aborted) error.value = documentError(cause); }
  finally { if (controller === request) { entries.value = found; loading.value = false; } }
}
async function step(direction: number) {
  const count = Math.min(results.value.length, 100);
  if (!count) return;
  selected.value = (selected.value + direction + count) % count;
  await nextTick();
  document.querySelector('.quickOpen .resultItem.selected')?.scrollIntoView({ block: "nearest" });
}
function choose(index: number) {
  const entry = results.value[index];
  if (!entry) return;
  cancel(); visible.value = false; emit("open", entry.selection);
}
watch(() => props.directory, () => { cancel(); visible.value = false; });
onBeforeUnmount(cancel);
defineExpose({ open });
</script>

<style scoped lang="scss">
.quickOpen {
  .status { color: var(--el-text-color-secondary); font-size: 12px; }
  .resultList {
    max-height: 50vh; overflow: auto; margin-top: 8px;
    .resultItem {
      display: flex; align-items: center; gap: 8px; width: 100%; border: 0; padding: 9px; text-align: left; background: transparent; color: var(--el-text-color-primary); cursor: pointer;
      &.selected, &:hover { background: var(--el-fill-color); }
      img { width: 16px; height: 16px; object-fit: contain; }
      .label { flex-shrink: 0; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      small { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--el-text-color-secondary); }
    }
  }
}
</style>
