import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User as UserSchema, Bot as BotSchema, Task as TaskSchema, Order as OrderSchema

app = FastAPI(title="ShopBot SaaS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utilities
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


def serialize_doc(doc: Dict[str, Any]):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Convert any nested ObjectIds
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc


@app.get("/")
def root():
    return {"message": "ShopBot SaaS Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(db, "name", "✅ Connected")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Simple auth placeholder (MVP - email only, no passwords)
class EmailSignup(BaseModel):
    email: str
    name: Optional[str] = None


@app.post("/api/auth/signup")
def signup(payload: EmailSignup):
    # Upsert by email
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        return serialize_doc(existing)
    user = UserSchema(email=payload.email, name=payload.name)
    user_id = create_document("user", user)
    created = db["user"].find_one({"_id": ObjectId(user_id)})
    return serialize_doc(created)


# Bots CRUD
@app.get("/api/bots")
def list_bots(user_id: str):
    docs = get_documents("bot", {"user_id": user_id})
    return [serialize_doc(d) for d in docs]


@app.post("/api/bots")
def create_bot(bot: BotSchema):
    bot_id = create_document("bot", bot)
    created = db["bot"].find_one({"_id": ObjectId(bot_id)})
    return serialize_doc(created)


@app.put("/api/bots/{bot_id}")
def update_bot(bot_id: str, updates: Dict[str, Any]):
    if not ObjectId.is_valid(bot_id):
        raise HTTPException(status_code=400, detail="Invalid bot id")
    result = db["bot"].find_one_and_update(
        {"_id": ObjectId(bot_id)}, {"$set": {**updates, "updated_at": __import__("datetime").datetime.utcnow()}}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Bot not found")
    return serialize_doc(result)


@app.delete("/api/bots/{bot_id}")
def delete_bot(bot_id: str):
    if not ObjectId.is_valid(bot_id):
        raise HTTPException(status_code=400, detail="Invalid bot id")
    db["bot"].delete_one({"_id": ObjectId(bot_id)})
    return {"ok": True}


# Retailer adapters (MVP: public search shims)
SUPPORTED_RETAILERS = ["amazon", "walmart", "bestbuy", "target", "shopify"]


@app.get("/api/retailers")
def retailers():
    return {"supported": SUPPORTED_RETAILERS}


class SearchQuery(BaseModel):
    query: str
    retailer: Optional[str] = None
    limit: int = 5


@app.post("/api/search")
def search_products(payload: SearchQuery):
    retailer = (payload.retailer or "amazon").lower()
    if retailer not in SUPPORTED_RETAILERS:
        raise HTTPException(status_code=400, detail="Unsupported retailer")

    # Stubbed search results. In production, integrate real APIs/scrapers or affiliates.
    items = [
        {
            "retailer": retailer,
            "title": f"{payload.query} - Option {i+1}",
            "price": round(19.99 + i * 5.25, 2),
            "rating": round(4.2 - i * 0.1, 2),
            "url": f"https://{retailer}.example.com/product/{i+1}",
            "image": "https://via.placeholder.com/300x200.png?text=Product",
        }
        for i in range(min(payload.limit, 8))
    ]
    return {"results": items}


# Tasks
class CreateTask(BaseModel):
    user_id: str
    bot_id: str
    prompt: str


@app.post("/api/tasks")
def create_task(payload: CreateTask):
    bot = db["bot"].find_one({"_id": ObjectId(payload.bot_id)}) if ObjectId.is_valid(payload.bot_id) else None
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    candidates = search_products(SearchQuery(query=payload.prompt, retailer=(bot.get("retailers") or ["amazon"])[0], limit=5))["results"]

    task = TaskSchema(
        user_id=payload.user_id,
        bot_id=payload.bot_id,
        prompt=payload.prompt,
        status="awaiting_approval",
        candidates=candidates,
        logs=["Task created", f"Searched {len(candidates)} candidates"],
    )
    task_id = create_document("task", task)
    created = db["task"].find_one({"_id": ObjectId(task_id)})
    return serialize_doc(created)


@app.get("/api/tasks")
def list_tasks(user_id: str, bot_id: Optional[str] = None):
    filter_q: Dict[str, Any] = {"user_id": user_id}
    if bot_id:
        filter_q["bot_id"] = bot_id
    docs = get_documents("task", filter_q, limit=50)
    return [serialize_doc(d) for d in docs]


class ApproveSelection(BaseModel):
    task_id: str
    index: int


@app.post("/api/tasks/approve")
def approve_selection(payload: ApproveSelection):
    if not ObjectId.is_valid(payload.task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    task = db["task"].find_one({"_id": ObjectId(payload.task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    candidates: List[Dict[str, Any]] = task.get("candidates", [])
    if payload.index < 0 or payload.index >= len(candidates):
        raise HTTPException(status_code=400, detail="Invalid candidate index")

    selection = candidates[payload.index]
    updated = db["task"].find_one_and_update(
        {"_id": ObjectId(payload.task_id)},
        {"$set": {"selection": selection, "status": "succeeded"}},
        return_document=True,
    )
    return serialize_doc(updated)


# ACP stubs - define the action schema and stub endpoints
@app.get("/api/acp/actions")
def acp_actions():
    return {
        "actions": [
            {
                "name": "search_products",
                "description": "Search for products by query across supported retailers",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "retailer": {"type": "string"}}},
            },
            {
                "name": "get_product",
                "description": "Get product details by URL or ID",
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
            },
            {
                "name": "add_to_cart",
                "description": "Add a product to cart for a specific retailer",
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "quantity": {"type": "integer"}}},
            },
            {
                "name": "start_checkout",
                "description": "Begin checkout flow (human approval in MVP)",
                "parameters": {"type": "object", "properties": {"cart_id": {"type": "string"}}},
            },
        ]
    }


class AcpInvoke(BaseModel):
    action: str
    arguments: Dict[str, Any] = {}


@app.post("/api/acp/invoke")
def acp_invoke(payload: AcpInvoke):
    # Route to internal functions. In a real integration, wire with OpenAI ACP.
    if payload.action == "search_products":
        q = payload.arguments.get("query", "")
        retailer = payload.arguments.get("retailer")
        return search_products(SearchQuery(query=q, retailer=retailer, limit=5))
    elif payload.action == "get_product":
        url = payload.arguments.get("url")
        if not url:
            raise HTTPException(status_code=400, detail="url required")
        # Stub product detail
        return {
            "product": {
                "title": "Sample Product",
                "price": 29.99,
                "url": url,
                "images": ["https://via.placeholder.com/640x480.png?text=Product"],
                "specs": {"brand": "Demo", "warranty": "1y"},
            }
        }
    elif payload.action == "add_to_cart":
        return {"cart_id": "demo-cart-123", "status": "added"}
    elif payload.action == "start_checkout":
        return {"checkout": "manual-approval-required", "status": "pending"}
    else:
        raise HTTPException(status_code=400, detail="Unknown action")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
