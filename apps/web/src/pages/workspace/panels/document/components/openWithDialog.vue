<template>
  <el-dialog :modelValue="visible" title="选择打开方式" width="min(520px, calc(100vw - 32px))" alignCenter appendToBody :beforeClose="cancel">
    <div class="openWithBody">
      <p class="resourceName" :title="resourceName">{{ resourceName }}</p>
      <el-radio-group v-model="selectedId" class="extensionOptions" aria-label="文件扩展">
        <el-radio v-for="option in options" :key="option.id" :value="option.id" class="extensionOption" border>
          <span class="optionInfo">
            <span class="optionName">{{ option.displayName }}</span>
            <span class="optionDetails">{{ option.id }}<span v-if="option.version"> · v{{ option.version }}</span></span>
          </span>
        </el-radio>
      </el-radio-group>
      <el-checkbox v-model="makeDefault">对此类文件设为默认</el-checkbox>
    </div>
    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button type="primary" :disabled="!selectedId" @click="confirm">打开</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, shallowRef } from "vue";
import { ElButton, ElCheckbox, ElDialog, ElRadio, ElRadioGroup } from "element-plus";

type ExtensionOption = { id: string; displayName: string; version: string };
type ExtensionChoice = { id: string; makeDefault: boolean };
const visible = ref(false);
const resourceName = ref("");
const options = shallowRef<ExtensionOption[]>([]);
const selectedId = ref<string>();
const makeDefault = ref(true);
let resolveChoice: ((choice: ExtensionChoice | undefined) => void) | undefined;

function choose(resourceLabel: string, candidates: ExtensionOption[], defaultId?: string): Promise<ExtensionChoice | undefined> {
  resolveChoice?.(undefined);
  resourceName.value = resourceLabel;
  options.value = candidates;
  selectedId.value = candidates.some(option => option.id === defaultId) ? defaultId : undefined;
  makeDefault.value = true;
  visible.value = true;
  return new Promise(resolve => { resolveChoice = resolve; });
}

function finish(choice?: ExtensionChoice) {
  visible.value = false;
  const resolve = resolveChoice;
  resolveChoice = undefined;
  resolve?.(choice);
}

function cancel() { finish(); }
function confirm() {
  if (selectedId.value && options.value.some(option => option.id === selectedId.value)) finish({ id: selectedId.value, makeDefault: makeDefault.value });
}
onBeforeUnmount(cancel);
defineExpose({ choose });
</script>

<style scoped lang="scss">
.openWithBody {
  display: flex;
  flex-direction: column;
  gap: 16px;

  .resourceName {
    margin: 0;
    color: var(--el-text-color-primary);
    overflow-wrap: anywhere;
  }

  .extensionOptions {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    max-height: 360px;
    overflow: auto;

    .extensionOption {
      height: auto;
      margin: 0;
      padding: 12px;

      :deep(.el-radio__label) {
        min-width: 0;
        white-space: normal;
      }

      .optionInfo {
        display: flex;
        flex-direction: column;
        gap: 4px;
        overflow-wrap: anywhere;

        .optionName { font-weight: 500; }
        .optionDetails { color: var(--el-text-color-secondary); font-size: 12px; }
      }
    }
  }
}
</style>
