from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])


@router.get("/")
async def test_api():
    """
    Test API endpoint that returns a simple message.
    """
    return {"message": "Test API is working successfully!"}

