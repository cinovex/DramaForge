---
name: pippit-skill
description: Self-contained end-to-end Pippit.ai skill for AI creative generation/editing, generated asset downloads, overseas social video publishing, scheduling, task management, and analytics. Use when the user wants an end-to-end Pippit flow from prompt or reference image/video assets to generated video, local download, TikTok/Facebook Page/Instagram scheduling, publish task CRUD, or performance analysis; also use for Pippit access-key setup for either creation or publishing.
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "P",
        "requires":
          {
            "bins": ["python3"],
            "env": ["PIPPIT_ACCESS_KEY"]
          },
        "primaryEnv": "PIPPIT_ACCESS_KEY"
      }
  }
---

# Pippit Skill Workflow

Use this self-contained skill for overseas Pippit.ai workflows. It includes both backend script sets locally:

- `scripts/nest/`: Pippit Nest AI generation, editing, reference uploads, progress polling, and result downloads.
- `scripts/publish/`: Social account lookup, video upload, scheduled publishing, task CRUD, and analytics.

No external Pippit skill directories are required. For local commands, resolve `{baseDir}` to this skill folder. For detailed publishing payload fields, read [references/publishing-api.md](references/publishing-api.md).

Pippit Nest owns creative interpretation, prompt expansion, model choice, storyboarding, and workflow routing. The local agent should only upload references, pass the user's request through, poll progress, handle clarification requests, download results, and then publish the selected video when requested.

## Route the Request

- **Creative only**: Use `scripts/nest/` to generate/edit, poll, and download outputs. Stop after returning local files unless the user asks to publish.
- **Publish only**: Use `scripts/publish/` for existing local videos, bound account checks, scheduling, task CRUD, or analytics.
- **Create-to-publish**: Use `scripts/nest/` first, download the generated video, then use `scripts/publish/` to upload and schedule it.
- **Image-only output**: Publishing supports video only. If the user wants to publish an image/poster, ask whether to generate or convert it into a video first.

## Creative Request Handling

- Pass the user's creative or edit request to `scripts/nest/submit_run.py --message` as-is. Do not compress, summarize, rewrite, polish, translate, split, or add prompt language unless the user explicitly asks.
- Keep one creative task as one Nest submission. Do not turn a single request into per-shot, per-scene, or per-asset runs unless the user explicitly asks for separate runs.
- Do not manually write storyboards, infer camera plans, analyze styles, choose models, or orchestrate sub-prompts locally. Let Pippit Nest do that work.
- When reference images or videos are provided, upload them and submit the original request with the returned asset IDs. Do not replace the user's wording with your own description of the references.
- When Pippit asks for clarification or interaction, show the question to the user and submit the user's answer to the same `thread_id`; do not answer on the user's behalf.

## Access Key

Use one Pippit access key for both creation and publishing. Resolve it in this order:

1. `PIPPIT_ACCESS_KEY`
2. `PippitAccessKey`
3. Local cache at `$CODEX_HOME/pippit-skill/secrets.json`

Save a new key once with either local save script:

```bash
python3 {baseDir}/scripts/nest/save_access_key.py --access-key "..."
```

Do not invent, retrieve, or echo the full access key. If no key is available, respond in English: "No Pippit access key is configured. Please get one from https://www.pippit.ai, then provide it or save it before continuing."

## End-to-End Flow

1. Collect the minimum missing inputs:
   - Creative request and any reference image/video files
   - Target platform: TikTok, Facebook Page, or Instagram
   - Bound platform account
   - Title or caption
   - Publish mode: default publish unless the user explicitly requests scheduled publish
   - For scheduled publish: scheduled publish time with timezone
2. For Pippit generation/editing, tell the user it consumes credits and wait for explicit confirmation before calling `submit_run.py`.
3. Upload reference files one by one with `scripts/nest/upload_file.py` when references are provided.
4. Submit the user's original creative request as a single `scripts/nest/submit_run.py --message` value, with uploaded asset IDs when present.
5. Show `web_thread_link` when returned, then poll with `scripts/nest/get_thread.py` using both `thread_id` and `run_id`.
6. If Pippit asks for clarification or interaction, show the question to the user and submit their answer to the same thread.
7. Download generated result URLs with `scripts/nest/download_results.py`.
8. Choose the generated video file to publish. If multiple videos exist and the user has not indicated one, ask them to choose.
9. List bound social accounts with `scripts/publish/list_user_platform_account.py`. If no usable account exists, stop and direct the user to bind one on Pippit.
10. Upload the final local video with `scripts/publish/upload_file.py`.
11. If the user does not mention scheduling, treat the request as default publish; do not ask the user to choose a publish mode.
12. For default publish, convert it into an explicit near-future scheduled time, defaulting to current local time plus 5 minutes rounded up to the next minute unless the user requests a different short delay. For scheduled publish, require an explicit absolute publish time with timezone.
13. Restate platform, account, video file, caption/title, publish mode, and absolute schedule time. Wait for confirmation only when the platform/account/video/caption is missing or ambiguous, or when the user asked for scheduled publish without providing a concrete time. Do not ask solely because default publish mode or its near-future schedule time was inferred.
14. Create the scheduled task with `scripts/publish/batchcreate_schedule_task.py`. Pippit publishing is scheduled-only; never claim an immediate publish path exists.
15. Return task IDs/statuses, generated local file paths, and the Pippit thread link. If default publish was used, briefly mention that scheduled publish is also supported.

## Local Commands

Use [references/command-map.md](references/command-map.md) for full command examples. Common commands:

```bash
python3 {baseDir}/scripts/nest/submit_run.py --message "Create a product video..."
python3 {baseDir}/scripts/nest/get_thread.py --thread-id THREAD_ID --run-id RUN_ID --after-seq 0
python3 {baseDir}/scripts/nest/download_results.py --urls URL1 URL2 --output-dir ./pippit_output --prefix artifact
python3 {baseDir}/scripts/publish/list_user_platform_account.py
python3 {baseDir}/scripts/publish/upload_file.py /path/to/video.mp4
python3 {baseDir}/scripts/publish/batchcreate_schedule_task.py --platform tiktok --platform-user-id PLATFORM_USER_ID --asset-id ASSET_ID --title "TITLE_OR_CAPTION" --schedule-time "2026-05-15T20:00:00+08:00"
```

## Publishing Rules

- Publish only videos through `scripts/publish/`.
- Treat unspecified publish mode as default publish. Default publish means "publish soon" and must still be implemented as a near-future scheduled task.
- Do not schedule without a platform account, caption/title, publish mode, and explicit absolute schedule time. For default publish, compute the absolute near-future schedule time before creating the task.
- After successfully creating a default publish task, add a short note that scheduled publish is also supported.
- Resolve relative dates such as "today", "tomorrow", or "next Friday" into absolute dates before scheduling.
- For TikTok, Instagram, or Facebook-specific settings, use script flags and JSON override options. Do not guess complex platform payloads; read [references/publishing-api.md](references/publishing-api.md) first.
- One batch create call supports up to 10 tasks. Split larger batches deliberately.

## Follow-Up Operations

- To update, delete, or list scheduled tasks, use `scripts/publish/` task scripts and keep platform plus `platform_user_id` in the query.
- To analyze published posts, use `scripts/publish/list_videos.py` and summarize title, platform, publish time, views, likes, comments, shares, and engagement rate when available.
- To refine a generated asset before publishing, continue the same Pippit Nest thread with `scripts/nest/submit_run.py --thread-id`.

## Output Expectations

Keep the user-facing response concise but include the operational identifiers they need:

- Nest generation: `thread_id`, `run_id`, `web_thread_link`, downloaded local files
- Publishing: platform, `platform_user_id`, uploaded `asset_id`, task IDs, task status, scheduled time
- Analytics: platform, account, video title, publish time, core metrics

Never claim a generation, upload, or publishing task succeeded unless the relevant local script returned success.
