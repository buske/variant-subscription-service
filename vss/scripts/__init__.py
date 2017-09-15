from pymongo import MongoClient

from .. import app

def connect_db():
    dbname = app.config['MONGO_DBNAME']
    port = app.config['MONGO_PORT']
    client = MongoClient('mongodb://localhost:{}'.format(port))
    db = client[dbname]
    return db
