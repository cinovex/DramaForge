<template>
  <div ref="target" class="nodeDocument" />
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { ExtContext } from "@toonflow/ext-scaffold/runtime";

const props = defineProps<{ context: ExtContext }>();
const target = ref<HTMLElement>();
let release: (() => void) | undefined;
let disposed = false;
let active = false;
let mounting = false;
let revision = 0;

async function mountNode() {
  if (!active || mounting || release) return;
  const currentRevision = revision;
  mounting = true;
  try {
    if (!target.value || !props.context.mountNode) throw new Error("节点文档宿主未就绪");
    const unmount = await props.context.mountNode(target.value);
    if (!active || disposed || currentRevision !== revision) unmount();
    else {
      release = unmount;
    }
  } catch (error) {
    if (active && !disposed && currentRevision === revision) props.context.error = error instanceof Error ? error.message : "节点加载失败";
  } finally {
    mounting = false;
    // ACT: 切换期间等待旧挂载先释放，再恢复当前视图，避免较晚返回的旧调用覆盖新投射。
    if (active && !disposed && currentRevision !== revision) void mountNode();
  }
}

function activate() {
  if (!props.context.active || active || disposed || !target.value?.isConnected) return;
  active = true;
  revision++;
  void mountNode();
}

function deactivate() {
  active = false;
  revision++;
  release?.();
  release = undefined;
}

onMounted(() => { void nextTick(activate); });
watch(() => props.context.active, value => { if (value) activate(); else deactivate(); }, { flush: "post" });
onBeforeUnmount(() => { disposed = true; deactivate(); });
</script>

<style scoped lang="scss">
.nodeDocument {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}
</style>
