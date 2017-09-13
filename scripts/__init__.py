from flask import g
from pymongo import MongoClient

from ..constants import MONGO_DBNAME

def connect_db():
    client = MongoClient('mongodb://localhost:27017')
    db = client[MONGO_DBNAME]
    return db

def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'mongo_db'):
        g.mongo_db = connect_db()
    return g.mongo_db
