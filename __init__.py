from flask import Flask
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect

from .frontend import frontend
from .nav import nav


def create_app():
    app = Flask('vss')
    app.config.from_object({
      'MONGO_DBNAME': 'vss',
    })

    Bootstrap(app)
    CSRFProtect(app)
    app.config['SECRET_KEY'] = 'verysecret'

    app.register_blueprint(frontend)
    nav.init_app(app)

    return app
