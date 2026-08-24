from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["satellite"])


@router.get("/{village_id}/satellite")
def get_satellite(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
