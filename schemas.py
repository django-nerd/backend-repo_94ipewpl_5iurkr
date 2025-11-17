"""
Database Schemas for Shopping Bot SaaS

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercase class name (e.g., User -> "user").
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal, Dict, Any


class User(BaseModel):
    """Users collection schema"""
    email: EmailStr = Field(..., description="Email address")
    name: Optional[str] = Field(None, description="Display name")
    plan: Literal["free", "pro", "enterprise"] = Field("free", description="Subscription plan")
    is_active: bool = Field(True, description="Whether the user is active")


class Bot(BaseModel):
    """Bots configured by users to perform shopping tasks"""
    user_id: str = Field(..., description="Owner user id")
    name: str = Field(..., description="Bot display name")
    goals: Optional[str] = Field(None, description="Bot high-level goal or description")
    retailers: List[str] = Field(default_factory=list, description="Allowed retailers")
    constraints: Dict[str, Any] = Field(
        default_factory=lambda: {"budget": None, "max_price": None, "approval_mode": "manual"},
        description="Constraints such as budget, max price, and approval mode",
    )
    model: Optional[str] = Field(None, description="Model identifier or ACP model config")
    acp_config: Dict[str, Any] = Field(default_factory=dict, description="ACP specific configuration")


class Task(BaseModel):
    """A single shopping run initiated by a user/bot"""
    user_id: str = Field(..., description="Owner user id")
    bot_id: str = Field(..., description="Bot used for the run")
    prompt: str = Field(..., description="User request or shopping criteria")
    status: Literal["queued", "running", "succeeded", "failed", "awaiting_approval"] = Field(
        "queued", description="Current status of the task"
    )
    candidates: List[Dict[str, Any]] = Field(default_factory=list, description="Candidate products")
    selection: Optional[Dict[str, Any]] = Field(None, description="Selected product")
    logs: List[str] = Field(default_factory=list, description="Log messages for the run")


class Order(BaseModel):
    """Represents a checkout/order flow - MVP keeps it optional/manual"""
    task_id: str = Field(..., description="Associated task id")
    retailer: Optional[str] = None
    status: Literal["created", "approved", "purchased", "failed"] = "created"
    total: Optional[float] = None
    external_ids: Dict[str, Any] = Field(default_factory=dict)
    receipts: List[Dict[str, Any]] = Field(default_factory=list)


class RetailerAccount(BaseModel):
    """Optional per-user retailer credentials (not used in MVP purchasing)"""
    user_id: str
    retailer: str
    credentials: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["unverified", "verified", "error"] = "unverified"
