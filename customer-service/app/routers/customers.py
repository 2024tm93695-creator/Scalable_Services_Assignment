"""Customer CRUD endpoints"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Customer
from app.schemas import CustomerCreate, CustomerUpdate, CustomerResponse, ErrorResponse, KYCStatus
from app.metrics import CUSTOMER_REGISTRATIONS, DUPLICATE_EMAIL_REJECTIONS

router = APIRouter(tags=["Customers"])

DB = Annotated[AsyncSession, Depends(get_db)]
_NOT_FOUND = "Customer not found"
_404 = {404: {"model": ErrorResponse, "description": _NOT_FOUND}}
_409 = {409: {"model": ErrorResponse, "description": "Email already registered"}}

@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=201,
    summary="Register a new customer",
    description="Creates a customer record. Email must be unique across all customers. KYC defaults to PENDING.",
    responses={**_409, 422: {"description": "Validation error"}},
)
async def create_customer(body: CustomerCreate, db: DB):
    existing = await db.scalar(select(Customer).where(Customer.email == body.email))
    if existing:
        DUPLICATE_EMAIL_REJECTIONS.labels("customer-svc").inc()
        raise HTTPException(409, "Email already registered")
    customer = Customer(**body.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    CUSTOMER_REGISTRATIONS.labels("customer-svc").inc()
    return customer

@router.get(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Fetch a customer by ID",
    responses=_404,
)
async def get_customer(customer_id: int, db: DB):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, _NOT_FOUND)
    return customer

@router.put(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Update customer profile",
    description="Partial update — only supplied fields are changed.",
    responses=_404,
)
async def update_customer(customer_id: int, body: CustomerUpdate, db: DB):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, _NOT_FOUND)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return customer

@router.delete(
    "/customers/{customer_id}",
    status_code=204,
    summary="Delete a customer",
    responses=_404,
)
async def delete_customer(customer_id: int, db: DB):
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, _NOT_FOUND)
    await db.delete(customer)
    await db.commit()

@router.get(
    "/customers",
    response_model=list[CustomerResponse],
    summary="List customers",
    description="Returns a paginated list of customers. Filter by KYC status using the `kyc_status` query param.",
)
async def list_customers(
    db: DB,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Records per page"),
    kyc_status: KYCStatus | None = Query(None, description="Filter by KYC status"),
):
    stmt = select(Customer)
    if kyc_status:
        stmt = stmt.where(Customer.kyc_status == kyc_status)
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    return result.scalars().all()
