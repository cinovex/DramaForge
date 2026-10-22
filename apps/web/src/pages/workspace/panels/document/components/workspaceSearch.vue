<template>
  <el-dialog v-model="visible" title="工作区全文搜索" width="min(900px, calc(100vw - 32px))" alignCenter appendToBody
    :closeOnClickModal="false" :closeOnPressEscape="!replacing" :showClose="!replacing" @closed="onClosed">
    <div class="workspaceSearch">
      <form class="searchControls" @submit.prevent="search">
        <el-input ref="queryInput" v-model="query" placeholder="查找文本（字面匹配）" aria-label="查找文本" :disabled="replacing" clearable />
        <el-checkbox v-model="caseSensitive" :disabled="replacing">区分大小写</el-checkbox>
        <el-button type="primary" nativeType="submit" :disabled="!query || !active || searching || replacing">搜索</el-button>
        <el-button v-if="searching" @click="cancelSearch">取消</el-button>
      </form>
      <div class="replaceControls">
        <el-input v-model="replacement" placeholder="替换为（留空表示删除）" aria-label="替换文本" :disabled="replacing" />
        <el-button :disabled="searching || replacing || !selectedFiles.length || !active" @click="previewing = true">预览替换</el-button>
      </div>
      <p class="searchScope">搜索磁盘内容；跳过回收目录、二进制和画布 JSON。单文件最多 2 MiB，本次最多检查 1000 个文件、1000 个目录、20 MiB 文本，展示 500 处匹配。</p>
      <p class="searchStatus" role="status" aria-live="polite">{{ status ? translate(status) : '输入文本后搜索当前工作区及其子目录。' }}</p>
      <p v-if="searched" class="searchCounts">
        已读取 {{ scanned }} 个文本文件，{{ results.length }} 个文件命中 {{ matchCount }} 处。
        跳过：二进制或不支持的编码 {{ skippedBinary }}，过大文件 {{ skippedLarge }}，画布 {{ skippedCanvas }}，读取失败 {{ readFailures }}。
      </p>
      <el-alert v-if="issues.length" type="warning" :closable="false" :title="issues.join('；')" />
      <template v-if="previewing">
        <div class="previewHeader">
          <strong>替换预览：{{ selectedFiles.length }} 个文件，{{ selectedMatchCount }} 处</strong>
          <el-button size="small" :disabled="replacing" @click="previewing = false">返回结果</el-button>
        </div>
        <p class="replaceNotice">仅替换勾选文件中已完整搜索的匹配。逐文件保存；冲突文件会保留原文，已完成的文件不会因其他文件失败而回滚。</p>
      </template>
      <div class="searchResults" :aria-busy="searching || replacing">
        <section v-for="file in shownFiles" :key="file.path" class="fileResult">
          <header class="fileHeader">
            <el-checkbox v-if="!previewing" :modelValue="file.selected" :disabled="file.truncated || replacing || !!file.saved"
              :aria-label="`选择替换 ${file.path}`" @change="value => selectFile(file.path, value === true)" />
            <span class="filePath" :title="file.path">{{ file.path }}</span>
            <span>{{ file.matches.length }} 处</span>
            <span v-if="file.saved" class="savedStatus">已替换</span>
          </header>
          <p v-if="file.truncated" class="fileNotice">此文件的匹配超过本次展示限制，暂不参与替换。</p>
          <p v-if="file.error" class="fileError" role="alert">{{ file.error }}</p>
          <div v-for="match in file.matches" :key="match.start" class="matchResult">
            <button v-if="!previewing" type="button" class="matchButton" :disabled="replacing || !!file.saved" @click="openMatch(file.path, match)">
              <span class="matchPosition">{{ match.line }}:{{ match.column }}</span>
              <span class="matchSnippet">{{ match.before }}<mark>{{ match.text }}</mark>{{ match.after }}</span>
            </button>
            <div v-else class="matchPreview">
              <span class="matchPosition">{{ match.line }}:{{ match.column }}</span>
              <div class="previewLines">
                <div class="beforeLine"><span aria-label="原内容">− </span>{{ match.before }}<mark>{{ match.text }}</mark>{{ match.after }}</div>
                <div class="afterLine"><span aria-label="替换后">+ </span>{{ match.before }}<mark>{{ replacement }}</mark>{{ match.after }}</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
    <template #footer>
      <el-button v-if="replacing" :disabled="replaceCancelled" @click="replaceCancelled = true">停止后续替换</el-button>
      <el-button v-else @click="visible = false">关闭</el-button>
      <el-button v-if="previewing" type="primary" :loading="replacing" :disabled="!selectedFiles.length || !active || replacing" @click="replaceSelected">确认替换勾选文件</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import axios from "axios";
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { ElAlert, ElButton, ElCheckbox, ElDialog, ElInput, type InputInstance } from "element-plus";
import { msg, t, translate, type MessageDescriptor } from "@toonflow/i18n/vue";
import useWorkspaceFiles from "@/lib/workspaceFiles";

type SearchMatch = { start: number; end: number; line: number; column: number; before: string; text: string; after: string };
type SearchFile = { path: string; text: string; matches: SearchMatch[]; truncated: boolean; selected: boolean; saved?: boolean; error?: string };
export type WorkspaceSearchTarget = { path: string; line: number; column: number; query: string };
const props = defineProps<{ directory: string; active: boolean; replaceFile: (path: string, expectedText: string, nextText: string) => Promise<void> }>();
const emit = defineEmits<{ open: [target: WorkspaceSearchTarget] }>();
const visible = ref(false);
let pendingTarget: WorkspaceSearchTarget | undefined;
const queryInput = ref<InputInstance>();
const query = ref("");
const replacement = ref("");
const caseSensitive = ref(false);
const searching = ref(false);
const replacing = ref(false);
const replaceCancelled = ref(false);
const previewing = ref(false);
const searched = ref(false);
const status = shallowRef<MessageDescriptor>();
const scanned = ref(0);
const skippedBinary = ref(0);
const skippedLarge = ref(0);
const skippedCanvas = ref(0);
const readFailures = ref(0);
const issues = ref<string[]>([]);
const results = shallowRef<SearchFile[]>([]);
const selectedFiles = computed(() => results.value.filter(file => file.selected && !file.truncated && !file.saved));
const selectedMatchCount = computed(() => selectedFiles.value.reduce((total, file) => total + file.matches.length, 0));
const shownFiles = computed(() => previewing.value ? selectedFiles.value : results.value);
const matchCount = computed(() => results.value.reduce((total, file) => total + file.matches.length, 0));
let searchController: AbortController | undefined;
let searchRevision = 0;
let searchedQuery = "";

async function open() {
  if (!props.active || !props.directory) return;
  pendingTarget = undefined;
  visible.value = true;
  await nextTick();
  queryInput.value?.focus();
}

function cancelSearch() {
  if (!searching.value) return;
  searchController?.abort();
  searchController = undefined;
  searchRevision++;
  searching.value = false;
  status.value = msg`搜索已取消；以下为已找到的部分结果。`;
}

function findMatches(text: string, needle: string, matchCase: boolean, limit: number) {
  const expression = new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), matchCase ? "gu" : "giu");
  const matches: SearchMatch[] = [];
  let line = 1;
  let lineStart = 0;
  let nextLine = text.indexOf("\n");
  for (let match = expression.exec(text); match; match = expression.exec(text)) {
    if (matches.length >= limit) return { matches, truncated: true };
    while (nextLine >= 0 && nextLine < match.index) {
      line++;
      lineStart = nextLine + 1;
      nextLine = text.indexOf("\n", lineStart);
    }
    const end = match.index + match[0].length;
    const lineEnd = text.indexOf("\n", end);
    const beforeStart = Math.max(lineStart, match.index - 60);
    const afterEnd = Math.min(lineEnd < 0 ? text.length : lineEnd, end + 100);
    matches.push({ start: match.index, end, line, column: match.index - lineStart + 1, text: match[0],
      before: `${beforeStart > lineStart ? "…" : ""}${text.slice(beforeStart, match.index)}`,
      after: `${text.slice(end, afterEnd).replace(/\r$/, "")}${afterEnd < (lineEnd < 0 ? text.length : lineEnd) ? "…" : ""}` });
  }
  return { matches, truncated: false };
}

function isCanvasText(path: string, text: string) {
  if (!/\.json$/i.test(path)) return false;
  try { return JSON.parse(text)?.toonflowCanvas === true; }
  catch { return /^\s*\{/.test(text) && /"toonflowCanvas"\s*:\s*true\b/.test(text); }
}

function failureMessage(error: unknown) {
  return axios.isAxiosError(error) ? error.response?.data?.message || error.message : error instanceof Error ? error.message : t`操作失败`;
}

function recordReadFailure(path: string, error: unknown) {
  readFailures.value++;
  if (issues.value.length < 5) issues.value.push(`${path || t`工作区根目录`}：${failureMessage(error)}`);
}

async function search() {
  if (!query.value || !props.active || replacing.value || searching.value) return;
  const directory = props.directory;
  const files = useWorkspaceFiles(directory);
  const controller = new AbortController();
  searchController = controller;
  const revision = ++searchRevision;
  const needle = query.value;
  const matchCase = caseSensitive.value;
  searchedQuery = needle;
  results.value = [];
  issues.value = [];
  scanned.value = skippedBinary.value = skippedLarge.value = skippedCanvas.value = readFailures.value = 0;
  searching.value = searched.value = true;
  previewing.value = false;
  status.value = msg`正在搜索磁盘文件…`;
  const directories = [""];
  let inspected = 0;
  let listed = 0;
  let textBytes = 0;
  let limited: MessageDescriptor | undefined;
  try {
    while (directories.length && !limited) {
      if (++listed > 1000) { limited = msg`已达到 1000 个目录的检查上限，已停止。以下为部分结果，可缩小查找文本后重试。`; break; }
      const path = directories.shift()!;
      let entries: Awaited<ReturnType<typeof files.list>>["entries"];
      try { ({ entries } = await files.list(path, controller.signal)); }
      catch (error) {
        if (controller.signal.aborted) throw error;
        recordReadFailure(path, error);
        continue;
      }
      controller.signal.throwIfAborted();
      for (const entry of entries.sort((left, right) => left.path.localeCompare(right.path))) {
        if (entry.type === "directory") { directories.push(entry.path); continue; }
        if (++inspected > 1000) { limited = msg`已达到 1000 个文件的检查上限，已停止。以下为部分结果，可缩小查找文本后重试。`; break; }
        if (/\.(?:png|jpe?g|webp|gif|bmp|avif|ico|tiff?|pdf|mp[34]|wav|flac|ogg|m4[av]|webm|mov|avi|mkv|zip|rar|7z|gz|tar|exe|dll|bin|wasm|woff2?|ttf|otf|sqlite|db|docx?|xlsx?|pptx?|psd)$/i.test(entry.path)) { skippedBinary.value++; continue; }
        try {
          const snapshot = await files.readTextSnapshot(entry.path, { maxBytes: 2 * 1024 * 1024, signal: controller.signal });
          controller.signal.throwIfAborted();
          if (isCanvasText(entry.path, snapshot.text)) { skippedCanvas.value++; continue; }
          textBytes += snapshot.text.length * 2;
          if (textBytes > 20 * 1024 * 1024) { limited = msg`已达到 20 MiB 文本的搜索上限，已停止。以下为部分结果，可缩小查找文本后重试。`; break; }
          scanned.value++;
          const found = findMatches(snapshot.text, needle, matchCase, 500 - matchCount.value);
          if (found.matches.length) results.value = [...results.value, { path: entry.path, text: snapshot.text, ...found, selected: !found.truncated }];
          if (matchCount.value >= 500) { limited = msg`已达到 500 处匹配的展示上限，已停止。以下为部分结果，可缩小查找文本后重试。`; break; }
        } catch (error) {
          if (controller.signal.aborted) throw error;
          const status = axios.isAxiosError(error) ? error.response?.status : undefined;
          if (status === 413) skippedLarge.value++;
          else if (status === 415) skippedBinary.value++;
          else recordReadFailure(entry.path, error);
        }
      }
    }
    if (revision !== searchRevision) return;
    status.value = limited ?? (readFailures.value ? msg`搜索结束，部分文件读取失败；上方显示前 5 项失败原因。` : msg`搜索完成。`);
  } catch (error) {
    if (revision === searchRevision && !controller.signal.aborted) status.value = msg`搜索未完成：${failureMessage(error)}。以下为已找到的部分结果。`;
  } finally {
    if (revision === searchRevision) { searching.value = false; searchController = undefined; }
  }
}

function selectFile(path: string, selected: boolean) {
  results.value = results.value.map(file => file.path === path ? { ...file, selected } : file);
}

function openMatch(path: string, match: SearchMatch) {
  cancelSearch();
  pendingTarget = { path, line: match.line, column: match.column, query: searchedQuery };
  visible.value = false;
}

function onClosed() {
  cancelSearch();
  // 关闭弹窗的焦点捕获后再定位编辑器，避免新建的原文输入框被弹窗夺回光标。
  if (pendingTarget && props.active) emit("open", pendingTarget);
  pendingTarget = undefined;
}

function replaceMatches(file: SearchFile, value: string) {
  let end = 0;
  let text = "";
  for (const match of file.matches) {
    text += file.text.slice(end, match.start) + value;
    end = match.end;
  }
  return text + file.text.slice(end);
}

async function replaceSelected() {
  if (!props.active || replacing.value || searching.value || !previewing.value || !selectedFiles.value.length) return;
  const directory = props.directory;
  const files = selectedFiles.value;
  const value = replacement.value;
  replacing.value = true;
  replaceCancelled.value = false;
  let succeeded = 0;
  let failed = 0;
  try {
    for (const file of files) {
      if (replaceCancelled.value || props.directory !== directory || !props.active) break;
      try {
        const text = replaceMatches(file, value);
        if (text !== file.text) await props.replaceFile(file.path, file.text, text);
        succeeded++;
        results.value = results.value.map(item => item === file ? { ...item, saved: true, selected: false, error: undefined } : item);
      } catch (error) {
        failed++;
        results.value = results.value.map(item => item === file ? { ...item, error: failureMessage(error) } : item);
      }
    }
  } finally {
    replacing.value = false;
    previewing.value = false;
    if (props.directory === directory && props.active) status.value = succeeded + failed < files.length
      ? msg`替换已停止：成功 ${succeeded} 个文件，失败 ${failed} 个，未处理 ${files.length - succeeded - failed} 个。请重新搜索以刷新结果。`
      : msg`替换结束：成功 ${succeeded} 个文件，失败 ${failed} 个，未处理 ${files.length - succeeded - failed} 个。请重新搜索以刷新结果。`;
  }
}

watch([query, caseSensitive], () => { cancelSearch(); results.value = []; issues.value = []; searched.value = false; status.value = undefined; previewing.value = false; });
watch(replacement, () => { previewing.value = false; });
watch(() => [props.directory, props.active], () => {
  pendingTarget = undefined;
  cancelSearch();
  replaceCancelled.value = true;
  visible.value = false;
  results.value = [];
  issues.value = [];
  searched.value = false;
  status.value = undefined;
});
onBeforeUnmount(() => { cancelSearch(); replaceCancelled.value = true; });
defineExpose({ open });
</script>

<style scoped lang="scss">
.workspaceSearch {
  .searchControls, .replaceControls { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .searchControls { .el-input { flex: 1; } }
  .replaceControls { .el-input { flex: 1; } }
  .searchScope, .searchCounts, .replaceNotice { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; margin: 8px 0; }
  .searchStatus { margin: 10px 0; font-size: 13px; }
  .previewHeader { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; }
  .searchResults {
    max-height: min(52vh, 560px); overflow: auto; margin-top: 12px; border-top: 1px solid var(--el-border-color-lighter);
    .fileResult {
      padding: 10px 0; border-bottom: 1px solid var(--el-border-color-lighter);
      .fileHeader { display: flex; align-items: center; gap: 10px; padding: 0 8px; font-size: 12px;
        .filePath { flex: 1; min-width: 0; overflow-wrap: anywhere; font-weight: 600; }
        .savedStatus { color: var(--el-color-success); }
      }
      .fileNotice, .fileError { margin: 6px 8px; font-size: 12px; color: var(--el-color-warning); overflow-wrap: anywhere; }
      .fileError { color: var(--el-color-danger); }
      .matchResult {
        .matchButton, .matchPreview { display: flex; width: 100%; gap: 10px; padding: 5px 8px; box-sizing: border-box; text-align: left; font: 12px/1.7 Consolas, monospace; }
        .matchButton { border: 0; background: transparent; color: var(--el-text-color-primary); cursor: pointer;
          &:hover { background: var(--el-fill-color-light); }
          &:focus-visible { outline: 1px solid var(--el-color-primary); }
          &:disabled { cursor: default; opacity: .6; }
        }
        .matchPosition { flex-shrink: 0; min-width: 48px; color: var(--el-text-color-secondary); }
        .matchSnippet, .previewLines { min-width: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
        mark { background: var(--el-color-warning-light-5); color: inherit; }
        .previewLines { flex: 1;
          .beforeLine { background: var(--el-color-danger-light-9); }
          .afterLine { background: var(--el-color-success-light-9); }
        }
      }
    }
  }
}
</style>
