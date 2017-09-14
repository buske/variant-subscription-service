#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import logging

from datetime import datetime
from flask import Blueprint, g
from base64 import urlsafe_b64encode

from .constants import DEFAULT_GENOME_BUILD, DEFAULT_NOTIFICATION_PREFERENCES, UNKNOWN
from .extensions import mongo
from .services.mailer import build_mail, send_mail
from .clinvar import parse_clinvar_category
from .utils import deep_get

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

backend = Blueprint('backend', __name__)

DEFAULT_RANDOM_BYTES = 36
# Must be a multiple of 3 to ensure there are no = in the URL
assert DEFAULT_RANDOM_BYTES % 3 == 0

# DEFAULT_BCRYPT_ROUNDS = 12
VARIANT_PART_DELIMITER = '-'


def make_variant_key(build, chrom, pos, ref, alt):
    return '-'.join([build, chrom, pos, ref, alt])


def get_variant_category(doc):
    return deep_get(doc, 'clinvar.current.category', UNKNOWN)


def build_variant_doc(build, chrom, pos, ref, alt,
                      variation_id=None,
                      clinical_significance=None, gold_stars=None,
                      review_status=None, last_evaluated=None,
                      **kwargs):
    key = make_variant_key(build, chrom, pos, ref, alt)

    variant = {
        # Basic variant information
        'build': build,
        'chrom': chrom,
        'pos': pos,
        'ref': ref,
        'alt': alt,
    }

    clinvar = {}
    if variation_id:
        clinvar['variation_id'] = variation_id

    if clinical_significance:
        clinvar['current'] = {
            'category': parse_clinvar_category(clinical_significance),
            'clinical_significance': clinical_significance,
            'gold_stars': gold_stars,
            'review_status': review_status,
            'last_evaluated': last_evaluated,
        }
        clinvar['history'] = []

    return {
        '_id': key,
        'variant': variant,
        'clinvar': clinvar,
        'subscribers': [],  # list of user_ids
        'tags': {},  # user_id -> tag
    }


def create_token():
    # standin for python secrets library which was only released in 3.6
    randbytes = os.urandom(DEFAULT_RANDOM_BYTES)
    token = str(urlsafe_b64encode(randbytes), 'utf-8')
    return token


def reset_user_token(db, user):
    new_token = create_token()
    logging.info('Reset token for user: {}'.format(user['email']))
    db.users.update_one({ '_id': user['_id'] }, { '$set': { 'token': new_token } })
    return new_token


def create_user(db, email):
    token = create_token()
    result = db.users.insert_one({
        'email': email,
        'token': token,
        'joined_at': datetime.utcnow(),
        'last_emailed': None,
        'is_active': True,
        'slack': None,
        'notification_preferences': DEFAULT_NOTIFICATION_PREFERENCES,
    })
    user_id = result.inserted_id
    return user_id, token


def subscribe_to_variants(db, user_id, variant_ids):
    logger.debug('Subscribing to {} variants'.format(len(variant_ids)))
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$addToSet': { 'subscribers': user_id } })
    num_subscribed = result.modified_count
    logger.info('Subscribed to {} new variants'.format(num_subscribed))
    return num_subscribed


def tag_variants(db, user_id, tag, variant_ids):
    logger.debug('Tagging {} variants'.format(len(variant_ids)))
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$set': { 'tags.{}'.format(user_id): tag } })
    num_tagged = result.modified_count
    logger.info('Tagged {} variants'.format(num_tagged))
    return num_tagged


def find_or_create_variants(db, genome_build, variant_strings):
    variant_docs = []
    for variant_string in variant_strings:
        chrom, pos, ref, alt = variant_string.split(VARIANT_PART_DELIMITER)
        key = make_variant_key(genome_build, chrom, pos, ref, alt)
        # TODO: normalize this here or in form validation
        variant = db.variants.find_one({ '_id': key })
        if variant:
            logger.debug('Found variant: {}'.format(key))
        else:
            logger.debug('Could not find variant: {}'.format(variant_string))
            # Create variant
            variant = build_variant_doc(genome_build, chrom, pos, ref, alt)
            result = db.variants.insert_one(variant)
            if result.inserted_id != variant['_id']:
                logger.error('Error creating variant: {}'.format(variant))
            logger.debug('Created new variant doc: {}'.format(variant))

        variant_docs.append(variant)

    return variant_docs


def subscribe(db, email, variant_strings, tag=None, genome_build=DEFAULT_GENOME_BUILD, notifier=None):
    user = db.users.find_one({ 'email': email })
    # Create user if they don't exist
    if user is None:
        logger.debug('User not found: {}'.format(email))
        user_id, token = create_user(db, email)
        logger.debug('Created user: {}'.format(user_id))
    else:
        logger.debug('Found user: {}'.format(user))
        user_id = user['_id']
        try:
            token = user['token']
        except KeyError:
            token = reset_user_token(db, user)

    # Subscribe to variants
    variant_docs = find_or_create_variants(db, genome_build, variant_strings)
    variant_ids = [variant['_id'] for variant in variant_docs]
    num_subscribed = subscribe_to_variants(db, user_id, variant_ids)
    if tag:
        num_tagged = tag_variants(db, user_id, tag, variant_ids)

    # Send update email
    if num_subscribed > 0 and notifier:
        notifier.notify_of_subscription(user_id, num_subscribed)

    return num_subscribed


def authenticate(token):
    """Given a token, return user data or None if not valid"""
    db = mongo.db
    return db.users.find_one({ 'token': token })


def get_stats():
    db = mongo.db
    # Get number of variants with subscribers
    subscribed_variants = db.variants.count({ 'subscribers': { '$exists': True, '$ne': [] } })
    return {
        'subscribed_variants': subscribed_variants,
    }


def set_user_slack_data(user, slack_data):
    db = mongo.db
    logger.debug('Setting user slack data: {}'.format(slack_data))
    user_id = deep_get(user, '_id')
    ok = deep_get(slack_data, 'ok')
    if user_id and ok:
        return db.users.update_one({ '_id': user['_id'] }, { '$set': { 'slack': slack_data } })


def remove_user_slack_data(user):
    db = mongo.db
    user_id = deep_get(user, '_id')
    logger.debug('Removing user slack data: {}'.format(user_id))
    if user_id:
        return db.users.update_one({ '_id': user['_id'] }, { '$set': { 'slack': None } })


def suspend_notifications(user):
    db = mongo.db
    user_id = deep_get(user, '_id')
    logger.debug('Suspending user notifications: {}'.format(user_id))
    if user_id:
        return db.users.update_one({ '_id': user['_id'] }, { '$set': { 'notification_preferences.notify_emails': False, 'notification_preferences.notify_slack': False } })


def delete_user(user):
    db = mongo.db
    user_id = deep_get(user, '_id')
    logger.debug('Deleting user: {}'.format(user_id))
    if user_id:
        # Remove variant subscriptions
        result = db.variants.update_many({ 'subscribers': user_id }, { '$pull': { 'subscribers': user_id } })
        logger.debug('Unsubscribed from {} variants'.format(result.modified_count))
        # Remove variant tags
        tag_field = 'tags.{}'.format(user_id)
        result = db.variants.update_many({ tag_field: { '$exists': True } }, { '$unset': { tag_field: '' } })
        logger.debug('Removed tags from {} variants'.format(result.modified_count))
        # Remove account last
        return db.users.delete_one({ '_id': user['_id'] })


def set_preferences(user, form):
    db = mongo.db
    assert user['_id']
    form_fields = [
        'unknown_to_benign',
        'vus_to_benign',
        'path_to_benign',

        'unknown_to_vus',
        'benign_to_vus',
        'path_to_vus',

        'unknown_to_path',
        'benign_to_path',
        'vus_to_path',

        'notify_emails',
        'notify_slack',
    ]
    notification_preferences = dict([(field, form[field].data) for field in form_fields])
    logger.debug('Setting notification preferences: {}'.format(notification_preferences))
    return db.users.update_one({ '_id': user['_id'] }, { '$set': { 'notification_preferences': notification_preferences } })
