"""
Transaction upload and analysis triggers.

CSV uploads enqueue work for the expense / budget / fraud agents via Kafka.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from agents.messaging import AgentEventPublisher, get_event_publisher
from agents.orchestrator import FinanceOrchestrator
from api.deps import get_db_session
from api.schemas.common import MessageResponse
from core.config import get_settings

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/upload", response_model=MessageResponse)
async def upload_transactions_csv(
    file: Annotated[UploadFile, File(description="Bank or card export CSV")],
    user_external_id: Annotated[str, Form(description="Stable user id from your auth system")],
    db: Session = Depends(get_db_session),
    publisher: AgentEventPublisher = Depends(get_event_publisher),
) -> MessageResponse:
    """
    Accept a CSV file, persist raw path metadata, and publish an agent event.

    Full parsing and persistence of rows belongs in a background worker;
    this endpoint demonstrates the API → Kafka → agents flow.
    """
    settings = get_settings()
    raw_name = file.filename or f"upload-{datetime.utcnow().isoformat()}.csv"
    payload = {
        "type": "transaction.csv_uploaded",
        "user_external_id": user_external_id,
        "filename": raw_name,
        "content_type": file.content_type,
    }
    orchestrator = FinanceOrchestrator(db=db, publisher=publisher)
    await orchestrator.on_csv_uploaded(payload)
    await publisher.publish(
        settings.kafka_topic_transactions,
        key=user_external_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
    )
    return MessageResponse(message=f"Accepted {raw_name}; agents notified.")


@router.post("/analyze-sample", response_model=MessageResponse)
async def analyze_sample(
    user_external_id: Annotated[str, Form()],
    db: Session = Depends(get_db_session),
    publisher: AgentEventPublisher = Depends(get_event_publisher),
) -> MessageResponse:
    """Trigger a demo multi-agent analysis (no file) for UI smoke tests."""
    orchestrator = FinanceOrchestrator(db=db, publisher=publisher)
    summary = await orchestrator.run_sample_pipeline(user_external_id)
    return MessageResponse(message=summary)
