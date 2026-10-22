# DramaForge

面向 AI 短剧制作的本地创作工作台。在 Toonflow 开源界面与节点画布基础上，融合 DramaForge 的剧本分析和素材生成流程，并探索 Pippit 海外 API 接入。

> 当前为开发预览版。部分入口已搭建，但不代表完整业务链路已验证。需要自行准备模型服务账号和 API 密钥，第三方生成可能收费。

## 功能状态

| 功能 | 状态 |
| --- | --- |
| 创作、营销、短剧首页与节点画布 | 已集成，持续调整 |
| 全局设置、文本与媒体模型配置 | 已有实现，需按供应商验证 |
| 剧本导入、人物/场景/分镜分析 | 已有实现，仍需完善质量与失败恢复 |
| 图片、视频生成和项目素材管理 | 已有实现，依赖外部模型与配置 |
| Pippit 参考图片/视频上传、任务提交和查询 | 已实测成功 |
| Pippit 视频仿制与反解 | 已实测触发 imitation_video 技能及反解工具；成片效果尚未验收 |
| Pippit 模型与技能强制选择 | 未完成；不能保证文字指定生效 |
| Pippit 积分余额查询 | 未打通；网页接口不接受现有 API 密钥认证 |
| Pippit 完整分析资产回收到画布 | 未完成 |
| 多账号素材映射、任务调度 | 未实现 |
| 一键安装、跨平台部署、完整端到端验收 | 未完成 |

## 架构

- `apps/web`：Vue 3、Element Plus、节点画布与设置界面。
- `apps/server`：Bun/TypeScript，工作区、画布和工具服务，开发端口 3001。
- `backend`：Python/FastAPI，剧本分析、生成任务和 Pippit 适配，端口 8000。
- `frontend`：Next.js 入口与代理，端口 3000。
- `packages`：共享组件、节点、工具及供应商适配。

## 本地运行

准备 Node.js、Bun 和 Python 3.11。以下操作分别在对应终端运行。

1. 仓库根目录安装工作区依赖并构建界面：

```powershell
bun install
cd apps/web
bun run build
```

2. 根目录启动画布服务：

```powershell
$env:TOONFLOW_PORT="3001"
$env:TOONFLOW_DATA_DIR="$PWD/storage/canvasData"
bun run --filter '@toonflow/server' dev
```

3. 启动 Python 服务（建议先创建虚拟环境）：

```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

4. 启动网站入口：

```powershell
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000 。若首页没有跳转，可进入 http://localhost:3000/canvasApp/index.html#/home 。修改 `apps/web` 后需重新构建。仓库中的 Windows 启动脚本仍包含本机路径，使用前需要调整。

## 使用方法

1. 在首页全局设置中配置文本、图片、视频模型的服务地址和密钥。
2. 在短剧工作室上传 TXT 或粘贴剧本，选择画幅后开始分析。
3. 打开项目画布，检查人物、场景及分镜，再执行需要的生成任务。
4. 重制入口可上传参考视频并描述改编要求。当前 Pippit 结果展示和素材回收仍在开发，不能视为完整官网功能替代。

## Pippit 配置与限制

项目使用官方 `pippit-skill`。可在服务进程中设置 `PIPPIT_ACCESS_KEY`；也支持技能提供的本地密钥缓存。不要将真实密钥提交到仓库。

现有接入提交自然语言需求和参考素材，由 Pippit 自动安排技能与模型。时长、画幅、分辨率在一次单镜头测试中已转换为生成参数，但最终输出和其他任务仍需逐项验证。多账号积分不能直接合并，后续计划通过任务分配和各账号独立上传素材实现复用。

## 后续开发

- 完成视频反解、追问确认、生成结果和画布回收闭环。
- 保存任务进度，支持刷新后恢复与同一会话继续修改。
- 建立共享本地素材与各账号素材 ID 的映射。
- 验证多账号调度、并发与防重复提交。
- 更新安装流程、部署说明和实际验收记录。

## 开源与致谢

本项目包含并修改了 [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) 的代码与界面，并使用 [Pippit 官方技能](https://github.com/Pippit-dev/pippit-skills)。保留原项目及各依赖的许可证和版权声明；详见 `LICENSE` 和各组件许可证。

不包含个人 API 密钥、数据库、生成视频、运行日志或本地工作区。Pippit 等第三方服务的会员、积分和使用条款由各自平台决定。
