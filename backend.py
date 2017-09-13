#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import logging

from datetime import datetime
from flask import Blueprint, g
from base64 import urlsafe_b64encode

from .constants import DEFAULT_GENOME_BUILD
from .extensions import mongo
from .services.mailer import build_mail, send_mail
from .clinvar import parse_clinvar_category

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
            {
                'category': parse_clinvar_category(clinical_significance),
                'clinical_significance': clinical_significance,
                'gold_stars': gold_stars,
                'review_status': review_status,
                'last_evaluated': last_evaluated,
            },
        }
        clinvar['history'] = []

    return {
        '_id': key,
        'variant': variant,
        'clinvar': clinvar,
        'subscribers': [],
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
        'notification_preferences': {
            'unknown_to_benign': True,
            'vus_to_benign': True,
            'path_to_benign': True,

            'unknown_to_vus': True,
            'benign_to_vus': True,
            'path_to_vus': True,

            'unknown_to_path': True,
            'benign_to_path': True,
            'vus_to_path': True,
        }
    })
    user_id = result.inserted_id
    return user_id, token


def subscribe_to_variants(db, user_id, variant_ids):
    logger.debug('Subscribing to {} variants'.format(len(variant_ids)))
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$addToSet': { 'subscribers': user_id } })
    num_subscribed = result.modified_count
    logger.info('Subscribed to {} new variants'.format(num_subscribed))
    return num_subscribed


def send_subscription_email(db, user_id, user_email, token, num_subscribed, total_subscribed):

    account_url = 'http://127.0.0.1:5000/login?t={}'.format(token)

    # send welcome email
    subject = "🙌  Subscribed to {} variants".format(num_subscribed)
    body = """
You're now subscribed to {} new variants

You're subscribed to a total of {} variants

Manage your account here: {}
""".format(num_subscribed, total_subscribed, account_url)

    logger.debug('Sending subscription email to: {}'.format(user_email))
    mail = build_mail(user_email, subject, body)
    send_mail(mail)
    logger.info('Sent subscription email to: {}'.format(user_email))


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


def subscribe(db, email, variant_strings, genome_build=DEFAULT_GENOME_BUILD):
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

    # Send update email
    if num_subscribed > 0:
        total_subscribed = db.variants.count({ 'subscribers': user_id })
        send_subscription_email(db, user_id, email, token, num_subscribed, total_subscribed)

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
    assert user['_id']
    return db.users.update({ '_id': user['_id'] }, { '$set': { 'slack', slack_data } })
