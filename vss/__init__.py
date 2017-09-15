import os
import logging

from flask import Flask
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect

from .backend import backend
from .frontend import frontend
from .extensions import mongo, nav

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def create_app():
    app = Flask('vss')

    app.config.from_object('config')
    # Override with config file pointed to by VSS_SETTING environment variable, if set
    settings_file = os.environ.get('VSS_SETTINGS')
    if settings_file:
        logger.debug('VSS_SETTINGS: {!r}'.format(settings_file))
        app.config.from_envvar('VSS_SETTINGS')

    register_blueprints(app)
    register_extensions(app)

    logger.debug('Created app with config:')
    logger.debug('BASE_URL: {!r}'.format(app.config['BASE_URL']))
    logger.debug('SLACK_CLIENT_ID: {!r}'.format(app.config['SLACK_CLIENT_ID']))

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
