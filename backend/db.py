import os
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/delivery_ops")
DB_NAME = "delivery_ops"

_sync_client: MongoClient = None
_async_client: AsyncIOMotorClient = None


def get_db():
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(MONGO_URI)
    return _sync_client[DB_NAME]


def get_async_db():
    global _async_client
    if _async_client is None:
        _async_client = AsyncIOMotorClient(MONGO_URI)
    return _async_client[DB_NAME]


def serialize_doc(doc: dict) -> dict:
    if doc is None:
        return None
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d


def serialize_docs(docs) -> list:
    return [serialize_doc(d) for d in docs]
