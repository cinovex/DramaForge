# Pippit Skill API Reference

## Domain and Authentication

- Base URL: `https://www.pippit.ai`
- Request header: `Authorization: Bearer <PIPPIT_ACCESS_KEY>`
- Successful responses follow `{ "ret": "0", "data": ... }`
- The skill does not query access keys. First check whether a local `PippitAccessKey` exists. If not, direct the user to [Pippit](https://www.pippit.ai) to get an access key, then save the user-provided key before using it.

## Core Endpoints

### 1. List Bound Platform Accounts

- Path: `POST /api/biz/v1/common/skill/list_user_platform_account`
- Request body: `{}`
- Key response fields:
  - `platform_name`
  - `platform_user_id`
  - `platform_nick_name`
  - `platform_email`
  - `status`
  - `binding_time`
  - `avatar_url`

### 2. Upload Video

- Path: `POST /api/biz/v1/skill/upload_file`
- Form fields:
  - `file`
  - `asset_type=1`
- `asset_type` enum:
  - `1 = Video`
  - `2 = Image`
  - `3 = Document`
  - `4 = Audio`
- Key response fields:
  - `asset_id`
  - `download_url`
  - `cover_url`
  - `duration_ms`
  - `mime`

### 3. Batch Create Publishing Tasks

- Path: `POST /api/biz/v1/publish/skill/batchcreate_schedule_task`
- One call supports up to 10 tasks.
- Top-level structure:

```json
{
  "requests": [
    {
      "task_type": 1,
      "publish_media_param": {
        "platform_type": 1,
        "publish_type": 1,
        "platform_user_ids": ["123"],
        "file_type": 1,
        "asset_id_list": ["asset_xxx"],
        "schedule_time": 1775547801000,
        "action_type": 2,
        "action_from": 0,
        "publish_tiktok_param": {
          "title": "caption here",
          "urls": [],
          "anchors": [],
          "privacy_level": 1,
          "disable_comment": false,
          "disable_duet": true,
          "disable_stitch": true,
          "asset_id_list": ["asset_xxx"],
          "schedule_time": 1775547801000,
          "is_brand_organic": false,
          "is_branded_content": false
        }
      }
    }
  ]
}
```

### 4. Publishing Task CRUD

- List: `POST /api/biz/v1/publish/skill/list_schedule_task`
- Update: `POST /api/biz/v1/publish/skill/update_schedule_task`
- Delete: `POST /api/biz/v1/publish/skill/delete_schedule_task`

Common fields:

- `task_type=1` means social media publishing.
- `action_type=2` means publish by default.
- `action_from=0` is fixed by the current scripts.
- `file_type=1` is fixed by the current scripts.
- `platform_user_ids`
  - Required for practical task queries.
  - Shape: `{ "<platform_type>": ["<platform_user_id>"] }`
  - Passing only a time window without a platform account filter can return an empty array.
- `status_list`
  - `1 = Pending`
  - `2 = Processing`
  - `3 = Done`
  - `4 = Failed`
  - `5 = Canceled`
  - `6 = Init`
  - `7 = PartialSuccess`
  - `8 = Queueing`

### 5. Content Analytics

- Path: `POST /api/biz/v1/analytics/skill/videos`
- Top-level structure:

```json
{
  "start_time_sec": 1711929600,
  "end_time_sec": 1714521600,
  "account_list": {
    "platform_type": 1,
    "platform_user_ids": ["123"]
  },
  "force_refresh": false
}
```

## Platform Enum

- `TikTok = 1`
- `Facebook Page = 301`
- `Instagram = 311`

The scripts accept these aliases:

- `tiktok`
- `facebook`
- `facebook-page`
- `ins`
- `instagram`

## Publishing Type Enum

- `publish_type`
  - `1 = Now`
  - `2 = Schedule`
- `task_type`
  - `1 = PublishMedia`
- `action_type`
  - `1 = Save`
  - `2 = Publish`

## Platform-Specific Parameters

Put platform-specific extra parameters in the matching platform JSON:

- TikTok: `--tiktok-json`, mapped to `publish_tiktok_param`
- Instagram: `--instagram-json`, mapped to `publish_instagram_param`
- Facebook Page: `--facebook-json`, mapped to `publish_facebook_param`

Keep only common fields in top-level `publish_media_param`. Put private platform capabilities in the matching platform JSON to avoid cross-platform field pollution.

### TikTok

Entry field: `publish_tiktok_param`

Use cases:

- Publish TikTok videos.
- Control comments, duet, stitch, and privacy.
- Mark branded content or brand-owned organic content.
- Add `anchors` when product anchors are needed.

Field details:

| Field | Type | Description | Common values/default |
| --- | --- | --- | --- |
| `title` | string | Video title or caption | Pass the natural-language title directly |
| `privacy_level` | int | Visibility setting | `1=Public` `2=Mutual friends` `3=Only me` `4=Followers` |
| `disable_comment` | bool | Disable comments | Passed from script flags or platform JSON |
| `disable_duet` | bool | Disable duet | Passed from script flags or platform JSON |
| `disable_stitch` | bool | Disable stitch | Passed from script flags or platform JSON |
| `video_cover_timestamp_ms` | int | Cover frame timestamp in milliseconds | Example: `3000` |
| `asset_id_list` | string[] | Platform-side asset list | Usually matches top-level `asset_id_list` |
| `schedule_time` | int | Platform-side publish time in milliseconds | Usually matches top-level `schedule_time` |
| `urls` | string[] | Used for publishing from remote URLs | Usually empty when `asset_id_list` is present |
| `anchors` | object[] | Platform anchor capabilities | See product anchor example below |
| `is_branded_content` | bool | Mark as branded partner content | Commonly `false` |
| `is_brand_organic` | bool | Mark as brand-owned organic content | Commonly `false` |
| `is_disclose_video_content` | bool | Business extension field | Pass through as required by the platform |
| `is_promote_own_brand` | bool | Business extension field | Pass through as required by the platform |
| `is_promote_other_brand` | bool | Business extension field | Pass through as required by the platform |
| `media_type` | int | Media type | `1=Video` `2=Image`; this skill usually publishes video only |

Recommended minimal JSON:

```json
{
  "privacy_level": 1,
  "disable_comment": false,
  "disable_duet": true,
  "disable_stitch": true
}
```

Example with a product anchor:

```json
{
  "privacy_level": 1,
  "disable_comment": false,
  "disable_duet": true,
  "disable_stitch": true,
  "anchors": [
    {
      "type": 1,
      "shop": {
        "product_id": "7212345678901234567",
        "keyword": "summer dress"
      }
    }
  ]
}
```

### Instagram

Entry field: `publish_instagram_param`

Use cases:

- Publish Instagram Reels.
- Publish regular Instagram video posts.
- Configure collaborators, user tags, and product tags.

Field details:

| Field | Type | Description | Common values/default |
| --- | --- | --- | --- |
| `title` | string | Instagram caption | Maximum 2200 characters |
| `media_type` | int | Publishing type | `1=Reels` `2=Image` `3=Video`; this skill commonly uses `1` or `3` |
| `audio_name` | string | Reels audio name | Meaningful only when `media_type=1` |
| `thumb_offset_ms` | int | Cover frame timestamp in milliseconds | Example: `1000` |
| `share_to_feed` | bool | Whether to share Reels to Feed | Commonly `true` for Reels |
| `collaborators` | string[] | Collaborator usernames | Example: `["brand_a","creator_b"]` |
| `user_tags` | object[] | User tags | See example below; `x/y` values are 0-100 |
| `product_tags` | object[] | Product tags | See example below; `x/y` values are 0-100 |

Recommended minimal JSON:

```json
{
  "media_type": 1,
  "share_to_feed": true
}
```

Example with collaborators and user tags:

```json
{
  "media_type": 1,
  "share_to_feed": true,
  "collaborators": ["brand_official"],
  "user_tags": [
    {
      "username": "brand_official",
      "x": 48,
      "y": 35
    }
  ]
}
```

Example with product tags:

```json
{
  "media_type": 1,
  "share_to_feed": true,
  "product_tags": [
    {
      "product_id": "gid://shopify/Product/1234567890",
      "x": 42,
      "y": 58
    }
  ]
}
```

### Facebook Page

Entry field: `publish_facebook_param`

Use cases:

- Publish Facebook Page Reels.
- Publish regular Facebook Page video posts.
- Add body text or hashtags through `description`.

Field details:

| Field | Type | Description | Common values/default |
| --- | --- | --- | --- |
| `title` | string | Title | Available for regular video posts and some Reels scenarios |
| `description` | string | Body text or extra description | Can contain hashtags or campaign copy |
| `media_type` | int | Publishing type | `1=Reels` `2=Image` `3=Video`; this skill commonly uses `1` or `3` |

Recommended minimal JSON:

```json
{
  "media_type": 1,
  "description": "#newdrop #behindthescenes"
}
```

Regular video post example:

```json
{
  "media_type": 3,
  "title": "Product walkthrough",
  "description": "Watch the full demo."
}
```

## Recommended Usage

- Do not query the access key through scripts. First check local `PippitAccessKey`; if none exists, direct the user to [Pippit](https://www.pippit.ai) for an access key, then save the user-provided key before use.
- For simple single-platform publishing, construct the request directly from script arguments.
- For complex TikTok, Instagram, or Facebook Page fields, use `--tiktok-json`, `--instagram-json`, or `--facebook-json`.
- When querying tasks, always pass both the platform and `platform_user_id`; time-window-only queries often return no results.
- If a field is platform-specific, put it in the matching platform JSON instead of top-level `publish_media_param`.
- When updating a task and only one or two fields are changing, list the existing task first with `list_schedule_task.py` if the old values are uncertain, then construct the update request.
