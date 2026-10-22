"""可选的 S3/R2 公网图床。默认继续使用图片提供商的原图 URL。"""
import os
import base64
from pathlib import Path
from urllib.parse import unquote, urlparse
from config import STORAGE_DIR, IMAGES_DIR, PROJECTS_DIR
from models.drama import ImageSource
from services.gpt_service import GPTError

# Agnes accepts image Data URIs as video references. Inline input avoids requiring
# users to configure a separate public image bucket for locally uploaded artwork.
MAX_INLINE_VIDEO_IMAGE_BYTES = 12 * 1024 * 1024
MAX_INLINE_VIDEO_REQUEST_BYTES = 24 * 1024 * 1024


def _local_image_path(local_url: str) -> Path | None:
    if not isinstance(local_url, str) or not local_url.startswith('/storage/'):
        return None
    relative = unquote(local_url.removeprefix('/storage/').split('?', 1)[0])
    path = (STORAGE_DIR / relative).resolve()
    if not path.is_relative_to(STORAGE_DIR.resolve()):
        return None
    in_legacy_images = path.is_relative_to(IMAGES_DIR.resolve())
    project_parts = (path.relative_to(PROJECTS_DIR.resolve()).parts
                     if path.is_relative_to(PROJECTS_DIR.resolve()) else ())
    in_project_images = (len(project_parts) >= 3 and project_parts[0].isdigit()
                         and project_parts[1] == 'images')
    return path if in_legacy_images or in_project_images else None


def _image_content_type(path: Path) -> str | None:
    try:
        with path.open('rb') as image:
            signature = image.read(12)
    except OSError:
        return None
    if signature.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if signature.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if signature.startswith(b'RIFF') and signature[8:12] == b'WEBP':
        return 'image/webp'
    return None


def can_inline_video_image(local_url: str | None) -> bool:
    path = _local_image_path(local_url or '')
    if path is None or not path.is_file():
        return False
    try:
        return path.stat().st_size <= MAX_INLINE_VIDEO_IMAGE_BYTES and bool(_image_content_type(path))
    except OSError:
        return False


def video_image_input(db, image_url: str | None) -> str | None:
    """Return an HTTPS provider URL or a safe local-image Data URI for Agnes."""
    if not image_url:
        return None
    if image_url.startswith('https://'):
        return image_url
    if image_url.startswith('http://'):
        raise GPTError('参考图地址必须使用 HTTPS', 400)

    source = db.query(ImageSource).filter_by(local_url=image_url).first()
    if source and source.remote_url:
        if source.remote_url.startswith('https://'):
            return source.remote_url
        raise GPTError('参考图原图地址不是 HTTPS，请重新发布图片', 400)

    path = _local_image_path(image_url)
    if path is None or not path.is_file():
        raise GPTError('参考图文件不存在或路径无效，请重新上传图片', 400)
    size = path.stat().st_size
    content_type = _image_content_type(path)
    if not content_type:
        raise GPTError('参考图格式无法识别，请上传 PNG、JPG 或 WEBP', 415)
    if size > MAX_INLINE_VIDEO_IMAGE_BYTES:
        raise GPTError('参考图超过 12 MB，无法直接传给视频模型；请压缩图片或配置公网图片存储', 413)
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{content_type};base64,{encoded}'


def validate_video_image_payload(image_inputs: list[str]) -> None:
    inline_size = sum(len(value) for value in image_inputs if value.startswith('data:image/'))
    if inline_size > MAX_INLINE_VIDEO_REQUEST_BYTES:
        raise GPTError('本次参考图片合计过大，请减少参考图或配置公网图片存储', 413)

def configured() -> bool:
    return all(os.getenv(k) for k in (
        'DRAMAFORGE_MEDIA_BUCKET','DRAMAFORGE_MEDIA_ENDPOINT',
        'DRAMAFORGE_MEDIA_ACCESS_KEY','DRAMAFORGE_MEDIA_SECRET_KEY',
        'DRAMAFORGE_MEDIA_PUBLIC_BASE'))

def publish_local_image(db, local_url: str) -> str | None:
    """上传本地图到用户配置的公网桶，并记录稳定地址。未配置则返回 None。"""
    if not configured(): return None
    if not (local_url.startswith('/storage/images/') or local_url.startswith('/storage/projects/')):
        raise GPTError('只允许发布项目图片',400)
    public_base=os.environ['DRAMAFORGE_MEDIA_PUBLIC_BASE'].rstrip('/')
    parsed=urlparse(public_base)
    if parsed.scheme!='https' or not parsed.netloc:
        raise GPTError('公网图片地址必须为 HTTPS',400)
    path=(STORAGE_DIR / local_url.removeprefix('/storage/')).resolve()
    in_legacy_images=path.is_relative_to(IMAGES_DIR.resolve())
    project_parts=(path.relative_to(PROJECTS_DIR.resolve()).parts
                   if path.is_relative_to(PROJECTS_DIR.resolve()) else ())
    in_project_images=len(project_parts)>=3 and project_parts[0].isdigit() and project_parts[1]=='images'
    if not (in_legacy_images or in_project_images): raise GPTError('无效参考图片路径',400)
    if not path.is_file(): raise GPTError('参考图片文件不存在',404)
    key='dramaforge/'+local_url.removeprefix('/storage/')
    try:
        import boto3
        signature=path.open('rb').read(12)
        content_type=('image/jpeg' if signature.startswith(b'\xff\xd8\xff') else
                      'image/webp' if signature.startswith(b'RIFF') and signature[8:12]==b'WEBP' else 'image/png')
        client=boto3.client('s3',endpoint_url=os.environ['DRAMAFORGE_MEDIA_ENDPOINT'],
            aws_access_key_id=os.environ['DRAMAFORGE_MEDIA_ACCESS_KEY'],
            aws_secret_access_key=os.environ['DRAMAFORGE_MEDIA_SECRET_KEY'])
        client.upload_file(str(path),os.environ['DRAMAFORGE_MEDIA_BUCKET'],key,
                           ExtraArgs={'ContentType':content_type,'CacheControl':'public, max-age=31536000, immutable'})
    except Exception as exc:
        raise GPTError(f'参考图发布失败：{type(exc).__name__}',502) from exc
    url=f'{public_base}/{key}'
    row=db.query(ImageSource).filter_by(local_url=local_url).first()
    if row: row.remote_url=url
    else: db.add(ImageSource(local_url=local_url,remote_url=url))
    db.flush()
    return url


def delete_published_image(remote_url: str) -> bool:
    """Delete only objects uploaded by DramaForge to its configured media bucket."""
    if not configured() or not remote_url:
        return False
    public_base=os.environ['DRAMAFORGE_MEDIA_PUBLIC_BASE'].rstrip('/')
    prefix=f'{public_base}/dramaforge/'
    if not remote_url.startswith(prefix):
        return False
    parsed=urlparse(remote_url)
    key=unquote(parsed.path.lstrip('/'))
    if not key.startswith('dramaforge/') or '..' in key.split('/'):
        return False
    try:
        import boto3
        client=boto3.client('s3',endpoint_url=os.environ['DRAMAFORGE_MEDIA_ENDPOINT'],
            aws_access_key_id=os.environ['DRAMAFORGE_MEDIA_ACCESS_KEY'],
            aws_secret_access_key=os.environ['DRAMAFORGE_MEDIA_SECRET_KEY'])
        client.delete_object(Bucket=os.environ['DRAMAFORGE_MEDIA_BUCKET'],Key=key)
        return True
    except Exception as exc:
        raise GPTError(f'云端参考图删除失败：{type(exc).__name__}',502) from exc
