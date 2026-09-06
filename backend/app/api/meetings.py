"""会议 API 路由"""
import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_meeting_or_404
from app.models.meeting import Meeting
from app.schemas.meeting import MeetingCreate, MeetingUpdate, MeetingResponse, TranscriptResponse, TranscriptionStatusResponse
from app.services.meeting_service import meeting_service
router = APIRouter(prefix='/meetings', tags=['会议管理'])

@router.post('', response_model=MeetingResponse, status_code=201)
async def create_meeting(data: MeetingCreate, db: AsyncSession=Depends(get_db)) -> Meeting:
    """创建会议"""
    return await meeting_service.create_meeting(db, data)

@router.get('', response_model=list[MeetingResponse])
async def list_meetings(page: int=Query(1, ge=1), page_size: int=Query(20, ge=1, le=100), db: AsyncSession=Depends(get_db)) -> list[Meeting]:
    """获取会议列表"""
    skip = (page - 1) * page_size
    meetings, _ = await meeting_service.list_meetings(db, skip=skip, limit=page_size)
    return meetings

@router.get('/{meeting_id}', response_model=MeetingResponse)
async def get_meeting(meeting: Meeting=Depends(get_meeting_or_404)) -> Meeting:
    """获取会议详情"""
    return meeting

@router.patch('/{meeting_id}', response_model=MeetingResponse)
async def update_meeting(data: MeetingUpdate, db: AsyncSession=Depends(get_db), meeting: Meeting=Depends(get_meeting_or_404)) -> Meeting:
    """更新会议"""
    updated = await meeting_service.update_meeting(db, meeting.id, data)
    return updated

@router.delete('/{meeting_id}', status_code=204)
async def delete_meeting(db: AsyncSession=Depends(get_db), meeting: Meeting=Depends(get_meeting_or_404)) -> None:
    """删除会议"""
    await meeting_service.delete_meeting(db, meeting.id)
