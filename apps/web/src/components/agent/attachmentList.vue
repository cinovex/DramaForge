<template>
  <div class="attachmentList">
    <attachmentPreview v-for="(attachment, index) in attachments" :key="attachment.path || index" :attachment="attachment" :directory="directory" :removable="removable" :restorable="restorable" :disabled="disabled" @remove="emit('remove', index)" @restore="emit('restore', index)" />
  </div>
</template>

<script setup lang="ts">
import attachmentPreview from "./attachmentPreview.vue";
import type { AgentAttachment } from "./types";

defineProps<{ attachments: AgentAttachment[]; directory?: string; removable?: boolean; restorable?: boolean; disabled?: boolean }>();
const emit = defineEmits<{ remove: [index: number]; restore: [index: number] }>();
</script>

<style scoped lang="scss">
.attachmentList {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
