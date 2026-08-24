from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["rainfall"])


@router.get("/{village_id}/rainfall")
def get_rainfall(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
