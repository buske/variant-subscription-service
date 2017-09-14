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
from flask import Blueprint, render_template, flash, redirect, url_for, request, session, g
from flask_nav.elements import Navbar, View, Subgroup, Link, Text, Separator
from markupsafe import escape
from slackclient import SlackClient

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger("frontend")
logger.setLevel(logging.DEBUG)

from .forms import *
from .extensions import mongo, nav
from .services.notifier import SubscriptionNotifier
from .backend import authenticate, delete_user, get_stats, remove_user_slack_data, subscribe, set_user_slack_data, set_preferences, get_user_subscribed_variants

frontend = Blueprint('frontend', __name__)


def top_nav():
    navbar_items = [
        View('VSS', '.index'),
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
        navbar_items.append(View('Login', '.login'))
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


@frontend.route('/account/', methods=('GET', 'POST'))
@protected
def account():
    user = g.user
    form = PreferencesForm(data=user.get('notification_preferences'))
    remove_slack_form = RemoveSlackForm()
    delete_form = DeleteForm()

    variants = get_user_subscribed_variants(user)
    logger.debug('Variants: %s', variants)
    if not variants:
        num_variants = 0
        variants_form = None
    else:
        num_variants = variants['total']
        for variant in variants['data']:
            v = variant['variant']
            v_id = '-'.join([v['chrom'], v['pos'], v['ref'], v['alt']])
            if 'tags' in variant and str(user['_id']) in variant['tags']:
                v_id += ' ({})'.format(variant['tags'][str(user['_id'])])
            if 'clinvar' in variant:
                v_id += ' - Current ClinVar status: {}'.format(variant['clinvar'])
            setattr(VariantForm, variant['_id'], BooleanField(v_id))
        variants_form = VariantForm()
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
            client_id=os.environ.get('SLACK_CLIENT_ID', ''),
            client_secret=os.environ.get('SLACK_CLIENT_SECRET', ''),
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

    if form.validate_on_submit():
        logger.debug('Deleting variants: {}'.format(form.data))
        success = unsubscribe(user, form)
        if success:
            flash('Success! Preferences updated.', category='success')

    return render_template('account.html', form=form, user=user, variants_form=variants_form, num_variants=num_variants,
                           remove_slack_form=remove_slack_form, delete_form=delete_form)


@frontend.route('/subscribe/', methods=('GET', 'POST'))
def subscribe_form():
    form = SignupForm()

    logger.debug('Validated: %s', form.validate_on_submit())
    logger.debug('Errors: %s', form.errors)
    if form.validate_on_submit():
        logger.debug('Email: {}'.format(form.email.data))
        logger.debug('Variant: {}'.format(form.chr_pos_ref_alt.data))
        logger.debug('Tag: {}'.format(form.tag.data))
        notifier = SubscriptionNotifier(mongo.db)
        num_subscribed = subscribe(mongo.db, form.email.data, [form.chr_pos_ref_alt.data], tag=form.tag.data, notifier=notifier)
        if num_subscribed > 0:
            flash('Subscribed to {} new variants'.format(num_subscribed), category='success')
        else:
            flash('Already subscribed to those variants', category='warning')
        return redirect(url_for('.index'))

    return render_template('subscribe.html', form=form)


@frontend.route('/logout', methods=('GET', 'POST'))
def logout():
    form = LogoutForm()
    if request.method == 'POST':
        g.user = None
        session['token'] = None
        return redirect(url_for('.index'))

    return render_template('logout.html', form=form)
