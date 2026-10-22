import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import desktopConfig from "../../electrobun.config.ts";
import postcssConfig from "../../postcss.config.ts";
import { i18nPlugin } from "@toonflow/i18n/vite";

const serverTarget = `http://127.0.0.1:${process.env.TOONFLOW_PORT ?? 3000}`;
const dramaforgeApiPrefix = {
  name: "dramaforgeApiPrefix",
  enforce: "pre" as const,
  transform(code: string, id: string) {
    const normalizedId = id.replaceAll("\\", "/");
    if (!normalizedId.includes("/apps/web/src/") && !normalizedId.endsWith("/packages/toolScaffold/src/client.ts")) return null;
    return code.replace(/(["'`])\/(api|mcp|a2a)\//g, "$1/studio-$2/");
  },
};

export default defineConfig({
  base: "/canvasApp/",
  css: { postcss: postcssConfig },
  define: {
    "import.meta.env.appVersion": JSON.stringify(desktopConfig.app.version),
  },
  server: {
    proxy: {
      "/studio-mcp": { target: serverTarget, changeOrigin: false, rewrite: (path) => path.replace(/^\/studio-mcp/, "/mcp") },
      "/studio-a2a": { target: serverTarget, changeOrigin: false, rewrite: (path) => path.replace(/^\/studio-a2a/, "/a2a") },
      "/studio-api": {
        target: serverTarget,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/studio-api/, "/api"),
        configure(proxy) {
          proxy.on("proxyReq", (request, incoming) => {
            request.setHeader("x-toonflow-local-client", ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(incoming.socket.remoteAddress ?? "") ? "1" : "0");
          });
        },
      },
    },
  },
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      { find: /^shiki$/, replacement: fileURLToPath(new URL("./src/lib/shiki.ts", import.meta.url)) },
    ],
  },
  build: {
    outDir: "../../frontend/public/canvasApp",
    emptyOutDir: true,
  },
  plugins: [
    dramaforgeApiPrefix,
    i18nPlugin(),
    vue(),
    components({
      globsExclude: ["src/components/settings/panels/**/*Dialog.vue"],
      dts: "src/types/components.d.ts",
      resolvers: [
        ElementPlusResolver(),
        (name) => {
          if (name.startsWith("Icon")) return { name, from: "@tabler/icons-vue" };
        },
      ],
    }),
  ],
});
