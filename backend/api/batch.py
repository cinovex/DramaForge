import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models.drama import Shot, Project, Scene, Character, Outline
from services import agnes_video_service, gpt_service
from config import VIDEOS_DIR, STORAGE_DIR, project_directory
from api.shots import _build_prompt, _background_generate

router = APIRouter(prefix="/api/projects", tags=["batch"])
_batch_tasks: set[asyncio.Task] = set()

FFMPEG = str(Path(__file__).resolve().parent.parent.parent / "tools" / "ffmpeg" / "ffmpeg.exe")
if not os.path.exists(FFMPEG):
    # fallback
    FFMPEG = "ffmpeg"
FFPROBE = str(Path(FFMPEG).with_name('ffprobe.exe')) if FFMPEG != 'ffmpeg' else 'ffprobe'

def _media_info(path: Path) -> tuple[float,bool]:
    result=subprocess.run([FFPROBE,'-v','error','-show_entries','format=duration:stream=codec_type',
                           '-of','json',str(path)],capture_output=True,text=True,timeout=30)
    if result.returncode: raise HTTPException(422,f'无法读取视频素材：{path.name}')
    try:
        value=json.loads(result.stdout)
        streams=value.get('streams',[])
        if not any(stream.get('codec_type')=='video' for stream in streams): raise ValueError('no video')
        return float(value['format']['duration']),any(stream.get('codec_type')=='audio' for stream in streams)
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,f'视频素材无效：{path.name}') from exc

def _output_dimensions(ratio: str, resolution: str) -> tuple[int,int]:
    short={'720P':720,'1080P':1080,'1K':1024,'2K':2048}.get(resolution,720)
    width,height=map(int,ratio.split(':'))
    if width>=height:
        target_h=short;target_w=round(short*width/height/2)*2
    else:
        target_w=short;target_h=round(short*height/width/2)*2
    return target_w,target_h


@router.post("/{project_id}/episodes/{ep_no}/batch-generate")
async def batch_generate(
    project_id: int,
    ep_no: int,
    model: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """批量生成该集待生成分镜"""
    from services.director_design import ensure_project_idle
    ensure_project_idle(project_id, db)
    shots = (
        db.query(Shot)
        .filter(Shot.project_id == project_id, Shot.episode_no == ep_no)
        .order_by(Shot.shot_no)
        .all()
    )
    if not shots:
        raise HTTPException(404, f"第 {ep_no} 集没有分镜")

    outline = db.query(Outline).filter_by(project_id=project_id).first()
    aspect_ratio = (outline.aspect_ratio if outline else "9:16") or "9:16"

    semaphore = asyncio.Semaphore(4)  # 并发限制（Token Plan 视频 RPM 为 5）

    async def process(shot_id: int):
        # 后台任务使用独立会话，避免请求会话关闭后对象失效
        db2 = SessionLocal()
        try:
            async with semaphore:
                shot = db2.query(Shot).get(shot_id)
                if not shot or shot.video_status not in ("pending", "failed"):
                    return
                scene = (
                    db2.query(Scene)
                    .filter(
                        Scene.project_id == project_id,
                        Scene.name == shot.scene_name,
                    )
                    .first()
                    if shot.scene_name
                    else None
                )
                characters = db2.query(Character).filter(Character.project_id == project_id, Character.name.in_(shot.character_names or [])).all()
                prompt = _build_prompt(shot, scene, characters=characters, aspect_ratio=aspect_ratio)

                # 参考图：关键帧 → 场景图 → 首个角色图
                ref = shot.keyframe_url or None
                if not ref and scene and scene.image_url:
                    ref = scene.image_url
                if not ref and shot.character_names:
                    c = (
                        db2.query(Character)
                        .filter(
                            Character.project_id == project_id,
                            Character.name == shot.character_names[0],
                        )
                        .first()
                    )
                    if c and c.base_image_url:
                        ref = c.base_image_url

                try:
                    from services.generation_design import compile_generation, generation_manifest
                    generation=compile_generation(db2,db2.get(Project,project_id),shot,model)
                    prompt=generation["prompt"]
                    claimed=db2.query(Shot).filter(Shot.id==shot_id,Shot.video_status.in_(["pending","failed"])).update({
                        Shot.video_status:"processing",Shot.provider_task_id:"",
                        Shot.started_at:datetime.utcnow(),Shot.finished_at:None,
                        Shot.last_error:""},synchronize_session=False)
                    db2.commit()
                    if not claimed: return
                    task_id = await agnes_video_service.create_video_task(
                        db2,prompt,shot.duration,model=model,generation=generation)

                    db2.refresh(shot)
                    shot.provider_task_id = task_id
                    shot.provider_model = generation["model"]
                    shot.generation_manifest = generation_manifest(generation)
                    db2.commit()
                    asyncio.create_task(
                        _background_generate(shot.id, task_id, prompt, model=generation["model"])
                    )
                except gpt_service.GPTError as e:
                    db2.rollback()
                    db2.refresh(shot)
                    shot.last_error=e.message
                    shot.video_status = "failed"
                    shot.finished_at = datetime.utcnow()
                    db2.commit()
                except Exception:
                    db2.rollback()
                    db2.refresh(shot)
                    shot.last_error="视频任务提交失败"
                    shot.video_status="failed"
                    shot.finished_at=datetime.utcnow()
                    db2.commit()
        finally:
            db2.close()

    submitted=0
    for shot in shots:
        if shot.video_status not in ("pending", "failed"):
            continue
        task=asyncio.create_task(process(shot.id))
        _batch_tasks.add(task)
        task.add_done_callback(_batch_tasks.discard)
        submitted+=1

    return {
        "project_id": project_id,
        "ep_no": ep_no,
        "shot_count": len(shots),
        "queued_count": submitted,
        "skipped_count": len(shots)-submitted,
        "message": f"已安排 {submitted} 个分镜的视频生成任务",
    }


@router.post("/{project_id}/export")
def export_episode(
    project_id: int, ep_no: int = 0, db: Session = Depends(get_db)
):
    """
    用 ffmpeg 拼接该集（或全部）已完成视频为单个 MP4
    ep_no=0 表示全部集
    """
    p = db.query(Project).get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    query = db.query(Shot).filter(Shot.project_id == project_id)
    if ep_no > 0: query = query.filter(Shot.episode_no == ep_no)
    shots = query.order_by(Shot.episode_no, Shot.shot_no).all()

    if not shots: raise HTTPException(400, "没有可导出的分镜")
    missing = [f"EP{s.episode_no} #{s.shot_no} ({s.video_status})" for s in shots
               if s.video_status != "done" or not s.video_url]
    if missing:
        raise HTTPException(409, f"成片尚不完整：{len(missing)} 个镜头未完成：" + "、".join(missing[:12]))

    # 导出前核对所有视频并固定片段规格。模型实际返回的时长常比规划长几帧。
    file_list: list[tuple[Path,Shot,bool]] = []
    for shot in shots:
        legacy_url = shot.video_url.startswith('/storage/videos/')
        project_prefix = f'/storage/projects/{project_id}/videos/'
        project_url = shot.video_url.startswith(project_prefix)
        if not (legacy_url or project_url):
            raise HTTPException(422,f'视频路径无效：EP{shot.episode_no} #{shot.shot_no}')
        path=(STORAGE_DIR / shot.video_url.removeprefix('/storage/')).resolve()
        allowed_roots = [VIDEOS_DIR.resolve()]
        if project_url:
            allowed_roots.append((project_directory(project_id) / 'videos').resolve())
        if not any(path.is_relative_to(root) for root in allowed_roots) or not path.is_file():
            raise HTTPException(500,f'视频文件缺失：EP{shot.episode_no} #{shot.shot_no}')
        actual,has_audio=_media_info(path)
        if actual < shot.duration-0.25:
            raise HTTPException(422,f'EP{shot.episode_no} #{shot.shot_no} 实际只有{actual:.2f}秒，短于计划{shot.duration:g}秒；请重做该镜头')
        file_list.append((path,shot,has_audio))

    # 生成 ffmpeg concat 列表文件
    import uuid
    export_id = uuid.uuid4().hex[:10]
    output_dir = project_directory(project_id) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_label = f"EP{ep_no:02d}" if ep_no > 0 else "全集"
    output_name = f"{episode_label}_成片_{export_id}.mp4"
    output_path = output_dir / output_name

    options=p.generation_settings or {}
    ratio=options.get('aspect_ratio') or (p.outline.aspect_ratio if p.outline else '9:16')
    resolution=options.get('resolution') or '720P'
    width,height=_output_dimensions(ratio,resolution)
    parts_dir=output_dir / f'.parts_{export_id}'
    if not parts_dir.resolve().is_relative_to(output_dir.resolve()):
        raise HTTPException(500,'临时导出目录无效')
    original_status = p.status
    p.status = "producing"
    db.commit()
    try:
        parts_dir.mkdir()
        try:
            normalized=[]
            for index,(path,shot,has_audio) in enumerate(file_list):
                part=parts_dir / f'{index:04d}.mp4'
                duration=float(shot.duration)
                cmd=[FFMPEG,'-y','-i',str(path)]
                if not has_audio: cmd += ['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']
                video_filter=f'[0:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.25,trim=duration={duration:g},fps=24,scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,format=yuv420p[v]'
                audio_source='0:a' if has_audio else '1:a'
                audio_filter=f'[{audio_source}]asetpts=PTS-STARTPTS,apad,atrim=duration={duration:g},aresample=48000[a]'
                cmd += ['-filter_complex',video_filter+';'+audio_filter,'-map','[v]','-map','[a]',
                        '-c:v','libx264','-preset','medium','-crf','18','-r','24',
                        '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{duration:g}',str(part)]
                result=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
                if result.returncode: raise HTTPException(500,f'EP{shot.episode_no} #{shot.shot_no} 规格统一失败：{result.stderr[-400:]}')
                normalized.append(part)
            concat_list=parts_dir/'concat.txt'
            with concat_list.open('w',encoding='utf-8') as listing:
                for part in normalized: listing.write(f"file '{part.as_posix()}'\n")
            result=subprocess.run([FFMPEG,'-y','-f','concat','-safe','0','-i',str(concat_list),
                                   '-c','copy','-movflags','+faststart',str(output_path)],
                                  capture_output=True,text=True,timeout=300)
            if result.returncode: raise HTTPException(500,f'成片拼接失败：{result.stderr[-400:]}')
            actual,_=_media_info(output_path)
            planned=sum(shot.duration for _,shot,_ in file_list)
            if abs(actual-planned)>max(0.5,0.04*len(file_list)):
                raise HTTPException(500,f'成片时长校验失败：计划{planned:g}秒，实际{actual:.2f}秒')
        except subprocess.TimeoutExpired:
            raise HTTPException(500, "导出超时，请减少本次导出镜头或降低分辨率")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"导出异常: {e}")
        finally:
            shutil.rmtree(parts_dir, ignore_errors=True)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        current = db.get(Project, project_id)
        if current:
            current.status = original_status
            db.commit()

    return {
        "project_id": project_id,
        "ep_no": ep_no,
        "file_count": len(file_list),
        "url": f"/storage/projects/{project_id}/exports/{output_name}",
        "output": str(output_path),
    }
