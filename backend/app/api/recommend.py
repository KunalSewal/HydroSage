from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["recommend"])


@router.post("/{village_id}/recommend")
def enqueue_recommendation(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
