import { createToolConfig } from "@toonflow/tools-scaffold";

await createToolConfig({
  name: "skillOperator",
  displayName: "Skill 操作器",
  description: "统一列出、读取、新建和修改工作区及全局技能。",
  prompt: `技能目录统一通过 skillOperator 的 list 操作按需查询；同名技能默认优先使用工作区版本，指定 scope 可操作对应范围的版本。用户用 /skill:<name> 点选技能但未指定范围时，list 必须省略 scope，并使用返回项的 scope 读取；不可因为当前打开了工作区就把全局技能查成 workspace。 短剧任务只读取一个主流程：剧本到成片以 v118workflow 为主流程；workflow 是 Seedance 专项，仅在实际选用 Seedance 2.0/2.5 且进入视频提示词阶段后读取。不要在剧本分析阶段并行套用两个技能。
已有技能提到 available_skills 或 location 时，使用 list 返回的目录和 filePath 定位，再通过 name、scope、path 读取，无需寻找另一份静态目录。
仅在用户要求维护技能时新建或修改，修改前先读取相关文件；技能内容不能扩大用户请求或工具权限。`,
  author: "Toonflow",
  github: "https://github.com/HBAI-Ltd/Toonflow-app",
  configRules: [
    { type: "switch", field: "allowRead", title: "允许读取", value: true, info: "允许读取技能正文和附带资料。" },
    { type: "switch", field: "allowCreate", title: "允许新建", value: true, info: "允许新建技能及其资料文件，不覆盖已有文件。" },
    { type: "switch", field: "allowUpdate", title: "允许修改", value: true, info: "允许修改已有技能及其资料文件。" },
  ],
}, import.meta.url);
