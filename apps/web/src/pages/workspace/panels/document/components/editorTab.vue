<template>
  <div class="editorTab" :class="{ previewTab: params.params.view.preview }" :title="session.context.resource.path" @dblclick.stop="params.params.action('keepOpen')" @contextmenu.stop.prevent="openMenu" @mousedown.middle.stop.prevent="close" @auxclick.middle.stop.prevent>
    <img v-if="session.extension.icon" class="fileIcon" :src="session.extension.icon" alt="" />
    <icon-file-text v-else :size="14" />
    <span class="tabLabel">{{ session.context.resource.label }}</span>
    <span v-if="params.params.view.description" class="tabDescription">{{ params.params.view.description }}</span>
    <span v-if="session.context.dirty" class="dirtyMark" aria-label="尚未保存">●</span>
    <button class="closeTab" :disabled="session.closing" :aria-label="`关闭 ${session.context.resource.label}`" @pointerdown.stop @mousedown.stop @click.stop="close">
      <icon-x :size="13" />
    </button>
  </div>
  <el-dropdown ref="menu" trigger="contextmenu" virtualTriggering :virtualRef="menuAnchor" placement="bottom-start" :showArrow="false" @command="params.params.action">
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-if="params.params.view.preview" command="keepOpen">保留打开</el-dropdown-item>
        <el-dropdown-item command="close">关闭</el-dropdown-item>
        <el-dropdown-item command="closeOthers">关闭其他标签</el-dropdown-item>
        <el-dropdown-item command="closeRight">关闭右侧标签</el-dropdown-item>
        <el-dropdown-item command="closeAll">关闭全部标签</el-dropdown-item>
        <el-dropdown-item command="reopen" divided>重新打开已关闭标签</el-dropdown-item>
        <el-dropdown-item command="splitRight" divided>向右拆分</el-dropdown-item>
        <el-dropdown-item command="splitDown">向下拆分</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, shallowRef } from "vue";
import type { DropdownInstance } from "element-plus";
import { IconFileText, IconX } from "@tabler/icons-vue";
import type { IDockviewPanelHeaderProps } from "dockview-vue";
import type { EditorParams } from "../documentSession";

const props = defineProps<{ params: IDockviewPanelHeaderProps<EditorParams> }>();
const session = computed(() => props.params.params.session);
const menu = ref<DropdownInstance>();
const menuAnchor = shallowRef({ getBoundingClientRect: () => new DOMRect() });
function close() { void props.params.params.close(); }
async function openMenu(event: MouseEvent) {
  menu.value?.handleClose();
  menuAnchor.value = { getBoundingClientRect: () => new DOMRect(event.clientX, event.clientY, 0, 0) };
  await nextTick();
  menu.value?.handleOpen();
}
</script>

<style scoped lang="scss">
.editorTab {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  width: max-content;
  min-width: 120px;
  max-width: 240px;
  height: 100%;
  gap: 7px;
  padding: 0 10px;
  font-size: 12px;
  > svg { flex-shrink: 0; }
  .fileIcon { width: 14px; height: 14px; flex-shrink: 0; object-fit: contain; }
  .tabLabel { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  &.previewTab .tabLabel { font-style: italic; }
  .tabDescription { max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--el-text-color-secondary); font-size: 10px; }
  .dirtyMark { flex-shrink: 0; font-size: 9px; }
  .closeTab {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border: 0;
    border-radius: 3px;
    padding: 0;
    color: inherit;
    background: transparent;
    cursor: pointer;
    &:hover { background: var(--el-fill-color-dark); }
    &:focus-visible { outline: 1px solid var(--el-color-primary); }
  }
}
</style>
