from flask import Flask
from flask_bootstrap import Bootstrap

def create_app():
    app = Flask('vss')
    app.config.from_object({
      'MONGO_DBNAME': 'vss',
    })

    Bootstrap(app)

    return app
