<template>
  <div class="about">
    <el-card class="infoCard" shadow="never">
      <div class="brand">
        <div class="brandMark" aria-hidden="true"><IconMovie :size="22" /></div>
        <div class="brandInfo">
          <h3>创作工作室</h3>
          <div class="brandMeta">v{{ currentVersion }}</div>
        </div>
      </div>
      <p class="description">剧本分析、素材生成与画布制作工作台。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { IconMovie } from "@tabler/icons-vue";

const currentVersion = import.meta.env.appVersion;
</script>

<style scoped lang="scss">
.about {
  display: grid;
  gap: 16px;

  .infoCard {
    max-width: 720px;
    border-radius: 14px;

    :deep(.el-card__body) { padding: 22px; }
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .brandMark {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border: 1px solid var(--el-border-color-light);
    border-radius: 12px;
    background: var(--el-fill-color-light);
    color: var(--el-color-primary);
  }

  .brandInfo h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 650;
  }

  .brandMeta,
  .description {
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }

  .brandMeta { margin-top: 5px; }
  .description { margin: 18px 0 0; }
}
</style>
