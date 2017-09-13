# This contains our frontend; since it is a bit messy to use the @app.route
# decorator style when using application factories, all of our routes are
# inside blueprints. This is the front-facing blueprint.
#
# You can find out more about blueprints at
# http://flask.pocoo.org/docs/blueprints/

from flask import Blueprint, render_template, flash, redirect, url_for, request
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
    View('About', '.about'),
    View('New variant', '.signup_form'),
    View('Login', '.login'),
    ))


@frontend.route('/')
def index():
    import random
    num_variants = random.randint(1000, 5000)  # get_number_of_variants()
    return render_template('index.html', num_variants=num_variants)


@frontend.route('/about/')
def about():
    return render_template('about.html')


@frontend.route('/account/')
def account():
    form = PreferencesForm()

    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    if form.validate_on_submit():

        return redirect(url_for('.index'))

    return render_template('account.html', form=form)


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


def validate_and_get_token_data(x):
    return True


@frontend.route('/login', methods=('GET', 'POST'))
def login():
    form = LoginForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            return redirect(url_for('.login'))
    else:
        token = request.args.get('t', '')
        if token:
            data = validate_and_get_token_data(token)
            if data:
                return render_template('account.html')
            else:
                flash('Wrong credentials. Please ensure the link is correct, or request a new token')
    return render_template('login.html', form=form)