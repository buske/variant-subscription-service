# This contains our frontend; since it is a bit messy to use the @app.route
# decorator style when using application factories, all of our routes are
# inside blueprints. This is the front-facing blueprint.
#
# You can find out more about blueprints at
# http://flask.pocoo.org/docs/blueprints/

from flask import Blueprint, render_template, flash, redirect, url_for
from flask_nav.elements import Navbar, View, Subgroup, Link, Text, Separator
from markupsafe import escape
import logging

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger("frontend")
logger.setLevel(logging.DEBUG)

from .forms import *
from .nav import nav

frontend = Blueprint('frontend', __name__)

nav.register_element('frontend_top', Navbar(
    View('VSS', '.index'),
    View('Home', '.index'),
    View('New variant', '.signup_form'),
    View('Login', '.login_form'),
    # View('Debug-Info', 'debug.debug_root'),
    ))


@frontend.route('/')
def index():
    import random
    num_variants = random.randint(1000, 5000)  # get_number_of_variants()
    return render_template('index.html', num_variants=num_variants)


@frontend.route('/my_variants/')
def my_variants():
    return render_template('my_variants.html')


@frontend.route('/signup/', methods=('GET', 'POST'))
def signup_form():
    form = SignupForm()

    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    if form.validate_on_submit():
        flash('Hello, {}. You have successfully signed up'
              .format(escape(form.eula.data)))
        return redirect(url_for('.index'))

    return render_template('signup.html', form=form)


@frontend.route('/login/', methods=('GET', 'POST'))
def login_form():
    form = LoginForm()

    if form.validate_on_submit():
        flash('Hello, {}. You have successfully signed up'
              .format(escape(form.email.data)))
        return redirect(url_for('.my_variants'))

    return render_template('login.html', form=form)
