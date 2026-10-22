<template>
  <settings v-model="visible" @closed="notifySettingsClosed" />
</template>

<script setup lang="ts">
import { ref } from "vue";
import settings from "@/components/settings/index.vue";

const visible = ref(true);
function notifySettingsClosed() {
  window.parent.postMessage({ source: "toonflow-global-settings", type: "close" }, window.location.origin);
}
</script>
