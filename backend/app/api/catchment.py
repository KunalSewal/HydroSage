from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["catchment"])


@router.post("/{village_id}/catchment")
def enqueue_catchment(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
