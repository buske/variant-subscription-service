from flask import Flask
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect

from .constants import MONGO_DBNAME
from .backend import backend
from .frontend import frontend
from .extensions import mongo, nav

def create_app():
    app = Flask('vss', instance_relative_config=True)

    app.config.from_object('config')
    app.config.from_pyfile('config.py')

    register_blueprints(app)
    register_extensions(app)

    return app

def register_blueprints(app):
    app.register_blueprint(frontend)
    app.register_blueprint(backend)

def register_extensions(app):
    Bootstrap(app)
    CSRFProtect(app)
    mongo.init_app(app)
    nav.init_app(app)

app = create_app()
