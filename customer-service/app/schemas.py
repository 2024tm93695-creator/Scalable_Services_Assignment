"""Pydantic schemas for Customer Service"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, constr

KYCStatus = Literal["PENDING", "VERIFIED", "REJECTED"]

class CustomerCreate(BaseModel):
    name:       str      = Field(..., min_length=1, max_length=100, examples=["Priya Sharma"])
    email:      EmailStr = Field(..., examples=["priya.sharma@example.com"])
    phone:      constr(min_length=10, max_length=15) = Field(..., examples=["9876543210"])
    kyc_status: KYCStatus = Field("PENDING", description="Initial KYC state; defaults to PENDING")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Priya Sharma",
                "email": "priya.sharma@example.com",
                "phone": "9876543210",
                "kyc_status": "PENDING",
            }
        }
    }

class CustomerUpdate(BaseModel):
    name:  Optional[str]       = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr]  = None
    phone: Optional[str]       = Field(None, min_length=10, max_length=15)

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Priya Sharma Reddy", "phone": "9000000001"}
        }
    }

class CustomerResponse(BaseModel):
    customer_id: int
    name:        str
    email:       str
    phone:       str
    kyc_status:  KYCStatus
    created_at:  datetime
    model_config = {"from_attributes": True}

class KYCUpdate(BaseModel):
    kyc_status: KYCStatus = Field(..., description="Target KYC state")

    model_config = {
        "json_schema_extra": {"example": {"kyc_status": "VERIFIED"}}
    }

class KYCResponse(BaseModel):
    customer_id: int
    kyc_status:  KYCStatus
    updated_at:  datetime
    model_config = {"from_attributes": True}

class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Customer not found"])
