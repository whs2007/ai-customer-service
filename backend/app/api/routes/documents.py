"""文档接口（08 §6.2 / 04 §3）：上传、列表、详情、删除、重新解析。"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.pipeline.parser import get_allowed_extensions, get_max_upload_size
from app.pipeline.scanner import scan_file, sniff_content
from app.schemas.knowledge import DocumentOut, UploadDocumentOut
from app.services import document_service, knowledge_service

router = APIRouter(tags=["documents"])


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=ResponseModel[PageData[DocumentOut]],
)
async def list_documents(
    kb_id: uuid.UUID,
    keyword: str | None = Query(default=None, max_length=100, description="文件名关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await knowledge_service.ensure_kb_accessible(db, kb_id, user)
    items, total = await document_service.list_documents(
        db, kb_id, keyword=keyword, page=page, page_size=page_size
    )
    return ok(
        data=PageData[DocumentOut](
            items=[DocumentOut.model_validate(doc) for doc in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=ResponseModel[UploadDocumentOut],
)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """上传文档（multipart）：校验扩展名与大小，登记后异步解析（08 §3.2 数据流）。"""
    kb = await knowledge_service.get_knowledge_base(db, kb_id)
    file_name = file.filename or ""
    ext = Path(file_name).suffix.lower()
    allowed_extensions = get_allowed_extensions()
    if ext not in allowed_extensions:
        raise BadRequestError(
            f"不支持的文件类型：{ext}（支持：{', '.join(sorted(allowed_extensions))}）"
        )

    content = await file.read()
    max_size = get_max_upload_size()
    if len(content) > max_size:
        raise BadRequestError(
            f"文件大小不能超过 {max_size // (1024 * 1024)}MB"
        )
    if not content:
        raise BadRequestError("文件内容为空")
    # 内容嗅探：拒绝伪装扩展名（08 §8 上传安全）
    if not sniff_content(ext, content):
        raise BadRequestError("文件内容与扩展名不匹配，疑似伪装文件")

    settings = get_settings()
    storage_dir = Path(settings.storage_dir).resolve()  # noqa: ASYNC240 - 纯路径解析，无阻塞 IO
    target_dir = storage_dir / str(kb.id)  # noqa: ASYNC240 - 纯路径计算，无阻塞 IO
    await asyncio.to_thread(  # noqa: ASYNC240 - 已移出事件循环，规则无法识别 to_thread
        target_dir.mkdir, parents=True, exist_ok=True
    )
    file_path = target_dir / f"{uuid.uuid4().hex}{ext}"
    # 阻塞 IO 移出事件循环（08 §10：async 路径不做阻塞写）
    await asyncio.to_thread(file_path.write_bytes, content)

    # 恶意文件扫描（可插拔，默认关闭；接入点见 pipeline/scanner.py）
    scan_result = scan_file(file_path, ext.lstrip("."))
    if not scan_result.ok:
        file_path.unlink(missing_ok=True)
        raise BadRequestError(scan_result.reason)

    doc = await document_service.create_document_record(
        db, kb_id, file_name, len(content), str(file_path)
    )
    background_tasks.add_task(document_service.process_document_job, str(doc.id))
    return ok(
        data=UploadDocumentOut(
            document_id=doc.id,
            file_name=doc.file_name,
            status=doc.status,
        ),
        message="上传成功，正在解析",
    )


@router.get("/documents/{doc_id}", response_model=ResponseModel[DocumentOut])
async def get_document(
    doc_id: uuid.UUID,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    doc = await document_service.get_document(db, doc_id)
    await knowledge_service.ensure_kb_accessible(db, doc.kb_id, user)
    return ok(data=DocumentOut.model_validate(doc))


@router.delete("/documents/{doc_id}", response_model=ResponseModel)
async def delete_document(
    doc_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await document_service.delete_document(
        db, doc_id, user, ip=request.client.host if request.client else None
    )
    return ok(message="删除成功")


@router.post("/documents/{doc_id}/reparse", response_model=ResponseModel[DocumentOut])
async def reparse_document(
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    doc = await document_service.reparse_document(db, doc_id)
    background_tasks.add_task(document_service.process_document_job, str(doc.id))
    return ok(data=DocumentOut.model_validate(doc), message="已开始重新解析")
