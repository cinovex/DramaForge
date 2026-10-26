"""Durable analysis units and cooperative pause at saved task boundaries."""
from datetime import datetime
from urllib.parse import urlsplit
from services.gpt_service import executionConfig


class analysisPaused(Exception):
    pass


def readAnalysisState(db, project):
    db.expire(project, ["analysis_state"])
    return dict(project.analysis_state or {})


def checkAnalysisPause(db, project):
    if readAnalysisState(db, project).get("pauseRequested"):
        raise analysisPaused()


def recordAnalysisUnit(db, project, key, label, status, error=""):
    state = readAnalysisState(db, project)
    units = dict(state.get("units") or {})
    unit = {**units.get(key, {}), "id": key, "label": label, "status": status,
            "updatedAt": datetime.utcnow().isoformat(), "error": error}
    if status == "running":
        cfg = executionConfig.get() or {}
        unit.update(attempts=unit.get("attempts", 0) + 1,
                    source={"provider": cfg.get("provider", ""), "model": cfg.get("model", ""),
                            "host": urlsplit(cfg.get("base_url", "")).hostname or "", "configRevision": cfg.get("configRevision", "")})
    units[key] = unit
    project.analysis_state = {**state, "units": units}


def splitAnalysisScript(text, limit=6000):
    import re
    # ACT: explicit episode headings define episodes; unmarked scripts remain one episode.
    headings = list(re.finditer(r"(?im)^[ \t]*(?:第(?P<cn>[零〇一二三四五六七八九十百0-9]+)集|episode[ \t]+(?P<en>\d+))(?:[ \t]*[:：][^\n]*|[ \t]+[^\n]+|[ \t]*\r?$)", text))
    def episodeNumber(heading):
        number = heading.group("cn") or heading.group("en")
        if number.isdigit(): return int(number)
        digits = {word: index for index, word in enumerate("零一二三四五六七八九")}
        digits["〇"] = 0
        total, digit = 0, 0
        for word in number:
            if word in digits: digit = digits[word]
            else:
                total += (digit or 1) * {"十": 10, "百": 100}[word]
                digit = 0
        return total + digit
    blocks = []
    if headings:
        numbers = [episodeNumber(heading) for heading in headings]
        if any(number < 1 for number in numbers) or numbers != sorted(set(numbers)):
            from services.gpt_service import GPTError
            raise GPTError("剧本分集标题重复或顺序不清，请整理分集标记后再分析；现有成果保留", 400)
        prefix = text[:headings[0].start()]
        for index, heading in enumerate(headings):
            end = headings[index+1].start() if index+1 < len(headings) else len(text)
            blocks.append(((prefix if index == 0 else "") + text[heading.start():end], numbers[index]))
    else:
        blocks = [(text, 1)]
    plan = []
    for block, episode in blocks:
        while block.strip():
            end = len(block) if len(block) <= limit else block.rfind("\n", limit//2, limit)
            if end <= 0: end = min(limit, len(block))
            plan.append({"episode": episode, "text": block[:end]})
            block = block[end:]
    return plan
