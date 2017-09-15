from pymongo import MongoClient


def connect_db():
    client = MongoClient('mongodb://localhost:27017')
    db = client['vss']
    return db
