<template>
  <main class="workspacePage" :style="{ '--agentWidth': `${agentVisible ? agentWidth : 0}px` }">
    <canvasPanel
      :key="workspaceStore.project?.directory"
      v-model:selectedTool="selectedTool"
      ref="canvasPanelRef"
      class="canvasPanel"
      :class="{ backgroundPanel: activePanel !== 'canvas' }"
      :inert="activePanel !== 'canvas'"
      :aria-hidden="activePanel !== 'canvas'"
      :active="activePanel === 'canvas'"
      :settingsVisible="settingsVisible" />
    <keep-alive :max="1">
      <documentPanel
        v-if="activePanel === 'document'"
        :key="workspaceStore.project?.directory"
        :ref="setDocumentPanel"
        :readNode="readDocumentNode"
        :readNodes="readDocumentNodes"
        :focusNode="focusDocumentNode"
        :mountNode="mountDocumentNode"
        :resolveNodeFile="resolveDocumentNodeFile"
        :observeNode="observeDocumentNode"
        :flushNodes="flushDocumentNodes"
        :fileAction="performFileAction"
        :saveNode="saveDocumentNode" />
    </keep-alive>
    <workspaceMenu class="workspaceMenu" />
    <section v-if="analysisProject && !analysisDismissed && (analysisProject.status === 'analyzing' || ['failed', 'paused', 'done'].includes(analysisProject.analysis_state?.status || ''))" class="analysisStatus" aria-label="剧本分析进度">
      <header class="analysisHeader" :class="{ episodeHeader: isEpisodeEditor }">
        <button class="analysisBack" type="button" :aria-label="isEpisodeEditor ? '返回剧集' : '返回项目资源'" @click="isEpisodeEditor ? selectedEpisode = null : router.push('/home?section=projects')">‹</button>
        <span class="analysisProjectName">{{ isEpisodeEditor ? `第 ${selectedEpisode} 集 · ${analysisProject.name}` : analysisProject.name }}</span>
        <el-tag v-if="analysisProject.generation_settings?.creativePreferences?.styleName" size="small" effect="plain">{{ analysisProject.generation_settings.creativePreferences.styleName }}</el-tag>
        <template v-if="isEpisodeEditor"><span class="episodeSaved">● {{ editingShotPrompt ? '未保存' : generationSettingsBusy || shotBusy ? '正在处理' : '已保存' }}</span><div class="episodeHeaderTools"><generationModelMenu v-model="videoModel" :options="generationModelOptions.video" :defaultLabel="defaultVideoModelLabel" :disabled="shotBusy || videoBatchRunning || activeEpisodeShot?.video_status === 'processing'" /><el-select class="compactSetting" :modelValue="videoModel === 'pippit' ? '自动' : currentGenerationOptions.resolution" :disabled="videoModel === 'pippit' || videoBatchRunning || generationSettingsBusy || activeEpisodeShot?.video_status === 'processing'" aria-label="视频清晰度" @change="saveClipGeneration('resolution', $event)"><el-option v-for="value in ['720P', '1080P', '1K', '2K']" :key="value" :label="value.toLowerCase()" :value="value" /></el-select><el-select class="compactSetting" :modelValue="videoModel === 'pippit' ? '自动' : currentGenerationOptions.aspect_ratio" :disabled="videoModel === 'pippit' || videoBatchRunning || generationSettingsBusy || activeEpisodeShot?.video_status === 'processing'" aria-label="视频画幅" @change="saveClipGeneration('aspect_ratio', $event)"><el-option v-for="value in ['9:16', '16:9', '1:1', '3:4', '4:3', '21:9']" :key="value" :label="value" :value="value" /></el-select></div></template>
        <ol v-else class="analysisSteps" aria-label="制作步骤"><li :class="{ active: analysisStep === 1 }">1. 脚本</li><li :class="{ active: analysisStep === 2 }"><button type="button" :disabled="analysisProject.analysis_state?.status !== 'done'" @click="productionView = 'assets'">2. 制作资产库</button></li><li :class="{ active: analysisStep === 3 }"><button type="button" :disabled="analysisProject.analysis_state?.status !== 'done'" @click="productionView = 'episodes'; selectedEpisode = null">3. 剧集</button></li></ol>
        <el-button round size="small" @click="router.push({ path: '/home', query: { section: 'dreamina', projectId: analysisProject?.id } })">即梦画布</el-button>
      </header>
      <div v-if="analysisProject.analysis_state?.status === 'done'" class="analysisResults" :class="{ editingEpisode: productionView === 'episodes' && selectedEpisode !== null }">
        <div v-if="!isEpisodeEditor && productionView === 'assets'" class="generationModels"><generationModelMenu v-model="imageModel" :options="generationModelOptions.image" :defaultLabel="defaultImageModelLabel" :disabled="assetGenerating" /></div>
        <p v-if="modelOptionsError" class="generationModelNote" role="alert">{{ modelOptionsError }}</p>
        <div v-if="pippitTargetProgress || activeEpisodeShot?.provider_model === 'pippit' && activeEpisodeShot?.provider_task_id" class="pippitTargetStatus" role="status"><span>{{ pippitTargetProgress || activeEpisodeShot?.last_error || '已保存 Pippit 任务，可查询原任务状态' }}</span><el-button text size="small" :loading="pippitQueryBusy" @click="refreshPippitTarget">刷新原任务状态</el-button><a v-if="pippitTargetLink" :href="pippitTargetLink" target="_blank" rel="noopener noreferrer">查看 Pippit 任务 ↗</a></div>
        <template v-if="productionView === 'episodes'">
          <div v-if="selectedEpisode === null" class="resultHeading"><div><h1>剧集</h1><p>共 {{ episodeItems.length }} 集</p></div><el-button round @click="productionView = 'assets'">制作资产库</el-button></div>
          <div v-if="selectedEpisode === null" class="episodeGrid">
            <button v-for="episode in episodeItems" :key="episode.number" type="button" class="episodeCard" @click="selectedEpisode = episode.number">
              <div class="episodePreview"><icon-file-text :size="30" :strokeWidth="1" /></div>
              <div class="episodeContent"><small>分镜脚本已就绪</small><h2>第 {{ episode.number }} 集</h2><p>{{ episode.characters }} 个角色 · {{ episode.scenes }} 个场景 · {{ episode.shots }} 个分镜</p><span class="episodeAction">编辑 · 生成视频 →</span></div>
            </button>
          </div>
          <div v-else class="episodeEditor">
            <aside class="productionLibrary"><h2>制作资产库</h2><input v-model="assetSearch" type="search" placeholder="搜索资产库" aria-label="搜索资产库" /><section v-for="group in episodeAssetGroups" :key="group.key"><h3>{{ group.label }}</h3><button v-for="asset in group.items" :key="asset.id" type="button" class="libraryAsset" @click="selectedResult = asset"><div><img v-if="asset.image" :src="asset.image" :alt="asset.name" /><icon-file-text v-else :size="20" /></div><span>{{ asset.name }}<small>{{ asset.image ? '参考图已就绪' : '参考图待生成' }}</small></span></button></section></aside>
            <div v-if="activeEpisodeShot" class="clipScript"><header><h2>片段 {{ String(activeEpisodeShot.shot_no).padStart(2, '0') }}</h2><span>{{ activeEpisodeShot.duration }} 秒 · {{ shotStatusText(activeEpisodeShot) }}</span></header><div class="clipReferences"><button v-for="asset in activeShotAssets" :key="`${asset.kind}-${asset.id}`" type="button" :class="{ missingReference: !asset.image }" @click="selectedResult = asset"><img v-if="asset.image" :src="asset.image" :alt="asset.name" /><span>{{ asset.name }}</span><small v-if="!asset.image">待设置参考图</small></button></div><article class="clipPrompt"><h3>{{ activeEpisodeShot.title }}</h3><p>{{ activeEpisodeShot.scene_name }} · {{ (activeEpisodeShot.character_names || []).join('、') }}</p><textarea v-if="editingShotPrompt" v-model="shotPromptDraft" aria-label="编辑分镜提示词" /><p v-else class="scriptText">{{ activeEpisodeShot.prompt }}</p><details><summary>镜头设计与首帧提示词</summary><p class="scriptText">{{ designText(activeEpisodeShot.direction) }}</p><p class="scriptText">{{ activeEpisodeShot.keyframe_prompt }}</p></details><footer><el-button round :disabled="shotBusy || videoBatchRunning || activeEpisodeShot.video_status === 'processing'" @click="editingShotPrompt ? saveEpisodeShot() : startEditingShot()">{{ editingShotPrompt ? '保存' : '编辑' }}</el-button><el-button v-if="editingShotPrompt" round @click="editingShotPrompt = false">取消</el-button><el-button type="primary" round :disabled="videoBatchRunning" :loading="shotBusy || activeEpisodeShot.video_status === 'processing'" @click="generateEpisodeShot">生成视频</el-button></footer></article><p v-if="activeEpisodeShot.last_error" class="clipError" role="alert">{{ activeEpisodeShot.last_error }}</p></div>
            <aside v-if="activeEpisodeShot" class="clipPreview"><video v-if="activeEpisodeShot.video_url" :key="activeEpisodeShot.video_url" :src="activeEpisodeShot.video_url" controls :poster="activeEpisodeShot.keyframe_url || undefined" /><div v-else class="emptyClipPreview"><icon-file-text :size="30" /><p>{{ activeEpisodeShot.video_status === 'processing' ? '视频正在生成…' : '生成的片段将会显示在这里' }}</p></div></aside>
            <section class="clipTimelineArea"><header class="clipBatchTools"><span>{{ videoBatchMessage || '本集片段' }}</span><template v-if="videoBatchRunning"><el-button size="small" :disabled="videoBatchPauseRequested" @click="videoBatchPauseRequested = true">{{ videoBatchPauseRequested ? '完成当前片段后暂停' : '暂停后续片段' }}</el-button></template><template v-else-if="selectingVideoShots"><el-button size="small" @click="selectedVideoShotIds = eligibleVideoShots.map(shot => shot.id)">全选待生成</el-button><el-button size="small" @click="selectingVideoShots = false">取消</el-button><el-button size="small" type="primary" :disabled="!selectedVideoShotIds.length || shotBusy" @click="generateVideoBatch">批量生成 · {{ selectedVideoShotIds.length }}</el-button></template><el-button v-else size="small" :disabled="shotBusy" @click="selectingVideoShots = true; selectedVideoShotIds = []">选择片段 · 批量生成</el-button></header><nav class="clipTimeline" aria-label="片段列表"><button v-for="shot in episodeShots" :key="shot.id" type="button" :class="{ active: activeEpisodeShot?.id === shot.id, selectedClip: selectingVideoShots && selectedVideoShotIds.includes(shot.id) }" :aria-pressed="selectingVideoShots ? selectedVideoShotIds.includes(shot.id) : activeEpisodeShot?.id === shot.id" @click="chooseTimelineShot(shot)"><div><video v-if="shot.video_url" :key="shot.video_url" :src="shot.video_url" :poster="shot.keyframe_url || undefined" muted playsinline preload="metadata" aria-label="已生成视频缩略图" @loadedmetadata="seekThumbnail" /><img v-else-if="shot.keyframe_url" :src="shot.keyframe_url" alt="" /><icon-file-text v-else :size="20" /><span v-if="selectingVideoShots" class="clipCheck">{{ selectedVideoShotIds.includes(shot.id) ? '✓' : canQueueVideo(shot) ? '○' : '—' }}</span><span v-else-if="shot.video_url" class="clipPlay">▶</span></div><span>片段 {{ String(shot.shot_no).padStart(2, '0') }} · {{ shot.duration }}s</span><small>{{ shotStatusText(shot) }}</small></button></nav></section>
          </div>
        </template>
        <template v-else>
        <nav class="resultTabs" aria-label="分析结果分类"><button v-for="tab in resultTabs" :key="tab.key" type="button" :class="{ active: resultTab === tab.key }" @click="resultTab = tab.key">{{ tab.label }} <span>{{ resultItemsFor(tab.key).length }}</span></button></nav>
        <div class="resultHeading"><div><h1>{{ resultTabs.find(tab => tab.key === resultTab)?.label }}</h1><p>分析结果已保存。选择卡片查看描述与生成提示词。</p></div><el-button round @click="analysisDismissed = true">查看画布 ↗</el-button></div>
        <div v-if="resultTab !== 'shots'" class="assetGenerationBar"><div><strong>{{ selectingAssets ? `已选择 ${selectedAssetIds.length} 项` : '生成制作参考图' }}</strong><p v-if="batchGenerating" role="status">正在生成 {{ batchProgress.completed + 1 }} / {{ batchProgress.total }}：{{ batchProgress.name }}</p><p v-else>{{ batchSummary || '选择需要生成的资产，生成结果会保存到当前项目。' }}</p></div><div class="assetGenerationActions"><el-select v-if="resultTab === 'characters'" v-model="characterReferenceVariant" aria-label="批量角色参考类型" style="width: 220px" :disabled="assetGenerating"><el-option v-for="item in characterReferenceOptions" :key="item.id" :label="item.label" :value="item.id" /></el-select><template v-if="selectingAssets"><el-button round :disabled="assetGenerating" @click="selectedAssetIds = resultItemsFor(resultTab).map(item => item.id)">全选</el-button><el-button round :disabled="assetGenerating" @click="selectingAssets = false; selectedAssetIds = []">取消</el-button><el-button type="primary" round :loading="batchGenerating" :disabled="!selectedAssetIds.length || assetGenerating && !batchGenerating" @click="generateSelectedImages">生成图片 · {{ selectedAssetIds.length }}</el-button></template><el-button v-else round :disabled="assetGenerating" @click="selectingAssets = true; batchSummary = ''">选择 · 批量生成</el-button></div></div>
        <div class="resultGrid">
          <div v-for="item in resultItemsFor(resultTab)" :key="item.id" class="resultCard" :class="{ selectedAsset: selectingAssets && selectedAssetIds.includes(item.id) }">
            <button type="button" class="assetCardOpen" :aria-pressed="selectingAssets ? selectedAssetIds.includes(item.id) : undefined" @click="selectingAssets ? toggleAssetSelection(item.id) : selectedResult = item">
            <span v-if="selectingAssets" class="assetSelectionMark">{{ selectedAssetIds.includes(item.id) ? '✓' : '○' }}</span>
            <div class="resultPreview"><img v-if="item.image" :src="item.image" :alt="item.name" /><icon-file-text v-else :size="38" :strokeWidth="1" /></div>
            <strong>{{ item.name }}</strong><span class="resultDescription">{{ item.description }}</span><small>{{ item.image ? '已有参考图' : resultTab === 'shots' ? '分镜设计与提示词已就绪' : '文字设定已就绪 · 参考图待生成' }}</small>
            </button><p v-if="assetImageErrors[`${item.kind}-${item.id}`]" class="assetImageError" role="alert">{{ assetImageErrors[`${item.kind}-${item.id}`] }}</p><el-button v-if="resultTab !== 'shots' && !selectingAssets" class="assetGenerateButton" round size="small" :loading="generatingAssetKey === `${item.kind}-${item.id}`" :disabled="assetGenerating" @click="generateResultImage(item)">{{ item.image ? '重新生成' : '生成图片' }}</el-button>
          </div>
        </div>
        <p v-if="!resultItemsFor(resultTab).length" class="resultEmpty">本次分析没有此类结果。</p>
        <div class="resultContinue"><el-button round @click="productionView = 'episodes'; selectedEpisode = null">继续 · 查看剧集 →</el-button></div>
        </template>
      </div>
      <div v-else class="analysisBody">
        <h1>分析脚本</h1>
        <div class="analysisStage" :class="{ running: analysisProject.status === 'analyzing' }">
          <div class="analysisStageContent" role="status" aria-live="polite">
            <div v-if="analysisProject.status === 'analyzing'" class="analysisActivity" aria-hidden="true"><i /><i /><i /></div>
            <h2>{{ analysisProject.status === 'analyzing' ? analysisProject.analysis_state?.progress || '正在深入分析脚本…' : analysisProject.analysis_state?.status === 'paused' ? '已暂停，完成部分已保存' : '分析暂未完成' }}</h2>
            <p v-if="analysisProject.analysis_state?.error" class="analysisError">{{ analysisProject.analysis_state.error }}</p>
            <p v-else>完成一项即保存一项。暂停后可在设置中更换文本 API，再继续未完成项；当前已提交的请求结束并保存后才会暂停。</p>
            <div v-if="analysisProject.analysis_state?.counts" class="analysisCounts"><span v-for="(label, key) in analysisCountLabels" :key="key">{{ label }} <b>{{ analysisProject.analysis_state.counts[key] ?? 0 }}</b></span></div>
            <div v-if="analysisProject.analysis_state?.total" class="analysisProgress">
              <el-progress :percentage="Math.min(100, Math.round((analysisProject.analysis_state.completed ?? 0) / analysisProject.analysis_state.total * 100))" :showText="false" :strokeWidth="3" />
              <span>已完成 {{ analysisProject.analysis_state.completed ?? 0 }} / {{ analysisProject.analysis_state.total }}</span>
            </div>
            <div class="analysisActions">
              <el-button v-if="analysisProject.status === 'analyzing'" round :disabled="analysisProject.analysis_state?.pauseRequested" :loading="analysisRetrying" @click="pauseAnalysis">{{ analysisProject.analysis_state?.pauseRequested ? '当前请求保存后暂停' : '暂停后续任务' }}</el-button>
              <el-button v-else round :loading="analysisRetrying" @click="retryAnalysis">继续未完成项</el-button>
              <el-button v-if="analysisProject.status !== 'analyzing'" round @click="settingsInitialPanel = 'languageModel'; settingsVisible = true">更换 API 配置</el-button>
              <el-button round @click="analysisDismissed = true">查看已保存画布</el-button>
              <el-button v-if="analysisRefreshError" round @click="refreshDramaForgeProject(String(analysisProject.id))">刷新状态</el-button>
            </div>
            <p v-if="analysisRefreshError" role="alert">{{ analysisRefreshError }}</p>
          </div>
        </div>
        <section v-if="analysisUnits.length" class="analysisTaskList" aria-label="已保存任务与来源">
          <h2>任务与已保存成果</h2><p>已保存 {{ analysisUnits.filter(unit => unit.status === 'done').length }} 项；下列任务不包含图片或视频生成。</p>
          <div v-for="unit in analysisUnits" :key="unit.id" class="analysisTaskRow"><strong>{{ unit.label }}</strong><span>{{ analysisUnitLabels[unit.status] || unit.status }}</span><small>{{ [unit.source?.provider, unit.source?.model].filter(Boolean).join(' · ') }}</small><small v-if="unit.error">{{ unit.error }}</small></div>
        </section>
        <section v-if="analysisProject.shots?.length" class="partialAnalysisResults" aria-label="已保存的部分分析结果">
          <h2>已保存内容</h2><div class="resultTabs"><button v-for="tab in resultTabs" :key="tab.key" type="button" :class="{ active: resultTab === tab.key }" @click="resultTab = tab.key">{{ tab.label }} {{ resultItemsFor(tab.key).length }}</button></div>
          <div class="partialResultGrid"><button v-for="item in resultItemsFor(resultTab)" :key="item.id" type="button" @click="selectedResult = item"><strong>{{ item.name }}</strong><span>{{ item.description }}</span><small>{{ Object.keys(item.design || {}).length ? '已保存设定 · 点击查看' : '已提取 · 详细设计待完成' }}</small></button></div>
        </section>
      </div>
    </section>
    <el-dialog :modelValue="!!selectedResult" :title="selectedResult?.name" width="760px" class="analysisResultDialog" @close="selectedResult = null">
      <template v-if="selectedResult"><img v-if="selectedReferenceImage" class="assetDetailImage" :src="selectedReferenceImage" :alt="selectedResult.name" /><p v-if="selectedCharacter && !selectedReferenceExists">当前显示主参考图；所选参考类型尚未生成。</p><p class="resultDetailText">{{ selectedResult.description }}</p><template v-if="selectedResult.kind && selectedResult.kind !== 'shots'"><el-select v-model="imageModel" aria-label="参考图生成模型" placeholder="选择图片模型"><el-option v-for="model in generationModelOptions.image" :key="model.id" :label="model.label" :value="model.id" /></el-select></template><section v-if="selectedResult.kind === 'characters'" class="characterMediaOptions"><h3>角色参考类型</h3><el-select v-model="characterReferenceVariant" aria-label="角色参考图类型"><el-option v-for="item in characterReferenceOptions" :key="item.id" :value="item.id" :label="item.label" /></el-select><h3>角色声音</h3><audio v-if="selectedCharacterAudio?.url" :src="selectedCharacterAudio.url" controls preload="metadata" /><input ref="characterAudioInput" type="file" accept=".mp3,.wav,.m4a,.ogg,.flac" hidden @change="uploadCharacterAudio" /><el-button :loading="characterAudioBusy" @click="characterAudioInput?.click()">{{ selectedCharacterAudio ? '更换角色声音' : '上传角色声音' }}</el-button><p>保存与试听你上传的声音；目前尚未接通角色配音生成。音频不会自动发送给生成模型。</p></section><h3>生成提示词</h3><p class="resultDetailText">{{ selectedReferencePrompt || '该类型的专用提示词尚未完成。' }}</p><section v-for="section in resultDesignSections" :key="section.label"><h3>{{ section.label }}</h3><p class="resultDetailText">{{ section.text }}</p></section><el-button v-if="selectedResult.prompt" @click="copyResultPrompt">复制提示词</el-button><el-button v-if="selectedResult.kind && selectedResult.kind !== 'shots'" type="primary" :loading="assetGenerating" @click="generateResultImage()">{{ selectedReferenceExists ? '重新生成所选类型' : '生成所选类型' }}</el-button></template>
    </el-dialog>
    <div class="workspaceTools">
      <div class="productionCanvasTools">
      <el-select v-if="analysisProject && activePanel === 'canvas'" :modelValue="''" filterable placeholder="定位剧本 / 提示词" aria-label="定位画布内容" style="width: 180px" @change="focusProductionContent"><el-option v-for="item in productionCanvasContents" :key="item.id" :label="item.label" :value="item.id" /></el-select>
      <el-tag v-if="analysisProject?.generation_settings?.creativePreferences?.styleName" size="small" effect="plain">风格 · {{ analysisProject.generation_settings.creativePreferences.styleName }}</el-tag>
      <el-button v-if="analysisProject?.analysis_state?.status" class="analysisResultsButton" round size="small" @click="analysisDismissed = false">{{ analysisProject.analysis_state.status === 'done' ? '分析结果' : '分析进度' }}</el-button>
      <el-button round size="small" @click="router.push({ path: '/home', query: { section: 'dreamina', projectId: analysisProject?.id } })">即梦画布</el-button>
      </div>
      <el-segmented :modelValue="activePanel" class="panelSwitcher" :options="panelOptions" size="small" aria-label="切换面板" @change="switchPanel">
        <template #default="{ item }">
          <span class="panelOption">
            <component :is="item.icon" :size="14" aria-hidden="true" />
            {{ item.label }}
          </span>
        </template>
      </el-segmented>
      <div class="bottomTools">
        <el-card v-if="activePanel === 'canvas'" class="toolMenu" shadow="never" :bodyStyle="{ padding: '3px 6px' }">
          <div class="toolMenuContent" role="toolbar" aria-label="画布工具">
            <el-tooltip content="添加节点" placement="top" :showArrow="false" :hideAfter="0" :enterable="false" :triggerKeys="[]">
              <el-button class="toolButton addNodeButton" :disabled="!canvasPanelRef?.canvasReady || settingsVisible" aria-label="添加节点" aria-haspopup="menu" @click="canvasPanelRef?.addNodeAtPointer()">
                <icon-plus :size="18" aria-hidden="true" />
              </el-button>
            </el-tooltip>
            <el-button class="pippitButton" size="small" :disabled="!canvasPanelRef?.canvasReady || settingsVisible" @click="pippitVisible = true">
              <icon-sparkles :size="15" aria-hidden="true" />
              Pippit 创作
            </el-button>
            <el-tooltip :content="selectedTool === 'move' ? '移动工具，点击切换为抓手' : '抓手工具，点击切换为移动'" placement="top" :showArrow="false" :hideAfter="0" :enterable="false" :triggerKeys="[]">
              <el-button
                class="toolButton"
                text
                :type="selectedTool === 'hand' ? 'primary' : 'default'"
                :aria-pressed="selectedTool === 'hand'"
                aria-label="切换抓手/移动工具"
                @click="selectedTool = selectedTool === 'move' ? 'hand' : 'move'">
                <component :is="selectedTool === 'move' ? IconPointer : IconHandStop" :size="18" aria-hidden="true" />
              </el-button>
            </el-tooltip>
            <el-tooltip :showArrow="false" content="帮助" placement="top" :hideAfter="0" :enterable="false" :triggerKeys="[]" :disabled="helpVisible">
              <span class="toolTrigger">
                <el-popover v-model:visible="helpVisible" trigger="click" placement="top-end" :width="196">
                  <template #reference>
                    <el-button class="toolButton" text aria-label="帮助">
                      <icon-help :size="18" />
                    </el-button>
                  </template>
                  <div class="helpMenu">
                    <el-button
                      class="helpAction"
                      tag="a"
                      text
                      :icon="IconBook"
                      href="https://qcn7xdsqgc4z.feishu.cn/docx/RXFqdgR2Xo0dXZxGfd0cZCGgnwf"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click="helpVisible = false">
                      使用教程
                    </el-button>
                    <el-button
                      class="helpAction"
                      tag="a"
                      text
                      :icon="IconBug"
                      href="https://docs.qq.com/smartsheet/form/EmvmQBrmlPmr%2Fss_vsqk2v%2FvhiGzE?tab=ss_vsqk2v"
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Toonflow 需求/BUG反馈表"
                      @click="helpVisible = false">
                      汇报 BUG
                    </el-button>
                    <el-button class="helpAction" text :icon="IconBrandWechat" @click="showContact('community')">加入交流群</el-button>
                    <el-button class="helpAction" text :icon="IconBriefcase" @click="showContact('business')">商务合作</el-button>
                  </div>
                </el-popover>
              </span>
            </el-tooltip>
          </div>
        </el-card>
        <el-tooltip v-if="!agentVisible" content="Toonflow Agent" placement="top" :showArrow="false" :hideAfter="0">
          <el-button
            class="agentButton"
            :class="{ standalone: activePanel !== 'canvas' }"
            :aria-expanded="agentVisible"
            aria-label="Toonflow Agent"
            aria-controls="agentPanel"
            @click="agentVisible = !agentVisible"></el-button>
        </el-tooltip>
      </div>
    </div>
    <floatingAgent v-model="agentVisible" @resize="agentWidth = $event" />
    <settings v-model="settingsVisible" :initialPanel="settingsInitialPanel" @closed="notifySettingsClosed" />
    <pippitCreator v-model="pippitVisible" @insertAssets="insertPippitAssets" />
    <el-dialog v-model="contactVisible" :title="contactInfo.title" width="min(360px, calc(100vw - 32px))" alignCenter appendToBody>
      <div class="contactContent">
        <q-r-code
          :value="contactInfo.url"
          :size="192"
          type="svg"
          color="#000000"
          bgColor="#ffffff"
          borderless
          role="img"
          :aria-label="`${contactInfo.title}二维码`" />
        <p class="contactTip">{{ contactInfo.tip }}</p>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onScopeDispose, provide, ref, shallowRef, watch, type ComponentPublicInstance } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import axios from "axios";
import { IconVector, IconFileText, IconPointer, IconHandStop, IconPlus, IconHelp, IconBook, IconBug, IconBrandWechat, IconBriefcase, IconSparkles } from "@tabler/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { QRCode } from "tdesign-vue-next";
import settings from "@/components/settings/index.vue";
import { useWorkspaceStore } from "@/stores/workspace";
import { registerWorkspaceControl, waitForControlValue } from "@/lib/mcpControl";
import anonymousData from "@/lib/anonymousData";
import { useProviderBalances } from "@/lib/providerBilling";
import canvasPanel from "./panels/canvas/canvasHost.vue";
import type { DocumentNodeOptions } from "./panels/canvas/canvasFiles";
import workspaceMenu from "./components/workspaceMenu.vue";
import floatingAgent from "./components/floatingAgent.vue";
import pippitCreator from "./components/pippitCreator.vue";
import generationModelMenu from "./components/generationModelMenu.vue";

const documentPanel = defineAsyncComponent(() => import("./panels/document/index.vue"));

function dramaForgeApiUrl(path: string) {
  return new URL(`api/${path.replace(/^\/+/, "")}`, `${window.location.origin}/`).toString();
}

const activePanel = ref<"canvas" | "document">("canvas");
const selectedTool = ref<"move" | "hand">("move");
const workspaceStore = useWorkspaceStore();
const route = useRoute();
function handleStudioPanelMessage(event: MessageEvent<{ source?: string; type?: string }>) {
  if (event.source !== window.parent || event.data?.source !== "dramaforge") return;
  if (event.data.type === "open-settings") settingsVisible.value = true;
  if (event.data.type === "open-canvas") settingsVisible.value = false;
}
onMounted(() => {
  anonymousData.track("workspace.canvas");
  window.addEventListener("message", handleStudioPanelMessage);
  if (route.query.settings === "1") settingsVisible.value = true;
});
onScopeDispose(() => window.removeEventListener("message", handleStudioPanelMessage));
useProviderBalances();
const panelOptions = [
  { label: "画布", value: "canvas", icon: IconVector },
  { label: "文档", value: "document", icon: IconFileText },
];
const agentVisible = ref(!route.query.dramaforgeProjectId);
const agentWidth = ref(0);
const settingsVisible = ref(route.query.settings === "1");
const settingsInitialPanel = ref("");
const pippitVisible = ref(false);
function notifySettingsClosed() {
  window.dispatchEvent(new Event("toonflow:settings-closed"));
  (window as Window & { __DRAMAFORGE_CLOSE_GLOBAL_SETTINGS__?: () => void }).__DRAMAFORGE_CLOSE_GLOBAL_SETTINGS__?.();
}
const helpVisible = ref(false);
const contactVisible = ref(false);
const contactType = ref<"community" | "business">("community");
const contacts = {
  community: {
    title: "加入交流群",
    url: "https://work.weixin.qq.com/u/vc36adcc89845edcbe?v=5.0.3.63936&bb=85b8d228e8",
    tip: "Toonflow 是为爱发电的开源项目。欢迎文明交流、友善反馈；回复可能需要一些时间，请避免责问或命令式沟通，感谢你的理解与尊重。",
  },
  business: {
    title: "商务合作",
    url: "https://work.weixin.qq.com/u/vc0f54596c5837d05a?v=5.0.8.70675",
    tip: "此联系方式仅用于商务合作接洽，不提供问题答疑。使用问题欢迎在交流群交流，需求与 BUG 可通过反馈表提交。感谢理解。",
  },
};
const contactInfo = computed(() => contacts[contactType.value]);

function showContact(type: "community" | "business") {
  contactType.value = type;
  helpVisible.value = false;
  contactVisible.value = true;
}
const canvasPanelRef = ref<InstanceType<typeof canvasPanel>>();

type PippitCanvasAsset = { url: string; name: string; mime?: string; kind: "image" | "video" };
async function insertPippitAssets(assets: PippitCanvasAsset[]) {
  try {
    if (!canvasPanelRef.value?.addPippitAssets) throw new Error("画布还没有准备好，请稍后再试");
    const count = await canvasPanelRef.value.addPippitAssets(assets);
    ElMessage.success(`已将 ${count} 个 Pippit 生成素材放入当前画布`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "放入画布失败");
  }
}
const documentPanelCache = shallowRef<{ directory: string; instance: InstanceType<typeof documentPanel> }>();
const documentPanelRef = computed(() => documentPanelCache.value?.directory === workspaceStore.project?.directory ? documentPanelCache.value?.instance : undefined);
watch(() => workspaceStore.project?.directory, () => { documentPanelCache.value = undefined; }, { flush: "sync" });
function setDocumentPanel(value: Element | ComponentPublicInstance | null) {
  const directory = workspaceStore.project?.directory;
  // KeepAlive 失活会清空模板 ref，保留同一工作区实例以协调后台文档保存和文件操作。
  if (value && directory) documentPanelCache.value = { directory, instance: value as InstanceType<typeof documentPanel> };
}
provide("canvas", () => canvasPanelRef.value?.getCanvasContext());
provide("mentionCanvas", () => canvasPanelRef.value?.mentionSource);
provide("activateCanvasPanel", () => switchPanel("canvas"));
provide("performWorkspaceFileAction", (directory: string, action: "copy" | "rename" | "move" | "delete", path: string, target?: string, entryType: "canvas" | "directory" = "canvas") =>
  documentPanelRef.value ? documentPanelRef.value.performFileAction(directory, action, path, target, entryType) : performFileAction(directory, action, path, target));

type DramaForgeProject = {
  id: number;
  name: string;
  status?: string;
  workspace_directory?: string;
  generation_settings?: Record<string, any>;
  outline?: { title?: string };
  analysis_state?: { status?: string; progress?: string; error?: string; completed?: number; total?: number; counts?: Record<string, number>; pauseRequested?: boolean; units?: Record<string, { id: string; label: string; status: string; error?: string; source?: { provider?: string; model?: string } }> };
  shots?: unknown[];
  [key: string]: unknown;
};
type DramaForgeWindow = Window & {
  __DRAMAFORGE_PROJECT__?: DramaForgeProject;
  __DRAMAFORGE_CANVAS_BRIDGE__?: { syncProject: (project: DramaForgeProject, force?: boolean) => Promise<unknown> };
};
let dramaForgeSyncRunning: Promise<unknown> = Promise.resolve();
let dramaForgeRefreshTimer: ReturnType<typeof setTimeout> | undefined;
let dramaForgeRefreshStopped = false;
const lastDramaForgeSync = new Map<number, string>();
let registeredDramaForgeBridge: NonNullable<DramaForgeWindow["__DRAMAFORGE_CANVAS_BRIDGE__"]> | undefined;
const analysisProject = ref<DramaForgeProject | null>(null);
const analysisRetrying = ref(false);
const analysisDismissed = ref(false);
const router = useRouter();
const analysisRefreshError = ref("");
const analysisCountLabels = { episodes: "分集", characters: "角色", scenes: "场景", props: "道具", shots: "分镜" };
const resultTabs = [{ key: "characters", label: "角色" }, { key: "scenes", label: "场景" }, { key: "props", label: "道具" }, { key: "shots", label: "分镜" }] as const;
type ResultTab = typeof resultTabs[number]["key"];
type AnalysisResultItem = { id: number; name: string; description: string; prompt: string; image?: string; design?: Record<string, unknown>; kind?: ResultTab };
const resultTab = ref<ResultTab>("characters");
const productionView = ref<"assets" | "episodes">(route.query.production === "episodes" ? "episodes" : "assets");
const selectedEpisode = ref<number | null>(Number(route.query.episode) > 0 ? Number(route.query.episode) : null);
watch([productionView, selectedEpisode], ([view, episode]) => {
  editingShotPrompt.value = false;
  void router.replace({ query: { ...route.query, production: view, episode: view === "episodes" && episode !== null ? String(episode) : undefined } });
});
watch(() => [route.query.production, route.query.episode], ([view, episode]) => {
  productionView.value = view === "episodes" ? "episodes" : "assets";
  selectedEpisode.value = Number(episode) > 0 ? Number(episode) : null;
});
const assetGenerating = ref(false);
const imageModel = ref("");
const videoModel = ref("");
const defaultImageModelLabel = ref("选择图片模型");
const defaultVideoModelLabel = ref("选择视频模型");
const isEpisodeEditor = computed(() => productionView.value === "episodes" && selectedEpisode.value !== null);
const pippitTargetProgress = ref("");
const pippitTargetLink = ref("");
const pippitQueryBusy = ref(false);
const pippitTargetTask = ref<{ thread_id: string; run_id: string; web_thread_link?: string }>();
const targetGenerationAbort = new AbortController();
onScopeDispose(() => targetGenerationAbort.abort());
async function generateWithPippit(projectId: number, kind: string, targetId: number, message: string, variant = "base") {
  pippitTargetProgress.value = "正在提交 Pippit 生成任务…";
  pippitTargetLink.value = "";
  pippitTargetTask.value = undefined;
  let submitted = false;
  try {
  const submit = await fetch(dramaForgeApiUrl("pippit/generate-target"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, kind, target_id: targetId, message, variant }), signal: targetGenerationAbort.signal });
  const task = await submit.json();
  if (!submit.ok) throw new Error(typeof task.detail === "string" ? task.detail : "Pippit 提交失败");
  submitted = true;
  pippitTargetTask.value = task;
  pippitTargetLink.value = task.web_thread_link || "";
  pippitTargetProgress.value = "Pippit 任务已提交，正在查询结果…";
  for (let attempt = 0; attempt < 720; attempt++) {
    if (targetGenerationAbort.signal.aborted) throw new Error("页面已关闭，任务仍在后台继续");
    const response = await fetch(dramaForgeApiUrl("pippit/thread"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ thread_id: task.thread_id, run_id: task.run_id }), signal: targetGenerationAbort.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Pippit 状态读取失败，可重新点击生成以恢复查询");
    if (result.binding?.bound_url) { pippitTargetProgress.value = "Pippit 生成完成，结果已保存到当前项目"; return; }
    const status = String(result.status || "").toLowerCase();
    if (["failed", "failure", "error", "canceled", "cancelled"].includes(status)) throw new Error("Pippit 未完成生成，请查看任务回复");
    if (["requires_action", "requires_user_input", "interaction_required"].includes(status)) throw new Error("Pippit 需要补充信息，请打开任务链接查看并回复");
    pippitTargetProgress.value = "Pippit 正在生成，完成后会自动保存到当前资产或片段…";
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
  throw new Error("Pippit 任务仍未完成，请刷新原任务状态，不要重复生成");
  } catch (error) {
    const message = error instanceof Error ? error.message : "请求异常";
    pippitTargetProgress.value = submitted ? `任务已提交，尚未确认生成结果：${message}。请刷新原任务状态，不会重复提交。` : `未确认提交成功：${message}。提交超时也可能已创建远端任务，请先查看官网。`;
    throw error;
  }
}
async function refreshPippitTarget() {
  if (pippitQueryBusy.value) return;
  pippitQueryBusy.value = true;
  try {
    const shot = activeEpisodeShot.value;
    if (analysisProject.value && shot?.provider_model === "pippit" && shot.provider_task_id) {
      const saved = await fetch(dramaForgeApiUrl(`pippit/targets/${analysisProject.value.id}/video/${shot.id}`));
      const task = await saved.json();
      if (!saved.ok) throw new Error(task.detail || "读取已保存任务失败");
      pippitTargetTask.value = task;
      pippitTargetLink.value = task.web_thread_link || "";
      if (["failed", "failure", "error", "requires_action", "requires_user_input", "interaction_required"].includes(task.status) && task.query_error) { pippitTargetProgress.value = task.query_error; return; }
    }
    const task = pippitTargetTask.value;
    if (!task) throw new Error("尚无可查询任务，请先核对官网任务记录");
    pippitTargetLink.value = task.web_thread_link || "";
    const response = await fetch(dramaForgeApiUrl("pippit/thread"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ thread_id: task.thread_id, run_id: task.run_id }), signal: targetGenerationAbort.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "状态查询失败");
    pippitTargetProgress.value = result.binding?.bound_url ? "Pippit 生成完成，成果已保存" : ["failed", "failure", "error", "canceled", "cancelled"].includes(result.status) ? "Pippit 已返回任务未完成，请查看官网回复" : ["requires_action", "requires_user_input", "interaction_required"].includes(result.status) ? "Pippit 需要补充信息，请打开官网任务回复" : "Pippit 已接收任务，尚未返回可保存的成果";
    if (analysisProject.value) await refreshDramaForgeProject(String(analysisProject.value.id));
  } catch (error) { pippitTargetProgress.value = `原任务查询暂时失败：${error instanceof Error ? error.message : "未知错误"}。未重新提交生成，请稍后刷新或查看官网任务。`; }
  finally { pippitQueryBusy.value = false; }
}
const generationModelOptions = ref<{ image: { id: string; label: string; description?: string }[]; video: { id: string; label: string; description?: string }[] }>({ image: [{ id: "pippit", label: "Pippit" }], video: [{ id: "pippit", label: "Pippit" }] });
const modelOptionsError = ref("");
async function loadGenerationModels() {
  try {
    const [stageResponse, catalogResponse] = await Promise.all([fetch(dramaForgeApiUrl("settings")), axios.get("/api/providers/media/list")]);
    if (!stageResponse.ok) throw new Error("读取生成配置失败");
    const stages = await stageResponse.json();
    const providers = catalogResponse.data.data as { id: string; label: string; models: { id: string; label: string; type: string }[] }[];
    for (const stage of ["image", "video"] as const) {
      const config = stages[stage];
      const provider = providers.find(item => item.id === config?.provider);
      const models = (provider?.models || []).filter(item => item.type === stage).map(item => ({ id: item.id, label: item.label || item.id, description: provider?.label || config.provider }));
      if (config?.model && !models.some(item => item.id === config.model)) models.unshift({ id: config.model, label: config.model, description: provider?.label || config.provider });
      generationModelOptions.value[stage] = [...models, { id: "pippit", label: "Pippit", description: "图片与视频生成 · 自动匹配模型" }];
      if (stage === "image") {
        defaultImageModelLabel.value = models.find(item => item.id === config?.model)?.label || "选择图片模型";
        if (!imageModel.value) imageModel.value = config?.model || "";
      } else {
        defaultVideoModelLabel.value = models.find(item => item.id === config?.model)?.label || "选择视频模型";
        if (!videoModel.value) videoModel.value = config?.model || "";
      }
    }
    modelOptionsError.value = "";
  } catch (error) { modelOptionsError.value = error instanceof Error ? error.message : "模型列表读取失败"; }
}
onMounted(() => { void loadGenerationModels(); });
const generatingAssetKey = ref("");
const selectingAssets = ref(false);
const selectedAssetIds = ref<number[]>([]);
const assetImageErrors = ref<Record<string, string>>({});
const batchGenerating = ref(false);
const batchProgress = ref({ completed: 0, total: 0, name: "" });
const batchSummary = ref("");
watch(resultTab, () => { selectingAssets.value = false; selectedAssetIds.value = []; batchSummary.value = ""; });
function toggleAssetSelection(id: number) {
  if (assetGenerating.value) return;
  selectedAssetIds.value = selectedAssetIds.value.includes(id) ? selectedAssetIds.value.filter(value => value !== id) : [...selectedAssetIds.value, id];
}
async function requestAssetImage(projectId: number, asset: AnalysisResultItem, variant = "base") {
  if (!asset.kind || asset.kind === "shots") throw new Error("请选择角色、场景或道具");
  const key = `${asset.kind}-${asset.id}`;
  generatingAssetKey.value = key;
  delete assetImageErrors.value[key];
  try {
    if (imageModel.value === "pippit") {
      const character = asset.kind === "characters" ? ((analysisProject.value?.characters || []) as any[]).find((item: any) => item.id === asset.id) as any : undefined;
      const design = character?.design || {};
      let referencePrompt = variant === "expressions" ? design.expression_sheet_prompt : variant === "turnaround" ? design.turnaround_prompt : ["front", "side", "back", "three_quarter"].includes(variant) ? design.views?.[variant] : asset.prompt;
      if (asset.kind === "characters" && variant !== "base") {
        const preview = await fetch(dramaForgeApiUrl(`projects/${projectId}/asset-image-prompt?kind=character&asset_id=${asset.id}&variant=${variant}`));
        const body = await preview.json();
        if (!preview.ok) throw new Error(body.detail || "参考提示词读取失败");
        referencePrompt = body.prompt;
      }
      if (variant !== "base" && !referencePrompt) throw new Error("该类型的提示词尚未完成");
      await generateWithPippit(projectId, { characters: "character", scenes: "scene", props: "prop" }[asset.kind], asset.id, referencePrompt || asset.description, variant);
      await refreshDramaForgeProject(String(projectId));
      if (selectedResult.value?.id === asset.id && selectedResult.value.kind === asset.kind) selectedResult.value = resultItemsFor(asset.kind).find(item => item.id === asset.id) || null;
      return;
    }
    const query = new URLSearchParams();
    if (asset.image) query.set("regenerate", "true");
    if (imageModel.value) query.set("model", imageModel.value);
    const endpoint = asset.kind === "characters" && variant !== "base" ? `projects/${projectId}/characters/${asset.id}/references/${variant}/generate?${query}` : `projects/${projectId}/${asset.kind}/${asset.id}/generate?${query}`;
    const response = await fetch(dramaForgeApiUrl(endpoint), { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "参考图生成失败");
    await refreshDramaForgeProject(String(projectId));
    if (selectedResult.value?.id === asset.id && selectedResult.value.kind === asset.kind) selectedResult.value = resultItemsFor(asset.kind).find(item => item.id === asset.id) || null;
  } catch (error) {
    assetImageErrors.value[key] = error instanceof Error ? error.message : "参考图生成失败";
    if (imageModel.value === "pippit") pippitTargetProgress.value = assetImageErrors.value[key] || "Pippit 任务暂未完成";
    throw error;
  } finally { generatingAssetKey.value = ""; }
}
async function generateSelectedImages() {
  const project = analysisProject.value;
  const assets = resultItemsFor(resultTab.value).filter(item => selectedAssetIds.value.includes(item.id));
  if (!project || !assets.length || assetGenerating.value) return;
  try { await ElMessageBox.confirm(`将生成 ${assets.length} 张${resultTab.value === "characters" ? characterReferenceOptions.find(item => item.id === characterReferenceVariant.value)?.label || "参考图" : "参考图"}，已有图片的选中资产将重新生成。${imageModel.value === "pippit" ? '使用 Pippit，可能消耗积分，API 无法预估费用。' : '使用所选图片模型，可能消耗额度。'}是否继续？`, "批量生成图片", { confirmButtonText: "开始生成", cancelButtonText: "取消" }); } catch { return; }
  assetGenerating.value = true;
  batchGenerating.value = true;
  batchProgress.value = { completed: 0, total: assets.length, name: "" };
  let succeeded = 0;
  try {
    for (const asset of assets) {
      batchProgress.value.name = asset.name;
      try { await requestAssetImage(project.id, asset, asset.kind === "characters" ? characterReferenceVariant.value : "base"); succeeded++; } catch { /* 每项失败原因保留在资产卡片，继续已确认的队列。 */ }
      batchProgress.value.completed++;
    }
    batchSummary.value = `生成结束：成功 ${succeeded} 张，失败 ${assets.length - succeeded} 张。`;
    if (succeeded === assets.length) { selectingAssets.value = false; selectedAssetIds.value = []; ElMessage.success(batchSummary.value); }
    else ElMessage.warning(batchSummary.value);
  } finally { assetGenerating.value = false; batchGenerating.value = false; }
}
async function generateResultImage(item?: AnalysisResultItem) {
  const asset = item?.kind ? item : selectedResult.value;
  const project = analysisProject.value;
  if (!asset?.kind || asset.kind === "shots" || !project || assetGenerating.value) return;
  try { await ElMessageBox.confirm(`将生成“${asset.name}”${asset.kind === "characters" ? ({ base: "主参考图", detail_sheet: "详细角色设定图", turnaround: "四视图", expressions: "表情图", front: "正面图", side: "侧面图", back: "背面图" } as Record<string,string>)[characterReferenceVariant.value] || "参考图" : "参考图"}。${imageModel.value === "pippit" ? '使用 Pippit，可能消耗积分，API 无法预估费用。' : '使用所选图片模型，可能消耗额度。'}是否继续？`, "生成参考图", { confirmButtonText: "提交生成", cancelButtonText: "取消" }); } catch { return; }
  assetGenerating.value = true;
  try {
    await requestAssetImage(project.id, asset, asset.kind === "characters" ? characterReferenceVariant.value : "base");
    ElMessage.success("参考图已保存");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "参考图生成失败"); }
  finally { assetGenerating.value = false; }
}
const selectedShotId = ref<number | null>(null);
const assetSearch = ref("");
const editingShotPrompt = ref(false);
const shotPromptDraft = ref("");
const shotBusy = ref(false);
const selectingVideoShots = ref(false);
const selectedVideoShotIds = ref<number[]>([]);
const videoBatchRunning = ref(false);
const videoBatchPauseRequested = ref(false);
const videoBatchMessage = ref("");
function canQueueVideo(shot: Record<string, any>) { return !shot.video_url && shot.video_status !== "processing"; }
function seekThumbnail(event: Event) { const video = event.target as HTMLVideoElement; if (Number.isFinite(video.duration) && video.duration > 0) video.currentTime = Math.min(0.15, video.duration / 2); }
function chooseTimelineShot(shot: Record<string, any>) {
  if (selectingVideoShots.value) {
    if (!canQueueVideo(shot)) return;
    selectedVideoShotIds.value = selectedVideoShotIds.value.includes(shot.id) ? selectedVideoShotIds.value.filter(id => id !== shot.id) : [...selectedVideoShotIds.value, shot.id];
  } else { selectedShotId.value = shot.id; editingShotPrompt.value = false; }
}

const episodeShots = computed(() => ((analysisProject.value?.shots || []) as Record<string, any>[]).filter(shot => Number(shot.episode_no) === selectedEpisode.value).sort((a, b) => a.shot_no - b.shot_no));
const eligibleVideoShots = computed(() => episodeShots.value.filter(canQueueVideo));
const activeEpisodeShot = computed(() => episodeShots.value.find(shot => shot.id === selectedShotId.value) || episodeShots.value[0]);
watch(() => activeEpisodeShot.value?.id, () => {
  if (activeEpisodeShot.value?.provider_model) videoModel.value = activeEpisodeShot.value.provider_model;
  pippitTargetProgress.value = "";
  pippitTargetLink.value = "";
  pippitTargetTask.value = undefined;
});
const generationSettingsBusy = ref(false);
const currentGenerationOptions = computed(() => ({ aspect_ratio: (analysisProject.value?.outline as Record<string, any> | undefined)?.aspect_ratio || "9:16", resolution: "720P", mode: "auto", references: null, ...((analysisProject.value?.generation_settings || {}) as Record<string, any>), ...(activeEpisodeShot.value?.generation_settings || {}) }));
async function saveClipGeneration(key: string, value: string) {
  const shot = activeEpisodeShot.value;
  const project = analysisProject.value;
  if (!shot || !project || generationSettingsBusy.value) return;
  generationSettingsBusy.value = true;
  try {
    const settings = currentGenerationOptions.value;
    const response = await fetch(dramaForgeApiUrl(`projects/${project.id}/shots/${shot.id}/generation`), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aspect_ratio: settings.aspect_ratio, resolution: settings.resolution, model: settings.model || null, mode: settings.mode, references: settings.references, [key]: value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "生成参数保存失败");
    await refreshDramaForgeProject(String(project.id));
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "生成参数保存失败"); }
  finally { generationSettingsBusy.value = false; }
}
const episodeAssetGroups = computed(() => {
  const characters = new Set(episodeShots.value.flatMap(shot => shot.character_names || []));
  const scenes = new Set(episodeShots.value.map(shot => shot.scene_name));
  return resultTabs.filter(tab => tab.key !== "shots").map(tab => ({ key: tab.key, label: tab.label, items: resultItemsFor(tab.key).filter(item => (tab.key === "characters" ? characters.has(item.name) : tab.key === "scenes" ? scenes.has(item.name) : true) && item.name.includes(assetSearch.value.trim())) }));
});
const activeShotAssets = computed(() => {
  const shot = activeEpisodeShot.value;
  if (!shot) return [];
  return resultTabs.filter(tab => tab.key === "characters" || tab.key === "scenes").flatMap(tab => resultItemsFor(tab.key).filter(item => tab.key === "characters" ? (shot.character_names || []).includes(item.name) : shot.scene_name === item.name).map(item => ({ ...item, kind: tab.key })));
});
function shotStatusText(shot: Record<string, any>): string {
  if (shot.video_status === "processing") return "视频生成中";
  if (shot.video_status === "failed") return "视频生成失败";
  if (shot.video_url) return "视频已生成";
  return shot.keyframe_url ? "首帧已就绪 · 视频待生成" : "分镜已就绪 · 视频待生成";
}
function startEditingShot() {
  shotPromptDraft.value = activeEpisodeShot.value?.prompt || "";
  editingShotPrompt.value = true;
}
async function saveEpisodeShot() {
  const shot = activeEpisodeShot.value;
  if (!shot || !analysisProject.value || shotBusy.value) return;
  if (!shotPromptDraft.value.trim()) { ElMessage.error("分镜提示词不能为空"); return; }
  if (shot.video_url) {
    try { await ElMessageBox.confirm("保存修改将清除当前分镜的视频关联，需要重新生成。是否继续？", "保存分镜", { type: "warning" }); } catch { return; }
  }
  shotBusy.value = true;
  try {
    const response = await fetch(dramaForgeApiUrl(`projects/${analysisProject.value.id}/shots/${shot.id}`), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: shotPromptDraft.value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "保存失败");
    editingShotPrompt.value = false;
    await refreshDramaForgeProject(String(analysisProject.value.id));
    ElMessage.success("分镜已保存");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "保存失败"); }
  finally { shotBusy.value = false; }
}
async function generateVideoBatch() {
  const project = analysisProject.value;
  if (!project || videoBatchRunning.value || shotBusy.value || editingShotPrompt.value) return;
  const chosenModel = videoModel.value;
  if (!chosenModel) return ElMessage.warning("请先选择视频模型");
  const shots = episodeShots.value.filter(shot => selectedVideoShotIds.value.includes(shot.id) && canQueueVideo(shot));
  if (!shots.length) return ElMessage.warning("没有可提交的待生成片段");
  const assets = [...resultItemsFor("characters"), ...resultItemsFor("scenes")];
  for (const shot of shots) {
    const mode = shot.generation_settings?.mode || (project.generation_settings as any)?.mode || "auto";
    const missing = assets.filter(asset => asset.kind === "characters" ? (shot.character_names || []).includes(asset.name) && !asset.image : asset.name === shot.scene_name && !asset.image);
    if ((chosenModel === "pippit" || mode === "auto" || mode === "reference") && missing.length) return ElMessage.warning(`片段 ${shot.shot_no} 缺少参考图：${missing.map(asset => asset.name).join("、")}`);
  }
  try { await ElMessageBox.confirm(`将使用 ${generationModelOptions.value.video.find(model => model.id === chosenModel)?.label || chosenModel} 依次生成所选 ${shots.length} 个片段，可能消耗额度，费用以平台实际为准。跳过已有视频和正在生成的片段；失败或状态无法确认时停止，不自动换账号或重复提交。离开本页将暂停尚未提交的片段，已提交任务仍在后台继续。是否开始？`, "批量生成视频", { confirmButtonText: "确认批量生成", cancelButtonText: "取消" }); } catch { return; }
  videoBatchRunning.value = true; videoBatchPauseRequested.value = false; selectingVideoShots.value = false;
  let completed = 0;
  try {
    for (const shot of shots) {
      if (videoBatchPauseRequested.value || targetGenerationAbort.signal.aborted) break;
      const current = (analysisProject.value?.shots as any[] || []).find(item => item.id === shot.id);
      if (!current || !canQueueVideo(current)) { selectedVideoShotIds.value = selectedVideoShotIds.value.filter(id => id !== shot.id); continue; }
      videoBatchMessage.value = `批量生成 ${completed + 1}/${shots.length} · 片段 ${shot.shot_no}`;
      if (chosenModel === "pippit") await generateWithPippit(project.id, "video", shot.id, shot.prompt);
      else {
        const response = await fetch(dramaForgeApiUrl(`projects/${project.id}/shots/${shot.id}/generate?${new URLSearchParams({ model: chosenModel })}`), { method: "POST", signal: targetGenerationAbort.signal });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "提交未确认，请先核对原任务");
        let finished = false;
        for (let attempt = 0; attempt < 720; attempt++) {
          if (targetGenerationAbort.signal.aborted) throw new Error("页面已离开，已提交任务继续执行");
          const response = await fetch(dramaForgeApiUrl(`projects/${project.id}`), { signal: targetGenerationAbort.signal });
          if (!response.ok) throw new Error("查询失败，请先核对原任务，不要重复生成");
          const fresh = await response.json();
          window.dispatchEvent(new CustomEvent("dramaforge:project-update", { detail: fresh }));
          const current = fresh.shots.find((item: any) => item.id === shot.id);
          if (current?.video_url) { finished = true; break; }
          if (current?.video_status === "failed") throw new Error(current.last_error || "片段生成失败");
          await new Promise(resolve => setTimeout(resolve, 5000));
        }
        if (!finished) throw new Error("仍未确认生成结果，后续片段已暂停");
      }
      completed++;
      selectedVideoShotIds.value = selectedVideoShotIds.value.filter(id => id !== shot.id);
      await refreshDramaForgeProject(String(project.id));
    }
    videoBatchMessage.value = `${completed === shots.length ? '批量完成' : '队列已暂停'}：已完成 ${completed}/${shots.length} 个片段`;
  } catch (error) { videoBatchMessage.value = `队列已停止，完成 ${completed}/${shots.length}：${error instanceof Error ? error.message : '请求异常'}。未自动重新提交。`; }
  finally { videoBatchRunning.value = false; if (!targetGenerationAbort.signal.aborted) await refreshDramaForgeProject(String(project.id)); }
}
async function generateEpisodeShot() {
  const shot = activeEpisodeShot.value;
  const project = analysisProject.value;
  if (!shot || !project || shotBusy.value || videoBatchRunning.value || shot.video_status === "processing") return;
  if (editingShotPrompt.value) { ElMessage.warning("请先保存或取消编辑"); return; }
  const missing = activeShotAssets.value.filter(asset => !asset.image);
  const mode = shot.generation_settings?.mode || (project.generation_settings as Record<string, unknown> | undefined)?.mode || "auto";
  if ((mode === "auto" || mode === "reference") && missing.length) {
    ElMessage.warning(`请先生成参考图：${missing.map(asset => asset.name).join("、")}`);
    selectedResult.value = missing[0] || null;
    return;
  }
  try { await ElMessageBox.confirm(videoModel.value === "pippit" ? "将使用 Pippit 生成当前片段，并上传当前片段的本地参考图。可能消耗积分，API 无法预估费用。是否提交？" : "将使用所选视频模型生成当前片段，可能消耗额度。是否提交？", "生成片段", { confirmButtonText: "提交生成", cancelButtonText: "取消" }); } catch { return; }
  shotBusy.value = true;
  try {
    if (videoModel.value === "pippit") {
      await generateWithPippit(project.id, "video", shot.id, shot.prompt);
      await refreshDramaForgeProject(String(project.id));
      ElMessage.success("Pippit 视频已保存到当前片段");
      return;
    }
    const query = new URLSearchParams();
    if (videoModel.value) query.set("model", videoModel.value);
    const response = await fetch(dramaForgeApiUrl(`projects/${project.id}/shots/${shot.id}/generate?${query}`), { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "视频提交失败");
    await refreshDramaForgeProject(String(project.id));
    ElMessage.success("视频任务已提交");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "视频提交失败"); }
  finally { shotBusy.value = false; }
}
const episodeItems = computed(() => {
  const groups = new Map<number, { number: number; shots: number; characters: Set<string>; scenes: Set<string> }>();
  for (const shot of (analysisProject.value?.shots || []) as Record<string, any>[]) {
    const number = Number(shot.episode_no) || 1;
    const group = groups.get(number) || { number, shots: 0, characters: new Set<string>(), scenes: new Set<string>() };
    group.shots++;
    for (const name of shot.character_names || []) if (name) group.characters.add(name);
    if (shot.scene_name) group.scenes.add(shot.scene_name);
    groups.set(number, group);
  }
  return [...groups.values()].sort((a, b) => a.number - b.number).map(group => ({ number: group.number, shots: group.shots, characters: group.characters.size, scenes: group.scenes.size }));
});
const visibleShotItems = computed(() => {
  const ids = new Set(((analysisProject.value?.shots || []) as Record<string, any>[]).filter(shot => Number(shot.episode_no) === selectedEpisode.value).map(shot => shot.id));
  return resultItemsFor("shots").filter(item => ids.has(item.id));
});
const selectedResult = ref<AnalysisResultItem | null>(null);
const characterReferenceVariant = ref("detail_sheet");
const characterReferenceOptions = [{id:'detail_sheet',label:'详细设定图（面部正侧面＋全身前后）'},{id:'turnaround',label:'四视图角色设定图'},{id:'base',label:'单人正面主参考图'},{id:'expressions',label:'表情参考图'},{id:'front',label:'正面'},{id:'side',label:'侧面'},{id:'back',label:'背面'}];
const selectedCharacter = computed(() => selectedResult.value?.kind === "characters" ? ((analysisProject.value?.characters || []) as any[]).find(item => item.id === selectedResult.value?.id) : undefined);
const selectedReferencePrompt = computed(() => {
  const character = selectedCharacter.value;
  if (!character) return selectedResult.value?.prompt || "";
  const design = character.design || {};
  const variant = characterReferenceVariant.value;
  if (variant === "detail_sheet") return `同一角色精细2×2设定图：正面头肩近景、侧面头肩近景、正面全身、背面全身。固定五官、发型、服装和身形，中性表情，清晰皮肤材质，无文字或水印。角色：${character.description || ""}。${design.identity || ""}。${design.wardrobe || ""}`;
  return variant === "turnaround" ? design.turnaround_prompt || "" : variant === "expressions" ? design.expression_sheet_prompt || "" : variant === "base" ? design.views?.front || character.description || "" : design.views?.[variant] || "";
});
const selectedReferenceExists = computed(() => selectedCharacter.value ? characterReferenceVariant.value === "base" ? !!selectedCharacter.value.base_image_url : !!selectedCharacter.value.reference_images?.[characterReferenceVariant.value] : !!selectedResult.value?.image);
const selectedReferenceImage = computed(() => selectedCharacter.value ? characterReferenceVariant.value === "base" ? selectedCharacter.value.base_image_url : selectedCharacter.value.reference_images?.[characterReferenceVariant.value] || selectedCharacter.value.base_image_url : selectedResult.value?.image);
const characterAudioInput = ref<HTMLInputElement>();
const characterAudioBusy = ref(false);
const selectedCharacterAudio = computed(() => selectedResult.value?.kind === "characters" ? (analysisProject.value?.generation_settings as any)?.characterAudio?.[String(selectedResult.value.id)] : undefined);
async function uploadCharacterAudio(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0]; input.value = "";
  const asset = selectedResult.value, project = analysisProject.value;
  if (!file || !project || asset?.kind !== "characters") return;
  if (file.size > 30 * 1024 * 1024) return ElMessage.warning("音频最多30MB");
  characterAudioBusy.value = true;
  try {
    const form = new FormData(); form.append("file", file);
    const response = await fetch(dramaForgeApiUrl(`projects/${project.id}/characters/${asset.id}/audio`), { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "声音上传失败");
    await refreshDramaForgeProject(String(project.id));
    ElMessage.success("角色声音已保存到本地项目");
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "声音上传失败"); }
  finally { characterAudioBusy.value = false; }
}
const designLabels: Record<string, string> = { identity: "人物身份", wardrobe: "服装与配饰", views: "多视图", front: "正面", side: "侧面", back: "背面", three_quarter: "四分之三侧面", turnaround_prompt: "四视图提示词", expressions: "表情设计", expression_sheet_prompt: "表情参考图提示词", negative_prompt: "避免内容", director_notes: "导演说明", geography: "空间布局", lighting: "灯光", palette: "色彩", atmosphere: "氛围", continuity: "连续性", reference_prompt: "场景参考图提示词", shot_size: "景别", camera_height: "机位高度", camera_angle: "机位角度", lens: "镜头焦段", camera_movement: "运镜", composition: "构图", blocking: "人物调度", performance: "表演", timeline: "动作时间线", sound: "声音", name: "名称", prompt: "提示词" };
function designText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(designText).filter(Boolean).join("\n\n");
  if (value && typeof value === "object") return Object.entries(value).map(([key, item]) => { const text = designText(item); return text ? `${designLabels[key] || key}：${text}` : ""; }).filter(Boolean).join("\n\n");
  return value == null ? "" : String(value);
}
const resultDesignSections = computed(() => Object.entries(selectedResult.value?.design || {}).map(([key, value]) => ({ label: designLabels[key] || key, text: designText(value) })).filter(item => item.text));
function resultItemsFor(key: ResultTab): AnalysisResultItem[] {
  const items = analysisProject.value?.[key];
  if (!Array.isArray(items)) return [];
  return items.map(item => {
    const design = item.design || item.direction || {};
    return {
      id: item.id,
      kind: key,
      name: key === "shots" ? `第 ${item.episode_no} 集 · 镜头 ${item.shot_no} · ${item.title || ""}` : item.name,
      description: key === "shots" ? `${item.duration} 秒 · ${item.scene_name || "未设置场景"} · ${(item.character_names || []).join("、")}` : item.description || "",
      prompt: key === "shots" ? [item.keyframe_prompt && `首帧提示词：\n${item.keyframe_prompt}`, item.prompt && `视频提示词：\n${item.prompt}`].filter(Boolean).join("\n\n") : design.turnaround_prompt || design.reference_prompt || design.prompt || item.description || "",
      image: item.base_image_url || item.image_url || item.keyframe_url,
      design,
    };
  });
}
async function copyResultPrompt() {
  if (!selectedReferencePrompt.value) return;
  try { await navigator.clipboard.writeText(selectedReferencePrompt.value); ElMessage.success("提示词已复制"); }
  catch { ElMessage.error("复制失败，请手动选取提示词复制"); }
}
const analysisStep = computed(() => {
  const state = analysisProject.value?.analysis_state;
  if (state?.status === "done") return productionView.value === "episodes" ? 3 : 2;
  if (!state?.counts) return 1;
  const assetBatches = Math.max(state.counts.characters ?? 0, state.counts.scenes ?? 0);
  return state.total && (state.completed ?? 0) >= assetBatches ? 3 : 2;
});

async function retryAnalysis() {
  const project = analysisProject.value;
  if (!project || analysisRetrying.value) return;
  analysisRetrying.value = true;
  try {
    const action = project.shots?.length ? "enrich" : "analyze";
    const response = await fetch(dramaForgeApiUrl(`projects/${project.id}/${action}`), { method: "POST" });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "分析启动失败");
    await refreshDramaForgeProject(String(project.id));
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "分析启动失败"); }
  finally { analysisRetrying.value = false; }
}

const analysisUnits = computed(() => Object.values(analysisProject.value?.analysis_state?.units || {}));
const analysisUnitLabels: Record<string, string> = { running: '进行中', done: '已保存', failed: '未完成', interrupted: '请求中断 · 待确认重试' };
async function pauseAnalysis() {
  if (!analysisProject.value || analysisRetrying.value) return;
  analysisRetrying.value = true;
  try {
    const response = await fetch(dramaForgeApiUrl(`projects/${analysisProject.value.id}/analysis/pause`), { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '暂停失败');
    ElMessage.success(result.message);
    await refreshDramaForgeProject(String(analysisProject.value.id));
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '暂停失败'); }
  finally { analysisRetrying.value = false; }
}

function openProductionMedia(event: Event) {
  const detail = (event as CustomEvent).detail;
  const project = analysisProject.value;
  if (!project || Number(detail?.projectId) !== project.id) return;
  if (detail.kind === "shots" && project.analysis_state?.status === "done") {
    productionView.value = "episodes";
    selectedEpisode.value = Number(detail.episode);
    selectedShotId.value = Number(detail.id);
    analysisDismissed.value = false;
    return;
  }
  if (detail.kind === "characters") characterReferenceVariant.value = detail.variant || "base";
  const item = resultItemsFor(detail.kind).find(item => item.id === Number(detail.id));
  if (item) selectedResult.value = item;
}
const productionCanvasContents = computed(() => {
  const project = analysisProject.value;
  if (!project) return [];
  const prefix = `dramaforge-${project.id}-`;
  return [
    { id: prefix + "script", label: "原始剧本文本" },
    { id: prefix + "story", label: "故事与分集大纲" },
    ...["characters", "scenes", "props"].map(kind => ({ id: prefix + `group-${kind}`, label: { characters: "角色参考素材分组", scenes: "场景参考素材分组", props: "道具参考素材分组" }[kind] || kind })),
    ...episodeItems.value.map(item => ({ id: prefix + `group-episode-${item.number}`, label: `第 ${item.number} 集 · 分镜视频分组` })),
    ...["characters", "scenes", "props"].flatMap(kind => ((project as any)[kind] || []).map((item: any) => ({ id: prefix + `${{ characters: "character", scenes: "scene", props: "prop" }[kind]}-${item.id}-prompt`, label: `${{ characters: "角色", scenes: "场景", props: "道具" }[kind]} · ${item.name} · 图片提示词` }))),
    ...((project.shots || []) as any[]).map(shot => ({ id: prefix + `shot-${shot.id}-prompt`, label: `第 ${shot.episode_no} 集 · 分镜 ${shot.shot_no} · 首帧与视频提示词` })),
  ];
});
async function focusProductionContent(nodeId: string) {
  try {
    if (!canvasPanelRef.value?.canvasReady) throw new Error("画布正在同步，请稍后重试");
    const context = canvasPanelRef.value.getCanvasContext();
    if (!context) throw new Error("画布尚未就绪");
    const result = await context.call({ name: "fitCanvas", args: { nodeIds: [nodeId] } }) as { fitted: boolean };
    if (!result.fitted) throw new Error("该节点尚未同步，请稍后重试");
  } catch (error) { ElMessage.warning(error instanceof Error ? error.message : "定位失败"); }
}

function dramaForgeCanvasSignature(project: DramaForgeProject) {
  return JSON.stringify({
    script: project.script_text,
    outline: project.outline,
    generation: project.generation_settings,
    characters: project.characters,
    scenes: project.scenes,
    props: project.props,
    shots: (project.shots as any[] | undefined)?.map(shot => ({
      id: shot.id, title: shot.title, duration: shot.duration, scene: shot.scene_name, characters: shot.character_names,
      prompt: shot.prompt, direction: shot.direction, keyframe_prompt: shot.keyframe_prompt, keyframe_url: shot.keyframe_url,
      video_url: shot.video_url, video_status: shot.video_status, last_error: shot.last_error,
    })),
  });
}

async function syncDramaForgeProject(project: DramaForgeProject, force = false) {
  if (String(route.query.dramaforgeProjectId ?? "") !== String(project.id)) return;
  const directory = project.workspace_directory;
  if (!directory) throw new Error("项目文件夹路径不可用，请重启 DramaForge 后重试");
  const task = dramaForgeSyncRunning.catch(() => {}).then(async () => {
    if (workspaceStore.project?.directory !== directory) await workspaceStore.openProject(directory);
    workspaceStore.renameProject(directory, project.outline?.title || project.name);
    const signature = dramaForgeCanvasSignature(project);
    if (!force && lastDramaForgeSync.get(project.id) === signature) return { unchanged: true, nodes: 0 };
    const panel = await waitForControlValue(
      () => canvasPanelRef.value?.canvasReady || canvasPanelRef.value?.loadError ? canvasPanelRef.value : undefined,
      AbortSignal.timeout(120000),
    );
    if (panel.loadError) throw new Error(panel.loadError);
    const result = await panel.syncDramaForgeProject(project);
    lastDramaForgeSync.set(project.id, signature);
    return result;
  });
  dramaForgeSyncRunning = task;
  await task;
}

function handleDramaForgeProject(event: Event) {
  const project = (event as CustomEvent<DramaForgeProject>).detail;
  if (!project || String(route.query.dramaforgeProjectId ?? "") !== String(project.id)) return;
  analysisProject.value = project;
  void syncDramaForgeProject(project).catch(error => {
    console.error("DramaForge 项目画布同步失败：", error);
    ElMessage.error(error instanceof Error ? error.message : "项目画布加载失败");
  });
}

async function refreshDramaForgeProject(projectId: string) {
  if (dramaForgeRefreshStopped) return;
  if (dramaForgeRefreshTimer) clearTimeout(dramaForgeRefreshTimer);
  try {
    const response = await fetch(dramaForgeApiUrl(`projects/${encodeURIComponent(projectId)}`));
    if (!response.ok) throw new Error("DramaForge 项目读取失败");
    const project = await response.json() as DramaForgeProject;
    analysisRefreshError.value = "";
    (window as DramaForgeWindow).__DRAMAFORGE_PROJECT__ = project;
    window.dispatchEvent(new CustomEvent("dramaforge:project-update", { detail: project }));
    if (project.status === "analyzing" || (project.shots as Record<string, any>[] | undefined)?.some(shot => shot.video_status === "processing")) dramaForgeRefreshTimer = setTimeout(() => void refreshDramaForgeProject(projectId), 5000);
  } catch (error) {
    console.error("DramaForge 项目刷新失败：", error);
    analysisRefreshError.value = error instanceof Error ? error.message : "项目分析状态刷新失败";
    dramaForgeRefreshTimer = setTimeout(() => void refreshDramaForgeProject(projectId), 5000);
  }
}

onMounted(() => {
  if (route.query.dramaforgeProjectId) {
    const bridge: NonNullable<DramaForgeWindow["__DRAMAFORGE_CANVAS_BRIDGE__"]> = { syncProject: syncDramaForgeProject };
    registeredDramaForgeBridge = bridge;
    (window as DramaForgeWindow).__DRAMAFORGE_CANVAS_BRIDGE__ = bridge;
    const project = (window as DramaForgeWindow).__DRAMAFORGE_PROJECT__;
    if (project) handleDramaForgeProject(new CustomEvent("dramaforge:project-update", { detail: project }));
    window.addEventListener("dramaforge:project-update", handleDramaForgeProject);
    window.addEventListener("dramaforge:open-production", openProductionMedia);
    void refreshDramaForgeProject(String(route.query.dramaforgeProjectId));
  }
});
onScopeDispose(() => {
  dramaForgeRefreshStopped = true;
  if (dramaForgeRefreshTimer) clearTimeout(dramaForgeRefreshTimer);
  window.removeEventListener("dramaforge:project-update", handleDramaForgeProject);
  window.removeEventListener("dramaforge:open-production", openProductionMedia);
  if (registeredDramaForgeBridge && (window as DramaForgeWindow).__DRAMAFORGE_CANVAS_BRIDGE__ === registeredDramaForgeBridge) {
    delete (window as DramaForgeWindow).__DRAMAFORGE_CANVAS_BRIDGE__;
  }
});

const controlLifetime = new AbortController();
onScopeDispose(() => controlLifetime.abort(new Error("工作区已关闭")));
registerWorkspaceControl({
  getState: () => ({
    directory: workspaceStore.project?.directory ?? null,
    canvasId: canvasPanelRef.value?.canvasId || null,
    panel: activePanel.value,
    tools: canvasPanelRef.value?.canvasReady ? canvasPanelRef.value.getCanvasContext()?.tools ?? [] : [],
    document: documentPanelRef.value?.getDocument(false),
  }),
  flushSave,
  async call(request, signal) {
    const directory = workspaceStore.project?.directory;
    if (!directory) throw new Error("请先打开工作区");
    const callSignal = AbortSignal.any([signal, controlLifetime.signal]);
    const checkDirectory = () => {
      callSignal.throwIfAborted();
      if (directory !== workspaceStore.project?.directory) throw new Error("工作区已切换，本次调用已停止");
    };
    checkDirectory();
    if (request.name === "switchPanel") {
      if (request.args.panel !== "canvas" && request.args.panel !== "document") throw new Error("未知面板");
      if (!(await switchPanel(request.args.panel))) throw new Error("面板切换失败，请检查文档是否保存成功");
      checkDirectory();
      return { panel: activePanel.value };
    }
    if (["getDocument", "openDocument", "writeDocument"].includes(request.name)) {
      if (!(await switchPanel("document"))) throw new Error("文档面板无法打开");
      const panel = await waitForControlValue(() => documentPanelRef.value, callSignal);
      checkDirectory();
      if (request.name === "openDocument") await panel.openDocument(request.args, callSignal);
      if (request.name === "writeDocument") await panel.writeDocument(request.args, callSignal);
      checkDirectory();
      return panel.getDocument();
    }
    if (!(await switchPanel("canvas"))) throw new Error("画布面板无法打开");
    const context = await waitForControlValue(
      () => (canvasPanelRef.value?.canvasReady || (!canvasPanelRef.value?.canvasId && canvasPanelRef.value?.canvasListReady) ? canvasPanelRef.value.getCanvasContext() : undefined),
      callSignal
    );
    checkDirectory();
    return context.call({ name: request.name, args: request.args }, callSignal);
  },
});

async function flushSave() {
  await documentPanelRef.value?.flushSave();
  await canvasPanelRef.value?.flushSave();
}

onBeforeRouteLeave(async () => {
  if (canvasPanelRef.value?.saveBusy) {
    ElMessage.warning("画布操作尚未完成，请稍后退出");
    return false;
  }
  try {
    await flushSave();
    return true;
  } catch (error) {
    const message = axios.isAxiosError<{ message?: string }>(error)
      ? error.response?.data?.message || error.message
      : error instanceof Error
      ? error.message
      : "项目保存失败";
    const leave = await ElMessageBox.confirm(`无法保存项目：${message}。文件或目录可能已被移动或删除。仍然退出将丢弃尚未保存的修改。`, "项目未保存", {
      type: "warning",
      confirmButtonText: "仍然退出",
      cancelButtonText: "留在项目",
      closeOnClickModal: false,
    }).then(
      () => true,
      () => false
    );
    if (leave) {
      documentPanelRef.value?.cancelSave();
      canvasPanelRef.value?.cancelSave();
    }
    return leave;
  }
});

async function switchPanel(value: string | number | boolean) {
  if (value !== "canvas" && value !== "document") return false;
  try {
    if (activePanel.value === "document") await documentPanelRef.value?.flushSave();
    const changed = activePanel.value !== value;
    activePanel.value = value;
    await nextTick();
    if (changed) anonymousData.track(value === "canvas" ? "workspace.canvas" : "workspace.document");
    return true;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "文本保存失败");
    return false;
  }
}

function readDocumentNode(directory: string, canvasPath: string, nodeId: string) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.readDocumentNode(directory, canvasPath, nodeId);
}

function readDocumentNodes(directory: string, options?: DocumentNodeOptions) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.readDocumentNodes(directory, options);
}

async function focusDocumentNode(directory: string, canvasPath: string, nodeId: string) {
  if (!directory || workspaceStore.project?.directory !== directory) throw new Error("工作目录已切换，请重新选择节点");
  if (!await switchPanel("canvas")) throw new Error("画布面板无法打开");
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  await canvasPanelRef.value.focusDocumentNode(directory, canvasPath, nodeId);
}

function mountDocumentNode(directory: string, canvasPath: string, nodeId: string, target: HTMLElement) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.mountDocumentNode(directory, canvasPath, nodeId, target);
}

function resolveDocumentNodeFile(directory: string, path: string) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.resolveDocumentNodeFile(directory, path);
}

function observeDocumentNode(directory: string, canvasPath: string, nodeId: string, onState: (state: { dirty: boolean; error: string; deleted: boolean }) => void) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.observeDocumentNode(directory, canvasPath, nodeId, onState);
}

async function flushDocumentNodes() {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  await canvasPanelRef.value.flushSave();
}

function performFileAction(directory: string, action: "copy" | "rename" | "move" | "delete", path: string, target?: string, nodeId?: string) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.performFileAction(directory, action, path, target, nodeId);
}

function saveDocumentNode(directory: string, canvasPath: string, nodeId: string, handleId: string, text: string, expectedText?: string) {
  if (!canvasPanelRef.value) throw new Error("画布尚未就绪");
  return canvasPanelRef.value.saveDocumentNode(directory, canvasPath, nodeId, handleId, text, expectedText);
}
</script>

<style scoped lang="scss">
.assetDetailImage { display: block; max-width: 100%; max-height: 360px; object-fit: contain; margin: 0 auto 20px; border-radius: 16px; }
.workspacePage {
  position: relative;
  width: 100%;
  height: 100dvh;
  background-color: var(--el-bg-color);

  .analysisStatus {
    position: absolute;
    inset: 0;
    z-index: 20;
    overflow: auto;
    color: var(--el-text-color-primary);
    background: var(--el-bg-color-page);

    .analysisResults {
      width: min(1200px, calc(100% - 64px)); margin: 36px auto 64px;
      .pippitTargetStatus { display: flex; flex-wrap: wrap; gap: 16px; padding: 14px 18px; margin: 12px 0; border-radius: 16px; background: var(--el-fill-color-light); font-size: 13px; a { color: var(--el-color-primary); } }
      .generationModels { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; label { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--el-text-color-secondary); } .el-select { width: 240px; } p { color: var(--el-color-danger); font-size: 12px; } }
      .generationModelNote { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 22px; }
      .assetGenerationBar { display: flex; align-items: center; justify-content: space-between; gap: 18px; background: var(--el-bg-color); border-radius: 20px; padding: 20px; margin-bottom: 18px; strong { font-size: 14px; font-weight: 500; } p { font-size: 12px; color: var(--el-text-color-secondary); margin: 8px 0 0; } }
      .assetGenerationActions { display: flex; flex-shrink: 0; gap: 8px; .el-button + .el-button { margin-left: 0; } }
      .assetCardOpen { display: block; position: relative; width: 100%; padding: 0; background: none; color: inherit; border: 0; text-align: left; cursor: pointer; }
      .resultCard.selectedAsset { border-color: var(--el-color-primary); box-shadow: 0 0 0 1px var(--el-color-primary); }
      .assetSelectionMark { position: absolute; right: 10px; top: 10px; display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; color: var(--el-color-primary); background: var(--el-bg-color); z-index: 1; }
      .assetGenerateButton { margin: 14px 8px 0; }
      .assetImageError { color: var(--el-color-danger); font-size: 12px; margin: 12px 8px; overflow-wrap: anywhere; }
      @media (max-width: 680px) { .assetGenerationBar { align-items: flex-start; flex-direction: column; } .assetGenerationActions { flex-wrap: wrap; } }
      &.editingEpisode { width: calc(100% - 16px); margin: 8px auto; .episodeEditor { height: calc(100vh - 84px); min-height: 560px; grid-template-rows: minmax(0, 1fr) 180px; } .productionLibrary { max-height: none; } .clipScript { overflow-y: auto; } .clipPreview { min-height: 0; overflow: hidden; video, .emptyClipPreview { max-height: 100%; } } .clipTimeline { align-items: center; } }
      .episodeEditor { display: grid; grid-template-columns: 260px minmax(0, 1fr) 300px; grid-template-rows: minmax(440px, 1fr) auto; gap: 8px; min-height: calc(100vh - 210px); }
      .productionLibrary, .clipScript, .clipPreview, .clipTimeline { border: 1px solid var(--el-border-color-lighter); border-radius: 24px; background: var(--el-bg-color); }
      .productionLibrary { grid-row: 1 / 3; padding: 20px 16px; max-height: calc(100vh - 210px); overflow: auto; h2 { font-size: 14px; font-weight: 500; margin: 0 0 20px; } input { box-sizing: border-box; width: 100%; border-radius: 20px; padding: 8px 12px; border: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light); color: inherit; } h3 { font-size: 12px; font-weight: 500; margin: 24px 0 10px; } }
      .libraryAsset { display: flex; align-items: center; width: 100%; gap: 10px; margin: 8px 0; padding: 6px; border: 0; background: none; color: inherit; text-align: left; cursor: pointer; border-radius: 10px; &:hover { background: var(--el-fill-color-light); } > div { display: grid; place-items: center; flex-shrink: 0; width: 38px; height: 42px; border-radius: 8px; background: var(--el-fill-color-light); color: var(--el-text-color-placeholder); overflow: hidden; } img { width: 100%; height: 100%; object-fit: cover; } span { min-width: 0; font-size: 12px; overflow-wrap: anywhere; } small { display: block; margin-top: 4px; color: var(--el-text-color-secondary); font-size: 10px; } }
      .clipScript { min-width: 0; padding: 24px; header { display: flex; align-items: center; gap: 20px; h2 { font-size: 21px; margin: 4px 0 20px; font-weight: 500; } span { font-size: 12px; color: var(--el-text-color-secondary); } } }
      .clipReferences { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; button { display: flex; align-items: center; gap: 5px; border: 1px solid var(--el-border-color-lighter); border-radius: 9px; padding: 7px 9px; background: var(--el-fill-color-light); color: inherit; cursor: pointer; font-size: 11px; } img { width: 28px; height: 28px; object-fit: cover; border-radius: 5px; } small { font-size: 10px; color: var(--el-color-warning); } }
      .clipPrompt { background: var(--el-fill-color-light); border-radius: 24px; padding: 20px; min-height: 320px; h3 { font-size: 15px; font-weight: 500; margin: 0 0 12px; } > p { font-size: 12px; color: var(--el-text-color-secondary); } .scriptText { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.95; color: var(--el-text-color-primary); } details { margin-top: 24px; summary { font-size: 12px; cursor: pointer; color: var(--el-text-color-secondary); } } textarea { box-sizing: border-box; width: 100%; min-height: 250px; border: 1px solid var(--el-border-color); border-radius: 12px; padding: 14px; background: var(--el-bg-color); color: inherit; font: inherit; line-height: 1.8; resize: vertical; } footer { display: flex; justify-content: flex-end; margin-top: 24px; } }
      .clipError { color: var(--el-color-danger); font-size: 12px; }
      .clipPreview { display: grid; place-items: center; padding: 24px; video, .emptyClipPreview { width: 100%; aspect-ratio: 9 / 16; border-radius: 24px; background: var(--el-fill-color-blank); object-fit: contain; } .emptyClipPreview { display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--el-text-color-placeholder); p { font-size: 12px; text-align: center; padding: 12px; } } }
      .clipTimelineArea { grid-column: 2 / 4; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
      .clipBatchTools { display: flex; gap: 8px; align-items: center; min-height: 34px; padding: 0 12px; > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--el-text-color-secondary); } :deep(.el-button) { margin: 0; } }
      .clipTimeline { flex: 1; min-height: 0; grid-column: 2 / 4; display: flex; gap: 10px; padding: 18px; overflow-x: auto; button { flex-shrink: 0; border: 0; background: none; color: var(--el-text-color-secondary); width: 122px; cursor: pointer; padding: 0; > div { position: relative; height: 72px; border: 1px solid transparent; border-radius: 12px; background: var(--el-fill-color-light); display: grid; place-items: center; overflow: hidden; } &.active > div { border-color: var(--el-text-color-primary); } img, video { width: 100%; height: 100%; object-fit: cover; } .clipCheck, .clipPlay { position: absolute; right: 5px; top: 4px; padding: 2px 5px; background: rgb(0 0 0 / 60%); color: white; border-radius: 8px; margin: 0; } &.selectedClip > div { border-color: var(--el-color-primary); } span, small { display: block; margin-top: 7px; font-size: 11px; } small { font-size: 10px; } } }
      @media (max-width: 900px) { .episodeEditor { grid-template-columns: 200px minmax(0, 1fr); } .clipPreview { grid-column: 2; grid-row: 2; video, .emptyClipPreview { max-width: 240px; } } .clipTimelineArea { grid-column: 1 / 3; } }
      @media (max-width: 680px) { .episodeEditor { display: flex; flex-direction: column; } .productionLibrary { max-height: 240px; } .clipScript { padding: 14px; } }
      .episodeGrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
      .episodeCard { display: flex; align-items: center; gap: 28px; min-width: 0; padding: 9px; border: 1px solid var(--el-border-color-lighter); border-radius: 22px; background: var(--el-bg-color); color: inherit; text-align: left; cursor: pointer; &:hover { border-color: var(--el-color-primary); } }
      .episodePreview { display: grid; place-items: center; width: 104px; height: 138px; flex-shrink: 0; border-radius: 13px; background: var(--el-fill-color-light); color: var(--el-text-color-placeholder); }
      .episodeContent { min-width: 0; small { font-size: 11px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); border-radius: 12px; padding: 3px 9px; } h2 { font-size: 15px; font-weight: 500; margin: 14px 0 8px; } p { font-size: 12px; color: var(--el-text-color-secondary); } }
      .episodeAction { display: inline-block; padding: 8px 14px; border-radius: 20px; background: var(--el-fill-color-light); font-size: 12px; }
      .resultContinue { display: flex; justify-content: flex-end; margin-top: 28px; }
      @media (max-width: 680px) { .episodeGrid { grid-template-columns: 1fr; } }
      .resultTabs { display: flex; gap: 28px; border-bottom: 1px solid var(--el-border-color-lighter); button { border: 0; border-bottom: 2px solid transparent; padding: 12px 4px; color: var(--el-text-color-secondary); background: none; cursor: pointer; &.active { border-color: var(--el-text-color-primary); color: var(--el-text-color-primary); } span { font-size: 11px; margin-left: 6px; } } }
      .resultHeading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 28px 0 22px; h1 { font-size: 20px; font-weight: 500; margin: 0 0 8px; } p { font-size: 13px; color: var(--el-text-color-secondary); margin: 0; } }
      .resultGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 18px; }
      .resultCard { min-width: 0; border: 1px solid var(--el-border-color-lighter); border-radius: 22px; background: var(--el-bg-color); color: inherit; padding: 8px 8px 16px; text-align: left; cursor: pointer; transition: border-color .2s; &:hover { border-color: var(--el-color-primary); } .resultPreview { display: grid; place-items: center; aspect-ratio: 1; border-radius: 16px; background: var(--el-fill-color-light); color: var(--el-text-color-placeholder); overflow: hidden; img { width: 100%; height: 100%; object-fit: contain; } } strong { display: block; font-size: 14px; font-weight: 500; margin: 14px 8px 8px; } .resultDescription { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin: 0 8px; font-size: 12px; line-height: 1.7; color: var(--el-text-color-secondary); } small { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin: 12px 8px 0; } }
      .resultEmpty { color: var(--el-text-color-secondary); margin-top: 40px; text-align: center; }
      @media (max-width: 680px) { width: calc(100% - 32px); .resultTabs { gap: 18px; } .resultGrid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; } .resultHeading { align-items: flex-start; } }
    }

    .analysisHeader {
      &.episodeHeader { min-height: 60px; box-sizing: border-box; padding: 8px 16px; gap: 12px; position: sticky; top: 0; z-index: 3; .analysisProjectName { max-width: 240px; font-size: 12px; } .analysisBack { width: 28px; height: 28px; } }
      .episodeSaved { font-size: 11px; color: var(--el-color-success); white-space: nowrap; }
      .episodeHeaderTools { display: flex; align-items: center; gap: 8px; margin-left: auto; .compactSetting { width: 88px; :deep(.el-select__wrapper) { box-shadow: none; background: transparent; } } }
      .analysisSteps button { border: 0; padding: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; &:disabled { cursor: default; } }
      display: flex; align-items: center; gap: 16px; min-height: 72px;
      padding: 12px 32px; background: var(--el-bg-color);
      .analysisBack { width: 34px; height: 34px; border: 0; border-radius: 50%; background: var(--el-fill-color-light); color: inherit; font-size: 26px; cursor: pointer; }
      .analysisProjectName { font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 38%; }
      .analysisSteps {
        display: flex; gap: 10px; margin: 0 0 0 auto; padding: 0; list-style: none; color: var(--el-text-color-secondary); font-size: 13px;
        li { padding: 10px 24px; border-radius: 24px; white-space: nowrap; }
        li.active { background: var(--el-text-color-primary); color: var(--el-bg-color); font-weight: 600; }
      }
    }
    .analysisBody {
      .analysisTaskList, .partialAnalysisResults { margin-top: 28px; padding: 24px; border: 1px solid var(--el-border-color-lighter); border-radius: 20px; background: var(--el-bg-color); h2 { font-size: 17px; font-weight: 500; margin: 0 0 14px; } > p { color: var(--el-text-color-secondary); font-size: 12px; } }
      .analysisTaskRow { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter); font-size: 12px; strong { flex: 1; min-width: 180px; font-weight: 500; } span { color: var(--el-color-primary); } small { color: var(--el-text-color-secondary); } }
      .partialResultGrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; margin-top: 18px; button { display: flex; flex-direction: column; gap: 10px; text-align: left; padding: 16px; border-radius: 14px; border: 1px solid var(--el-border-color); color: inherit; background: var(--el-fill-color-extra-light); cursor: pointer; strong { font-size: 13px; font-weight: 500; } span { white-space: pre-wrap; font-size: 12px; max-height: 90px; overflow: hidden; } small { color: var(--el-text-color-secondary); } } }
      width: min(960px, calc(100% - 64px)); margin: 54px auto;
      h1 { font-size: 28px; font-weight: 500; margin: 0 0 34px; }
      .analysisStage {
        position: relative; display: grid; place-items: center; min-height: min(500px, 62vh); padding: 48px 32px;
        border-radius: 36px; background: color-mix(in srgb, var(--el-fill-color) 92%, #aaa0d7 8%);
        box-shadow: 0 0 32px 3px #9c81e71a, inset 0 0 38px #9c81e70d;
        &.running { animation: analysisGlow 3s ease-in-out infinite alternate; }
      }
    }
    .analysisStageContent {
      text-align: center; width: min(600px, 100%);
      h2 { font-size: 18px; font-weight: 500; line-height: 1.7; margin: 0; overflow-wrap: anywhere; }
      p { font-size: 13px; line-height: 1.8; color: var(--el-text-color-secondary); margin: 8px 0 0; }
      .analysisError { max-width: 520px; margin: 12px auto 0; }
      .analysisCounts { display: flex; justify-content: center; flex-wrap: wrap; gap: 12px 22px; margin-top: 28px; font-size: 12px; color: var(--el-text-color-secondary); b { color: var(--el-text-color-primary); font-weight: 500; margin-left: 4px; } }
      .analysisProgress { width: min(280px, 100%); margin: 26px auto 0; span { display: block; margin-top: 10px; font-size: 12px; color: var(--el-text-color-secondary); } }
      .analysisActions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 26px; .el-button { margin: 0; min-width: 106px; } }
      .analysisActivity { display: flex; justify-content: center; gap: 5px; height: 24px; margin-bottom: 22px; i { width: 4px; height: 16px; border-radius: 4px; background: #aa96db; animation: analysisPulse 1.2s ease-in-out infinite; &:nth-child(2) { animation-delay: .15s; } &:nth-child(3) { animation-delay: .3s; } } }
    }
    @media (max-width: 680px) {
      .analysisHeader { padding: 12px 16px; flex-wrap: wrap; gap: 10px; .analysisProjectName { max-width: calc(100% - 48px); } .analysisSteps { width: 100%; justify-content: center; margin: 4px 0 0; gap: 0; li { padding: 8px 16px; } } }
      .analysisBody { width: calc(100% - 32px); margin-top: 32px; h1 { font-size: 24px; margin-bottom: 24px; } .analysisStage { padding: 32px 20px; border-radius: 24px; } }
    }
    @media (prefers-reduced-motion: reduce) { .analysisBody .analysisStage.running, .analysisStageContent .analysisActivity i { animation: none; } }
  }

  @keyframes analysisGlow { to { box-shadow: 0 0 44px 6px #9c81e72b, inset 0 0 46px #9c81e714; } }
  @keyframes analysisPulse { 0%, 100% { transform: scaleY(.45); opacity: .4; } 50% { transform: scaleY(1); opacity: 1; } }
  .resultDetailText { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; font-size: 14px; }
  .analysisResultsButton { margin-top: 8px; }

  .canvasPanel {
    position: absolute;
    inset: 0;
    width: calc(100% - var(--agentWidth, 0px));
    container: canvasWorkspace / inline-size;

    &.backgroundPanel {
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
    }
  }

  .workspaceMenu {
    position: absolute;
    top: 15px;
    left: 15px;
    z-index: 5;
  }

  .workspaceTools {
    position: absolute;
    inset: 0;
    width: calc(100% - var(--agentWidth, 0px));
    container: workspaceTools / inline-size;
    pointer-events: none;

    .productionCanvasTools { position: absolute; top: 60px; right: 16px; z-index: 5; display: flex; align-items: center; gap: 8px; pointer-events: auto; flex-wrap: wrap; justify-content: flex-end; max-width: calc(100% - 32px); .analysisResultsButton { margin: 0; } :deep(.el-button) { margin-left: 0; } }
    .panelSwitcher {
      --el-border-radius-base: 999px;
      --el-segmented-bg-color: var(--el-bg-color-overlay);
      --el-segmented-item-selected-color: var(--el-color-primary);
      --el-segmented-item-selected-bg-color: var(--el-color-primary-light-9);
      position: absolute;
      top: 15px;
      left: 50%;
      z-index: 5;
      min-height: 32px;
      padding: 3px;
      border: 1px solid var(--el-border-color-light);
      box-shadow: var(--el-box-shadow-lighter);
      font-size: 12px;
      transform: translateX(-50%);
      pointer-events: auto;

      .panelOption {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        padding: 0 3px;
        line-height: 24px;
      }
    }

    .bottomTools {
      position: absolute;
      bottom: 15px;
      left: 50%;
      z-index: 5;
      display: flex;
      align-items: center;
      gap: 8px;
      transform: translateX(-50%);
      pointer-events: auto;

      .toolMenu {
        flex-shrink: 0;
        transition: none;

        .toolMenuContent {
          display: flex;
          align-items: center;
          gap: 2px;

          .toolButton {
            width: 32px;
            height: 32px;
            margin: 0;
            padding: 0;

            &.addNodeButton {
              margin-right: 8px;
              color: var(--el-bg-color);
              background: var(--el-text-color-primary);
              border-color: transparent;

              &:hover { opacity: 0.85; }
              &.is-disabled { opacity: 0.45; }
            }
          }

          .pippitButton {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            height: 30px;
            margin: 0 4px;
            border-radius: 999px;
          }

          .toolTrigger { display: inline-flex; }

          .el-divider { margin: 0; }
        }
      }

      .agentButton {
        position: absolute;
        left: calc(100% + 8px);
        width: 40px;
        height: 40px;
        flex-shrink: 0;
        margin: 0;
        padding: 0;
        border: 1px solid color-mix(in srgb, #6edfdc 30%, var(--el-border-color-light));
        border-radius: 50%;
        background: linear-gradient(145deg, color-mix(in srgb, #96f9f0 15%, var(--el-bg-color-overlay)), var(--el-bg-color-overlay) 65%,
          color-mix(in srgb, #8588ff 18%, var(--el-bg-color-overlay)));
        box-shadow: inset 0 1px 0 #ffffff52;
        color: #f4fffe;
        overflow: hidden;
        isolation: isolate;
        transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;

        &.standalone {
          position: relative;
          left: auto;
        }

        &::before,
        &::after {
          content: "";
          position: absolute;
          inset: 4px;
          border-radius: 50%;
          pointer-events: none;
        }

        &::before {
          z-index: -2;
          background: radial-gradient(ellipse at 22% 15%, #adfff0, transparent 50%), radial-gradient(ellipse at 85% 85%, #b29aff, transparent 55%),
            radial-gradient(ellipse at 85% 20%, #25dccc, transparent 50%), linear-gradient(150deg, #10aec1, #3765c6 60%, #765bd3);
          animation: agentFlow 5.4s linear infinite;
          filter: saturate(1.05);
          transition: filter 180ms ease;
        }

        &::after {
          z-index: -1;
          background: radial-gradient(ellipse 12% 18% at 50% 50%, #ffffffa6, #d3fff773 35%, transparent 80%),
            radial-gradient(ellipse at 32% 18%, #ffffff99, transparent 42%), radial-gradient(ellipse at 65% 95%, #17246070, transparent 65%);
          background-size: 160% 160%, 100% 100%, 100% 100%;
          background-position: 75% 85%, 0 0, 0 0;
          background-repeat: no-repeat;
          box-shadow: inset 0 0 0 1px #ffffff52, inset 0 2px 3px #ffffff80, inset 0 -3px 6px #16305b73;
          animation: agentShine 3.2s linear infinite;
        }

        &:hover::before {
          filter: saturate(1.2);
        }

        &:hover {
          transform: translateY(-1px);
          border-color: #87f2eb99;
          box-shadow: inset 0 1px 0 #ffffff70;
        }

        &:active {
          transform: scale(0.95);
        }

        &:focus-visible {
          outline: 2px solid var(--el-color-primary);
          outline-offset: 3px;
        }

        .agentLogo {
          width: 24px;
          height: 24px;
          flex-shrink: 0;
          background: currentColor;
          mask-size: contain;
          mask-position: center;
          mask-repeat: no-repeat;
        }

        @media (prefers-reduced-motion: reduce) {
          transition: none;

          &::before,
          &::after {
            animation: none;
          }
        }
      }
    }
  }
}

@keyframes agentFlow {
  from {
    transform: rotate(0deg) scale(1);
  }
  25% {
    transform: rotate(90deg) scale(1.06, 1.02);
  }
  50% {
    transform: rotate(180deg) scale(1.02, 1.06);
  }
  75% {
    transform: rotate(270deg) scale(1.05, 1.03);
  }
  to {
    transform: rotate(360deg) scale(1);
  }
}

@keyframes agentShine {
  0%,
  100% {
    background-size: 160% 160%, 100% 100%, 100% 100%;
    background-position: 75% 85%, 0 0, 0 0;
  }
  12.5% {
    background-position: 40% 98%, 0 0, 0 0;
  }
  25% {
    background-size: 180% 140%, 100% 100%, 100% 100%;
    background-position: 10% 75%, 0 0, 0 0;
  }
  37.5% {
    background-position: 2% 40%, 0 0, 0 0;
  }
  50% {
    background-size: 160% 160%, 100% 100%, 100% 100%;
    background-position: 25% 10%, 0 0, 0 0;
  }
  62.5% {
    background-position: 60% 2%, 0 0, 0 0;
  }
  75% {
    background-size: 140% 180%, 100% 100%, 100% 100%;
    background-position: 95% 25%, 0 0, 0 0;
  }
  87.5% {
    background-position: 98% 60%, 0 0, 0 0;
  }
}
.helpMenu {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .helpAction {
    justify-content: flex-start;
    margin-left: 0;
  }
}

.contactContent {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;

  .contactTip {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.7;
  }
}
</style>
