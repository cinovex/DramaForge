# Pippit Skill Command Map

## Creation Scripts

Base directory: `{baseDir}/scripts/nest`

```bash
python3 {baseDir}/scripts/nest/save_access_key.py --access-key "..."
python3 {baseDir}/scripts/nest/upload_file.py /path/to/reference.png
python3 {baseDir}/scripts/nest/upload_file.py /path/to/reference.mp4
python3 {baseDir}/scripts/nest/submit_run.py --message "USER_REQUEST"
python3 {baseDir}/scripts/nest/submit_run.py --thread-id THREAD_ID --message "FOLLOW_UP"
python3 {baseDir}/scripts/nest/submit_run.py --message "USER_REQUEST" --asset-ids ASSET_ID_1 ASSET_ID_2
python3 {baseDir}/scripts/nest/get_thread.py --thread-id THREAD_ID --run-id RUN_ID --after-seq 0
python3 {baseDir}/scripts/nest/download_results.py --urls URL1 URL2 --output-dir ./pippit_output --prefix artifact
```

When uploading reference assets, prefer `reference_asset_ids` if it is present in the response. Otherwise use `pippit_asset_id` first, then `asset_id` or `everphoto_asset_id`.

## Publishing Scripts

Base directory: `{baseDir}/scripts/publish`

```bash
python3 {baseDir}/scripts/publish/save_access_key.py --access-key "..."
python3 {baseDir}/scripts/publish/list_user_platform_account.py
python3 {baseDir}/scripts/publish/upload_file.py /path/to/video.mp4
python3 {baseDir}/scripts/publish/batchcreate_schedule_task.py --platform tiktok --platform-user-id PLATFORM_USER_ID --asset-id ASSET_ID --title "TITLE_OR_CAPTION" --schedule-time "2026-05-15T20:00:00+08:00"
python3 {baseDir}/scripts/publish/list_schedule_task.py --platform tiktok --platform-user-id PLATFORM_USER_ID
python3 {baseDir}/scripts/publish/update_schedule_task.py --id TASK_ID --platform tiktok --platform-user-id PLATFORM_USER_ID --asset-id ASSET_ID --title "TITLE_OR_CAPTION" --schedule-time "2026-05-15T20:00:00+08:00"
python3 {baseDir}/scripts/publish/delete_schedule_task.py --ids TASK_ID
python3 {baseDir}/scripts/publish/list_videos.py --platform tiktok --platform-user-id PLATFORM_USER_ID --start-time-sec START --end-time-sec END
```

Platform aliases:

- `tiktok`: TikTok
- `facebook` or `facebook-page`: Facebook Page
- `instagram` or `ins`: Instagram

## Handoff from Creation to Publishing

The reliable handoff uses local files:

1. Use `scripts/nest/download_results.py` to download generated video URLs into local video files.
2. Use `scripts/publish/upload_file.py` to upload the local video file.
3. Use `scripts/publish/batchcreate_schedule_task.py` to create the scheduled publishing task.

Do not pass asset IDs from the Nest generation flow directly into the publishing flow unless the publishing script or API explicitly confirms that those IDs are valid for publishing.
