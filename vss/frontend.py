#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This contains our frontend; since it is a bit messy to use the @app.route
# decorator style when using application factories, all of our routes are
# inside blueprints. This is the front-facing blueprint.
#
# You can find out more about blueprints at
# http://flask.pocoo.org/docs/blueprints/

import os
import logging

from functools import wraps
from flask import Blueprint, render_template, flash, redirect, url_for, request, session, g, current_app
from flask_nav.elements import Navbar, View
from slackclient import SlackClient

from wtforms.validators import ValidationError

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger("frontend")
logger.setLevel(logging.DEBUG)

from .forms import *
from .extensions import mongo, nav
from .services.notifier import SubscriptionNotifier, ResendTokenNotifier
from .backend import authenticate, delete_user, get_stats, get_user_subscribed_variants, \
    remove_user_slack_data, subscribe, set_user_slack_data, set_preferences, \
    suspend_notifications, unsubscribe
from .utils import deep_get

frontend = Blueprint('frontend', __name__)


def top_nav():
    navbar_items = [
        View(current_app.config.get('APP_NAME', 'VSS'), '.index'),
        View('Home', '.index'),
        View('About', '.about'),
        View('Subscribe', '.subscribe_form'),
    ]
    if g.get('user'):
        navbar_items.extend([
            View('Account', '.account'),
            View('Logout', '.logout')
        ])
    else:
        navbar_items.extend([
            View('Login', '.login')
        ])
    return Navbar(*navbar_items)

nav.register_element('frontend_top', top_nav)


def do_login(token):
    if token:
        user = authenticate(token)
        if user:
            logger.debug('User logged in: {}'.format(user['email']))
            session['token'] = token
            g.user = user
            return user
        else:
            session['token'] = ''
            g.user = None


# If there is a session cookie with the token, resolve to a user object
@frontend.before_request
def fetch_user():
    token = request.args.get('t')
    if token:
        logger.debug('Found token in URL')
    elif session.get('token'):
        logger.debug('Found token in session')
        token = session.get('token')

    if token:
        user = do_login(token)
        if user:
            # Store user in request context and session
            g.user = user
            session['token'] = token
        else:
            flash('Wrong credentials. Please ensure the link is correct, or request a new token', category='danger')


def protected(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.get('user'):
            # Already logged in
            return f(*args, **kwargs)
        else:
            flash('You must be logged in to view this page', category='danger')
            return redirect(url_for('.login'))

    return decorated_function


@frontend.route('/')
def index():
    stats = get_stats()
    return render_template('index.html', stats=stats)


@frontend.route('/about/')
def about():
    return render_template('about.html')


@frontend.route('/account/delete/', methods=('GET', 'POST'))
@protected
def delete_account():
    user = g.user
    logger.debug('Deleting: %s', user)
    success = delete_user(user)
    if success:
        flash('Your account has been deleted! Now leave.', category='info')
    else:
        flash('Error deleting account', category='danger')

    return redirect(url_for('.index'))


@frontend.route('/account/silence/', methods=('GET', 'POST'))
@protected
def silence_account():
    user = g.user
    logger.debug('Silencing: %s', user)
    success = suspend_notifications(user)
    if success:
        flash('Your notifications have been silenced!', category='info')
    else:
        flash('Error silencing notifications', category='danger')

    return redirect(url_for('.account'))


@frontend.route('/account/remove_slack/', methods=('GET', 'POST'))
@protected
def remove_slack_from_account():
    user = g.user
    logger.debug('Removing Slack integration from: %s', user)
    success = remove_user_slack_data(user)
    if success:
        flash('Slack integration removed!', category='success')
    else:
        flash('Error removing Slack integration 😢', category='danger')
    return redirect(url_for('.account'))


@frontend.route('/account/update/', methods=('GET', 'POST'))
@protected
def update_preferences():
    user = g.user
    form = PreferencesForm(data=user.get('notification_preferences'))

    if form.validate_on_submit():
        logger.debug('Setting preferences: {}'.format(form.data))
        success = set_preferences(user, form)
        if success:
            flash('Success! Preferences updated.', category='success')
    return redirect(url_for('.account'))


def create_variants_form(user):
    variants = get_user_subscribed_variants(user)
    logger.debug('Variants: %s', variants)
    if variants:
        class CustomVariantForm(VariantForm):
            pass

        for variant in variants['data']:
            v = variant['variant']
            v_id = '-'.join([v['chrom'], v['pos'], v['ref'], v['alt']])

            user_id = str(user['_id'])
            tag = deep_get(variant, 'tags.{}'.format(user_id))
            category = deep_get(variant, 'clinvar.current.category')
            gold_stars = deep_get(variant, 'clinvar.current.gold_stars')

            if tag:
                v_id += ' ({})'.format(tag)
            if category:
                try:
                    stars = int(gold_stars)
                except:
                    stars = 0
                v_id += ': {} {}'.format(category, ' '.join(['⭐'] * stars))

            setattr(CustomVariantForm, variant['_id'], BooleanField(v_id))

        return CustomVariantForm()
    else:
        return None


@frontend.route('/account/', methods=('GET', 'POST'))
@protected
def account():
    user = g.user
    form = PreferencesForm(data=user.get('notification_preferences'))
    remove_slack_form = RemoveSlackForm()
    delete_form = DeleteForm()
    silence_form = SilenceForm()
    variants_form = create_variants_form(user)

    slack_client_id = current_app.config.get('SLACK_CLIENT_ID', '')
    slack_client_secret = current_app.config.get('SLACK_CLIENT_SECRET', '')
    logger.debug('Slack client ID: {}'.format(slack_client_id))
    logger.debug('Data: %s', user)
    logger.debug('Payload: %s', request.args)
    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    logger.debug('User: %s', user)

    slack_code = request.args.get('code', '')
    if slack_code:
        sc = SlackClient('')

        # Request the auth tokens from Slack
        auth_response = sc.api_call(
            "oauth.access",
            client_id=slack_client_id,
            client_secret=slack_client_secret,
            code=slack_code
        )
        logger.debug('Slack auth response: {}'.format(auth_response))
        success = set_user_slack_data(user, auth_response)
        if success:
            flash('Slack successfully connected!', category='success')
            # Update current user data to ensure render is up-to-date
            user['slack'] = auth_response
        else:
            flash('Error connecting slack', category='danger')

    if variants_form.validate_on_submit():
        logger.debug('Deleting variants: {}'.format(variants_form.data))
        num_unsubscribed = unsubscribe(user, variants_form)
        if num_unsubscribed > 0:
            flash('Unsubscribed from {} variants'.format(num_unsubscribed), category='success')
            # Regenerate variants form
            variants_form = create_variants_form(user)

    return render_template('account.html', form=form, user=user, variants_form=variants_form,
                           remove_slack_form=remove_slack_form, delete_form=delete_form, silence_form=silence_form)


@frontend.route('/subscribe/', methods=('GET', 'POST'))
def subscribe_form():
    email = ''
    user = g.get('user')
    if user:
        email = user.get('email')

    form = SignupForm(data={'email': email})

    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    if form.validate_on_submit():
        variant_string = form.variant.data
        logger.debug('Email: {}'.format(form.email.data))
        logger.debug('Variant: {}'.format(form.variant.data))
        logger.debug('Tag: {}'.format(form.tag.data))
        notifier = SubscriptionNotifier(mongo.db, current_app.config)
        num_subscribed = subscribe(mongo.db, form.email.data, [form.variant.data], tag=form.tag.data, notifier=notifier)
        if num_subscribed > 0:
            flash('Subscribed to {} new variants'.format(num_subscribed), category='success')
        else:
            flash('Already subscribed to those variants', category='warning')
        return redirect(url_for('.index'))

    return render_template('subscribe.html', form=form)


@frontend.route('/login', methods=('GET', 'POST'))
def login():
    form = LoginForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            email = form.email.data
            notifier = ResendTokenNotifier(mongo.db, current_app.config)
            success = notifier.resend_token(email)
            if success:
                flash('Sent! Please check your email for a login link', category='success')
            else:
                flash('Error sending email', category='danger')

    return render_template('login.html', form=form)


@frontend.route('/logout', methods=('GET', 'POST'))
def logout():
    form = LogoutForm()
    if request.method == 'POST':
        g.user = None
        session['token'] = None
        return redirect(url_for('.index'))

    return render_template('logout.html', form=form)
