<template>
  <el-container class="home">
    <el-aside class="homeSidebar" width="252px">
      <button class="sidebarBrand" type="button" aria-label="回到创作首页" @click="selectCreationMode('prompt')">
        <span class="sidebarGlyph" aria-hidden="true"><icon-movie :size="19" /></span>
        <span>创作工作室<small>AI CREATIVE STUDIO</small></span>
      </button>
      <nav class="sidebarNav" aria-label="工作区导航">
        <span class="navCaption">创作工作室</span>
        <button class="navItem" :class="{ active: homeSection === 'create' && creationMode === 'prompt' }" type="button" @click="selectCreationMode('prompt')"><icon-sparkles :size="18" />创作</button>
        <button class="navItem" :class="{ active: homeSection === 'create' && creationMode === 'marketing' }" type="button" @click="selectCreationMode('marketing')"><icon-speakerphone :size="18" />营销 Agent</button>
        <button class="navItem" :class="{ active: homeSection === 'create' && creationMode === 'script' }" type="button" @click="selectCreationMode('script')"><icon-movie :size="18" />短剧 Agent</button>
        <button class="navItem" type="button" @click="createBlankCanvas"><icon-layout-grid :size="18" />创建画布</button>
        <button class="navItem" :class="{ active: homeSection === 'dreamina' }" type="button" @click="router.push('/home?section=dreamina')"><icon-layout-grid :size="18" />即梦生成</button>
        <span class="navDivider" />
        <span class="navCaption">项目</span>
        <button class="navItem" :class="{ active: homeSection === 'projects' }" type="button" @click="showProjects"><icon-folder :size="18" />项目资源</button>
        <button class="navItem" :class="{ active: homeSection === 'assets' }" type="button" @click="scrollToProjects"><icon-folder-open :size="18" />资产库</button>
        <button class="navItem" :class="{ active: homeSection === 'skills' }" type="button" @click="showSkills"><icon-book :size="18" />技能</button>
        <div class="sidebarRecent">
          <span class="navCaption">最近打开</span>
          <button v-for="project in sortedProjects.slice(0, 4)" :key="project.directory" class="recentItem" type="button" :title="project.name" @click="openProject(project)">
            <span class="recentIcon"><icon-folder :size="16" /></span><span>{{ project.name }}</span>
          </button>
          <button v-for="item in sortedDramaForgeProjects.slice(0, Math.max(0, 4 - sortedProjects.length))" :key="`recent-drama-${item.id}`" class="recentItem" type="button" :title="item.name" @click="openDramaForgeProject(item)">
            <span class="recentIcon drama"><icon-movie :size="16" /></span><span>{{ item.name || `短剧项目 ${item.id}` }}</span>
          </button>
        </div>
      </nav>
      <div class="sidebarFooter">
        <div class="sidebarFooterActions">
          <el-badge isDot :hidden="!hasDesktopUpdate"><el-button text :icon="IconSettings" :aria-label="hasDesktopUpdate ? '设置，有新版本可用' : '设置'" @click="settingsVisible = true">设置</el-button></el-badge>
          <el-button text :type="deviceHubEnabled ? 'success' : undefined" :icon="deviceHubEnabled || mobileConnection.mode === 'remote' ? IconDeviceDesktop : IconQrcode" @click="mobileConnectVisible = true">{{ mobileConnectionLabel }}</el-button>
        </div>
      </div>
    </el-aside>
    <el-container class="homeShell">
      <el-header class="pageHeader">
        <div class="headerBreadcrumb"><span>工作空间</span><span class="breadcrumbSlash">/</span><strong>{{ homeSection === 'dreamina' ? '即梦生成' : homeSection === 'projects' ? '项目资源' : homeSection === 'assets' ? '资产库' : homeSection === 'skills' ? '技能' : creationMode === 'script' ? '短剧工作室' : creationMode === 'marketing' ? '营销 Agent' : '创作' }}</strong></div>
      </el-header>
      <el-main class="pageContent">
      <dreaminaCanvas v-if="homeSection === 'dreamina'" :key="String(router.currentRoute.value.query.projectId || '')" :localProjectId="Number(router.currentRoute.value.query.projectId) > 0 ? Number(router.currentRoute.value.query.projectId) : undefined" />
      <assetLibrary v-else-if="homeSection === 'assets'" @openProject="openLibraryProject" />
      <skillLibrary v-else-if="homeSection === 'skills'" @select="selectLibrarySkill" />
      <template v-else>
      <section v-if="homeSection === 'create'" class="creationPanel" :class="{ conversationActive: activeStudioConversation }" aria-label="创建项目">
        <div v-if="creationMode === 'script' && !activeStudioConversation" class="studioTitle scriptStudioTitle">短剧工作室</div>
        <div v-else-if="creationMode !== 'script'" class="studioTitle">
          <span>开启</span>
          <div class="creationModes" role="tablist" aria-label="创作方式">
            <button type="button" role="tab" :aria-selected="creationMode === 'prompt'" :class="{ active: homeSection === 'create' && creationMode === 'prompt' }" @click="selectCreationMode('prompt')">创作</button>
            <button type="button" role="tab" :aria-selected="creationMode === 'marketing'" :class="{ active: homeSection === 'create' && creationMode === 'marketing' }" @click="selectCreationMode('marketing')">营销</button>
            <button type="button" role="tab" :aria-selected="false" @click="selectCreationMode('script')">短剧</button>
          </div>
          <span>Agent，将创意变成视频</span>
        </div>
        <p v-if="!activeStudioConversation" class="studioSubtitle">{{ creationMode === 'script' ? '你的 AI 故事工作室，分析剧本后进入画布继续创作。' : creationMode === 'marketing' ? '描述产品、受众和目标，构思营销内容。' : '描述你的创意，开始创作。' }}</p>
        <div v-if="creationMode !== 'script'" class="promptArea">
          <el-card class="promptCard" :class="{ draggingAttachments }" shadow="never" :bodyStyle="{ padding: '20px' }" :footerStyle="{ padding: '12px 16px' }" @dragenter.capture="dragEnterAttachments" @dragover.capture="dragOverAttachments" @dragleave.capture="dragLeaveAttachments" @drop.capture="dropAttachments">
            <div v-if="draggingAttachments" class="attachmentDropOverlay" role="status" aria-live="polite">
              <icon-paperclip :size="20" aria-hidden="true" />
              <strong>松开添加附件</strong>
              <span>图片、视频、文档或代码文件</span>
            </div>
            <input ref="attachmentInput" type="file" :accept="attachmentAccept" multiple hidden :disabled="creating || opening" @change="selectAttachments" />
            <attachmentList v-if="promptAttachments.length" class="promptAttachments" :attachments="promptAttachments" removable restorable :disabled="creating || opening" @remove="promptAttachments.splice($event, 1)" @restore="restoreAttachment" />
            <el-input ref="promptInput" v-model="prompt" type="textarea" :rows="4" resize="none" :disabled="creating || opening" :placeholder="creationMode === 'marketing' ? '描述产品或服务、目标人群和推广目标……' : promptPlaceholder" :aria-label="creationMode === 'marketing' ? '营销创意描述' : '创作描述'" @paste.capture="pasteAttachments" />
            <template #footer>
              <div class="composerFooter">
                <div class="composerTools">
                  <el-select v-model="creationEngine" class="creationEngine" aria-label="创作智能体" :disabled="creating || opening || pippitBusy"><el-option label="工作室智能体" value="studio" /><el-option label="Pippit 海外创作" value="pippit" /></el-select>
                  <workspacePicker v-if="creationEngine === 'studio'" ref="promptWorkspacePicker" v-model="workspaceDirectory" :disabled="creating || opening" />
                  <el-button text circle :icon="IconPaperclip" :disabled="creating || opening" aria-label="添加附件" title="添加附件" @click="attachmentInput?.click()" />
                  <span v-if="creationEngine === 'studio'" class="skillControl"><skillMenu ref="homeSkillMenu" :directory="workspaceDirectory" :active="true" :disabled="creating || opening" @select="insertSkill" /><span>技能</span></span>
                  <span class="toolDivider" />
                  <span v-if="creationEngine === 'pippit'" class="engineHint">技能与模型由 Pippit 自动编排</span>
                  <modelPopover v-else v-model="selectedModel" v-model:reasoningEffort="reasoningEffort" class="modelSelect" :disabled="creating || opening" />
                  <el-button v-if="creationEngine === 'studio'" class="canvasToggle" text :aria-pressed="openCanvasAfterPrompt" @click="openCanvasAfterPrompt = !openCanvasAfterPrompt">画布 <el-switch v-model="openCanvasAfterPrompt" size="small" aria-label="创建后打开画布" /></el-button>
                </div>
                <el-space class="sendActions" wrap :size="12">
                  <el-button class="sendButton" type="primary" circle :icon="IconArrowUp" :loading="creating || pippitBusy" :disabled="creating || opening || pippitBusy || (!prompt.trim() && !promptAttachments.length)" aria-label="开始创作" @click="startCreation">
                  </el-button>
                </el-space>
              </div>
              <p v-if="creationEngine === 'studio' && !workspaceDirectory" class="workspaceHint" role="status">请先选择一个空文件夹作为工作目录，画布和素材会保存在这里。</p>
            </template>
          </el-card>
        </div>
        <el-card v-else class="scriptComposer" shadow="never">
          <div class="scriptComposerTabs">
            <button v-for="tab in studioTabs" :key="tab.id" type="button" class="scriptComposerTab" :class="{ active: studioTab === tab.id }" @click="studioTab = tab.id">{{ tab.name }}</button>
            
          </div>
          <div v-if="studioTab === 'upload'">
          <input ref="scriptFileInput" type="file" accept=".txt,text/plain" hidden :disabled="scriptCreating" @change="selectScriptFile" />
          <div
            class="scriptDropZone"
            :class="{ dragging: scriptDragging }"
            @dragenter.prevent="scriptDragging = true"
            @dragover.prevent
            @dragleave.prevent="scriptDragging = false"
            @drop.prevent="dropScriptFile">
            <template v-if="scriptInputMode === 'upload' && !scriptText">
              <div class="scriptUploadMark"><icon-movie :size="24" /></div>
              <div class="scriptUploadActions">
                <el-button class="scriptUploadButton" :disabled="scriptCreating" @click="scriptFileInput?.click()"><icon-arrow-up :size="16" />上传剧本</el-button>
                <el-button class="scriptPasteButton" :disabled="scriptCreating" @click="openScriptPaste">粘贴脚本</el-button>
              </div>
              <p>将 TXT 文件拖到此处，或直接粘贴剧本（最多 10 万字）</p>
            </template>
            <template v-else>
              <div class="scriptPasteHeader">
                <strong>{{ scriptFileName ? `已载入：${scriptFileName}` : '粘贴剧本' }}</strong>
                <el-button text :disabled="scriptCreating" @click="scriptInputMode = 'upload'; scriptText = ''; scriptFileName = ''">重新选择</el-button>
              </div>
              <el-input ref="scriptInput" v-model="scriptText" type="textarea" :rows="7" maxlength="100000" resize="vertical" :disabled="scriptCreating" aria-label="短剧剧本" placeholder="粘贴完整剧本或故事梗概……支持多集、场景和对白。" />
            </template>
          </div>
          <div class="scriptComposerOptions">
            <el-input v-model="scriptName" maxlength="80" placeholder="项目名称（可留空，自动识别）" aria-label="项目名称" :disabled="scriptCreating" />
            <creationPreferences v-model="scriptPreferences" mode="upload" :disabled="scriptCreating" />
            <el-input v-model="scriptModel" placeholder="沿用全局剧本模型" aria-label="剧本分析模型" :disabled="scriptCreating" />
          </div>
          <div class="scriptComposerFooter">
            <span>{{ scriptText.length.toLocaleString() }} 字 · 分析后进入画布，不会自动生成媒体</span>
            <el-button type="primary" :loading="scriptCreating" :disabled="!scriptText.trim()" @click="startScriptAnalysis">{{ scriptCreating ? '正在创建并分析…' : '开始分析' }}<icon-arrow-up v-if="!scriptCreating" :size="16" /></el-button>
          </div>
          <el-alert v-if="scriptError" class="scriptError" :title="scriptError" type="error" :closable="false" showIcon />
</div>
<div v-else-if="studioTab === 'canvas'" class="scriptDropZone"><strong>在创意画布中自由创作</strong><el-button @click="createBlankCanvas">创建空白画布</el-button></div>
<pippitConversation v-else v-model="pippitMessage" :mode="studioTab" :task="pippitTask" :snapshot="pippitSnapshot" :statusLabel="pippitStatusLabel" :busy="pippitBusy" :error="pippitError" :progress="pippitUploadProgress" :submissionVersion="pippitSubmissionVersion" @send="sendStudioMessage" @refresh="refreshStudioTask" @save="importStudioResults" @newSession="newStudioSession" />
        </el-card>
        <section v-if="creationMode === 'script' && studioTasks.length" class="pippitHistory">
          <h2>创作任务</h2><button v-for="task in studioTasks" :key="task.run_id" @click="restoreStudioTask(task)"><span>{{ task.message }}</span><small>{{ task.creativeOptions?.styleName ? task.creativeOptions.styleName + ' · ' : '' }}{{ pippitStatusNames[task.status] || task.status }}</small></button>
        </section>
      </section>
      <section v-if="homeSection === 'create' && creationMode !== 'script'" class="recommendations" aria-labelledby="recommendationsTitle">
        <div class="sectionHeader"><h2 id="recommendationsTitle">推荐创作</h2><span>从一个工作流快速开始</span></div>
        <div class="recommendationGrid">
          <button class="recommendationCard" type="button" @click="selectCreationMode('script')"><span class="recommendationIcon"><icon-movie :size="20" /></span><strong>短剧导演工作流</strong><small>剧本分析、人物连续性与镜头设计</small><icon-arrow-up-right class="recommendationArrow" :size="16" /></button>
          <button class="recommendationCard" type="button" @click="selectCreationMode('marketing')"><span class="recommendationIcon"><icon-speakerphone :size="20" /></span><strong>营销视频创意</strong><small>从产品与受众描述开始构思</small><icon-arrow-up-right class="recommendationArrow" :size="16" /></button>
          <button class="recommendationCard" type="button" @click="selectCreationMode('prompt')"><span class="recommendationIcon"><icon-photo :size="20" /></span><strong>角色与场景设计</strong><small>进入画布继续生成图像与视频</small><icon-arrow-up-right class="recommendationArrow" :size="16" /></button>
        </div>
      </section>
      <section id="recentProjects" class="projectList" aria-labelledby="projectListTitle">
        <div class="sectionHeader">
          <div><h2 id="projectListTitle">{{ homeSection === 'projects' ? '全部项目' : creationMode === 'script' ? '我的草稿' : '最近项目' }}</h2><span>{{ creationMode === 'script' ? '继续短剧创作' : '继续你的创作' }}</span></div>
          <el-space v-if="creationMode !== 'script'" wrap>
            <el-button :icon="IconFolderOpen" :disabled="creating || opening" @click="openProject()">导入项目</el-button>
            <el-button :icon="IconFolderPlus" :disabled="creating || opening" @click="createBlankCanvas">创建画布</el-button>
            <el-button circle :icon="sortDescending ? IconSortDescending : IconSortAscending" :aria-label="sortDescending ? '按时间降序' : '按时间升序'" @click="sortDescending = !sortDescending" />
            <el-radio-group v-model="viewMode" aria-label="项目视图">
              <el-radio-button value="grid" aria-label="网格视图"><icon-layout-grid :size="16" /></el-radio-button>
              <el-radio-button value="list" aria-label="列表视图"><icon-list :size="16" /></el-radio-button>
            </el-radio-group>
          </el-space>
        </div>
        <div class="projectItems" :class="{ listView: viewMode === 'list' }">
          <template v-if="creationMode !== 'script'">
          <el-card v-for="project in sortedProjects" :key="project.directory" class="projectCard" shadow="hover" :bodyStyle="{ padding: '0' }">
            <button class="projectEntry" type="button" :disabled="creating || opening" :aria-label="`打开项目 ${project.name}`" @click="openProject(project)">
              <icon-folder class="projectIcon" :size="28" aria-hidden="true" />
              <span class="projectInfo">
                <span class="projectName" :title="project.name">{{ project.name }}</span>
                <span class="projectPath" :title="project.directory">{{ project.directory }}</span>
                <span class="projectTime">最近打开 {{ new Date(project.lastOpenedAt).toLocaleString(locale, { hour12: false }) }}</span>
              </span>
            </button>
            <div class="projectActions">
              <el-button text :icon="IconEdit" :disabled="creating || opening" :aria-label="`重命名项目 ${project.name}`" title="重命名" @click="renameProject(project)" />
              <el-button text type="danger" :icon="IconFolderMinus" :disabled="creating || opening" :aria-label="`移除项目 ${project.name}`" title="从列表移除，不删除文件" @click="workspaceStore.removeProject(project.directory)" />
            </div>
          </el-card>
          </template>
          <el-card v-for="item in sortedDramaForgeProjects" :key="`dramaforge-${item.id}`" class="projectCard dramaProjectCard" shadow="hover" :bodyStyle="{ padding: '0' }">
            <button class="projectEntry" type="button" :disabled="creating || opening" :aria-label="`打开短剧项目 ${item.name}`" @click="openDramaForgeProject(item)">
              <icon-movie class="projectIcon" :size="28" aria-hidden="true" />
              <span class="projectInfo">
                <span class="projectName" :title="item.name">{{ item.name || `短剧项目 ${item.id}` }}</span>
                <span class="projectPath">{{ item.project_type === 'canvas' ? '画布项目' : '短剧创作' }} · {{ dramaForgeStatusLabel(item.status) }}</span>
                <span v-if="item.generation_settings?.creativePreferences?.styleName" class="projectPath">风格 · {{ item.generation_settings.creativePreferences.styleName }}</span>
                <span class="projectTime">创建于 {{ item.created_at ? new Date(item.created_at).toLocaleString(locale, { hour12: false }) : '时间未知' }}</span>
              </span>
            </button>
            <el-tag class="dramaProjectTag" size="small" effect="plain">{{ item.project_type === 'canvas' ? '画布' : '短剧' }}</el-tag>
            <div class="projectActions"><el-button text type="danger" :icon="IconFolderMinus" :disabled="creating || opening || deletingProjectId !== null" :loading="deletingProjectId === item.id" :aria-label="`删除项目 ${item.name}`" @click="deleteDramaForgeProject(item)">删除</el-button></div>
          </el-card>
        </div>
      </section>
      </template>
      </el-main>
    </el-container>
    <settings v-model="settingsVisible" />
    <mobileConnect v-model="mobileConnectVisible" />
    <workspacePicker ref="relocationPicker" hideTrigger />
  </el-container>
</template>

<script setup lang="ts">
import { locale, translate } from "@toonflow/i18n/vue";
import axios from "axios";
import { storeToRefs } from "pinia";
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type InputInstance } from "element-plus";
import { getReadableFileMimeType, readableFileAccept } from "@toonflow/server/documentFormats";
import {
  IconSettings, IconQrcode, IconDeviceDesktop,
  IconArrowUp, IconLayoutGrid,
  IconList, IconSortDescending,
  IconSortAscending, IconFolder, IconEdit,
  IconFolderMinus, IconFolderPlus, IconFolderOpen, IconPaperclip, IconMovie,
  IconSparkles, IconSpeakerphone, IconBook, IconPhoto,
} from "@tabler/icons-vue";
import modelPopover from "@/components/modelPopover.vue";
import skillMenu from "@/components/agent/skillMenu.vue";
import attachmentList from "@/components/agent/attachmentList.vue";
import { createPastedTextFile, readTextAttachment } from "@/components/agent/textAttachments";
import type { AgentAttachment } from "@/components/agent/types";
import { useWorkspaceStore, type Project } from "@/stores/workspace";
import { hasDesktopUpdate } from "@/stores/desktopUpdate";
import { deviceHubEnabled, mobileConnection, mobileConnectionLabel } from "@/lib/mobile";
import useWorkspaceFiles from "@/lib/workspaceFiles";
import settings from "@/components/settings/index.vue";
import assetLibrary from "./assetLibrary.vue";
import dreaminaCanvas from "./dreaminaCanvas.vue";
import pippitConversation from "./pippitConversation.vue";
import creationPreferences from "./creationPreferences.vue";
import skillLibrary from "./skillLibrary.vue";
import workspacePicker from "./workspacePicker.vue";

const settingsVisible = ref(false);
const mobileConnectVisible = ref(false);
const mobileConnect = defineAsyncComponent(() => import("@/components/mobileConnect.vue"));
const router = useRouter();
const homeSection = computed(() => { const section = router.currentRoute.value.query.section; return section === "projects" || section === "assets" || section === "skills" || section === "dreamina" ? section : "create"; });
const creationMode = ref<"prompt" | "marketing" | "script">("prompt");
const creationEngine = ref("studio");
const creating = ref(false);
const opening = ref(false);
const scriptText = ref("");
const scriptName = ref("");
const scriptAspectRatio = ref("9:16");
const scriptPreferences = ref({ styleId: 'none', customStyle: '', aspectRatio: '9:16', episodes: 10 });
watch(scriptPreferences, value => { scriptAspectRatio.value = value.aspectRatio; }, { deep: true });
const scriptModel = ref("");
const scriptCreating = ref(false);
const scriptError = ref("");
const studioTab = ref("upload");
const activeStudioConversation = computed(() => creationMode.value === 'script' && ['writer', 'remix'].includes(studioTab.value) && !!pippitTask.value);
const studioTabs = [{ id: "upload", name: "上传脚本" }, { id: "writer", name: "AI 编剧" }, { id: "canvas", name: "创意画布" }, { id: "remix", name: "重制转绘" }];
const pippitMessage = ref("");
const pippitUploadProgress = ref("");
const pippitSubmissionVersion = ref(0);
let pippitPollTimer: ReturnType<typeof setTimeout> | undefined;
let pippitStopped = false;
const pippitUploadedFiles = new WeakMap<File, string>();
const pippitBusy = ref(false);
const pippitResult = ref("");
type PippitTask = { thread_id: string; run_id: string; web_thread_link?: string; source?: 'local'; project_id?: number; shot_id?: number };
type StudioCreativeOptions = { styleId: string; customStyle: string; aspectRatio: string; episodes: number; modelId?: string; resolution?: string; duration?: number; outputKind?: string };
const localMediaRequestId = ref('');
const pippitTask = ref<PippitTask>();
const pippitError = ref("");
type StudioTask = PippitTask & { message: string; status: string; project_id?: number; creativeOptions?: { styleName?: string } };
const studioTasks = ref<StudioTask[]>([]);
async function loadStudioTasks() {
  try {
    const response = await fetch(dramaForgeApiUrl("pippit/tasks"));
    if (!response.ok) return;
    studioTasks.value = await response.json();
  } catch { /* A saved task can still be restored while the server is offline. */ }
}
async function restoreStudioTask(task: StudioTask) {
  if (pippitBusy.value) return;
  studioTab.value = "writer";
  const sameTask = pippitTask.value?.run_id === task.run_id;
  pippitTask.value = { thread_id: task.thread_id, run_id: task.run_id, web_thread_link: task.web_thread_link };
  pippitMessage.value = "";
  if (!sameTask) pippitResult.value = "";
  pippitBusy.value = true;
  pippitError.value = "";
  try {
    const response = await fetch(dramaForgeApiUrl(`pippit/tasks/${encodeURIComponent(task.run_id)}`));
    if (!response.ok) throw new Error("保存的会话读取失败");
    pippitResult.value = JSON.stringify(await response.json());
    saveStudioTask();
  } catch (error) { pippitError.value = error instanceof Error ? error.message : "读取失败"; }
  finally { pippitBusy.value = false; }
  scheduleStudioPoll();
}
async function importStudioResults() {
  if (!pippitTask.value || pippitBusy.value) return;
  if (pippitTask.value.source === 'local') { await router.push(`/workspace?dramaforgeProjectId=${pippitTask.value.project_id}`); return; }
  pippitBusy.value = true;
  pippitError.value = "";
  try {
    const result = await studioRequest("import", JSON.stringify(pippitTask.value));
    await fetchDramaForgeProjects();
    await loadStudioTasks();
    ElMessage.success(result.already_imported ? "此任务已保存，可在资产库查看" : "素材已保存到资产库和项目画布");
  } catch (error) { pippitError.value = error instanceof Error ? error.message : "保存素材失败"; }
  finally { pippitBusy.value = false; }
}
const pippitSnapshot = computed(() => {
  try { return JSON.parse(pippitResult.value || "{}"); } catch { return {}; }
});
const pippitStatusNames: Record<string, string> = { submitted: "任务已提交", queued: "任务排队中", pending: "任务等待中", running: "创作进行中", processing: "正在处理", in_progress: "创作进行中", completed: "会话已结束，请查看结果", success: "会话已结束，请查看结果", failed: "任务失败", requires_action: "等待你的回复", cancelled: "任务已取消" };
const pippitStatusLabel = computed(() => pippitStatusNames[pippitSnapshot.value.status] || "任务已提交，刷新查看进度");
function saveStudioTask() {
  try { localStorage.setItem("dramaForgePippitTask", JSON.stringify({ task: pippitTask.value, result: pippitResult.value, message: pippitMessage.value })); }
  catch { ElMessage.warning("浏览器未能保存任务记录，请保留 Pippit 会话链接"); }
}
async function studioRequest(path: string, body: BodyInit, json = true) {
  const response = await fetch(dramaForgeApiUrl(`pippit/${path}`), { method: "POST", headers: json ? { "Content-Type": "application/json" } : undefined, body });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Pippit 请求失败");
  return value;
}
async function startCreation() {
  if (creationEngine.value === "pippit") {
    if (!prompt.value.trim()) return ElMessage.warning("请描述创作需求");
    if (promptAttachments.value.some(item => !item.file || !/^(image|video)\//.test(item.mimeType))) return ElMessage.warning("Pippit 创作目前支持本次添加的图片、视频附件，请移除其他附件后重试");
    pippitMessage.value = prompt.value;
    await submitStudioTask();
    return;
  }
  if (workspaceDirectory.value) await createProject();
  else await promptWorkspacePicker.value?.chooseDirectory();
}
async function submitStudioTask(files?: File[], followup = false, options?: StudioCreativeOptions) {
  if (pippitBusy.value) return;
  if (studioTab.value === "remix" && !followup) {
    pippitError.value = "Pippit 官网专用重制转绘尚未接通：当前公开接口不能指定原片解析流程。本次不会上传视频、提交通用创作或扣除积分。";
    return;
  }
  if (!pippitMessage.value.trim()) return ElMessage.warning("请输入创作需求或回复");
  const fromHome = creationMode.value !== "script";
  const references = files || (fromHome ? promptAttachments.value.map(item => item.file!) : []);
  const types = ['image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/quicktime', 'video/webm'];
  if (references.length > 32 || references.some(file => !types.includes(file.type) || !file.size || file.size > 200 * 1024 * 1024)) return ElMessage.warning("最多添加 32 个 PNG/JPG/WEBP/MP4/MOV/WEBM，每个文件不超过 200 MB");
  pippitBusy.value = true;
  const confirmed = await ElMessageBox.confirm(options && studioTab.value === 'writer' && !followup && !options.outputKind ? `将按所选风格和比例创作 ${options.episodes} 集剧本文本，不生成图片或视频，可能消耗 Pippit 积分，是否继续？` : "将通过 Pippit 海外 API 提交，可能消耗账户积分，是否继续？", "提交创作", { confirmButtonText: "确认提交", cancelButtonText: "取消" }).then(() => true, () => false);
  if (!confirmed) { pippitBusy.value = false; scheduleStudioPoll(); return; }
  pippitError.value = "";
  try {
    const assetIds: string[] = [];
    for (const [index, reference] of references.entries()) {
      pippitUploadProgress.value = `正在上传参考素材 ${index+1}/${references.length} · ${reference.name}`;
      const cachedId = pippitUploadedFiles.get(reference);
      if (cachedId) { assetIds.push(cachedId); continue; }
      const form = new FormData(); form.append("file", reference);
      const uploaded = await studioRequest("upload", form, false);
      const assetId = uploaded.asset_id ?? uploaded.data?.asset_id;
      if (!assetId) throw new Error("上传未返回素材编号，请重试");
      assetIds.push(String(assetId));
      pippitUploadedFiles.set(reference, String(assetId));
    }
    pippitUploadProgress.value = "参考素材已就绪，正在提交创作请求…";
    const result = await studioRequest("submit", JSON.stringify({ message: pippitMessage.value, asset_ids: assetIds, thread_id: followup ? pippitTask.value?.thread_id : undefined, creativeOptions: options, creationMode: options ? options.outputKind || studioTab.value : '' }));
    const task = result.data ?? result;
    if (task.thread_id && task.run_id) pippitTask.value = { thread_id: task.thread_id, run_id: task.run_id, web_thread_link: task.web_thread_link };
    else throw new Error("接口未返回任务编号，请到 Pippit 检查任务，避免重复提交");
    pippitResult.value = JSON.stringify(result, null, 2);
    saveStudioTask();
    pippitMessage.value = "";
    pippitSubmissionVersion.value++;
    void loadStudioTasks();
    if (fromHome) { selectCreationMode("script"); studioTab.value = "writer"; }
  } catch (error) { pippitError.value = error instanceof Error ? error.message : "提交失败"; if (fromHome) ElMessage.error(pippitError.value); }
  finally { pippitBusy.value = false; pippitUploadProgress.value = ""; }
  scheduleStudioPoll();
}
async function refreshStudioTask() {
  if (!pippitTask.value || pippitBusy.value) return;
  pippitBusy.value = true;
  pippitError.value = "";
  try {
    if (pippitTask.value.source === 'local') {
      const response = await fetch(dramaForgeApiUrl(`creation/tasks/${pippitTask.value.project_id}/${pippitTask.value.shot_id}`));
      if (!response.ok) throw new Error('生成状态读取失败');
      pippitResult.value = JSON.stringify(await response.json());
    } else pippitResult.value = JSON.stringify(await studioRequest("thread", JSON.stringify(pippitTask.value)), null, 2);
    saveStudioTask();
  }
  catch (error) { pippitError.value = error instanceof Error ? error.message : "查询失败"; }
  finally { pippitBusy.value = false; scheduleStudioPoll(); }
}
function sendStudioMessage(files: File[], options: StudioCreativeOptions) {
  if (options.styleId === "custom" && !options.customStyle.trim()) options = { ...options, styleId: "none", customStyle: "" };
  if (options.modelId && options.modelId !== 'pippit') void submitLocalStudio(files, options);
  else void submitStudioTask(files, !!pippitTask.value && pippitTask.value.source !== 'local', options);
}
async function submitLocalStudio(files: File[], options: StudioCreativeOptions) {
  if (pippitBusy.value || !pippitMessage.value.trim()) return;
  if (files.some(file => !file.type.startsWith('image/'))) return ElMessage.warning('这个独立 API 模型暂不支持视频参考，请使用 Pippit 或移除视频');
  pippitBusy.value = true;
  const confirmed = await ElMessageBox.confirm(`将使用 ${options.modelId?.split(':').slice(1).join(':')} 生成一${options.outputKind === 'image' ? '张图片' : '段视频'}，比例 ${options.aspectRatio}、清晰度 ${options.resolution}${options.outputKind === 'video' ? `、${options.duration}秒` : ''}。使用该供应商额度，不消耗 Pippit 账号积分；实际费用暂未知，是否提交？`, '确认生成', { confirmButtonText: '提交生成' }).then(() => true, () => false);
  if (!confirmed) { pippitBusy.value = false; scheduleStudioPoll(); return; }
  pippitError.value = '';
  localMediaRequestId.value ||= crypto.randomUUID();
  try {
    const form = new FormData();
    form.append('payload', JSON.stringify({ requestId: localMediaRequestId.value, modelId: options.modelId, message: pippitMessage.value, preferences: options, resolution: options.resolution, duration: options.duration, projectId: pippitTask.value?.project_id }));
    for (const file of files) form.append('files', file);
    const response = await fetch(dramaForgeApiUrl('creation/generate'), { method: 'POST', body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '生成提交失败');
    pippitTask.value = { thread_id: '', run_id: `local-${result.project_id}-${result.shot_id}`, source: 'local', project_id: result.project_id, shot_id: result.shot_id };
    pippitResult.value = JSON.stringify(result);
    pippitMessage.value = ''; pippitSubmissionVersion.value++; localMediaRequestId.value = '';
    saveStudioTask(); void fetchDramaForgeProjects();
  } catch (cause) { pippitError.value = cause instanceof Error ? cause.message : '提交状态未确认，请先查看项目'; }
  finally { pippitBusy.value = false; scheduleStudioPoll(); }
}
function newStudioSession() {
  if (pippitBusy.value) return;
  if (pippitPollTimer) clearTimeout(pippitPollTimer);
  pippitTask.value = undefined; pippitResult.value = ""; pippitMessage.value = ""; pippitError.value = "";
  pippitSubmissionVersion.value++;
  localMediaRequestId.value = '';
  localStorage.removeItem("dramaForgePippitTask");
}
function scheduleStudioPoll() {
  if (pippitPollTimer) clearTimeout(pippitPollTimer);
  if (pippitStopped || !pippitTask.value || pippitError.value) return;
  const status = pippitSnapshot.value.status || 'submitted';
  if (['submitted', 'queued', 'pending', 'running', 'processing', 'in_progress'].includes(status)) pippitPollTimer = setTimeout(() => void refreshStudioTask(), 5000);
}
onUnmounted(() => { pippitStopped = true; if (pippitPollTimer) clearTimeout(pippitPollTimer); });
const scriptFileInput = ref<HTMLInputElement>();
const scriptInput = ref<InputInstance>();
const scriptInputMode = ref("upload");
const scriptFileName = ref("");
const scriptDragging = ref(false);
const promptWorkspacePicker = ref<InstanceType<typeof workspacePicker>>();
const relocationPicker = ref<InstanceType<typeof workspacePicker>>();
const prompt = ref("");
const promptInput = ref<InputInstance>();
const homeSkillMenu = ref<InstanceType<typeof skillMenu>>();
const promptAttachments = ref<AgentAttachment[]>([]);
const attachmentInput = ref<HTMLInputElement>();
const attachmentAccept = `image/*,video/*,${readableFileAccept}`;
const draggingAttachments = ref(false);
let attachmentDragDepth = 0;
const workspaceStore = useWorkspaceStore();
const { project, projectList } = storeToRefs(workspaceStore);
type DramaForgeProjectSummary = { id: number; name: string; status?: string; created_at?: string; workspace_directory?: string; project_type?: string; generation_settings?: { creativePreferences?: { styleName?: string } } };
const dramaForgeProjects = ref<DramaForgeProjectSummary[]>([]);
const deletingProjectId = ref<number | null>(null);
const workspaceDirectory = ref(project.value?.directory ?? "");
const placeholderPhrases = [
  "描述你想创作的内容，让灵感从这里开始…",
  "把一个故事灵感，变成一段精彩的短片…",
  "为你的主角设计独特的外形和性格…",
  "创作一段雨夜街头的电影感镜头…",
  "把这段文字拆解成连贯的分镜画面…",
  "为一场奇幻冒险生成场景和角色…",
  "为你的画面配上一段合适的音乐…",
  "写一段温暖的旁白，讲述这个故事…",
  "设计一支富有想象力的产品宣传片…",
  "从一句话开始，搭建你的创作工作流…",
];
const promptPlaceholder = ref(translate(placeholderPhrases[0]!));

function dramaForgeApiUrl(path: string) {
  return new URL(`api/${path.replace(/^\/+/, "")}`, `${window.location.origin}/`).toString();
}

onMounted(() => {
  window.addEventListener("dragend", clearAttachmentDrag, true);
  window.addEventListener("drop", clearAttachmentDrag, true);
  window.addEventListener("blur", clearAttachmentDrag);
  fetch(dramaForgeApiUrl("settings")).then(response => response.json()).then(value => {
    if (typeof value?.script?.model === "string") scriptModel.value = value.script.model;
  }).catch(() => {});
  void fetchDramaForgeProjects();
  void loadStudioTasks();
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let phraseIndex = 0;
  watch([() => !!prompt.value, locale], ([hasInput], _previous, onCleanup) => {
    if (reduceMotion) {
      promptPlaceholder.value = translate(placeholderPhrases[0]!);
      return;
    }
    if (hasInput) return;
    const segmenter = new Intl.Segmenter(locale.value, { granularity: "grapheme" });
    const phrases = placeholderPhrases.map(phrase => [...segmenter.segment(translate(phrase))].map(part => part.segment));
    let characterCount = 0;
    let deleting = false;
    let timer: ReturnType<typeof setTimeout>;
    promptPlaceholder.value = "";

    function typePlaceholder() {
      const phrase = phrases[phraseIndex]!;
      characterCount += deleting ? -1 : 1;
      promptPlaceholder.value = phrase.slice(0, characterCount).join("");
      let delay = deleting ? 35 : 85;
      if (characterCount === phrase.length) {
        deleting = true;
        delay = 1800;
      } else if (characterCount === 0) {
        deleting = false;
        phraseIndex = (phraseIndex + 1) % placeholderPhrases.length;
        delay = 300;
      }
      timer = setTimeout(typePlaceholder, delay);
    }

    timer = setTimeout(typePlaceholder, 300);
    onCleanup(() => clearTimeout(timer));
  }, { immediate: true });
});

onUnmounted(() => {
  window.removeEventListener("dragend", clearAttachmentDrag, true);
  window.removeEventListener("drop", clearAttachmentDrag, true);
  window.removeEventListener("blur", clearAttachmentDrag);
});
watch([creating, opening], ([creating, opening]) => {
  if (creating || opening) clearAttachmentDrag();
}, { flush: "sync" });

const selectedModel = ref("");
const reasoningEffort = ref("");
const openCanvasAfterPrompt = ref(true);
const sortDescending = ref(true);
const viewMode = ref("grid");
function normalizedDirectory(path: string) { return path.replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase(); }
const sortedProjects = computed(() => projectList.value.filter(project => !dramaForgeProjects.value.some(item => item.workspace_directory && normalizedDirectory(item.workspace_directory) === normalizedDirectory(project.directory))).sort((left, right) =>
  sortDescending.value ? right.lastOpenedAt - left.lastOpenedAt : left.lastOpenedAt - right.lastOpenedAt
));
const sortedDramaForgeProjects = computed(() => [...dramaForgeProjects.value].sort((left, right) => {
  const leftTime = left.created_at ? Date.parse(left.created_at) : 0;
  const rightTime = right.created_at ? Date.parse(right.created_at) : 0;
  return sortDescending.value ? rightTime - leftTime : leftTime - rightTime;
}));

async function fetchDramaForgeProjects() {
  try {
    const response = await fetch(dramaForgeApiUrl("projects"), { cache: "no-store" });
    if (!response.ok) return;
    const value: unknown = await response.json();
    if (Array.isArray(value)) dramaForgeProjects.value = value.filter((item): item is DramaForgeProjectSummary => !!item && typeof item.id === "number");
  } catch { /* The native Toonflow project list remains available if DramaForge is offline. */ }
}

function dramaForgeStatusLabel(status?: string) {
  return ({ draft: "草稿", analyzing: "分析中", analysis_failed: "分析失败", ready: "已就绪", producing: "制作中", done: "已完成" } as Record<string, string>)[status || ""] || status || "草稿";
}

async function deleteDramaForgeProject(item: DramaForgeProjectSummary) {
  if (deletingProjectId.value !== null) return;
  const confirmed = await ElMessageBox.confirm(`确定删除“${item.name}”？项目记录和专属素材将被永久删除，无法恢复。`, "删除项目", { type: "warning", confirmButtonText: "删除项目", cancelButtonText: "取消" }).then(() => true, () => false);
  if (!confirmed) return;
  deletingProjectId.value = item.id;
  try {
    const response = await fetch(dramaForgeApiUrl(`projects/${item.id}`), { method: "DELETE" });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "删除失败，请重试");
    if (item.workspace_directory) workspaceStore.removeProject(item.workspace_directory);
    dramaForgeProjects.value = dramaForgeProjects.value.filter(project => project.id !== item.id);
    ElMessage.success("项目已删除");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "删除失败，请重试"); }
  finally { deletingProjectId.value = null; }
}

async function openDramaForgeProject(item: DramaForgeProjectSummary) {
  if (opening.value) return;
  opening.value = true;
  try {
    const response = await fetch(dramaForgeApiUrl(`projects/${encodeURIComponent(item.id)}`));
    const projectData = await response.json().catch(() => ({}));
    if (!response.ok || !projectData.id) throw new Error(typeof projectData.detail === "string" ? projectData.detail : "无法读取短剧项目");
    if (projectData.project_type === "canvas") {
      await workspaceStore.openProject(projectData.workspace_directory);
      workspaceStore.renameProject(projectData.workspace_directory, projectData.name);
      await router.push("/workspace");
      return;
    }
    (window as Window & { __DRAMAFORGE_PROJECT__?: Record<string, unknown> }).__DRAMAFORGE_PROJECT__ = projectData;
    await router.push({ path: "/workspace", query: { dramaforgeProjectId: String(item.id) } });
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "打开短剧项目失败");
  } finally {
    opening.value = false;
  }
}

async function openScriptPaste() {
  scriptInputMode.value = "paste";
  await nextTick();
  scriptInput.value?.focus();
}
async function loadScriptFile(file?: File) {
  scriptDragging.value = false;
  if (!file || scriptCreating.value) return;
  try {
    if (!/\.txt$/i.test(file.name) || !file.size || file.size > 400000) throw new Error("请选择不超过 400 KB 的 TXT 剧本");
    const text = await readTextAttachment({ name: file.name, path: "", mimeType: "text/plain", file });
    if (text.length > 100000) throw new Error("剧本不能超过 10 万字");
    scriptText.value = text;
    scriptFileName.value = file.name;
    scriptError.value = "";
    await openScriptPaste();
  } catch (error) { scriptError.value = error instanceof Error ? error.message : "读取剧本失败"; }
}
function selectScriptFile(event: Event) {
  const input = event.target as HTMLInputElement;
  void loadScriptFile(input.files?.[0]);
  input.value = "";
}
function dropScriptFile(event: DragEvent) {
  void loadScriptFile(event.dataTransfer?.files[0]);
}
async function startScriptAnalysis() {
  if (scriptCreating.value) return;
  const text = scriptText.value.trim();
  if (!text) return ElMessage.warning("请先粘贴剧本或故事梗概");
  scriptCreating.value = true;
  scriptError.value = "";
  try {
    const firstLine = text.split(/\r?\n/).map(line => line.replace(/^\s*[#《》]+\s*/g, "").trim()).find(Boolean) || "新短剧";
    const name = scriptName.value.trim() || firstLine.slice(0, 28);
    const createResponse = await fetch(dramaForgeApiUrl("projects"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, script_text: text, aspect_ratio: scriptAspectRatio.value, creativeOptions: scriptPreferences.value }),
    });
    const created = await createResponse.json().catch(() => ({}));
    if (!createResponse.ok || !created.id) throw new Error(typeof created.detail === "string" ? created.detail : "项目创建失败");
    const modelQuery = scriptModel.value.trim() ? `?model=${encodeURIComponent(scriptModel.value.trim())}` : "";
    const analysisResponse = await fetch(dramaForgeApiUrl(`projects/${created.id}/analyze${modelQuery}`), { method: "POST" });
    const analysis = await analysisResponse.json().catch(() => ({}));
    if (!analysisResponse.ok) throw new Error(typeof analysis.detail === "string" ? analysis.detail : "项目已创建，但分析未能启动");
    const projectResponse = await fetch(dramaForgeApiUrl(`projects/${created.id}`));
    if (!projectResponse.ok) throw new Error("分析已启动，但项目详情读取失败；请从项目列表重新打开");
    const projectData = await projectResponse.json();
    (window as Window & { __DRAMAFORGE_PROJECT__?: Record<string, unknown> }).__DRAMAFORGE_PROJECT__ = projectData;
    void fetchDramaForgeProjects();
    ElMessage.success("剧本分析已开始，结果会同步到创作画布");
    await router.push({ path: "/workspace", query: { dramaforgeProjectId: String(created.id) } });
  } catch (error) {
    scriptError.value = error instanceof Error ? error.message : "剧本分析启动失败，请重试";
  } finally {
    scriptCreating.value = false;
  }
}

function selectCreationMode(mode: "prompt" | "marketing" | "script") {
  void router.replace({ path: "/home" });
  creationMode.value = mode;
  document.querySelector(".pageContent")?.scrollTo({ top: 0, behavior: "smooth" });
}

function insertSkill(name: string) {
  prompt.value = `/skill:${name} ${prompt.value.replace(/^\s*\/skill:\S+(?:\s+|$)/, "")}`;
  void nextTick(() => promptInput.value?.focus());
}

function showSkills() {
  void router.push({ path: "/home", query: { section: "skills" } });
}
function scrollToProjects() {
  void router.push({ path: "/home", query: { section: "assets" } });
}
function selectLibrarySkill(name: string) {
  if (name === "pippit-skill") {
    selectCreationMode("script");
    studioTab.value = "writer";
    return;
  }
  selectCreationMode("prompt");
  insertSkill(name);
}
async function openLibraryProject(id: number) {
  const item = dramaForgeProjects.value.find(project => project.id === id);
  if (item) await openDramaForgeProject(item);
  else ElMessage.warning("项目未找到，请刷新项目列表");
}

function showProjects() {
  creationMode.value = "prompt";
  void router.push({ path: "/home", query: { section: "projects" } });
}
async function createBlankCanvas() {
  if (creating.value || opening.value) return;
  creating.value = true;
  try {
    const response = await fetch(dramaForgeApiUrl("projects"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "未命名画布", project_type: "canvas" }) });
    if (!response.ok) throw new Error("创建画布项目失败，请重试");
    const created = await response.json();
    const detail = await fetch(dramaForgeApiUrl(`projects/${created.id}`));
    if (!detail.ok) throw new Error("项目已创建，但读取工作目录失败，请从项目资源重试");
    const projectData = await detail.json();
    await useWorkspaceFiles(projectData.workspace_directory).writeJson("画布1.json", { toonflowCanvas: true, nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } }, true);
    await workspaceStore.openProject(projectData.workspace_directory);
    workspaceStore.renameProject(projectData.workspace_directory, projectData.name);
    await router.push("/workspace");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "创建画布失败"); }
  finally { creating.value = false; }
}

function pasteAttachments(event: ClipboardEvent) {
  if (creating.value || opening.value) return;
  try {
    const files = Array.from(event.clipboardData?.files ?? []);
    if (!files.length) {
      const file = createPastedTextFile(event.clipboardData?.getData("text/plain") ?? "");
      if (file) files.push(file);
    }
    if (!files.length) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    addAttachments(files);
  } catch (error) {
    event.preventDefault();
    event.stopImmediatePropagation();
    ElMessage.error(error instanceof Error ? error.message : "添加附件失败，请重试");
  }
}

function selectAttachments(event: Event) {
  const input = event.target as HTMLInputElement;
  addAttachments(Array.from(input.files ?? []));
  input.value = "";
}

function clearAttachmentDrag() {
  attachmentDragDepth = 0;
  draggingAttachments.value = false;
}

function dragEnterAttachments(event: DragEvent) {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  event.stopPropagation();
  if (creating.value || opening.value) return clearAttachmentDrag();
  attachmentDragDepth++;
  draggingAttachments.value = true;
}

function dragOverAttachments(event: DragEvent) {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  event.stopPropagation();
  event.dataTransfer.dropEffect = creating.value || opening.value ? "none" : "copy";
  if (creating.value || opening.value) return clearAttachmentDrag();
  attachmentDragDepth = Math.max(1, attachmentDragDepth);
  draggingAttachments.value = true;
}

function dragLeaveAttachments(event: DragEvent) {
  if (!draggingAttachments.value) return;
  attachmentDragDepth = Math.max(0, attachmentDragDepth - 1);
  const target = event.currentTarget;
  if (!attachmentDragDepth || (target instanceof Node && event.relatedTarget instanceof Node && !target.contains(event.relatedTarget))) clearAttachmentDrag();
}

function dropAttachments(event: DragEvent) {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  event.stopPropagation();
  clearAttachmentDrag();
  addAttachments(Array.from(event.dataTransfer.files));
}

function addAttachments(files: File[]) {
  if (creating.value || opening.value) return;
  for (const file of files) {
    const readableMimeType = getReadableFileMimeType(file.name, file.type);
    const mimeType = readableMimeType ?? file.type.split(";")[0]!.trim().toLowerCase();
    if (!readableMimeType && !/^(image|video)\//.test(mimeType)) {
      ElMessage.warning("只支持图片、视频和受支持的文本或文档文件");
      continue;
    }
    if (!file.size || file.size > 100 * 1024 * 1024) {
      ElMessage.warning("附件不能为空且不能超过 100 MB");
      continue;
    }
    if (mimeType === "text/plain" && file.size > 400000) {
      ElMessage.warning("文本附件不能超过 400000 字节");
      continue;
    }
    if (promptAttachments.value.length >= 20) {
      ElMessage.warning("每条消息最多添加 20 个附件");
      break;
    }
    promptAttachments.value.push({ name: file.name, path: "", mimeType, file });
  }
}

async function restoreAttachment(index: number) {
  const attachment = promptAttachments.value[index];
  if (attachment?.mimeType !== "text/plain" || creating.value || opening.value) return;
  try {
    const text = await readTextAttachment(attachment);
    const currentIndex = promptAttachments.value.indexOf(attachment);
    if (currentIndex < 0 || creating.value || opening.value) return;
    prompt.value += `${prompt.value ? "\n" : ""}${text}`;
    promptAttachments.value.splice(currentIndex, 1);
    await nextTick();
    promptInput.value?.focus();
    promptInput.value?.textarea?.setSelectionRange(prompt.value.length, prompt.value.length);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "取回文本失败，请重试");
  }
}

async function openProject(project?: Project) {
  if (creating.value || opening.value) return;
  opening.value = true;
  try {
    const directory = project?.directory ?? await relocationPicker.value?.chooseDirectory();
    if (!directory) return;
    try { await workspaceStore.openProject(directory); }
    catch (err) {
      if (!project || !axios.isAxiosError(err) || err.response?.status !== 404) throw err;
      const reselect = await ElMessageBox.confirm(`项目“${project.name}”的文件夹不存在，是否重新选择文件夹？`, "工作目录不存在", {
        confirmButtonText: "重新选择", cancelButtonText: "取消", type: "warning",
      }).then(() => true, () => false);
      if (!reselect) return;
      const directory = await relocationPicker.value?.chooseDirectory();
      if (!directory) return;
      await workspaceStore.openProject(directory, project.directory);
    }
    await router.push("/workspace");
  } catch (err) {
    ElMessage.error(axios.isAxiosError<{ message?: string }>(err)
      ? err.response?.data.message || "无法打开项目，请重试"
      : err instanceof Error ? err.message : "无法打开项目，请重试");
  } finally { opening.value = false; }
}

async function renameProject(project: Project) {
  const result = await ElMessageBox.prompt("请输入项目名称", "重命名项目", {
    inputValue: project.name, confirmButtonText: "保存", cancelButtonText: "取消",
    inputValidator: value => !!value?.trim() || "项目名称不能为空",
  }).catch(() => null);
  if (result) workspaceStore.renameProject(project.directory, result.value);
}

async function createProject(fromPrompt = true) {
  if (creating.value || opening.value || (fromPrompt && !workspaceDirectory.value)) return;
  creating.value = true;
  try {
    let path = workspaceDirectory.value;
    if (!fromPrompt) {
      const confirmed = await ElMessageBox.confirm("请选择一个空文件夹作为项目目录，画布和素材将保存在其中。", "添加项目", {
        confirmButtonText: "选择空文件夹", cancelButtonText: "取消", type: "info",
      }).then(() => true, () => false);
      if (!confirmed) return;
      path = await relocationPicker.value?.chooseDirectory() ?? "";
      if (!path) return;
    }
    const { directory, empty } = await useWorkspaceFiles(path).list();
    if (!empty) return ElMessage.warning("该文件夹不为空，请重新选择空文件夹；已有项目请使用“导入项目”或点击项目列表打开。");
    await useWorkspaceFiles(directory).writeJson("画布1.json", { toonflowCanvas: true, nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } }, true);
    await workspaceStore.openProject(directory);
    if (fromPrompt && (prompt.value.trim() || promptAttachments.value.length)) {
      const agentPrompt = creationMode.value === "marketing"
        ? `请以短视频营销创意总监的身份，先根据产品、受众和推广目标整理创意方向，再提出可执行的视频结构与镜头方案。\n\n用户需求：\n${prompt.value.trim()}`
        : prompt.value;
      workspaceStore.pendingAgentMessage = { directory: workspaceStore.project!.directory, prompt: agentPrompt, attachments: [...promptAttachments.value], model: selectedModel.value, reasoningEffort: reasoningEffort.value };
    }
    if (openCanvasAfterPrompt.value) await router.push("/workspace");
    else ElMessage.success("项目已创建；可从左侧“画布”或最近项目继续编辑");
  } catch (err) {
    ElMessage.error(axios.isAxiosError<{ message?: string }>(err)
      ? err.response?.data.message || "创建项目失败，请重试"
      : err instanceof Error ? err.message : "创建项目失败，请重试");
  } finally {
    creating.value = false;
  }
}
</script>

<style lang="scss" scoped>
.creationEngine { width: 150px; }
.home .creationPanel.conversationActive { margin-top: 16px; }
.engineHint { color: var(--el-text-color-secondary); font-size: 12px; }

.pippitHistory { margin-top: 28px; h2 { font-size: 18px; } button { display: flex; justify-content: space-between; gap: 20px; width: 100%; padding: 16px; margin-bottom: 8px; text-align: left; border: 1px solid var(--el-border-color-lighter); border-radius: 14px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); cursor: pointer; span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } small { flex-shrink: 0; color: var(--el-text-color-secondary); } } }

.pippitTaskPanel {
  width: 100%; min-width: 0; text-align: left; padding: 20px; border: 1px solid var(--el-border-color); border-radius: 16px; box-sizing: border-box;
  .pippitTaskHeader { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .pippitTaskText { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
  .pippitTaskDownloads { display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0; }
  a { color: var(--el-color-primary); }
  details { margin-top: 16px; }
  pre { max-height: 320px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
}

.home {
  position: relative;
  isolation: isolate;
  width: 100%;
  height: 100dvh;
  overflow: hidden;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color-page);

  .pageBackground {
    position: absolute;
    inset: 0;
    z-index: -1;
    pointer-events: none;
  }

  .homeSidebar {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    flex: 0 0 252px;
    width: 252px;
    height: 100%;
    padding: 22px 14px 16px;
    border-right: 1px solid var(--el-border-color-lighter);
    background: var(--el-bg-color-overlay);

    .sidebarBrand {
      display: flex;
      align-items: center;
      gap: 11px;
      padding: 3px 10px 28px;
      border: 0;
      background: transparent;
      color: var(--el-text-color-primary);
      font: inherit;
      font-size: 20px;
      font-weight: 700;
      text-align: left;
      cursor: pointer;

      .sidebarGlyph {
        display: grid;
        place-items: center;
        width: 32px;
        height: 32px;
        flex: none;
        border: 1px solid var(--el-border-color-light);
        border-radius: 10px;
        background: var(--el-fill-color-light);
        color: var(--el-color-primary);
      }
      small {
        display: block;
        margin-top: 3px;
        color: var(--el-text-color-secondary);
        font-size: 8px;
        font-weight: 600;
        letter-spacing: .24em;
      }
    }

    .sidebarNav {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-height: 0;
      overflow: auto;

      .navCaption {
        padding: 13px 12px 7px;
        color: var(--el-text-color-secondary);
        font-size: 11px;
        letter-spacing: .05em;
      }

      .navItem {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        min-height: 42px;
        padding: 0 12px;
        border: 1px solid transparent;
        border-radius: 11px;
        background: transparent;
        color: var(--el-text-color-regular);
        font: inherit;
        font-size: 13px;
        text-align: left;
        cursor: pointer;
        transition: background .16s ease, color .16s ease, border-color .16s ease;

        svg { flex: none; color: var(--el-text-color-secondary); }
        &:hover { background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
        &.active {
          border-color: color-mix(in srgb, var(--el-color-primary) 25%, transparent);
          background: color-mix(in srgb, var(--el-color-primary) 11%, transparent);
          color: var(--el-color-primary);
          font-weight: 600;
          svg { color: var(--el-color-primary); }
        }
        &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 1px; }
      }

      .navDivider { height: 1px; margin: 12px 6px 4px; background: var(--el-border-color-lighter); }

      .sidebarRecent {
        display: flex;
        flex-direction: column;
        gap: 3px;
        margin-top: 10px;

        .recentItem {
          display: flex;
          align-items: center;
          gap: 10px;
          width: 100%;
          min-width: 0;
          padding: 8px 9px;
          border: 0;
          border-radius: 9px;
          background: transparent;
          color: var(--el-text-color-regular);
          font: inherit;
          font-size: 12px;
          text-align: left;
          cursor: pointer;
          &:hover { background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
          > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .recentIcon { display: grid; width: 29px; height: 29px; place-items: center; flex: none; border-radius: 7px; background: var(--el-fill-color); color: var(--el-text-color-secondary); }
          .recentIcon.drama { background: color-mix(in srgb, var(--el-color-primary) 12%, transparent); color: var(--el-color-primary); }
        }
      }
    }

    .sidebarFooter { margin-top: auto; padding-top: 14px; }
    .sidebarFooterActions { display: flex; justify-content: space-between; gap: 4px; padding: 2px 2px 9px; }
    .githubLink { display: flex; align-items: center; gap: 7px; padding: 9px 6px 0; border-top: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-secondary); font-size: 11px; text-decoration: none; }
  }

  .homeShell { min-width: 0; height: 100%; }

  .pageHeader {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 62px;
    padding: 0 clamp(22px, 4vw, 54px);
    border-bottom: 1px solid var(--el-border-color-lighter);
    background: color-mix(in srgb, var(--el-bg-color) 82%, transparent);
    .headerBreadcrumb { display: flex; align-items: center; gap: 12px; color: var(--el-text-color-secondary); font-size: 12px; }
    .headerBreadcrumb strong { color: var(--el-text-color-primary); font-weight: 500; }
    .breadcrumbSlash { opacity: .45; }
    .headerActions { display: flex; align-items: center; gap: 10px; }
    a { text-decoration: none; }
  }

  .pageContent {
    height: calc(100% - 62px);
    overflow: auto;
    padding: 12px clamp(22px, 4vw, 54px) 56px;

    .creationPanel {
      width: min(100%, 1000px);
      margin: clamp(28px, 5vh, 54px) auto 48px;

      .studioTitle {
        display: flex;
        align-items: center;
        justify-content: center;
        flex-wrap: wrap;
        gap: 10px;
        color: var(--el-text-color-primary);
        font-size: clamp(20px, 2.5vw, 29px);
        line-height: 1.4;
        letter-spacing: -.035em;
        strong { font-weight: 750; }
      }

      .creationModes {
        margin: 0 2px;
        padding: 3px;
        border: 0;
        border-radius: 999px;
        background: var(--el-fill-color-light);
        :deep(.el-radio-button__inner) { padding: 7px 17px; border: 0 !important; border-radius: 999px !important; background: transparent; box-shadow: none !important; color: var(--el-text-color-secondary); font-size: 13px; transition: color .18s ease, background-color .18s ease, box-shadow .18s ease; }
        :deep(.is-active .el-radio-button__inner) { background: var(--el-bg-color-overlay); color: var(--el-text-color-primary); box-shadow: 0 1px 4px rgb(0 0 0 / 12%) !important; }
        :deep(.el-radio-button:not(.is-active) .el-radio-button__inner:hover) { color: var(--el-text-color-primary); }

        .dark & {
          border: 1px solid rgb(255 255 255 / 6%);
          background: #242424;
          :deep(.el-radio-button__inner) { color: #b8b8b8; }
          :deep(.is-active .el-radio-button__inner) { background: #4a4a4a; color: #fff; box-shadow: none !important; }
          :deep(.el-radio-button:not(.is-active) .el-radio-button__inner:hover) { color: #fff; }
        }
      }

      .studioSubtitle { margin: 10px 0 25px; color: var(--el-text-color-secondary); font-size: 13px; text-align: center; }

      .promptArea {
        position: relative;

        .promptCard {
          position: relative;
          min-height: 228px;
          border-radius: 24px;
          border-color: var(--el-border-color-lighter);
          background: var(--el-bg-color-overlay);
          box-shadow: 0 14px 38px rgb(0 0 0 / 12%);

          &:focus-within {
            border-color: var(--el-color-primary-light-5);
            box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 25%, transparent), 0 16px 42px rgb(0 0 0 / 16%);
          }

          &.draggingAttachments {
            border-color: var(--el-color-primary-light-5);
          }

          .attachmentDropOverlay {
            position: absolute;
            inset: 0;
            z-index: 2;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 4px;
            border-radius: inherit;
            background: var(--el-bg-color);
            color: var(--el-text-color-primary);
            pointer-events: none;

            > svg { color: var(--el-text-color-secondary); }
            strong { font-size: 14px; font-weight: 500; }
            span { color: var(--el-text-color-secondary); font-size: 12px; }
          }

          .promptAttachments {
            margin-bottom: 12px;
          }

          :deep(.el-textarea__inner) {
            min-height: 116px !important;
            padding: 4px 2px;
            box-shadow: none;
            background: transparent;
            color: var(--el-text-color-primary);
            font-size: 15px;
            line-height: 1.75;
          }

          :deep(.el-card__footer) {
            border-top: 1px solid var(--el-border-color-lighter);
            background: transparent;
          }

          .composerFooter {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;

            .composerTools { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; }
            .skillControl { display: inline-flex; align-items: center; gap: 4px; color: var(--el-text-color-regular); font-size: 12px; }
            .toolDivider { width: 1px; height: 22px; margin: 0 2px; background: var(--el-border-color); }
            .canvasToggle { display: inline-flex; align-items: center; gap: 8px; color: var(--el-text-color-regular); }

            .sendActions {
              margin-left: auto;
              justify-content: flex-end;

              .sendButton {
                width: 40px;
                height: 40px;
              }
            }
          }

          .workspaceHint {
            margin: 6px 0 0;
            color: var(--el-text-color-regular);
            font-size: 11px;
            line-height: 1.6;
          }
        }
      }

      .scriptComposer {
        border-radius: 24px;
        border-color: var(--el-border-color-lighter);
        background: var(--el-bg-color-overlay);
        box-shadow: 0 14px 38px rgb(0 0 0 / 12%);
        :deep(.el-card__body) { padding: 22px; }

        .scriptComposerHeader {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          margin-bottom: 16px;

          > div { display: grid; gap: 6px; }
          strong { font-size: 16px; font-weight: 600; }
          span { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
        }

        :deep(.el-textarea__inner) { min-height: 174px !important; line-height: 1.7; }

        .scriptComposerOptions {
          display: grid;
          grid-template-columns: minmax(0, 1.5fr) minmax(210px, auto) minmax(140px, 1fr);
          gap: 12px;
          margin-top: 14px;
        }

        .scriptComposerFooter {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 16px;

          > span { color: var(--el-text-color-secondary); font-size: 12px; }
        }

        .scriptError { margin-top: 14px; }

        @media (max-width: 640px) {
          .scriptComposerOptions { grid-template-columns: 1fr; }
          .scriptComposerFooter { align-items: stretch; }
        }
      }
    }

    .recommendations, .projectList { width: min(100%, 1120px); margin: 0 auto 44px; }
    .sectionHeader {
      display: flex;
      align-items: end;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 15px;
      > div { display: grid; gap: 5px; }
      h2 { margin: 0; font-size: 17px; font-weight: 650; }
      > span, > div > span { color: var(--el-text-color-secondary); font-size: 12px; }
    }
    .recommendationGrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }
    .recommendationCard {
      position: relative;
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr);
      column-gap: 12px;
      align-items: center;
      min-height: 86px;
      padding: 15px;
      border: 1px solid var(--el-border-color-lighter);
      border-radius: 14px;
      background: var(--el-bg-color-overlay);
      color: var(--el-text-color-primary);
      text-align: left;
      cursor: pointer;
      transition: transform .16s ease, border-color .16s ease, background .16s ease;
      &:hover { transform: translateY(-2px); border-color: var(--el-color-primary-light-5); background: var(--el-fill-color-light); }
      &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
      .recommendationIcon { grid-row: span 2; display: grid; width: 40px; height: 40px; place-items: center; border-radius: 11px; background: color-mix(in srgb, var(--el-color-primary) 13%, transparent); color: var(--el-color-primary); }
      strong { align-self: end; font-size: 13px; font-weight: 600; }
      small { align-self: start; margin-top: 3px; color: var(--el-text-color-secondary); font-size: 11px; line-height: 1.45; }
      .recommendationArrow { position: absolute; top: 15px; right: 15px; color: var(--el-text-color-secondary); }
    }

    .projectList {
      .projectItems {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
        gap: 16px;
        margin-top: 0;

        &.listView { grid-template-columns: 1fr; }

        .projectCard {
          position: relative;

          .projectActions {
            position: absolute;
            top: 12px;
            right: 8px;
            display: flex;
            gap: 4px;

            .el-button { width: 32px; height: 32px; margin: 0; padding: 0; }
          }

          .dramaProjectTag { position: absolute; top: 12px; right: 12px; }
          &.dramaProjectCard .projectActions { top: auto; bottom: 8px; right: 12px; }
        }

        .projectEntry {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          width: 100%;
          padding: 20px 84px 20px 20px;
          border: 0;
          background: transparent;
          color: inherit;
          font: inherit;
          text-align: left;
          cursor: pointer;

          &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
          &:disabled { cursor: wait; opacity: 0.6; }

          .projectIcon { flex-shrink: 0; color: var(--el-text-color-secondary); }

          .projectInfo {
            display: flex;
            flex-direction: column;
            gap: 6px;
            min-width: 0;

            .projectName, .projectPath {
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }

            .projectName { font-weight: 600; }
            .projectPath { font-size: 13px; color: var(--el-text-color-regular); }
            .projectTime { font-size: 12px; color: var(--el-text-color-secondary); }
          }
        }
      }

      .sectionHeader { align-items: center; }
    }
  }
}

@media (max-width: 900px) {
  .home .homeSidebar { flex-basis: 216px; width: 216px; }
  .home .pageContent { padding-inline: 22px; }
  .home .recommendationGrid { grid-template-columns: 1fr; }
}

@media (max-width: 680px) {
  .home { height: 100dvh; flex-direction: column; }
  .home .homeSidebar {
    flex: 0 0 auto;
    width: 100% !important;
    height: auto;
    padding: 8px 12px 0;
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
    .sidebarBrand { padding: 2px 8px 7px; font-size: 16px; .sidebarGlyph { width: 25px; height: 25px; } small { display: none; } }
    .sidebarNav { flex-direction: row; align-items: center; gap: 4px; overflow-x: auto; overflow-y: hidden; padding-bottom: 7px; .navCaption, .navDivider, .sidebarRecent { display: none; } .navItem { width: auto; min-height: 36px; white-space: nowrap; padding-inline: 10px; } }
    .sidebarFooter { display: none; }
  }
  .home .homeShell { min-height: 0; flex: 1; }
  .home .pageHeader { height: 48px; padding-inline: 14px; }
  .home .pageContent { height: calc(100% - 48px); padding: 12px 14px 40px; }
  .home .creationPanel { margin-top: 20px; }
  .home .studioTitle { gap: 6px; font-size: 18px; }
  .home .creationModes :deep(.el-radio-button__inner) { padding: 7px 10px; }
  .home .promptCard :deep(.el-card__body) { padding: 14px !important; }
  .home .composerFooter { align-items: flex-end; }
  .home .composerTools { gap: 4px !important; }
  .home .composerTools .canvasToggle { font-size: 11px; }
  .home .scriptComposerOptions { grid-template-columns: 1fr !important; }
  .home .scriptComposerOptions > :last-child { grid-column: 1 / -1; }
  .home .projectList .sectionHeader { align-items: flex-start; }
  .home .projectList .sectionHeader > .el-space { justify-content: flex-start; }
}
</style>

<style lang="scss" scoped>
.home .creationModes {
  display: inline-flex; padding: 3px; border: 0; border-radius: 999px; background: var(--el-fill-color-light);
  button { border: 0; border-radius: 999px; padding: 7px 19px; background: transparent; color: var(--el-text-color-secondary); font: 500 13px/1.4 inherit; cursor: pointer; }
  button.active { background: var(--el-fill-color-darker); color: var(--el-text-color-primary); }
}
.home .scriptStudioTitle { font-size: 32px !important; font-weight: 700; padding: 18px 0 12px; }
.home .scriptComposer {
  box-shadow: none !important; border-radius: 30px !important;
  :deep(.el-card__body) { padding: 0 12px 20px !important; }
  .scriptComposerTabs { display:flex; align-items:center; justify-content:space-between; padding:0 28px; height:50px; margin:0 -12px 12px; background:var(--el-fill-color-light); border-radius:30px 30px 0 0; }
  .scriptComposerTab, .scriptCanvasTab { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; }
  .scriptDropZone { min-height:230px; border:1px dashed var(--el-border-color); border-radius:22px; padding:20px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:16px; }
  .scriptDropZone.dragging { border-color:var(--el-color-primary); background:var(--el-fill-color-light); }
  .scriptUploadMark { color:var(--el-text-color-secondary); }
  .scriptUploadActions { display:flex; gap:12px; }
  .scriptUploadActions .el-button { border-radius:999px; padding:18px 24px; }
  .scriptUploadButton { background:var(--el-text-color-primary); color:var(--el-bg-color); }
  .scriptDropZone p { margin:0; font-size:12px; color:var(--el-text-color-secondary); }
  .scriptPasteHeader { display:flex; width:100%; justify-content:space-between; align-items:center; font-size:13px; }
  .scriptComposerOptions, .scriptComposerFooter { margin-left:12px; margin-right:12px; }
}
</style>

<style scoped>.scriptComposerTabs { display:grid !important; grid-template-columns:repeat(4,1fr); padding:0 !important; }.scriptComposerTab { justify-content:center; height:50px; border:0; background:transparent; color:var(--el-text-color-secondary); cursor:pointer; border-radius:28px 28px 16px 16px; }.scriptComposerTab.active { background:var(--el-bg-color-overlay); color:var(--el-text-color-primary); }</style>
