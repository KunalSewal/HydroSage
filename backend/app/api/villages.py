from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/villages", tags=["villages"])


@router.get("")
def list_villages():
    raise HTTPException(status_code=501, detail="not implemented yet")


@router.get("/{village_id}/elevation")
def get_elevation(village_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
