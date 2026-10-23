def updateAnalysisProgress(db, project, message, phase, completed=0, total=0, counts=None):
    state = {**(project.analysis_state or {}), "progress": message, "phase": phase,
             "completed": completed, "total": total}
    if counts is not None:
        state["counts"] = counts
    project.analysis_state = state
    db.commit()
