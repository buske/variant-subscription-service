from pymongo import MongoClient

from ..constants import MONGO_DBNAME

def connect_db():
    client = MongoClient('mongodb://localhost:27017')
    db = client[MONGO_DBNAME]
    return db
