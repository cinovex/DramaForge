<template>
  <div
    ref="canvasElement"
    class="canvas"
    :class="{ edgesHidden: !showEdges, handMode, multiSelectionMode: flow.multiSelectionActive.value, compositingEnabled: generalSettings.canvasCompositingEnabled }"
    :style="{ '--canvasEdgeColor': generalSettings.canvasEdgeColorMode === 'custom' ? generalSettings.canvasEdgeColor : 'var(--el-color-primary)' }"
    @dblclick="openNodeMenu"
    @wheel.capture="zoomCanvas"
    @gesturestart.capture="zoomCanvas"
    @gesturechange.capture="zoomCanvas"
    @gestureend.capture="zoomCanvas"
    @pointerdown.capture="updateCanvasSelection"
    @click.capture="updateCanvasSelection"
    @pointermove="pointerPosition = { x: $event.clientX, y: $event.clientY }; if (!$event.buttons) updateCanvasSelection($event)"
    @pointerleave="pointerPosition = undefined"
    @dragover="dragFilesOver"
    @drop="dropFiles">
    <vue-flow
      :id="runtimeKey"
      :only-render-visible-elements="false"
      :nodes-draggable="true"
      :node-types="nodeTypes"
      :snap-to-grid="snapEnabled"
      :snap-grid="[16, 16]"
      :min-zoom="0.2"
      :max-zoom="8"
      :nodes-connectable="true"
      :connection-mode="ConnectionMode.Strict"
      :nodes-focusable="false"
      :edges-focusable="false"
      :edges-updatable="false"
      :elevate-nodes-on-select="true"
      :elevate-edges-on-select="false"
      :disable-keyboard-a11y="true"
      :selectNodesOnDrag="false"
      :auto-pan-on-node-drag="false"
      :auto-pan-on-connect="false"
      :zoom-on-double-click="false"
      :zoomOnScroll="false"
      :zoomOnPinch="active && !settingsVisible"
      :panOnScroll="active && !settingsVisible && !defaultWheelZoom"
      :panOnScrollSpeed="1"
      :panOnDrag="handMode || isMobile ? true : defaultDragPan ? [0, 1] : [1]"
      :panOnScrollMode="PanOnScrollMode.Free"
      :delete-key-code="null"
      :selectionKeyCode="active && !settingsVisible && !handMode && !isMobile && selectionKeyPressed"
      :selectionMode="SelectionMode.Partial"
      :multi-selection-key-code="null"
      :zoomActivationKeyCode="zoomKeyPressed ? true : null"
      :pan-activation-key-code="null"
      v-model="flowData"
      @connect="addEdges"
      @edgeClick="showEdgeDisconnect"
      @paneClick="edgeDisconnect = undefined"
      @moveStart="edgeDisconnect = undefined"
      :default-edge-options="defaultEdgeOptions">
      <template v-for="type in remoteNodeTypes" :key="type" #[`node-${type}`]="nodeProps">
        <remoteNode
          v-bind="nodeProps"
          :component="nodeTypes[type]"
          :error="nodeErrors[type]"
          :loading="nodeLoads.has(type) || (nodeListLoading && !nodeTypes[type] && !nodeErrors[type])" />
      </template>
      <background :gap="16" pattern-color="var(--el-border-color)" />
      <canvasEmpty
        v-if="active && !settingsVisible && project?.directory && canvasReady && !flow.getNodes.value.length"
        :availableNodes="availableNodes"
        @create="createEmptyNode" />
      <canvasMenu ref="canvasMenuRef" v-model:canvasId="canvasId" :directory="project?.directory" :initialCanvasId="initialCanvasId" :activateCanvas="activateCanvas" :flushSave="flushCanvases ?? flushCanvasSave">
        <assetLibrary ref="assetLibraryRef" v-model="assetsVisible" :directory="project?.directory" />
      </canvasMenu>
      <canvasControls
        ref="canvasControlsRef"
        v-model:assetsVisible="assetsVisible"
        v-model:snapEnabled="snapEnabled"
        v-model:showEdges="showEdges"
        :canvasId="canvasId"
        :directory="project?.directory"
        :batchHistory="canvasHistory.batch"
        @update:showEdges="edgeDisconnect = undefined" />
      <nodeMenu
        :key="JSON.stringify(['nodeMenu', project?.directory, canvasId])"
        ref="nodeMenuRef"
        :remoteNodes="availableNodes"
        :pasteNode="pasteClipboardNode"
        :uploadFiles="canvasId && project?.directory ? selectFiles : undefined"
        :canUndo="canUndo"
        :canRedo="canRedo"
        :selectionBusy="selectionToolbarRef?.busy"
        :batchHistory="canvasHistory.batch"
        @duplicateSelection="selectionToolbarRef?.operate('duplicate')"
        @history="canvasHistory.commit"
        @undo="changeHistory('undo')"
        @redo="changeHistory('redo')" />
      <selectionToolbar
        :key="JSON.stringify(['selectionToolbar', project?.directory, canvasId])"
        ref="selectionToolbarRef"
        :batchHistory="canvasHistory.batch"
        :getSignal="() => canvasController.signal"
        :disabled="!canvasId || !project?.directory" />
      <nodeSearch ref="nodeSearchRef" :disabled="!active || settingsVisible || !canvasId || !project?.directory" />
    </vue-flow>
    <teleport to="body">
      <el-button
        v-if="edgeDisconnect && findEdge(edgeDisconnect.id)"
        class="edgeDisconnect"
        type="danger"
        circle
        aria-label="断开连接"
        title="断开连接"
        :style="{ left: `${edgeDisconnect.x}px`, top: `${edgeDisconnect.y}px` }"
        @click.stop="
          removeEdges(edgeDisconnect.id);
          edgeDisconnect = undefined;
        "
        @mouseleave="edgeDisconnect = undefined">
        <icon-unlink :size="16" />
      </el-button>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, onScopeDispose, provide, ref, shallowReactive, shallowRef, watch } from "vue";
import axios from "axios";
import { debounce } from "lodash-es";
import { ElMessage } from "element-plus";
import { isMobile, isDesktop } from "@/lib/platform";
import { storeToRefs } from "pinia";
import { IconUnlink } from "@tabler/icons-vue";
import * as vueRuntime from "vue";
import * as vueFlowRuntime from "@vue-flow/core";
import * as elementPlusRuntime from "element-plus";
import * as threeRuntime from "three";
import { runAgentLoop } from "@earendil-works/pi-agent-core";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import "element-plus/dist/index.css";
import {
  VueFlow,
  PanOnScrollMode,
  ConnectionMode,
  SelectionMode,
  useVueFlow,
  wheelDelta,
  isNode,
  type Node,
  type Edge,
  type GraphEdge,
  type EdgeMouseEvent,
  type NodeTypesObject,
  type XYPosition,
} from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { useCanvasTools } from "./useCanvasTools";
import type { CanvasContext } from "@toonflow/tool-canvas/runtime";
import { loadNodeComponent } from "./loadNodeComponent";
import { useCanvasHistory } from "./useCanvasHistory";
import { copyNodeToClipboard, copyNodesToClipboard, nodeClipboardCommand, readClipboardNodes } from "./nodeClipboard";
import { readClipboardFiles, readClipboardText, writeClipboardImage } from "@/lib/clipboard";
import nodeMenu from "./components/nodeMenu.vue";
import remoteNode from "./components/remoteNode.vue";
import canvasMenu from "./components/canvasMenu.vue";
import canvasControls from "./components/canvasControls.vue";
import canvasEmpty from "./components/canvasEmpty.vue";
import assetLibrary from "./components/assetLibrary.vue";
import groupNode from "./components/groupNode.vue";
import productionMedia from "./components/productionMedia.vue";
import selectionToolbar from "./components/selectionToolbar.vue";
import nodeSearch from "./components/nodeSearch.vue";
import { finishGroupDrag, getSelectionTree } from "./selectionNodes";
import type { NodeOutput } from "@toonflow/nodes-scaffold/values";
import type { NodeConnectionFeedback, NodeHandle } from "@toonflow/nodes-scaffold/connection";
import { useNodeEvent } from "@toonflow/nodes-scaffold/nodeEvent";
import type { NodeDocumentContext, NodeDocumentState } from "@toonflow/nodes-scaffold/nodeDocument";
import { useNodeToolsContext } from "@toonflow/nodes-scaffold/nodeTools";
import { useWorkspaceStore } from "@/stores/workspace";
import { generalSettings } from "@/stores/settings";
import { getShortcutBindings, shortcutLabel, shortcutMatches, shortcutPressed } from "@/lib/canvasShortcuts";
import useWorkspaceFiles from "@/lib/workspaceFiles";
import anonymousData from "@/lib/anonymousData";
import { createClipboardMediaFile, dropCanvasFiles, getClipboardMediaFiles, importCanvasFiles, isCanvasFileDrag } from "./canvasDrop";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/minimap/dist/style.css";

const props = withDefaults(defineProps<{
  active?: boolean;
  settingsVisible?: boolean;
  runtimeKey?: string;
  initialCanvasId?: string;
  activateCanvas?: (canvasId: string, signal?: AbortSignal) => Promise<void>;
  resolveCanvasContext?: (canvasId: string) => CanvasContext | undefined;
  flushCanvases?: (action?: () => Promise<void>) => Promise<void>;
}>(), { active: true, settingsVisible: false });
const workspaceStore = useWorkspaceStore();
const { project } = storeToRefs(workspaceStore);

const canvasElement = ref<HTMLElement>();
const flowData = ref<(Node | Edge)[]>([]);
const canvasId = ref("");
const nodeMenuRef = ref<InstanceType<typeof nodeMenu>>();
const canvasMenuRef = ref<InstanceType<typeof canvasMenu>>();
const canvasControlsRef = ref<InstanceType<typeof canvasControls>>();
const selectionToolbarRef = ref<InstanceType<typeof selectionToolbar>>();
const nodeSearchRef = ref<InstanceType<typeof nodeSearch>>();
const nodeTypes = shallowRef<NodeTypesObject>({ canvasGroup: markRaw(groupNode), productionMedia: markRaw(productionMedia) });
const nodeConfigs = shallowRef<Record<string, Record<string, unknown>>>({});
const nodeOptions = ref<{ type: string; label: string }[]>([]);
const nodeLoads = shallowReactive(new Map<string, Promise<void>>());
const nodeReloads = new Set<string>();
const nodeErrors = ref<Record<string, string>>({});
const availableNodes = computed(() => nodeOptions.value.filter(node => nodeTypes.value[node.type] && !nodeErrors.value[node.type]));
const nodeListLoading = ref(true);
const remoteNodeTypes = computed(() => [
  ...new Set((flowData.value as { type?: string }[]).map((item) => item.type).filter((type): type is string => !!type?.startsWith("remote-"))),
]);
let loadRequest = 0;
const snapEnabled = ref(false);
const zoomKeyPressed = ref(false);
const panKeyPressed = ref(false);
const selectionKeyPressed = ref(false);
const defaultWheelZoom = computed(() => getShortcutBindings(generalSettings.value.canvasShortcuts.zoom).includes("None"));
const defaultDragPan = computed(() => getShortcutBindings(generalSettings.value.canvasShortcuts.pan).includes("None"));
const selectedTool = defineModel<"move" | "hand">("selectedTool", { default: "move" });
const handMode = computed(() => props.active && !props.settingsVisible && (selectedTool.value === "hand" || panKeyPressed.value));
let pointerPosition: XYPosition | undefined;
const pressedCodes = new Set<string>();
let gestureScale: number | undefined;
let copyingNodes = false;
const showEdges = ref(true);
const assetsVisible = ref(false);
const assetLibraryRef = ref<InstanceType<typeof assetLibrary>>();
const edgeDisconnect = ref<{ id: string; x: number; y: number }>();
const flow = useVueFlow(props.runtimeKey);
const nodeDocument: NodeDocumentContext = { targets: shallowReactive(new Map()), mounts: new Map(), states: shallowReactive(new Map()) };
const canvasDirty = ref(false);
const canvasSaveError = ref("");
const documentObservers = new Set<() => void>();
onScopeDispose(() => { for (const release of documentObservers) release(); });
provide("nodeDocument", nodeDocument);
onScopeDispose(anonymousData.observeCanvas(() => props.active && canvasId.value
  ? { nodes: flow.nodes.value, edgeCount: flow.edges.value.length }
  : undefined));
let dragCopy: ReturnType<InstanceType<typeof selectionToolbar>["startDragCopy"]>;
flow.onNodeDragStart(({ event, nodes }) => {
  dragCopy = undefined;
  if (!props.active || props.settingsVisible) return;
  const shortcuts = generalSettings.value.canvasShortcuts;
  const withEdges = shortcutPressed(event, shortcuts.duplicateOnDrag, pressedCodes);
  if (withEdges || shortcutPressed(event, shortcuts.copyOnDrag, pressedCodes)) {
    dragCopy = selectionToolbarRef.value?.startDragCopy(nodes, withEdges);
  }
});
flow.onNodeDrag(() => dragCopy?.update());
flow.onNodeDragStop(({ nodes }) => {
  const copy = dragCopy;
  dragCopy = undefined;
  if (copy) copy.finish();
  else finishGroupDrag(flow.getNodes.value, nodes);
});
const canvasHistory = useCanvasHistory(flow, () =>
  project.value?.directory && canvasId.value ? JSON.stringify([project.value.directory, canvasId.value]) : ""
);
const { canUndo, canRedo } = canvasHistory;
provide("batchCanvasHistory", canvasHistory.batch);
const getNodeTools = useNodeToolsContext();
const { addNodes, addEdges, removeEdges, findEdge, findNode, toObject, viewport, screenToFlowCoordinate } = flow;
provide("copyNodeToClipboard", async (node: Parameters<typeof copyNodeToClipboard>[0]) => {
  const directory = project.value?.directory;
  if (!directory) throw new Error("请先选择工作目录");
  if (await copyImageNodeToClipboard(directory, node)) return;
  await copyNodeToClipboard(node, directory);
});
provide("retainNodeFiles", true);
provide("selectionConnection", shallowRef<NodeConnectionFeedback>());
provide("saveNodeToAssets", (label: string, outputs: { label: string; output: NodeOutput }[]) => assetLibraryRef.value?.openSave(label, outputs));
let canvasController = new AbortController();
let workspaceController = new AbortController();
const createCanvasContext = useCanvasTools({
  availableNodes,
  flushSave: flushCanvasSave,
  menu() {
    if (!canvasMenuRef.value) throw new Error("画布菜单尚未就绪");
    return canvasMenuRef.value;
  },
  getCanvasBinding: () => ({ id: canvasId.value, signal: canvasController.signal }),
  resolveCanvasContext: id => props.resolveCanvasContext?.(id),
});
function getCanvasContext() {
  return canvasId.value || canvasMenuRef.value?.initialized ? createCanvasContext(canvasId.value, canvasController.signal, workspaceController.signal) : undefined;
}
const canvasReady = computed(() => !!canvasId.value && !nodeListLoading.value && nodeLoads.size === 0);

function dramaForgeTextNode(projectId: number, suffix: string, label: string, text: string, x: number, y: number) {
  return {
    id: `dramaforge-${projectId}-${suffix}`,
    type: "remote-textNode",
    position: { x, y },
    data: { label, textSnapshot: text, dramaforgeProjectId: projectId, dramaforgeContentHash: dramaForgeHash(text), dramaforgeLayoutVersion: 2 },
  };
}

function dramaForgeMediaNode(projectId: number, suffix: string, kind: "image" | "video", label: string, url: string, x: number, y: number) {
  const extension = url.split(/[?#]/, 1)[0]?.split(".").at(-1)?.toLowerCase() || "";
  const mimeType = kind === "image"
    ? ({ jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif" } as Record<string, string>)[extension] || "image/png"
    : ({ webm: "video/webm", mov: "video/quicktime" } as Record<string, string>)[extension] || "video/mp4";
  const output = kind === "image" ? { image: { dataType: "IMAGE", value: { url, mimeType } } } : { video: { dataType: "VIDEO", value: { url, mimeType } } };
  return {
    id: `dramaforge-${projectId}-${suffix}`,
    type: kind === "image" ? "remote-imageNode" : "remote-videoNode",
    position: { x, y },
    data: { label, outputs: output, dramaforgeProjectId: projectId, dramaforgeMediaUrl: url },
  };
}

function dramaForgeHash(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index++) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  return (hash >>> 0).toString(36);
}

function buildDramaForgeNodes(project: any) {
  const projectId = Number(project.id);
  const nodes: any[] = [];
  const title = project.outline?.title || project.name || `项目 ${projectId}`;
  const outline = project.outline || {};
  const source = outline.raw_data && typeof outline.raw_data === "object" ? outline.raw_data : {};
  const story = source.story_analysis && typeof source.story_analysis === "object" ? source.story_analysis : {};
  const plannedEpisodes = Array.isArray(source.episodes) ? source.episodes : [];
  const textValue = (value: any) => typeof value === "string" ? value : value == null ? "" : JSON.stringify(value, null, 2);
  const beats = Array.isArray(story.story_beats) ? story.story_beats : [];
  const storyText = [
    `# ${title}`,
    outline.synopsis && `## 故事梗概\n${outline.synopsis}`,
    story.logline && `## 故事核\n${story.logline}`,
    story.central_conflict && `## 核心冲突\n${story.central_conflict}`,
    story.protagonist_arc && `## 主角变化\n${story.protagonist_arc}`,
    beats.length && `## 故事节拍\n${beats.map((beat: any, index: number) => `${index + 1}. ${beat.stage || "阶段"}：${beat.event || ""}${beat.dramatic_function ? `（作用：${beat.dramatic_function}）` : ""}`).join("\n")}`,
    Array.isArray(story.themes) && story.themes.length && `## 主题\n${story.themes.map(textValue).join("；")}`,
    Array.isArray(story.continuity_risks) && story.continuity_risks.length && `## 连续性待核对\n${story.continuity_risks.map((risk: any) => `- ${textValue(risk)}`).join("\n")}`,
    `## 类型与受众\n${outline.story_type || "未标注"} · ${outline.target_audience || "未标注"}`,
    `## 全局视觉设定\n${outline.video_style || "未设置"} · ${outline.aspect_ratio || "9:16"}`,
    plannedEpisodes.length && `## 分集大纲\n${plannedEpisodes.map((episode: any) => [
      `### EP${String(episode.ep_no || 1).padStart(2, "0")} · ${episode.title || "未命名"}`,
      episode.summary && `剧情推进：${episode.summary}`,
      episode.conflict && `本集冲突：${episode.conflict}`,
      episode.turning_point && `关键转折：${episode.turning_point}`,
      episode.ending_hook && `结尾钩子：${episode.ending_hook}`,
      episode.estimated_duration != null && `预计时长：${episode.estimated_duration} 秒${episode.duration_basis ? `（${episode.duration_basis}）` : ""}`,
    ].filter(Boolean).join("\n")).join("\n\n")}`,
    `## 原始剧本\n${project.script_text || "暂无剧本文本"}`,
  ].filter(Boolean).join("\n\n");
  nodes.push(dramaForgeTextNode(projectId, "script", "原始剧本文本", project.script_text || "暂无剧本文本", -1000, 0));
  nodes.push(dramaForgeTextNode(projectId, "story", "剧本文本与分集大纲", storyText, -520, 0));

  const characters = Array.isArray(project.characters) ? project.characters : [];
  const assetSections: string[] = ["# 角色 / 场景 / 道具连续性"];
  characters.forEach((character: any) => {
    const design = character.design || {};
    const references = character.reference_images || {};
    const views = design.views && typeof design.views === "object" ? design.views : {};
    const expressions = Array.isArray(design.expressions) ? design.expressions : [];
    assetSections.push([
      `## 角色：${character.name || "未命名角色"}`,
      `剧本事实：${character.description || "暂无人物描述"}`,
      design.identity && `身份锚点：${design.identity}`,
      design.wardrobe && `服装与配饰：${design.wardrobe}`,
      Object.keys(views).length && `四视图提示词：\n${Object.entries(views).map(([view, prompt]) => `${view}：${textValue(prompt)}`).join("\n")}`,
      design.turnaround_prompt && `四视图整图提示词：${design.turnaround_prompt}`,
      expressions.length && `表情提示词：\n${expressions.map((item: any) => `${item.name || "表情"}：${item.prompt || ""}${item.negative_prompt ? `；避免：${item.negative_prompt}` : ""}`).join("\n")}`,
      design.expression_sheet_prompt && `表情参考图提示词：${design.expression_sheet_prompt}`,
      design.negative_prompt && `避免：${design.negative_prompt}`,
      design.director_notes && `导演备注：${design.director_notes}`,
    ].filter(Boolean).join("\n\n"));
    nodes.push(dramaForgeTextNode(projectId, `character-${character.id}-prompt`, `角色 · ${character.name} · 图片提示词`, assetSections.at(-1) || "", -520, 600 + characters.indexOf(character) * 650));
    const media = new Map<string, string>();
    if (character.base_image_url) media.set("主参考", character.base_image_url);
    for (const [variant, url] of Object.entries(references)) if (typeof url === "string" && url) media.set(variant, url);
    [...media.entries()].forEach(([variant, url], imageIndex) => {
      nodes.push(dramaForgeMediaNode(projectId, `character-${character.id}-image-${imageIndex}`, "image", `${character.name || "角色"} · ${variant}`, url, -180 + imageIndex * 280, 600 + characters.indexOf(character) * 650));
    });
  });

  const scenes = Array.isArray(project.scenes) ? project.scenes : [];
  scenes.forEach((scene: any, index: number) => {
    assetSections.push([`## 场景：${scene.name || "未命名场景"}`, `剧本事实：${scene.description || "暂无场景描述"}`, `连续性与场景提示词：\n${JSON.stringify(scene.design || {}, null, 2)}`].join("\n\n"));
    nodes.push(dramaForgeTextNode(projectId, `scene-${scene.id}-prompt`, `场景 · ${scene.name} · 图片提示词`, assetSections.at(-1) || "", 600, 600 + index * 650));
    if (scene.image_url) nodes.push(dramaForgeMediaNode(projectId, `scene-${scene.id}-image`, "image", `${scene.name || "场景"} · 参考图`, scene.image_url, 940, 600 + index * 650));
  });

  const props = Array.isArray(project.props) ? project.props : [];
  props.forEach((item: any, index: number) => {
    assetSections.push([`## 道具：${item.name || "未命名道具"}`, item.description || "暂无道具描述"].join("\n\n"));
    nodes.push(dramaForgeTextNode(projectId, `prop-${item.id}-prompt`, `道具 · ${item.name} · 图片提示词`, [assetSections.at(-1), item.design?.prompt || item.design?.reference_prompt || item.description].filter(Boolean).join("\n\n图片提示词：\n"), 1720, 600 + index * 650));
    if (item.image_url) nodes.push(dramaForgeMediaNode(projectId, `prop-${item.id}-image`, "image", `${item.name || "道具"} · 参考图`, item.image_url, 2060, 600 + index * 650));
  });
  nodes.push(dramaForgeTextNode(projectId, "assets", "角色 / 场景 / 道具连续性", assetSections.join("\n\n---\n\n"), 300, 0));

  const shots = Array.isArray(project.shots) ? project.shots : [];
  const episodeNumbers = [...new Set<number>(shots.map((shot: any) => Number(shot.episode_no) || 1))].sort((left, right) => left - right);
  const episodePlan = new Map<number, any>(plannedEpisodes.map((episode: any) => [Number(episode.ep_no) || 1, episode]));
  const storyboardSections: string[] = ["# 逐镜导演设计与生成提示词"];
  let episodeTop = 0;
  for (const episode of episodeNumbers) {
    const list = shots.filter((shot: any) => (Number(shot.episode_no) || 1) === episode).sort((left: any, right: any) => Number(left.shot_no) - Number(right.shot_no));
    const plan = episodePlan.get(episode);
    storyboardSections.push([`## EP${String(episode).padStart(2, "0")} · ${plan?.title || "分镜"}`, plan?.summary && `本集：${plan.summary}`, `分镜数：${list.length} · 预计时长：${list.reduce((sum: number, shot: any) => sum + (Number(shot.duration) || 0), 0)} 秒`].filter(Boolean).join("\n"));
    list.forEach((shot: any, index: number) => {
      const column = index % 3;
      const row = Math.floor(index / 3);
      const text = [
        `### 镜头 ${String(shot.shot_no).padStart(2, "0")} · ${shot.title || "未命名镜头"}`,
        `时长：${shot.duration || 0} 秒`,
        `场景：${shot.scene_name || "未指定"}`,
        `出场角色：${(shot.character_names || []).join("、") || "无"}`,
        "## 视频提示词",
        shot.prompt || "暂无视频提示词",
        "## 首帧提示词",
        shot.keyframe_prompt || "暂无首帧提示词",
        "## 导演镜头设计",
        JSON.stringify(shot.direction || {}, null, 2),
      ].join("\n\n");
      storyboardSections.push(text);
      const x = 2840 + column * 940;
      const y = 600 + episodeTop + row * 650;
      nodes.push(dramaForgeTextNode(projectId, `shot-${shot.id}-prompt`, `第 ${episode} 集 · 分镜 ${shot.shot_no} · 首帧与视频提示词`, text, x, y));
      if (shot.keyframe_url) nodes.push(dramaForgeMediaNode(projectId, `shot-${shot.id}-keyframe`, "image", `EP${episode} · 镜头 ${shot.shot_no} · 关键帧`, shot.keyframe_url, x + 340, y));
      if (shot.video_url) nodes.push(dramaForgeMediaNode(projectId, `shot-${shot.id}-video`, "video", `EP${episode} · 镜头 ${shot.shot_no} · 视频`, shot.video_url, x + 620, y));
    });
    episodeTop += Math.max(1, Math.ceil(list.length / 3)) * 650 + 180;
  }
  nodes.push(dramaForgeTextNode(projectId, "storyboard", "逐镜导演设计与完整提示词", storyboardSections.join("\n\n---\n\n"), 1120, 0));
  const groupedNodes: any[] = nodes.filter(node => node.type === "remote-textNode" && !node.id.endsWith("-prompt"));
  function addMediaGroup(suffix: string, label: string, items: any[], x: number, y: number) {
    const id = `dramaforge-${projectId}-group-${suffix}`;
    groupedNodes.push({ id, type: "canvasGroup", position: { x, y }, style: { width: "850px", height: `${Math.max(1, Math.ceil(items.length / 3)) * 360 + 60}px` }, data: { label: `${label} · ${items.length}`, dramaforgeProjectId: projectId, dramaforgeLayoutVersion: 3 } });
    items.forEach((item, index) => groupedNodes.push({ id: `dramaforge-${projectId}-${item.suffix}-prompt`, type: "productionMedia", parentNode: id, expandParent: false, position: { x: 24 + index % 3 * 276, y: 40 + Math.floor(index / 3) * 360 }, data: { ...item, dramaforgeProjectId: projectId, dramaforgeLayoutVersion: 3 } }));
  }
  for (const [index, kind] of ["characters", "scenes", "props"].entries()) {
    const category = { characters: "角色", scenes: "场景", props: "道具" }[kind];
    const singular = { characters: "character", scenes: "scene", props: "prop" }[kind];
    addMediaGroup(kind, `${category}参考素材`, (project[kind] || []).map((item: any) => ({ suffix: `${singular}-${item.id}`, category, targetKind: kind, targetId: item.id, kind: "image", label: item.name, url: item.base_image_url || item.image_url || "", prompt: item.design?.turnaround_prompt || item.design?.reference_prompt || item.design?.prompt || item.description || "" })), index * 1000 - 520, 600);
  }
  let groupTop = 600;
  for (const episode of episodeNumbers) {
    const list = shots.filter((shot: any) => Number(shot.episode_no || 1) === episode).sort((a: any, b: any) => a.shot_no - b.shot_no);
    addMediaGroup(`episode-${episode}`, `第 ${episode} 集 · 分镜视频`, list.map((shot: any) => ({ suffix: `shot-${shot.id}`, category: `分镜 ${shot.shot_no}`, targetKind: "shots", targetId: shot.id, episode, kind: "video", label: shot.title || `镜头 ${shot.shot_no}`, url: shot.video_url || "", poster: shot.keyframe_url || "", duration: shot.duration, running: shot.video_status === "processing", prompt: shot.prompt || shot.keyframe_prompt || "" })), 2600, groupTop);
    groupTop += Math.max(1, Math.ceil(list.length / 3)) * 360 + 180;
  }
  return groupedNodes;
}

let dramaForgeViewChecked = false;
async function syncDramaForgeProject(project: any) {
  if (!props.active || !canvasReady.value || !project?.id || !canvasId.value) throw new Error("Toonflow 画布尚未就绪，请稍后重试");
  const projectId = Number(project.id);
  const wanted = buildDramaForgeNodes(project).filter(node => ["canvasGroup", "productionMedia"].includes(node.type) || availableNodes.value.some(available => available.type === node.type));
  const wantedById = new Map(wanted.map(node => [node.id, node]));
  const current = flow.getNodes.value;
  const owned = current.filter(node => node.data?.dramaforgeProjectId === projectId);
  const ownedIds = new Set(owned.map(node => node.id));
  const needsReadableView = !dramaForgeViewChecked && viewport.value.zoom < 0.4 || owned.length === 0 || owned.some(node => node.type === "remote-textNode" && node.data?.dramaforgeLayoutVersion !== 2);
  const add: any[] = [];
  const replace: string[] = [];

  for (const desired of wanted) {
    const existing = flow.findNode(desired.id);
    if (!existing) { add.push(desired); continue; }
    if (existing.type !== desired.type) { replace.push(existing.id); add.push(desired); continue; }
    if (desired.type === "remote-textNode") {
      if (existing.data?.textPath !== `assets/${desired.id}/content.md`) {
        replace.push(existing.id);
        add.push(desired);
        continue;
      }
      if (existing.data?.dramaforgeContentHash !== desired.data.dramaforgeContentHash) {
        await getNodeTools().call({ nodeId: desired.id, name: "node:setText", args: { text: desired.data.textSnapshot } }, canvasController.signal);
      }
      Object.assign(existing.data, desired.data);
      delete existing.data.textSnapshot;
    } else {
      if (desired.type === "canvasGroup" && existing.data?.label !== desired.data.label) existing.style = desired.style;
      Object.assign(existing.data, desired.data);
    }
  }

  const stale = owned.filter(node => !wantedById.has(node.id)).map(node => node.id);
  const firstSync = needsReadableView;
  dramaForgeViewChecked = true;
  const textAdds = add.filter(node => node.type === "remote-textNode");
  if (textAdds.length) {
    const directory = workspaceStore.project?.directory;
    if (!directory) throw new Error("项目工作目录不可用，无法保存提示词节点");
    const files = useWorkspaceFiles(directory);
    const ensureDirectory = async (path: string) => files.mkdir(path).catch(error => {
      const code = axios.isAxiosError<{ data?: { code?: string } }>(error) ? error.response?.data?.data?.code : undefined;
      if (code !== "EEXIST") throw error;
    });
    await ensureDirectory("assets");
    for (const node of textAdds) {
      const path = `assets/${node.id}/content.md`;
      await ensureDirectory(`assets/${node.id}`);
      if (typeof node.data.textSnapshot !== "string") throw new Error(`提示词节点“${node.data.label || node.id}”内容无效`);
      await files.write(path, node.data.textSnapshot, false);
      node.data.textPath = path;
      delete node.data.textSnapshot;
    }
  }
  await canvasHistory.batch(async () => {
    if (stale.length || replace.length) flow.removeNodes([...stale, ...replace]);
    if (replace.length) await nextTick();
    if (add.length) addNodes(add);
  });
  await nextTick();
  await flushCanvasSave();
  if (firstSync && wanted.length) requestAnimationFrame(() => void flow.fitView({ nodes: [`dramaforge-${projectId}-script`], padding: 0.2, minZoom: 0.8, maxZoom: 1, duration: 350 }));
  return { nodes: wanted.length, canvas: canvasId.value };
}

async function addPippitAssets(assets: { url: string; name: string; mime?: string; kind: "image" | "video" }[]) {
  if (!props.active || !canvasReady.value || !canvasId.value) throw new Error("Toonflow 画布尚未就绪，请稍后重试");
  const mediaAssets = assets.filter(asset => /^https?:\/\//i.test(asset.url));
  if (!mediaAssets.length) throw new Error("没有可放入画布的媒体链接");
  const missingTypes = [...new Set(mediaAssets.map(asset => asset.kind === "video" ? "remote-videoNode" : "remote-imageNode"))]
    .filter(type => !availableNodes.value.some(node => node.type === type));
  if (missingTypes.length) throw new Error("画布的图片或视频节点尚未加载完成，请稍后重试");

  const rect = canvasElement.value?.getBoundingClientRect();
  if (!rect) throw new Error("无法读取画布位置");
  const center = screenToFlowCoordinate({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
  const nodes = mediaAssets.map((asset, index) => {
    const kind = asset.kind;
    const mimeType = asset.mime || (kind === "video" ? "video/mp4" : "image/jpeg");
    const output = kind === "video"
      ? { video: { dataType: "VIDEO", value: { url: asset.url, mimeType } } }
      : { image: { dataType: "IMAGE", value: { url: asset.url, mimeType } } };
    return {
      id: `pippit-${crypto.randomUUID()}`,
      type: kind === "video" ? "remote-videoNode" : "remote-imageNode",
      position: { x: center.x - 170 + (index % 3) * 360, y: center.y - 120 + Math.floor(index / 3) * 250 },
      data: { label: asset.name || `Pippit · ${kind === "video" ? "视频" : "图片"}`, outputs: output, pippitMediaUrl: asset.url },
    };
  });
  await canvasHistory.batch(async () => { addNodes(nodes); });
  await nextTick();
  await flushCanvasSave();
  return nodes.length;
}

provide("canvas", getCanvasContext);
defineExpose({ canvasId, canvasReady, getCanvasContext, addNodeAtPointer, syncDramaForgeProject, addPippitAssets, readDocumentNode, saveDocumentNode, mountDocumentNode, observeDocumentNode, prepareCanvasDelete, flushSave: flushCanvasSave, cancelSave: cancelCanvasSave,
  getCanvases: (signal?: AbortSignal) => {
    if (!canvasMenuRef.value) throw new Error("画布菜单尚未就绪");
    return canvasMenuRef.value.getCanvases(signal);
  },
  syncCanvasPath: (previous: string, target: string) => canvasMenuRef.value?.syncCanvasPath(previous, target),
  getMentionNodes: () => flow.nodes.value, findMentionNode: flow.findNode,
  getRetainedNodes: canvasHistory.getRetainedNodes,
  get canvasListReady() { return canvasMenuRef.value?.initialized ?? false; },
  get saveBusy() { return savePaused; }, get loadError() { return canvasMenuRef.value?.loadError ?? ""; },
});

async function prepareCanvasDelete() {
  const directory = project.value?.directory;
  const fileName = canvasId.value;
  const nodes = [...flow.getNodes.value];
  const signal = AbortSignal.any([workspaceController.signal, canvasController.signal]);
  function checkCanvas() {
    signal.throwIfAborted();
    if (!directory || directory !== project.value?.directory || !fileName || fileName !== canvasId.value) {
      throw new Error("工作区或画布已切换，请重新删除");
    }
  }
  checkCanvas();
  await nextTick();
  checkCanvas();
  // 宿主已暂停画布保存；这里只执行节点生命周期，文件删除成功后由宿主取消保存并卸载。
  for (const node of nodes) {
    if (flow.findNode(node.id) !== node) throw new Error("画布节点已变化，请重新删除");
    await useNodeEvent(node.id, flow).emit("delete");
    checkCanvas();
    if (flow.findNode(node.id) !== node) throw new Error("画布节点已变化，请重新删除");
  }
  if (flow.getNodes.value.length !== nodes.length || nodes.some(node => flow.findNode(node.id) !== node)) {
    throw new Error("画布节点已变化，请重新删除");
  }
}

type DocumentNodeData = { label?: string; handles?: NodeHandle[]; outputs?: Record<string, NodeOutput | undefined>; textPath?: string };

function checkDocumentDirectory(directory: string) {
  if (!directory || directory !== project.value?.directory) throw new Error("工作目录已切换，请重新打开节点");
}

function observeDocumentNode(directory: string, canvasPath: string, nodeId: string, onState: (state: NodeDocumentState) => void) {
  checkDocumentDirectory(directory);
  if (canvasId.value !== canvasPath || !findNode(nodeId)) throw new Error("节点不存在，请刷新文件树");
  const stop = watch((): NodeDocumentState => {
    const node = findNode(nodeId);
    const state = nodeDocument.states.get(nodeId);
    return { dirty: !!node && (canvasDirty.value || !!state?.dirty),
      error: state?.error || canvasSaveError.value || (node && nodeErrors.value[node.type]) || "", deleted: !node };
  }, onState, { immediate: true, flush: "sync" });
  const release = () => { stop(); documentObservers.delete(dispose); };
  const dispose = () => { onState({ dirty: false, error: "", deleted: true }); release(); };
  documentObservers.add(dispose);
  return {
    release,
    async flushSave() {
      checkDocumentDirectory(directory);
      if (!findNode(nodeId)) throw new Error("节点已删除，请刷新文件树");
      await flushCanvasSave();
    },
  };
}

async function mountDocumentNode(directory: string, canvasPath: string, nodeId: string, target: HTMLElement) {
  checkDocumentDirectory(directory);
  if (canvasId.value !== canvasPath) throw new Error("画布已切换，请重新打开节点");
  await nextTick();
  checkDocumentDirectory(directory);
  const node = findNode(nodeId);
  if (!node) throw new Error("节点已删除，请刷新文件树");
  if (nodeErrors.value[node.type]) throw new Error(nodeErrors.value[node.type]);
  const mount = nodeDocument.mounts.get(nodeId);
  if (!mount) throw new Error("当前节点未提供文档视图，请确认节点正常加载并更新节点插件");
  const release = mount(target);
  try {
    await nextTick();
    checkDocumentDirectory(directory);
    if (!target.isConnected || !target.querySelector(".documentNode")) throw new Error("节点文档视图加载失败，请重新打开节点");
    return release;
  } catch (error) {
    release();
    throw error;
  }
}

function documentHandles(node: Node<DocumentNodeData>) {
  const handles = node.data?.handles;
  if (Array.isArray(handles) && handles.length) {
    return handles.filter(
      (handle) =>
        handle &&
        typeof handle.id === "string" &&
        handle.type === "source" &&
        (Array.isArray(handle.dataType) ? handle.dataType.includes("STRING") : handle.dataType === "STRING")
    );
  }
  return Object.entries(node.data?.outputs ?? {}).flatMap(([id, output]) => (output?.dataType === "STRING" ? [{ id, label: id }] : []));
}

async function readDocumentCanvas(directory: string, canvasPath: string, nodeId: string) {
  checkDocumentDirectory(directory);
  const files = useWorkspaceFiles(directory);
  const canvas = await files.readJson<{ toonflowCanvas?: boolean; nodes?: Node<DocumentNodeData>[] }>(canvasPath);
  checkDocumentDirectory(directory);
  if (canvas?.toonflowCanvas !== true || !Array.isArray(canvas.nodes)) throw new Error("文件不是有效画布");
  const node = canvas.nodes.find((item) => item && item.id === nodeId);
  if (!node) throw new Error("节点已删除，请刷新文件树");
  if (node.data !== undefined && (!node.data || typeof node.data !== "object" || Array.isArray(node.data))) throw new Error("节点数据无效");
  const liveNode = canvasId.value === canvasPath ? findNode(nodeId) : undefined;
  if (canvasId.value === canvasPath && !liveNode) throw new Error("节点已删除，请刷新文件树");
  const textPath = node.data?.textPath;
  if (
    textPath !== undefined &&
    (typeof textPath !== "string" ||
      !textPath.trim() ||
      /^(?:[a-z][a-z\d+.-]*:|[\\/])/i.test(textPath) ||
      textPath.includes("\0") ||
      textPath.split(/[\\/]/).includes(".."))
  )
    throw new Error("文本文件路径必须位于工作区内");
  return { files, canvas, node, liveNode, textPath };
}

async function readDocumentNode(directory: string, canvasPath: string, nodeId: string) {
  checkDocumentDirectory(directory);
  await flushCanvasSave();
  const { files, node, liveNode, textPath } = await readDocumentCanvas(directory, canvasPath, nodeId);
  const source = liveNode ?? node;
  const handles = documentHandles(source);
  const storedText = textPath === undefined ? undefined : await files.readText(textPath);
  checkDocumentDirectory(directory);
  return {
    label: typeof source.data?.label === "string" ? source.data.label : nodeId,
    outputs: handles.map((handle) => {
      const output = source.data?.outputs?.[handle.id];
      return {
        id: handle.id,
        label: handle.label || handle.id,
        text: output?.dataType === "STRING" && typeof output.value === "string" ? output.value : storedText ?? "",
      };
    }),
  };
}

async function saveDocumentNode(directory: string, canvasPath: string, nodeId: string, handleId: string, text: string, expectedText?: string) {
  checkDocumentDirectory(directory);
  await flushCanvasSave(async () => {
    const { files, canvas, node, liveNode, textPath } = await readDocumentCanvas(directory, canvasPath, nodeId);
    if (!documentHandles(liveNode ?? node).some((handle) => handle.id === handleId)) throw new Error("文本输出已删除，请重新打开节点");
    if (expectedText !== undefined) {
      const output = (liveNode ?? node).data?.outputs?.[handleId];
      const currentText = output?.dataType === "STRING" && typeof output.value === "string" ? output.value : textPath === undefined ? "" : await files.readText(textPath);
      if (currentText !== expectedText) throw new Error("文档内容已变化，请重新读取后编辑");
    }
    if (liveNode?.type === "remote-textNode") {
      await getNodeTools().call({ nodeId, name: "node:setText", args: { text } }, canvasController.signal);
      checkDocumentDirectory(directory);
      // 节点工具已同步输出并排队保存；等待期间用户可能继续编辑，不能再写入旧文本快照。
      return;
    }
    if (liveNode && canvasId.value === canvasPath && findNode(nodeId) === liveNode) {
      const output = liveNode.data.outputs?.[handleId];
      if (output?.dataType === "STRING") output.value = text;
      else if (textPath === undefined) (liveNode.data.outputs ??= {})[handleId] = { dataType: "STRING", value: text };
    }
    canvasMenuRef.value?.syncDocumentNode(canvasPath, nodeId, handleId, text, textPath === undefined);
    if (textPath !== undefined) {
      await files.write(textPath, text);
    } else {
      const data = (node.data ??= {});
      const output = data.outputs?.[handleId];
      if (output?.dataType === "STRING") output.value = text;
      else (data.outputs ??= {})[handleId] = { dataType: "STRING", value: text };
      await files.writeJson(canvasPath, canvas);
    }
    checkDocumentDirectory(directory);
  });
}

function showEdgeDisconnect({ event, edge }: EdgeMouseEvent) {
  if (!(event instanceof MouseEvent)) return;
  event.stopPropagation();
  edgeDisconnect.value = { id: edge.id, x: event.clientX, y: event.clientY };
}

function dragFilesOver(event: DragEvent) {
  if (!props.active || props.settingsVisible || !canvasId.value || !project.value?.directory || !isCanvasFileDrag(event)) return;
  if (!(event.target instanceof Element) || !event.target.closest(".vue-flow__pane")) return;
  event.preventDefault();
  event.dataTransfer!.dropEffect = "copy";
  return true;
}

async function dropFiles(event: DragEvent) {
  const directory = project.value?.directory;
  if (!directory || !dragFilesOver(event)) return;
  try {
    await canvasHistory.batch(() => dropCanvasFiles(event, { directory, availableNodes: availableNodes.value, signal: canvasController.signal, flow }));
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "文件导入失败");
  }
}

function selectFiles(position: { x: number; y: number }) {
  const directory = project.value?.directory;
  if (!props.active || props.settingsVisible || !canvasId.value || !directory) return;
  const context = { directory, availableNodes: availableNodes.value, signal: canvasController.signal, flow };
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.onchange = async () => {
    const files = Array.from(input.files ?? []);
    if (!files.length || context.signal.aborted) return;
    try {
      await canvasHistory.batch(() => importCanvasFiles(files, position, context));
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : "文件导入失败");
    }
  };
  input.click();
}

function openNodeMenu(event: MouseEvent) {
  if (event.target instanceof Element && event.target.classList.contains("vue-flow__pane")) nodeMenuRef.value?.openMenu(event, true);
}

function createEmptyNode(type: string) {
  if (!props.active || props.settingsVisible || !project.value?.directory || !canvasReady.value || flow.getNodes.value.length) return;
  const rect = canvasElement.value?.getBoundingClientRect();
  if (!rect) return;
  const center = screenToFlowCoordinate({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
  void nodeMenuRef.value?.addNode(type, { x: center.x - 200, y: center.y - 160 });
}

function addNodeAtPointer() {
  if (!props.active || props.settingsVisible || !project.value?.directory || !canvasReady.value) return;
  const rect = canvasElement.value?.getBoundingClientRect();
  if (!rect) return;
  const position = pointerPosition ?? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  void nodeMenuRef.value?.openMenu(new MouseEvent("contextmenu", { clientX: position.x, clientY: position.y }), true);
}

async function changeHistory(direction: "undo" | "redo") {
  try {
    await canvasHistory[direction]();
    edgeDisconnect.value = undefined;
  } catch (error) {
    ElMessage.error(
      axios.isAxiosError<{ message?: string }>(error)
        ? error.response?.data.message || "恢复画布失败"
        : error instanceof Error
        ? error.message
        : "恢复画布失败"
    );
  }
}

let saving = Promise.resolve();
let flushing = Promise.resolve();
let saveError: unknown;
let savePaused = false;
let saveCancelled = false;
let changedWhilePaused = false;
let saveRevision = 0;
const saveCanvas = debounce((directory: string, fileName: string) => {
  const flow = toObject();
  const revision = saveRevision;
  // ACT: 同页保存按顺序完成，防止慢请求覆盖后续修改；不处理多个客户端的并发编辑。
  saving = saving.then(async () => {
    try {
      await useWorkspaceFiles(directory).writeJson(fileName, { toonflowCanvas: true, nodes: flow.nodes, edges: flow.edges, viewport: flow.viewport });
      saveError = undefined;
      canvasSaveError.value = "";
      if (revision === saveRevision) canvasDirty.value = false;
    } catch (err) {
      saveError = err;
      canvasSaveError.value = axios.isAxiosError<{ message?: string }>(err) ? err.response?.data.message || err.message : err instanceof Error ? err.message : "画布保存失败";
      ElMessage.error(
        axios.isAxiosError<{ message?: string }>(err)
          ? err.response?.data.message || "画布保存失败"
          : err instanceof Error
          ? err.message
          : "画布保存失败"
      );
    }
  });
}, 500);

function scheduleCanvasSave() {
  if (saveCancelled) return;
  canvasDirty.value = true;
  saveRevision++;
  if (savePaused) {
    changedWhilePaused = true;
    return;
  }
  const directory = project.value?.directory;
  if (directory && canvasId.value) saveCanvas(directory, canvasId.value);
}

function scheduleCanvasChange() {
  scheduleCanvasSave();
  canvasHistory.record();
}

const elementSaveWatchers = new Map<Node | Edge, () => void>();
const nodeRuntimeFields = new Set([
  "data",
  "computedPosition",
  "handleBounds",
  "selected",
  "dimensions",
  "isParent",
  "resizing",
  "dragging",
  "events",
]);
const edgeRuntimeFields = new Set(["data", "selected", "sourceNode", "targetNode", "sourceX", "sourceY", "targetX", "targetY", "events"]);
// ACT: 仅增删、替换元素时扫描列表；位移与 data 各自监听，单个节点变化不遍历其余节点。
watch(
  () => [...flow.nodes.value, ...flow.edges.value],
  (elements) => {
    const current = new Set<Node | Edge>(elements);
    for (const [element, stop] of elementSaveWatchers) {
      if (!current.has(element)) {
        stop();
        elementSaveWatchers.delete(element);
      }
    }
    for (const element of elements) {
      if (elementSaveWatchers.has(element)) continue;
      // 与 toObject 排除的运行态字段保持一致，其他自定义持久字段仍参与自动保存。
      const runtimeFields = isNode(element) ? nodeRuntimeFields : edgeRuntimeFields;
      const stopFields = watch(
        () =>
          Object.keys(element)
            .filter((key) => !runtimeFields.has(key))
            .map((key) => Reflect.get(element, key)),
        scheduleCanvasChange,
        { deep: true, flush: "post" }
      );
      const stopData = watch(() => element.data, scheduleCanvasSave, { deep: true, flush: "post" });
      const stopName = isNode(element)
        ? watch(
            () => element.data?.label,
            () => canvasHistory.record(),
            { flush: "post" }
          )
        : () => {};
      elementSaveWatchers.set(element, () => {
        stopFields();
        stopData();
        stopName();
      });
    }
    scheduleCanvasChange();
  },
  { immediate: true, flush: "post" }
);
onScopeDispose(() => elementSaveWatchers.forEach((stop) => stop()));
watch(() => [viewport.value.x, viewport.value.y, viewport.value.zoom], scheduleCanvasSave, { flush: "post" });

watch(
  [() => project.value?.directory, canvasId],
  ([directory, fileName], [previousDirectory, previousFileName]) => {
    if (directory !== previousDirectory) {
      workspaceController.abort(new Error("工作区已切换，本轮画布操作已停止"));
      workspaceController = new AbortController();
    }
    edgeDisconnect.value = undefined;
    dragCopy = undefined;
    pointerPosition = undefined;
    resetCanvasKeys();
    // 同一实例只在重新装载画布时失效；重命名仅更新保存路径。
    if (directory !== previousDirectory || !fileName || !previousFileName) {
      canvasController.abort(new Error("画布已重新加载，本次画布调用已停止"));
      canvasController = new AbortController();
    }
    if (!savePaused) saveCanvas.flush();
  },
  { flush: "sync" }
);

// ACT: 切换显示面板不会卸载画布；仅清理交互，不中断本轮工具调用。
watch(() => props.active, (active) => {
  if (!active) assetsVisible.value = false;
  edgeDisconnect.value = undefined;
  dragCopy = undefined;
  pointerPosition = undefined;
  resetCanvasKeys();
}, { flush: "sync" });

function flushCanvasSave(action?: () => Promise<void>): Promise<void> {
  // ACT: 完整保存及其文件操作串行执行，重命名暂停期间的显式保存也必须等待。
  const next = flushing.then(() => saveCanvasState(action)).then(() => { canvasSaveError.value = ""; }, error => {
    canvasSaveError.value = axios.isAxiosError<{ message?: string }>(error) ? error.response?.data.message || error.message : error instanceof Error ? error.message : "画布保存失败";
    throw error;
  });
  flushing = next.catch(() => {});
  return next;
}

async function saveCanvasState(action?: () => Promise<void>) {
  if (saveCancelled) throw new Error("画布保存已取消");
  await Promise.all(flow.getNodes.value.map((node) => useNodeEvent(node.id, flow).emit("save")));
  await nextTick();
  if (saveCancelled) throw new Error("画布保存已取消");
  if (saveError && project.value?.directory && canvasId.value) saveCanvas(project.value.directory, canvasId.value);
  if (action) savePaused = true;
  try {
    let revision: number;
    do {
      if (saveCancelled) throw new Error("画布保存已取消");
      revision = saveRevision;
      if (changedWhilePaused && project.value?.directory && canvasId.value) {
        saveCanvas(project.value.directory, canvasId.value);
        changedWhilePaused = false;
      }
      saveCanvas.flush();
      await saving;
      if (saveError) throw saveError;
      // 画布写入期间节点可能完成生成，等新增落盘后重新保存变化。
      await Promise.all(flow.getNodes.value.map((node) => useNodeEvent(node.id, flow).emit("save")));
      await nextTick();
    } while (revision !== saveRevision);
    if (saveCancelled) throw new Error("画布保存已取消");
    await action?.();
  } finally {
    if (action && !saveCancelled) {
      savePaused = false;
      if (changedWhilePaused && project.value?.directory && canvasId.value) saveCanvas(project.value.directory, canvasId.value);
      changedWhilePaused = false;
    }
  }
}

function cancelCanvasSave() {
  saveCancelled = true;
  savePaused = true;
  changedWhilePaused = false;
  saveCanvas.cancel();
}
function canUseCanvasClipboard(event: Event) {
  const target = event.target;
  return props.active && !event.defaultPrevented && !props.settingsVisible && !!canvasId.value && !!project.value?.directory
    && target instanceof Element
    && !target.closest("input, textarea, select, button, [contenteditable]:not([contenteditable='false']), [role='textbox'], [role='slider'], [role='dialog'], #agentPanel")
    && (target === document.body || target === document.documentElement || canvasElement.value?.contains(target));
}

function beforeClipboard(event: Event) {
  if (!canUseCanvasClipboard(event)) return;
  if (event.type === "beforecopy" && (!flow.getSelectedNodes.value.length || window.getSelection()?.toString())) return;
  // ACT: WKWebView 通过 beforecopy/beforepaste 判定非输入区能否使用原生编辑菜单。
  event.preventDefault();
}

function copyNode(event: ClipboardEvent) {
  if (!canUseCanvasClipboard(event) || !flow.getSelectedNodes.value.length || window.getSelection()?.toString()) return;
  event.preventDefault();
  void copySelectedNodes();
}

function imageOutput(data: { outputs?: Record<string, NodeOutput | undefined> } | undefined) {
  for (const output of Object.values(data?.outputs ?? {})) {
    if (output?.dataType !== "IMAGE" || !output.value || typeof output.value !== "object") continue;
    if (typeof output.value.url === "string" && output.value.url) return output.value;
  }
}

async function copyImageNodeToClipboard(directory: string, node: Parameters<typeof copyNodeToClipboard>[0]) {
  const output = imageOutput(node.data);
  if (!output) return false;
  const content = await useWorkspaceFiles(directory).read(output.url);
  await writeClipboardImage(new Blob([content], { type: output.mimeType || "image/png" }));
  return true;
}

async function copySelectedNodes() {
  if (copyingNodes || !project.value?.directory) return;
  const nodes = getSelectionTree(flow.getSelectedNodes.value, flow.getNodes.value);
  if (!nodes.length) return;
  const directory = project.value.directory;
  const signal = canvasController.signal;
  copyingNodes = true;
  try {
    if (nodes.length === 1 && await copyImageNodeToClipboard(directory, { data: nodes[0]!.data ?? {} })) {
      ElMessage.success("已复制图片");
      return;
    }
    const ids = new Set(nodes.map(node => node.id));
    const snapshot = toObject();
    const savedNodes = new Map(snapshot.nodes.map(node => [node.id, node]));
    const copies = await Promise.all(nodes.map(async node => {
      const patch = await useNodeEvent(node.id, flow).emit("copy");
      const saved = savedNodes.get(node.id)!;
      const parentNode = ids.has(saved.parentNode ?? "") ? saved.parentNode : undefined;
      return { ...saved, data: { ...saved.data, ...patch }, parentNode,
        ...(saved.parentNode && !parentNode ? { extent: undefined, expandParent: false } : {}),
        position: parentNode ? { ...saved.position } : { x: node.computedPosition.x, y: node.computedPosition.y } };
    }));
    signal.throwIfAborted();
    if (nodes.some(node => findNode(node.id) !== node)) throw new Error("节点已变化，请重新复制");
    const edges = snapshot.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target));
    await copyNodesToClipboard(copies, edges, directory);
  } catch (error) {
    if (!signal.aborted) ElMessage.error(error instanceof Error ? error.message : "节点复制失败");
  } finally {
    copyingNodes = false;
  }
}

async function pasteNode(event: ClipboardEvent) {
  if (!canUseCanvasClipboard(event)) return;
  const text = event.clipboardData?.getData("text/plain") ?? "";
  if (nodeClipboardCommand.test(text)) {
    event.preventDefault();
    await pasteNodeAtCenter(text);
    return;
  }
  const canvasSignal = canvasController.signal;
  let files = getClipboardMediaFiles(event);
  if (files.length || text.trim()) event.preventDefault();
  // ACT: 部分 WebView 不向 paste 事件暴露剪贴板文件，桌面端回退到原生剪贴板读取。
  if (!files.length && isDesktop) files = await readClipboardFiles().catch(() => []);
  if (canvasSignal.aborted) return;
  if (!files.length && text.trim()) files = [new File([text], "粘贴文本.txt", { type: "text/plain" })];
  if (!files.length) return;
  event.preventDefault();
  const position = pastePosition();
  if (position) await importCanvasContent(files, position);
}

function pastePosition() {
  const rect = canvasElement.value?.getBoundingClientRect();
  if (!rect) return;
  const point = pointerPosition && pointerPosition.x >= rect.left && pointerPosition.x <= rect.right && pointerPosition.y >= rect.top && pointerPosition.y <= rect.bottom
    ? pointerPosition
    : { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  return screenToFlowCoordinate(point);
}

async function pasteNodeAtCenter(command?: string) {
  const position = pastePosition();
  if (position) await pasteClipboardNode(position, command);
}

async function importCanvasContent(files: File[], position: { x: number; y: number }) {
  const directory = project.value?.directory;
  if (!directory) return false;
  const canvasSignal = canvasController.signal;
  try {
    await canvasHistory.batch(() => importCanvasFiles(files, position, { directory, availableNodes: availableNodes.value, signal: canvasSignal, flow }));
    return true;
  } catch (error) {
    if (!canvasSignal.aborted) ElMessage.error(error instanceof Error ? error.message : "剪贴板内容导入失败");
    return false;
  }
}

async function pasteClipboardNode(position: { x: number; y: number }, command?: string) {
  if (!props.active || !canvasId.value || !project.value?.directory) return false;
  const canvasSignal = canvasController.signal;
  try {
    const directory = project.value.directory;
    const text = command ?? (await readClipboardText());
    const snapshot = await readClipboardNodes(text, directory);
    if (canvasSignal.aborted) return false;
    if (snapshot) {
      if (snapshot.nodes.some(node => !["canvasGroup", "productionMedia"].includes(node.type || "") && !availableNodes.value.some(item => item.type === node.type))) {
        throw new Error("请先安装并启用对应的节点插件");
      }
      const ids = new Map(snapshot.nodes.map(node => [node.id, crypto.randomUUID()]));
      const roots = snapshot.nodes.filter(node => !node.parentNode);
      const left = Math.min(...roots.map(node => node.position.x));
      const top = Math.min(...roots.map(node => node.position.y));
      await canvasHistory.batch(async () => {
        flow.removeSelectedElements();
        addNodes(snapshot.nodes.map(node => ({ ...node, id: ids.get(node.id)!, parentNode: ids.get(node.parentNode ?? ""), selected: true,
          position: node.parentNode ? node.position : { x: position.x + node.position.x - left, y: position.y + node.position.y - top } })));
        await nextTick();
        if (canvasSignal.aborted) return;
        addEdges(snapshot.edges.map(edge => ({ ...edge, id: crypto.randomUUID(), source: ids.get(edge.source)!, target: ids.get(edge.target)! })));
      });
      return true;
    }
    const files = await readClipboardFiles().catch((error): File[] => {
      if (text.trim()) return [];
      throw error;
    });
    if (canvasSignal.aborted) return false;
    if (!files.length && text.trim()) files.push(new File([text], "粘贴文本.txt", { type: "text/plain" }));
    if (!files.length) throw new Error("剪贴板中没有可粘贴的节点、文本、图片、视频或音频");
    return await importCanvasContent(files, position);
  } catch (error) {
    const pasteShortcut = generalSettings.value.canvasShortcuts.paste;
    const clipboardMessage = getShortcutBindings(pasteShortcut).some(binding => /^(Ctrl|Meta)\+KeyV$/.test(binding))
      ? `无法读取剪贴板，请在画布上按 ${shortcutLabel(pasteShortcut)} 粘贴`
      : "无法读取剪贴板，请允许浏览器访问剪贴板";
    if (!canvasSignal.aborted)
      ElMessage.error(
        error instanceof DOMException && error.name === "NotAllowedError" ? clipboardMessage : error instanceof Error ? error.message : "剪贴板内容粘贴失败"
      );
    return false;
  }
}
function zoomCanvas(event: WheelEvent | (Event & { scale: number })) {
  if (event.type === "gestureend") gestureScale = undefined;
  if (!props.active || props.settingsVisible || document.fullscreenElement || flow.userSelectionActive.value) return;
  if (!(event.target instanceof Element) || !event.target.closest(".vue-flow__pane, .vue-flow__node, .vue-flow__edge, .vue-flow__nodesselection")) return;
  let factor: number;
  let point = pointerPosition;
  if ("scale" in event) {
    if (!Number.isFinite(event.scale) || event.scale <= 0) return;
    factor = event.type === "gesturechange" && gestureScale !== undefined ? event.scale / gestureScale : 1;
    gestureScale = event.type === "gestureend" ? undefined : event.scale;
  } else {
    // ACT: Chromium 捏合发送 Ctrl+wheel，但不发送 Control 按键；WebKit 使用上方原生 gesture 事件。
    const pinching = event.ctrlKey && !pressedCodes.has("ControlLeft") && !pressedCodes.has("ControlRight");
    // 无需按键的滚轮缩放让节点控件保留自己的滚动；显式缩放快捷键及捏合仍沿用原行为。
    if (defaultWheelZoom.value && !pinching && !zoomKeyPressed.value
      && event.target.closest(".nowheel, input, textarea, select, [contenteditable]:not([contenteditable='false']), [role='slider']")) return;
    if (!pinching && !shortcutPressed(event, generalSettings.value.canvasShortcuts.zoom, pressedCodes)) {
      if (!event.ctrlKey) return;
      // 实体 Ctrl 未绑定缩放时，阻止 Vue Flow 和节点骨架将它误判为捏合。
      factor = 1;
    } else {
      factor = pinching && gestureScale !== undefined ? 1 : 2 ** (pinching ? -event.deltaY * 0.02 : wheelDelta(event));
    }
    point = { x: event.clientX, y: event.clientY };
  }
  const zoom = flow.d3Zoom.value;
  const selection = flow.d3Selection.value;
  if (!zoom || !selection) return;
  event.preventDefault();
  event.stopPropagation();
  if (factor === 1) return;
  const bounds = selection.node()?.getBoundingClientRect();
  if (!bounds) return;
  point ??= { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 };
  selection.call<[number, [number, number], Event]>(zoom.scaleBy, factor, [point.x - bounds.left, point.y - bounds.top], event);
}

function updateCanvasSelection(event: MouseEvent | KeyboardEvent) {
  // 失焦期间可能漏掉修饰键；不能在按下到抬起之间改变已命中的选区，避免 click 落到画布清空选择。
  if (event.type === "pointerdown" && event.target instanceof Element && event.target.closest(".vue-flow__nodesselection-rect")) return;
  flow.multiSelectionActive.value = props.active && !props.settingsVisible && !handMode.value
    && shortcutPressed(event, generalSettings.value.canvasShortcuts.multiSelection, pressedCodes);
}

function updateCanvasKeys(event: KeyboardEvent) {
  if (event.type === "keydown") {
    pressedCodes.add(event.code);
  } else pressedCodes.delete(event.code);
  if (!props.active || props.settingsVisible) return resetCanvasKeys();
  const target = event.target;
  const shortcuts = generalSettings.value.canvasShortcuts;
  const inCanvas =
    target instanceof Element &&
    !target.closest("[role='dialog'], #agentPanel") &&
    (target === document.body || target === document.documentElement || canvasElement.value?.contains(target));
  // None 只配置默认鼠标手势，不能触发会禁用节点交互的临时抓手或节点内部缩放。
  zoomKeyPressed.value = !event.isComposing && shortcutPressed(event, getShortcutBindings(shortcuts.zoom).filter(binding => binding !== "None").join(" / "), pressedCodes);
  selectionKeyPressed.value = !event.isComposing && shortcutPressed(event, shortcuts.selection, pressedCodes);
  if (!selectionKeyPressed.value && !flow.userSelectionActive.value) flow.userSelectionRect.value = null;
  const editing =
    !(target instanceof Element) ||
    !!target.closest("input, textarea, select, button, [contenteditable]:not([contenteditable='false']), [role='textbox'], [role='slider']");
  panKeyPressed.value = !!inCanvas && !editing && !event.isComposing
    && shortcutPressed(event, getShortcutBindings(shortcuts.pan).filter(binding => binding !== "None").join(" / "), pressedCodes);
  updateCanvasSelection(event);
  if (event.type === "keyup" || event.defaultPrevented || event.isComposing || !inCanvas || editing) return;
  const action = ([
    "group", "mergeGroup", "ungroup", "addNode", "moveTool", "handTool", "arrange", "search",
    "delete", "copy", "paste", "undo", "redo", "zoomIn", "zoomOut", "fitView",
  ] as const).find((action) =>
    shortcutMatches(event, shortcuts[action])
  );
  if (!action) {
    const nativeClipboardKey = (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey
      && (event.code === "KeyV" || event.code === "KeyC" && flow.getSelectedNodes.value.length && !window.getSelection()?.toString());
    if (panKeyPressed.value || nativeClipboardKey) event.preventDefault();
    return;
  }
  if (!canvasId.value || !project.value?.directory) return;
  if (action === "copy" && (!flow.getSelectedNodes.value.length || window.getSelection()?.toString())) return;
  // 桌面快捷键直接复用原生剪贴板桥接；浏览器 Ctrl/Cmd+V 保留原生事件，避免额外读取权限。
  if (!isDesktop && action === "paste" && event.code === "KeyV" && (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey) return;
  event.preventDefault();
  if (event.repeat) return;
  if (action === "delete") {
    const nodes = [...flow.getSelectedNodes.value];
    const menu = nodeMenuRef.value;
    if (!menu || !nodes.some((node) => node.deletable !== false)) return;
    void canvasHistory
      .batch(() => menu.deleteSelection(nodes))
      .catch((error) => {
        ElMessage.error(error instanceof Error ? error.message : "节点删除失败");
      });
    return;
  }
  if (action === "copy") void copySelectedNodes();
  else if (action === "paste") void pasteNodeAtCenter();
  else if (action === "undo" || action === "redo") void changeHistory(action);
  else if (action === "group" || action === "mergeGroup" || action === "ungroup") {
    void selectionToolbarRef.value?.operate(action);
  } else if (action === "addNode") addNodeAtPointer();
  else if (action === "moveTool" || action === "handTool") selectedTool.value = action === "handTool" ? "hand" : "move";
  else if (action === "arrange") void canvasControlsRef.value?.arrangeNodes();
  else if (action === "search") nodeSearchRef.value?.open();
  else void flow[action]();
}

function resetCanvasKeys() {
  pressedCodes.clear();
  gestureScale = undefined;
  zoomKeyPressed.value = false;
  panKeyPressed.value = false;
  selectionKeyPressed.value = getShortcutBindings(generalSettings.value.canvasShortcuts.selection).includes("None");
  flow.multiSelectionActive.value = false;
  if (!flow.userSelectionActive.value) flow.userSelectionRect.value = null;
}

watch([() => props.active, () => props.settingsVisible, () => generalSettings.value.canvasShortcuts], resetCanvasKeys, { deep: true, flush: "sync", immediate: true });

function refreshInstalled(event: WindowEventMap["toonflow:plugin-installed"]) {
  if (event.detail.type === "node") void loadRemoteNodes(event.detail.name);
}

const refreshNodeConfig = () => { void loadRemoteNodes(); };

onMounted(() => {
  // 在捕获阶段同步修饰键，避免节点编辑器截断 keydown/keyup 后缩放状态丢失或卡住。
  window.addEventListener("keydown", updateCanvasKeys, true);
  window.addEventListener("keyup", updateCanvasKeys, true);
  window.addEventListener("blur", resetCanvasKeys);
  window.addEventListener("toonflow:plugin-installed", refreshInstalled);
  window.addEventListener("toonflow:node-config-updated", refreshNodeConfig);
  document.addEventListener("paste", pasteNode);
  document.addEventListener("copy", copyNode);
  document.addEventListener("beforecopy", beforeClipboard);
  document.addEventListener("beforepaste", beforeClipboard);
  void loadRemoteNodes();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", updateCanvasKeys, true);
  window.removeEventListener("keyup", updateCanvasKeys, true);
  window.removeEventListener("blur", resetCanvasKeys);
  window.removeEventListener("toonflow:plugin-installed", refreshInstalled);
  window.removeEventListener("toonflow:node-config-updated", refreshNodeConfig);
  document.removeEventListener("paste", pasteNode);
  document.removeEventListener("copy", copyNode);
  document.removeEventListener("beforecopy", beforeClipboard);
  document.removeEventListener("beforepaste", beforeClipboard);
  workspaceController.abort(new Error("工作区已关闭"));
  canvasController.abort(new Error("画布已关闭"));
  saveCanvas.flush();
  loadRequest++;
});

const nodeWindow = window as typeof window & {
  toonflowNodeHost?: { vue: typeof vueRuntime; vueFlow: typeof vueFlowRuntime; elementPlus: typeof elementPlusRuntime; three: typeof threeRuntime; ai: { runAgentLoop: typeof runAgentLoop; createAssistantMessageEventStream: typeof createAssistantMessageEventStream } };
  toonflowNodes?: NodeTypesObject;
};
nodeWindow.toonflowNodeHost = { vue: vueRuntime, vueFlow: vueFlowRuntime, elementPlus: elementPlusRuntime, three: threeRuntime, ai: { runAgentLoop, createAssistantMessageEventStream } };
provide("nodeConfig", (nodeType: string) => nodeConfigs.value[nodeType] ?? {});
provide("workspaceFiles", () => {
  const directory = project.value?.directory;
  if (!directory) throw new Error("请先选择工作目录");
  return useWorkspaceFiles(directory);
});
provide("workspaceDirectory", () => {
  const directory = project.value?.directory;
  if (!directory) throw new Error("请先选择工作目录");
  return directory;
});
provide("reloadRemoteNode", (type: string) => {
  const name = type.replace(/^remote-/, "");
  if (!type.startsWith("remote-") || !/^[a-z][a-zA-Z0-9]*$/.test(name)) throw new Error("节点类型无效");
  return loadNode(name, `/api/nodes/files?name=${name}`, true);
});

async function loadNode(name: string, url: string, force = false): Promise<void> {
  const nodeType = `remote-${name}`;
  const signal = canvasController.signal;
  const pending = nodeLoads.get(nodeType);
  if (pending) {
    if (!force) return pending;
    await pending.catch(() => {});
  }
  if (!force && nodeTypes.value[nodeType] && !nodeErrors.value[nodeType]) return;
  if (force) {
    signal.throwIfAborted();
    // ACT: 复用画布修订号收敛等待期间的编辑；持续修改画布时延后刷新，不额外维护节点修订状态。
    let revision: number;
    do {
      revision = saveRevision;
      await Promise.all(flow.getNodes.value.filter(node => node.type === nodeType).map(node => useNodeEvent(node.id, flow).emit("save", "reload")));
      await nextTick();
      signal.throwIfAborted();
    } while (revision !== saveRevision);
    const loading = nodeLoads.get(nodeType);
    if (loading) return loading;
  }
  delete nodeErrors.value[nodeType];
  const nodeLoad = loadNodeComponent(name, url, force)
    .then((remoteNode) => {
      // 同类型节点共享组件，运行错误由每个节点自己的边界显示。
      nodeTypes.value = { ...nodeTypes.value, [nodeType]: markRaw(remoteNode) };
    })
    .catch((error) => {
      nodeErrors.value[nodeType] = error instanceof Error ? error.message : String(error);
      throw error;
    })
    .finally(() => nodeLoads.delete(nodeType));
  nodeLoads.set(nodeType, nodeLoad);
  return nodeLoad;
}

async function loadRemoteNodes(reloadName?: string) {
  if (reloadName) nodeReloads.add(reloadName);
  const requestId = ++loadRequest;
  const signal = canvasController.signal;
  nodeListLoading.value = true;
  try {
    const { data } = await axios.get<{ code: number; data: { name: string; displayName: string; url: string; enabled?: boolean; config?: Record<string, unknown> }[] }>(
      "/api/nodes/get",
      { headers: { "Cache-Control": "no-cache", "x-toonflow-workspace": "1" } }
    );
    if (requestId !== loadRequest) return;
    if (data.code !== 200 || !Array.isArray(data.data)) throw new Error("节点列表格式错误");
    const nodes = data.data.filter(node => {
      if (!node || typeof node.name !== "string" || !/^[a-z][a-zA-Z0-9]*$/.test(node.name) || node.url !== `/api/nodes/files?name=${node.name}`) {
        console.error("节点地址无效", node);
        return false;
      }
      return true;
    });
    nodeConfigs.value = Object.fromEntries(nodes.map(node => [`remote-${node.name}`, node.config ?? {}]));
    const enabledNodes = nodes.filter(node => node.enabled !== false);
    // 节点各自加载完成后即可出现在菜单中，不等待其他节点的脚本。
    nodeOptions.value = enabledNodes.map(node => ({ type: `remote-${node.name}`, label: node.displayName }))
      .sort((left, right) => left.type.localeCompare(right.type));
    // ACT: 安装事件合并到最新列表请求，避免连续更新不同节点时丢失较早的刷新名称。
    const reloadNames = new Set(nodeReloads);
    nodeReloads.clear();
    await Promise.all(
      enabledNodes.map(async (node) => {
        const nodeType = `remote-${node.name}`;
        try {
          if (nodeTypes.value[nodeType] && !nodeErrors.value[nodeType] && !reloadNames.has(node.name)) return;
          await loadNode(node.name, node.url, reloadNames.has(node.name));
        } catch (error) {
          console.error("加载远端节点失败", node, error);
          // 保存拒绝时旧组件仍可用，不从节点菜单中移除；脚本加载错误仍排除。
          if (nodeTypes.value[nodeType] && !nodeErrors.value[nodeType]) {
            if (reloadNames.has(node.name) && !signal.aborted) ElMessage.warning({
              message: `${node.displayName}已安装，但当前节点无法刷新。请等待任务结束后，点击节点右上角的刷新按钮。`,
              grouping: true,
            });
          }
        }
      })
    );
  } catch (error) {
    if (requestId === loadRequest) console.error("获取远端节点列表失败", error);
  } finally {
    if (requestId === loadRequest) nodeListLoading.value = false;
  }
}

const defaultEdgeOptions = markRaw({
  type: "simple-bezier",
  animated: false,
  class: ({ sourceNode, targetNode }: GraphEdge) => {
    if (!sourceNode.selected && !sourceNode.dragging && !targetNode.selected && !targetNode.dragging) return "";
    return ["edgeNodeActive", generalSettings.value.canvasEdgeColorMode !== "none" && "edgeActive", generalSettings.value.canvasEdgeAnimationEnabled && "animated"].filter(Boolean).join(" ");
  },
  focusable: false,
  selectable: false,
  updatable: false,
  interactionWidth: 40,
});
</script>

<style lang="scss" scoped>
.canvas {
  width: 100%;
  height: 100%;

  &.compositingEnabled :deep(.vue-flow__transformationpane) {
    will-change: transform;
  }

  &.handMode :deep(.vue-flow__transformationpane),
  &.handMode :deep(.vue-flow__transformationpane *) {
    pointer-events: none !important;
  }

  &.handMode :deep(.vue-flow__pane) {
    cursor: grab;
  }

  &.edgesHidden :deep(.vue-flow__edges:not(:has(.edgeNodeActive))) {
    display: none;
  }
  &.edgesHidden :deep(.vue-flow__handle:not(.connectedNodeActive)) {
    // Vue Flow 仍会测量隐藏端口，必须保留布局以免零尺寸污染连线坐标。
    visibility: hidden !important;
  }

  :deep(.vue-flow__edge.edgeActive .vue-flow__edge-path) {
    stroke: var(--canvasEdgeColor);
  }

  &:has(.selectionConnection) :deep(.vue-flow__node:not(.selected) .nodeHandle.target .handleIcon) {
    opacity: 1;
  }

  :deep(.vue-flow__nodesselection-rect) {
    box-sizing: content-box;
    padding: 8px;
    margin: -8px;
    border-radius: 4px;
  }

  &.multiSelectionMode :deep(.vue-flow__nodesselection-rect) {
    pointer-events: none;
  }
}
.edgeDisconnect {
  position: fixed;
  z-index: 1000;
  width: 32px;
  height: 32px;
  padding: 0;
  transform: translate(-50%, -50%);
}
</style>
