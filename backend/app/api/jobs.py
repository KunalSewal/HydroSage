from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job_status(job_id: str):
    raise HTTPException(status_code=501, detail="not implemented yet")
