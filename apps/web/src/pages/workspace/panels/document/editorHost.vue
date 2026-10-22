<template>
  <dockview-vue class="editorHost" :theme="theme" defaultTabComponent="editorTab" defaultRenderer="always" watermarkComponent="editorEmpty" @ready="params.params.ready" />
</template>

<script setup lang="ts">
import { DockviewVue, type DockviewReadyEvent, type IDockviewPanelProps } from "dockview-vue";
import editorTab from "./components/editorTab.vue";
import extView from "./components/extView.vue";
import editorEmpty from "./components/editorEmpty.vue";
import { theme } from "./theme";

defineOptions({ components: { editorTab, extView, editorEmpty } });
defineProps<{ params: IDockviewPanelProps<{ ready: (event: DockviewReadyEvent) => void }> }>();
</script>

<style scoped lang="scss">
.editorHost { width: 100%; height: 100%; min-width: 0; min-height: 0; }
</style>
