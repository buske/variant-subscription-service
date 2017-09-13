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
from slackclient import SlackClient
import os

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger("frontend")
logger.setLevel(logging.DEBUG)

from .forms import *
from .extensions import mongo, nav
from .backend import authenticate, get_stats, subscribe, set_user_slack_data

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
    stats = get_stats()
    return render_template('index.html', stats=stats)


@frontend.route('/about/')
def about():
    return render_template('about.html')


@frontend.route('/account/', methods=('GET', 'POST'))
@frontend.route('/account/<user>', methods=('GET', 'POST'))
def account(user=None):
    form = PreferencesForm()

    logger.debug('Data: %s', user)
    logger.debug('Payload: %s', request.args)
    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)

    slack_code = request.args.get('code', '')
    if slack_code:
        sc = SlackClient('')

        # Request the auth tokens from Slack
        auth_response = sc.api_call(
            "oauth.access",
            client_id=os.environ.get('SLACK_CLIENT_ID', ''),
            client_secret=os.environ.get('SLACK_CLIENT_SECRET', ''),
            code=slack_code
        )
        logger.debug('Slack auth response: {}'.format(auth_response))
        set_user_slack_data(user, auth_response)

    return render_template('account.html', form=form, user=user)


@frontend.route('/signup/', methods=('GET', 'POST'))
def signup_form():
    form = SignupForm()

    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    if form.validate_on_submit():
        logger.debug('Email: {}'.format(form.email.data))
        logger.debug('Variant: {}'.format(form.chr_pos_ref_alt.data))
        num_subscribed = subscribe(mongo.db, form.email.data, [form.chr_pos_ref_alt.data])
        if num_subscribed > 0:
            flash('Success! Subscribed to {} new variants'.format(num_subscribed))
        else:
            flash('Already subscribed to those variants')
        return redirect(url_for('.index'))

    return render_template('signup.html', form=form)


def validate_and_get_token_data(x):
    return {
        'email': 'a@a.com',
        'preferences': '',
        'slack': ''
    }


def email_token(email):
    return True


@frontend.route('/login', methods=('GET', 'POST'))
def login():
    form = LoginForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            email_status = email_token(form.email.data)
            if email_status:
                flash('Success! Click the link in the email sent to {}'.format(escape(form.email.data)))
            else:
                flash('Error sending email to {}. Please contact the sysadmin'.format(escape(form.email.data)))
            return redirect(url_for('.index'))
    else:
        token = request.args.get('t', '')
        if token:
            user = authenticate(token)
            if user:
                logger.debug('Data: %s', user)
                return account(user)
            else:
                flash('Wrong credentials. Please ensure the link is correct, or request a new token')
    return render_template('login.html', form=form)
