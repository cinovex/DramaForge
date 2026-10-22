import { $ } from "bun";
import { cp, realpath, rm } from "@toonflow/file";
import { dirname, resolve } from "node:path";
import config from "../../../electrobun.config";
import copyDocumentPackages from "./copyDocumentPackages";

const projectDir = resolve(import.meta.dirname, "../../..");
const agentDirectory = dirname(await realpath(Bun.resolveSync("@earendil-works/pi-coding-agent", resolve(projectDir, "apps/server"))));
const photonDirectory = dirname(Bun.resolveSync("@silvia-odwyer/photon-node", agentDirectory));
// ACT: 团队暂不打包，恢复时取消注释。
// await $`${process.execPath} run build:teams`.cwd(projectDir);
await $`${process.execPath} run build`.cwd(resolve(projectDir, "packages/mcp"));
// ACT: Photon 与 anydoc 保留完整包及相邻的 WASM/原生文件，运行时不依赖源码目录或启动位置。
await $`${process.execPath} build src/index.ts --target=bun --minify --external @silvia-odwyer/photon-node --external @firecrawl/anydoc --external @firecrawl/anydoc-wasm --define ${`process.env.appVersion:${JSON.stringify(config.app.version)}`} --outdir ../../build/server`.cwd(resolve(projectDir, "apps/server"));
const photonOutput = resolve(projectDir, "build/server/node_modules/@silvia-odwyer/photon-node");
await rm(photonOutput, { recursive: true, force: true });
await cp(photonDirectory, photonOutput, { recursive: true });
await copyDocumentPackages(resolve(projectDir, "build/server/node_modules"));
const skillsOutput = resolve(projectDir, "build/skills");
await rm(skillsOutput, { recursive: true, force: true });
await cp(resolve(projectDir, "packages/skills"), skillsOutput, { recursive: true });
const providersOutput = resolve(projectDir, "build/providers");
await rm(providersOutput, { recursive: true, force: true });
await cp(resolve(projectDir, "packages/providers/src"), providersOutput, { recursive: true });
