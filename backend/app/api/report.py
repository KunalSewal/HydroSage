from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["report"])


@router.get("/{village_id}/report")
def get_report(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
