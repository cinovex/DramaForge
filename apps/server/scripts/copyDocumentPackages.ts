import { cp, readFile, realpath, rm } from "@toonflow/file";
import { dirname, resolve } from "node:path";

export default async function copyDocumentPackages(nodeModulesDirectory: string) {
  const serverDirectory = resolve(import.meta.dir, "..");
  const nativeDirectory = dirname(await realpath(Bun.resolveSync("@firecrawl/anydoc", serverDirectory)));
  const metadata = JSON.parse(await readFile(resolve(nativeDirectory, "package.json"), "utf8")) as {
    optionalDependencies?: Record<string, string>;
  };
  const optionalDependencies = metadata.optionalDependencies ?? {};
  // ACT: 保留包目录与所有已安装的原生平台包；缺少目标平台二进制时由运行时回退到独立 WASM 包。
  for (const packageName of ["@firecrawl/anydoc", "@firecrawl/anydoc-wasm", ...Object.keys(optionalDependencies)]) {
    const destination = resolve(nodeModulesDirectory, packageName);
    await rm(destination, { recursive: true, force: true });
    let entrypoint: string;
    try {
      entrypoint = Bun.resolveSync(packageName, packageName in optionalDependencies ? nativeDirectory : serverDirectory);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (!(packageName in optionalDependencies) || !["ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND"].includes(code ?? "")) throw error;
      continue;
    }
    await cp(dirname(await realpath(entrypoint)), destination, { recursive: true, dereference: true });
  }
}
