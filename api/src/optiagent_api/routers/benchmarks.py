from fastapi import APIRouter, HTTPException

from optiagent_eval.report import SUMMARY, Summary

router = APIRouter(prefix="/api/v1", tags=["benchmarks"])


@router.get("/benchmarks", response_model=Summary)
def benchmarks() -> Summary:
    if not SUMMARY.exists():
        raise HTTPException(404, "No benchmark summary yet. Run: python -m optiagent_eval.report")
    return Summary.model_validate_json(SUMMARY.read_text(encoding="utf-8"))
