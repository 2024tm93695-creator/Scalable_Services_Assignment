"""KYC management endpoints"""
import json
import logging
import os
from typing import Annotated

import aio_pika
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError, before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.db import get_db
from app.metrics import KYC_CHANGES
from app.models import Customer
from app.schemas import ErrorResponse, KYCResponse, KYCUpdate

router = APIRouter(tags=["KYC"])
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
logger = logging.getLogger("customer-svc")

DB = Annotated[AsyncSession, Depends(get_db)]
_NOT_FOUND = "Customer not found"
_404 = {404: {"model": ErrorResponse, "description": _NOT_FOUND}}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)
async def _publish_with_retry(payload: dict) -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=5)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "banking.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="banking.KYCStatusUpdated",
        )


async def publish_kyc_event(customer_id: int, old_status: str, new_status: str) -> None:
    payload = {"customer_id": customer_id, "old_status": old_status, "new_status": new_status}
    try:
        await _publish_with_retry(payload)
    except RetryError:
        # All 3 attempts failed — log and continue; DB update already committed
        logger.error(
            "KYCStatusUpdated event dropped after retries",
            extra={"customer_id": customer_id},
        )


@router.patch(
    "/customers/{customer_id}/kyc",
    response_model=KYCResponse,
    summary="Update KYC status",
    description=(
        "Transitions a customer's KYC state. Valid values: `PENDING`, `VERIFIED`, `REJECTED`. "
        "A `KYCStatusUpdated` event is published to RabbitMQ on success."
    ),
    responses={**_404, 422: {"description": "Invalid kyc_status value"}},
)
async def update_kyc(customer_id: int, body: KYCUpdate, db: DB):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, _NOT_FOUND)
    old_status = customer.kyc_status
    customer.kyc_status = body.kyc_status
    await db.commit()
    await db.refresh(customer)
    KYC_CHANGES.labels("customer-svc", body.kyc_status).inc()
    await publish_kyc_event(customer_id, old_status, body.kyc_status)
    return customer


@router.get(
    "/customers/{customer_id}/kyc",
    response_model=KYCResponse,
    summary="Get KYC status",
    responses=_404,
)
async def get_kyc(customer_id: int, db: DB):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, _NOT_FOUND)
    return customer
