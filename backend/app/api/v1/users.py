"""User API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.user import (
    UserResponse,
    UserDetailResponse,
    UserListResponse,
    UserListItemResponse,
    BanHistoryListResponse,
    UserUpdate,
    BanUserRequest,
    UnbanUserRequest,
    UserSearchParams
)
from app.schemas.common import Response
from app.services.user_service import UserService
from app.config import settings

router = APIRouter()


@router.get("/users", response_model=Response[UserListResponse])
async def get_users(
    uid: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    displayname: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    wallet_address: Optional[str] = Query(None),
    tel: Optional[str] = Query(None),
    status: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user list with search and pagination.

    - **uid**: Filter by user ID
    - **username**: Filter by username
    - **displayname**: Filter by display name
    - **email**: Filter by email
    - **wallet_address**: Filter by wallet address
    - **tel**: Filter by telephone
    - **status**: Filter by status (all, active, banned)
    - **page**: Page number
    - **page_size**: Items per page (max 100)
    - **sort_by**: Sort field
    - **sort_order**: Sort order (asc/desc)
    """
    params = UserSearchParams(
        user_id=uid,
        username=username or displayname,
        email=email,
        phone_number=tel,
        wallet_address=wallet_address,
        status=None if status == "all" else status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    user_service = UserService(db)
    result = await user_service.get_users(params)

    return Response(data=result)


@router.get("/users/{uid}", response_model=Response[UserDetailResponse])
async def get_user_detail(
    uid: str = Path(..., description="User ID (e.g., 'BhqB31UxCNa')"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user detail by ID.

    Returns complete user information including:
    - User basic info
    - Author profile (if exists)
    - Wallet information
    - Active ban records
    """
    user_service = UserService(db)
    user = await user_service.get_user_detail(uid)
    return Response(data=user)


@router.get("/users/{uid}/ban-history", response_model=Response[BanHistoryListResponse])
async def get_user_ban_history(
    uid: str = Path(..., description="User ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get ban/unban history for a user."""
    user_service = UserService(db)
    history = await user_service.get_ban_history(uid, page, page_size)
    return Response(data=history)


@router.put("/users/{uid}", response_model=Response[UserResponse])
async def update_user(
    uid: str = Path(..., description="User ID (e.g., 'BhqB31UxCNa')"),
    user_data: UserUpdate = None,
    db: AsyncSession = Depends(get_db),
):
    """Update user information."""
    if user_data is None:
        raise HTTPException(status_code=400, detail="No update payload provided")

    user_service = UserService(db)
    user = await user_service.update_user(uid, user_data)
    return Response(data=user, message="User updated successfully")


@router.post("/users/{uid}/ban", response_model=Response[dict])
async def ban_user(
    uid: str = Path(..., description="User ID"),
    ban_data: BanUserRequest = None,
    role: str = Query("write", description="Operation role"),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth from Bearer token
):
    """
    Ban user account.

    - **uid**: User ID (e.g., 'BhqB31UxCNa')
    - **reason**: Ban reason
    - **duration**: Ban duration in seconds
    - **role**: Operation role (default: write)

    After banning, user's status will be set to 'banned'.
    """
    operator_id = settings.DEFAULT_OPERATOR_ID
    if not operator_id:
        raise HTTPException(status_code=500, detail="DEFAULT_OPERATOR_ID not configured")

    user_service = UserService(db)
    await user_service.ban_user(uid, ban_data, operator_id)

    return Response(message="User banned successfully")


@router.post("/users/{uid}/unban", response_model=Response[dict])
async def unban_user(
    uid: str = Path(..., description="User ID"),
    unban_data: UnbanUserRequest = None,
    role: str = Query("write", description="Operation role"),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth from Bearer token
):
    """
    Unban user account.

    - **uid**: User ID (e.g., 'BhqB31UxCNa')
    - **role**: Operation role (default: write)

    After unbanning, user's status will be set to 'active'.
    """
    operator_id = settings.DEFAULT_OPERATOR_ID
    if not operator_id:
        raise HTTPException(status_code=500, detail="DEFAULT_OPERATOR_ID not configured")

    user_service = UserService(db)
    await user_service.unban_user(uid, unban_data, operator_id)

    return Response(message="User unbanned successfully")
