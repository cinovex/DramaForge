"""统一画幅、生成模式与参考图绑定，预览和实际提交共用同一组装逻辑。"""
import re
from typing import Literal
from pydantic import BaseModel, Field
from models.drama import Project, Character, Scene, Prop
from services.gpt_service import GPTError
from services.agnes_video_service import _to_public_reference
from services.media_host import can_inline_video_image
from services.settings_service import get_stage_config

Ratio = Literal['21:9','16:9','4:3','1:1','3:4','9:16']
class ReferenceChoice(BaseModel):
    kind: Literal['character','scene','prop']
    id: int = Field(gt=0)
    variant: str = Field(default='base',pattern=r'^(base|front|side|back|three_quarter|turnaround|detail_sheet|expressions|expression_\d+)$')
class GenerationOptions(BaseModel):
    aspect_ratio: Ratio | None = None
    resolution: Literal['720P','1080P','1K','2K'] | None = None
    model: str | None = Field(default=None,max_length=120)
    mode: Literal['auto','text','keyframe','reference'] = 'auto'
    references: list[ReferenceChoice] | None = Field(default=None,max_length=8)

def effective_options(project, shot=None):
    defaults = {'aspect_ratio': project.outline.aspect_ratio if project.outline else '9:16','resolution':'720P','mode':'auto','references':None}
    defaults.update({k:v for k,v in (project.generation_settings or {}).items() if v is not None})
    if shot: defaults.update({k:v for k,v in (shot.generation_settings or {}).items() if v is not None})
    return defaults

def format_prompt(text, ratio):
    # 清除旧的画幅限定，追加唯一权威的用户选定画幅，避免横竖提示矛盾。
    text = re.sub(r'(?:21:9|16:9|4:3|1:1|3:4|9:16)\s*(?:竖屏|横屏|竖构图|横构图|构图|画幅|比例)?','',text or '')
    text = re.sub(r'竖屏|横屏|竖构图|横构图','所选画幅构图',text)
    w,h=map(int,ratio.split(':'))
    return text + f'\n输出画幅：{ratio}（{"竖屏" if w<h else "横屏" if w>h else "方形"}），按此比例组织人物、机位和场景构图，不添加黑边或画框。'

def reference_items(db,project,shot,options):
    choices=options.get('references')
    required=[{'kind':'character','id':c.id,'variant':'base'} for c in project.characters if c.name in (shot.character_names or [])]
    scene=next((s for s in project.scenes if s.name==shot.scene_name),None)
    if scene: required.append({'kind':'scene','id':scene.id,'variant':'base'})
    if choices is None:
        choices=required
    else:
        if not choices: raise GPTError('不能清空本镜头的角色和场景参考图',400)
        choices=[*choices,*(item for item in required if not any(
            choice['kind']==item['kind'] and choice['id']==item['id'] for choice in choices))]
    if len(choices)>8: raise GPTError('本镜头参考图超过8张，请拆分镜头或减少额外参考',400)
    output=[]
    for choice in choices:
        cls={'character':Character,'scene':Scene,'prop':Prop}[choice['kind']]
        item=db.query(cls).filter_by(id=choice['id'],project_id=project.id).first()
        if not item: raise GPTError('参考资产不属于当前项目',400)
        if choice['kind']!='character' and choice.get('variant','base')!='base':
            raise GPTError('场景与道具目前只支持主参考图',400)
        url=(item.base_image_url if choice.get('variant','base')=='base' else (item.reference_images or {}).get(choice['variant'],'')) if choice['kind']=='character' else item.image_url
        output.append({**choice,'name':item.name,'url':url or '', 'public_url':_to_public_reference(url,db)})
    return output

def compile_generation(db,project,shot,model=None,strict=True):
    warnings=[]
    from api.shots import _build_prompt
    opts=effective_options(project,shot)
    cfg=get_stage_config(db,'video') or {}
    chosen_model=model or opts.get('model') or cfg.get('model','agnes-video-2.5')
    if strict and chosen_model.endswith('-flash') and opts['resolution']!='720P':
        raise GPTError('当前 Flash 视频模型仅支持720P，请选择720P或切换支持更高分辨率的模型',400)
    if opts['mode'] in ('auto','reference'):
        known_characters={character.name for character in project.characters}
        unknown_characters=set(shot.character_names or [])-known_characters
        unknown_scene=shot.scene_name and not any(scene.name==shot.scene_name for scene in project.scenes)
        if unknown_characters or unknown_scene:
            absent='、'.join([*sorted(unknown_characters),*([shot.scene_name] if unknown_scene else [])])
            message=f'分镜中的角色或场景没有对应参考资产：{absent}。请先修正资产名称或生成参考资产'
            if strict: raise GPTError(message,400)
            warnings.append(message)
    if opts.get('references') == [] and not strict:
        warnings.append('不能清空本镜头的角色和场景参考图；预览仍显示自动绑定结果')
        opts['references']=None
    candidates=reference_items(db,project,shot,opts)
    if opts['mode'] in ('auto','reference') and any(not r['url'] for r in candidates):
        missing='、'.join(r['name'] for r in candidates if not r['url'])
        if strict: raise GPTError(f'参考资产尚未生成：{missing}。请先生成角色与场景参考图',400)
        warnings.append(f'请先生成参考图：{missing}；否则无法按角色与场景一致性生成')
    existing=[r for r in candidates if r['url']]
    mode=opts['mode']
    public_keyframe=_to_public_reference(shot.keyframe_url,db) if shot.keyframe_url else None
    usable_keyframe = bool(public_keyframe or can_inline_video_image(shot.keyframe_url))
    if mode=='auto':
        # Agnes does not accept images and first_frame in the same request.
        # Honor an explicit reference selection; otherwise use a usable keyframe
        # first because it was itself generated from the shot's character/scene refs.
        if opts.get('references') is not None and existing:
            mode='reference'
        elif usable_keyframe:
            mode='keyframe'
        elif existing:
            mode='reference'
        else:
            mode='text'
    refs=[];frame=None
    if mode=='keyframe':
        frame=public_keyframe or (shot.keyframe_url if can_inline_video_image(shot.keyframe_url) else None)
        if not frame:
            if strict: raise GPTError('首帧模式需要可访问的关键帧，请先生成本镜头关键帧',400)
            warnings.append('请先生成本镜头关键帧，以绑定视频首帧')
        refs=[{'kind':'keyframe','id':shot.id,'name':'本镜头首帧','url':shot.keyframe_url,'public_url':frame,'token':'首帧'}]
    elif mode=='reference':
        if not existing:
            if strict: raise GPTError('图片参考模式需要参考图，请生成或选择角色、场景参考图',400)
            warnings.append('请生成或选择角色、场景参考图')
        for r in existing:
            inline_ready = can_inline_video_image(r['url'])
            if not r['public_url'] and not inline_ready:
                if strict: raise GPTError(f'参考图“{r["name"]}”缺少提供商原图地址，请重新生成该参考图或关键帧',400)
                warnings.append(f'“{r["name"]}”没有可用的公网地址或本地图片文件')
            refs.append({**r,'token':f'<Picture {len(refs)+1}>'})
    chars=[c for c in project.characters if c.name in (shot.character_names or [])]
    scene=next((s for s in project.scenes if s.name==shot.scene_name),None)
    prompt=format_prompt(_build_prompt(shot,scene,chars,opts['aspect_ratio']),opts['aspect_ratio'])
    prompt+=f'\n视频输出分辨率档位：{opts["resolution"]}；时长：{shot.duration}秒。'
    if mode=='keyframe': prompt+='\n以绑定首帧为开场构图，保持首帧中的人物身份、服装和场景布局；依照上述动作与表演推进。'
    if mode=='reference':
        prompt+='\n参考图绑定：\n'+'\n'.join(f'{r["token"]} = {r["name"]}（{"角色身份与服装" if r["kind"]=="character" else "场景空间与灯光" if r["kind"]=="scene" else "道具外观"}参考），保持对应主体一致。' for r in refs)
    return {**opts,'warnings':warnings,'mode':mode,'prompt':prompt,'references':refs,'first_frame':frame,'model':chosen_model}

def generation_manifest(generation: dict) -> dict:
    """冻结本次实际使用的角色/场景版本，便于跨集追溯与重做。"""
    return {'model':generation['model'],'mode':generation['mode'],
            'aspect_ratio':generation['aspect_ratio'],'resolution':generation['resolution'],
            'references':[{key:r.get(key) for key in ('kind','id','name','variant','url','public_url','token')}
                          for r in generation['references']],
            'first_frame':generation.get('first_frame'),'prompt':generation['prompt']}
