<template>
  <section class="pippitConversation" :class="{ initialConversation: !task }" aria-label="创作会话">
    <header v-if="task"><div><h2>{{ snapshot.execution ? snapshot.execution.kind === 'image' ? '图片创作' : '视频创作' : mode === 'remix' ? '重制转绘' : 'AI 编剧' }}</h2><span>{{ statusLabel }}</span><p v-if="snapshot.creativeOptions" class="savedPreferences">{{ snapshot.creativeOptions.styleName }} · {{ snapshot.creativeOptions.aspectRatio }}<template v-if="!snapshot.execution && snapshot.creationMode === 'writer'"> · {{ snapshot.creativeOptions.episodes }} 集</template></p></div><el-button text :disabled="busy" @click="emit('newSession')">新建会话</el-button></header>
    <div v-if="task" ref="messageList" class="conversationMessages" aria-live="polite">
      <article v-for="message in messages" :key="message.id" class="conversationMessage" :class="{ userMessage: message.role === 'user' }">
        <small>{{ message.role === 'user' ? '你' : snapshot.execution?.provider || 'Pippit' }}</small>
        <template v-for="(part, index) in message.parts" :key="index"><p v-if="part.text">{{ part.text }}</p><video v-if="part.media?.kind === 'video'" :src="part.media.url" class="messageReference" controls preload="metadata" /><img v-else-if="part.media?.kind === 'image'" :src="part.media.url" class="messageReference" alt="已上传的参考图" loading="lazy" /><details v-if="part.tool" class="toolStep"><summary>{{ toolLabels[part.tool] || part.tool }} <span>已请求</span></summary><p>接口记录了此工具调用，未单独返回完成状态。</p></details></template>
      </article>
      <p v-if="task && !messages.length" class="conversationHint">任务已提交，正在等待会话内容。</p>
      <div v-if="interactions.length" class="conversationQuestions"><strong>需要你的回复</strong><p v-for="question in interactions" :key="question">{{ question }}</p></div>
      <div v-if="assets.length" class="conversationAssets"><article v-for="asset in assets" :key="asset.url"><video v-if="asset.kind === 'video'" :src="asset.url" controls preload="metadata" /><img v-else-if="asset.kind === 'image'" :src="asset.url" alt="Pippit 生成结果" loading="lazy" /><a :href="asset.url" target="_blank" rel="noopener noreferrer">查看 / 下载结果 ↗</a></article></div>
      <div v-if="task" class="conversationActions"><el-button text :loading="busy" @click="emit('refresh')">刷新状态</el-button><el-button text :disabled="busy || !assets.length" @click="emit('save')">保存成果到项目</el-button><a v-if="safeUrl(task.web_thread_link)" :href="safeUrl(task.web_thread_link)" target="_blank" rel="noopener noreferrer">官网会话 ↗</a></div>
    </div>
    <p v-if="error" class="conversationError" role="alert">{{ error }}</p>
    <div class="conversationComposer" @dragover.prevent @drop.prevent="dropFiles">
      <div v-if="attachments.length" class="referenceList"><div v-for="item in attachments" :key="item.id" :title="item.file.name"><img v-if="item.file.type.startsWith('image/')" :src="item.url" :alt="item.file.name" /><video v-else :src="item.url" preload="metadata" muted @loadedmetadata="readDuration(item, $event)" /><small v-if="item.duration" class="referenceDuration">{{ item.duration }}</small><span>{{ item.file.name }}</span><button type="button" :disabled="busy" :aria-label="`移除 ${item.file.name}`" @click="removeFile(item.id)">×</button></div></div>
      <el-input :modelValue="modelValue" type="textarea" :rows="task ? 4 : 6" :disabled="busy" :placeholder="snapshot.execution ? '描述下一次生成；修改已有素材时，请从资产库添加参考。' : task ? '继续修改、回答追问，或添加图片和视频…' : mode === 'remix' ? '描述要如何重制视频，可上传视频和角色参考图…' : '描述你的剧本创意'" aria-label="创作需求或会话回复" @update:modelValue="emit('update:modelValue', $event)" />
      <div class="composerToolbar"><input ref="fileInput" type="file" multiple :accept="acceptedTypes" hidden @change="chooseFiles" /><el-popover v-model:visible="attachmentMenuVisible" popperClass="studioAttachmentPopover" trigger="click" placement="top-start" :width="224" :disabled="busy"><template #reference><el-button text circle :disabled="busy" class="addMaterial" aria-label="添加素材"><icon-plus :size="19" /></el-button></template><div class="attachmentMenu"><button type="button" @click="attachmentMenuVisible = false; fileInput?.click()"><icon-paperclip :size="18" /><span>上传图片或视频</span></button><button type="button" @click="attachmentMenuVisible = false; openAssetLibrary()"><icon-cloud :size="18" /><span>从资产库选择</span></button><button type="button" @click="attachmentMenuVisible = false; addLink()"><icon-link :size="18" /><span>添加链接</span></button></div></el-popover><creationPreferences v-model="preferences" :mode="chosenModel === 'pippit' && !chosenKind ? mode : ''" :disabled="busy" /><mediaModelPicker v-model="chosenModel" v-model:ratio="preferences.aspectRatio" v-model:resolution="chosenResolution" v-model:duration="chosenDuration" :disabled="busy" @selectKind="chosenKind = $event" /><el-button class="sendMessage" type="primary" circle :loading="busy" :disabled="busy || !modelValue.trim() || preferences.styleId === 'custom' && !preferences.customStyle.trim()" :aria-label="chosenModel === 'pippit' ? '提交创作' : chosenKind === 'image' ? '生成图片' : '生成视频'" @click="emit('send', attachments.map(item => item.file), { ...preferences, modelId: chosenModel, resolution: chosenResolution, duration: chosenDuration, outputKind: chosenKind })">↑</el-button></div>
      <small class="conversationHint">{{ chosenModel === 'pippit' ? 'Pippit 积分 · 费用以平台为准' : '独立 API 额度 · 费用以供应商为准' }}</small><p v-if="progress" role="status">{{ progress }}</p>
    </div>
    <el-dialog v-model="assetLibraryVisible" title="选择项目素材" width="min(760px, calc(100vw - 32px))"><p v-if="assetLibraryError" role="alert">{{ assetLibraryError }}</p><div class="assetReferenceGrid"><button v-for="item in libraryItems" :key="item.id" type="button" :disabled="busy || addingAsset" @click="useLibraryAsset(item)"><video v-if="item.kind === 'video'" :src="item.url" preload="metadata" /><img v-else :src="item.url" :alt="item.name" loading="lazy" /><span>{{ item.name }}</span><small>{{ item.projectName }}</small></button></div><p v-if="!libraryItems.length && !assetLibraryError">暂无可用的本地图片或视频素材。</p></el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import creationPreferences from './creationPreferences.vue';
import { IconPaperclip, IconCloud, IconLink, IconPlus } from "@tabler/icons-vue";
import mediaModelPicker from './mediaModelPicker.vue';
const props = defineProps<{ modelValue: string; mode: string; task?: { thread_id: string; run_id: string; web_thread_link?: string }; snapshot: Record<string, any>; statusLabel: string; busy: boolean; error: string; progress: string; submissionVersion: number }>();
const emit = defineEmits<{ 'update:modelValue': [value: string]; send: [files: File[], options: { styleId: string; customStyle: string; aspectRatio: string; episodes: number; modelId: string; resolution: string; duration: number; outputKind: string }]; refresh: []; save: []; newSession: [] }>();
const chosenModel = ref('pippit');
const chosenKind = ref('');
const chosenResolution = ref('720P');
const chosenDuration = ref(6);
watch(() => props.task?.run_id, () => {
  const execution = props.snapshot.execution;
  chosenModel.value = execution?.model ? `${execution.kind}:${execution.model}` : 'pippit';
  chosenKind.value = execution?.kind || '';
  if (execution?.resolution) chosenResolution.value = execution.resolution;
  if (execution?.duration) chosenDuration.value = execution.duration;
}, { flush: 'post' });
const attachmentMenuVisible = ref(false);
const assetLibraryVisible = ref(false);
const assetLibraryError = ref('');
const addingAsset = ref(false);
type LibraryItem = { id: string; name: string; url: string; kind: string; projectName: string };
const libraryItems = ref<LibraryItem[]>([]);
const preferences = ref({ styleId: 'none', customStyle: '', aspectRatio: '9:16', episodes: 10 });
try { const saved = JSON.parse(localStorage.getItem('studioCreativePreferences') || 'null'); if (saved && typeof saved.styleId === 'string') preferences.value = { ...preferences.value, ...saved }; } catch { /* Use defaults if the local draft is unreadable. */ }
watch(preferences, value => { try { localStorage.setItem('studioCreativePreferences', JSON.stringify(value)); } catch { /* Submitted settings are also stored on the server. */ } }, { deep: true });
watch(() => props.snapshot.creativeOptions, value => { if (value) preferences.value = { styleId: value.styleId, customStyle: value.customStyle || '', aspectRatio: value.aspectRatio, episodes: value.episodes }; }, { immediate: true });
const fileInput = ref<HTMLInputElement>();
const messageList = ref<HTMLElement>();
const acceptedTypes = 'image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm';
const attachments = ref<{ id: string; file: File; url: string; duration?: string }[]>([]);
const toolLabels: Record<string, string> = { load_skill: '技能调用', sandbox_read: '读取文件', sandbox_bash: '执行任务', sandbox_generate_video: '生成视频', sandbox_generate_image: '生成图片' };
function decode(value: unknown): any { if (typeof value !== 'string') return value; try { return JSON.parse(value); } catch { return value; } }
function safeUrl(value: unknown): string | undefined { if (typeof value !== 'string') return; if (value.startsWith('/storage/')) return new URL(value, window.location.origin).href; try { const url = new URL(value); if (url.protocol === 'https:') return url.href; } catch { return; } }
const messages = computed(() => {
  const input = props.snapshot.conversation_messages || props.snapshot.messages || [];
  if (!Array.isArray(input)) return [];
  return input.flatMap((message: any, index: number) => {
    if (!['user', 'assistant'].includes(message.role)) return [];
    const parts: { text?: string; tool?: string; media?: { kind: string; url: string } }[] = [];
    for (const part of Array.isArray(message.content) ? message.content : []) {
      if (!part || part.hidden || part.is_thought) continue;
      const subtype = part.sub_type || part.subtype;
      if (subtype === 'tool_call_req') { const data = decode(part.data); if (typeof data?.tool_name === 'string') parts.push({ tool: data.tool_name }); }
      else if (['biz/x_data_upload_video', 'biz/x_data_upload_image'].includes(subtype)) { const data = decode(part.data); const media = data?.video || data?.image; const url = safeUrl(media?.url); if (url) parts.push({ media: { kind: data?.video ? 'video' : 'image', url } }); else parts.push({ text: '参考素材已上传' }); }
      else if (subtype === 'biz/x_data_intermediate_message') { const data = decode(part.data); if (typeof data?.message === 'string') parts.push({ text: data.message }); }
      else if (part.type === 'text' && typeof part.data === 'string') parts.push({ text: part.data });
    }
    return parts.length ? [{ id: message.displayId || `${message.id || 'message'}-${index}`, role: message.role, parts }] : [];
  });
});
watch(messages, async () => {
  const list = messageList.value;
  const nearBottom = !list || list.scrollHeight - list.scrollTop - list.clientHeight < 80;
  await nextTick();
  if (nearBottom && messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight;
}, { immediate: true });
const interactions = computed(() => [...new Set<string>((props.snapshot.interactions || []).flatMap((item: any) => (item.questions || []).filter((question: unknown) => typeof question === 'string')))]);
const assets = computed(() => {
  const result = new Map<string, { url: string; kind: string }>();
  for (const item of props.snapshot.generated_assets || []) {
    if (item.role !== 'assistant') continue;
    const url = safeUrl(item.download_url || item.url);
    const type = String(item.mime || item.format || item.type || '').toLowerCase();
    if (url) result.set(url, { url, kind: /video|mp4|mov|webm/.test(type) ? 'video' : /image|png|jpe?g|webp/.test(type) ? 'image' : 'file' });
  }
  for (const value of props.snapshot.download_urls || []) { const url = safeUrl(value); if (url && !result.has(url)) result.set(url, { url, kind: 'file' }); }
  return [...result.values()];
});
function addFiles(files: File[]) {
  if (props.busy) return;
  for (const file of files) {
    if (!acceptedTypes.split(',').includes(file.type) || !file.size || file.size > 200 * 1024 * 1024) { ElMessage.warning(`${file.name}：文件类型不支持或大小超过 200 MB`); continue; }
    if (attachments.value.length >= 32) { ElMessage.warning('每次最多添加 32 个参考素材'); break; }
    if (!attachments.value.some(item => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)) attachments.value.push({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file) });
  }
}
function chooseFiles(event: Event) { const input = event.target as HTMLInputElement; addFiles(Array.from(input.files || [])); input.value = ''; }
function dropFiles(event: DragEvent) { addFiles(Array.from(event.dataTransfer?.files || [])); }
function readDuration(item: { duration?: string }, event: Event) { const seconds = (event.target as HTMLVideoElement).duration; if (Number.isFinite(seconds)) item.duration = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`; }
async function openAssetLibrary() { assetLibraryVisible.value = true; assetLibraryError.value = ''; try { const response = await fetch(new URL('api/library', `${window.location.origin}/`)); if (!response.ok) throw new Error('资产库读取失败'); libraryItems.value = (await response.json()).items.filter((item: LibraryItem) => item.url.startsWith('/storage/') && ['image','video'].includes(item.kind)); } catch (cause) { assetLibraryError.value = cause instanceof Error ? cause.message : '读取失败'; } }
async function useLibraryAsset(item: LibraryItem) { addingAsset.value = true; try { const response = await fetch(item.url); if (!response.ok || Number(response.headers.get('content-length')) > 200*1024*1024) throw new Error('素材不可读取或超过200MB'); const blob = await response.blob(); const extension = blob.type.startsWith('video/') ? 'mp4' : 'png'; addFiles([new File([blob], `${item.name}.${extension}`, { type: blob.type })]); assetLibraryVisible.value = false; } catch (cause) { assetLibraryError.value = cause instanceof Error ? cause.message : '添加失败'; } finally { addingAsset.value = false; } }
async function addLink() { const answer = await ElMessageBox.prompt('链接会作为创作需求文本发送，不会伪装成已上传素材。', '添加链接', { inputPlaceholder: 'https://…', inputValidator: value => { try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password || '请输入不含账号密码的 HTTPS 链接'; } catch { return '请输入有效链接'; } } }).catch(() => null); if (answer) emit('update:modelValue', `${props.modelValue}\n${answer.value}`.trim()); }
function removeFile(id: string) { const item = attachments.value.find(item => item.id === id); if (item) URL.revokeObjectURL(item.url); attachments.value = attachments.value.filter(item => item.id !== id); }
function clearFiles() { for (const item of attachments.value) URL.revokeObjectURL(item.url); attachments.value = []; }
watch(() => props.submissionVersion, clearFiles);
onScopeDispose(clearFiles);
</script>

<style scoped lang="scss">
.pippitConversation { &.initialConversation { height: auto; min-height: 0; padding: 10px 12px; .conversationComposer { border-color: var(--el-border-color); &:focus-within { border-color: var(--el-color-primary-light-5); } } } .savedPreferences { color: var(--el-text-color-secondary); font-size: 12px; margin: 8px 0 0; } display: flex; flex-direction: column; height: calc(100dvh - 220px); min-height: 480px; width: 100%; text-align: left; padding: 24px; box-sizing: border-box; > header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; h2 { margin: 0 0 8px; font-size: 18px; } span { color: var(--el-text-color-secondary); font-size: 12px; } } .conversationMessages { flex: 1; min-height: 120px; overflow-y: auto; padding: 24px 2px; } .messageReference { display: block; width: min(280px, 100%); max-height: 240px; object-fit: contain; border-radius: 12px; margin-top: 12px; } .conversationMessage { margin-bottom: 22px; small { color: var(--el-text-color-secondary); font-size: 11px; } p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; font-size: 14px; } &.userMessage { margin-left: auto; max-width: 80%; width: fit-content; padding: 12px 18px; border-radius: 18px 18px 4px 18px; background: var(--el-fill-color); p { margin: 6px 0 0; } } } .toolStep { width: fit-content; max-width: 100%; margin: 8px 0; border: 1px solid var(--el-border-color); border-radius: 18px; padding: 8px 12px; font-size: 12px; summary { cursor: pointer; span { color: var(--el-text-color-secondary); margin-left: 10px; } } p { font-size: 12px; } } .conversationQuestions { padding: 18px; border-left: 2px solid var(--el-color-primary); white-space: pre-wrap; } .conversationAssets { display: flex; flex-wrap: wrap; gap: 16px; margin: 20px 0; article { width: min(320px, 100%); img, video { display: block; width: 100%; max-height: 320px; object-fit: contain; border-radius: 14px; margin-bottom: 10px; } } } a { color: var(--el-color-primary); font-size: 12px; } .conversationActions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; } .conversationComposer { flex-shrink: 0; border: 1px solid var(--el-border-color); border-radius: 22px; padding: 16px; :deep(.el-textarea__inner) { box-shadow: none; background: transparent; resize: vertical; } } .composerToolbar { :deep(.el-button) { margin: 0; font-weight: 400; font-size: 12px; height: 32px; border-radius: 18px; } :deep(.creationPreferences > .el-button), :deep(.creationPreferences .el-select__wrapper) { background: var(--el-fill-color-light); } .addMaterial { width: 32px; padding: 0; color: var(--el-text-color-regular); } display: flex; flex-wrap: wrap; gap: 10px; align-items: center; padding: 10px 0; .sendMessage { margin-left: auto; } .automaticModel { font-size: 12px; padding: 8px 14px; border-radius: 20px; background: var(--el-fill-color); color: var(--el-text-color-secondary); } } .conversationHint { font-size: 11px; line-height: 1.7; color: var(--el-text-color-secondary); } .conversationError { color: var(--el-color-danger); font-size: 13px; } .referenceDuration { position: absolute; left: 6px; top: 42px; padding: 2px 4px; border-radius: 3px; color: white; background: rgb(0 0 0 / 65%); font-size: 9px; } .assetReferenceGrid { display: grid; grid-template-columns: repeat(auto-fill,minmax(130px,1fr)); gap: 12px; button { padding: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 12px; background: var(--el-fill-color-extra-light); color: inherit; text-align: left; cursor: pointer; img, video { width: 100%; height: 100px; object-fit: contain; border-radius: 8px; } span, small { display: block; margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } small { color: var(--el-text-color-secondary); } } } .referenceList { display: flex; flex-wrap: wrap; gap: 10px; > div { position: relative; width: 72px; padding: 4px; border: 1px solid var(--el-border-color); border-radius: 12px; img, video { width: 100%; height: 56px; object-fit: cover; border-radius: 8px; } span { display: block; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } button { position: absolute; top: 0; right: 0; border: 0; border-radius: 50%; cursor: pointer; } } } }
</style>

<style lang="scss">
.studioAttachmentPopover.el-popover.el-popper { padding: 8px; border-radius: 20px; border: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color-overlay); box-shadow: 0 12px 40px rgb(0 0 0 / 16%); .attachmentMenu { display: flex; flex-direction: column; gap: 3px; button { appearance: none; display: flex; align-items: center; gap: 13px; width: 100%; min-height: 44px; margin: 0; padding: 0 14px; border: 0; border-radius: 12px; background: transparent; color: var(--el-text-color-primary); font-family: inherit; font-size: 13px; font-weight: 400; line-height: 1.4; text-align: left; cursor: pointer; transition: background .15s; svg { flex-shrink: 0; stroke-width: 1.6; } &:hover, &:focus-visible { background: var(--el-fill-color); outline: none; } } } }
</style>
