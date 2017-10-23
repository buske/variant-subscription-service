#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import logging

from copy import deepcopy
from datetime import datetime
from flask import Blueprint, g
from base64 import urlsafe_b64encode
from pymongo import ASCENDING, DESCENDING, InsertOne, ReplaceOne

from .constants import DEFAULT_GENOME_BUILD, DEFAULT_NOTIFICATION_PREFERENCES, UNKNOWN
from .extensions import mongo
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


def unsubscribe_from_variants(db, user_id, variant_ids):
    logger.debug('Unsubscribing from {} variants'.format(len(variant_ids)))
    # Unsubscribe
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$pull': { 'subscribers': user_id } })
    num_unsubscribed = result.modified_count
    # Remove tags
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$unset': { 'tags.{}'.format(user_id): '' } })
    logger.info('Unsubscribed from {} new variants'.format(num_unsubscribed))
    return num_unsubscribed


def tag_variants(db, user_id, tag, variant_ids):
    logger.debug('Tagging {} variants'.format(len(variant_ids)))
    result = db.variants.update_many({ '_id': { '$in': variant_ids } }, { '$set': { 'tags.{}'.format(user_id): tag } })
    num_tagged = result.modified_count
    logger.info('Tagged {} variants'.format(num_tagged))
    return num_tagged


def get_variant_by_clinvar_id(db, clinvar_id):
    logger.error('Finding variant by clinvar id: {!r}'.format(clinvar_id))
    result = db.variants.find_one({ 'clinvar.variation_id': clinvar_id })
    logger.error('Result: {!r}'.format(result))
    return result


def find_or_create_variants(db, genome_build, variant_strings):
    variant_docs = []
    for variant_string in variant_strings:
        if variant_string.count(VARIANT_PART_DELIMITER) == 3:
            chrom, pos, ref, alt = variant_string.split(VARIANT_PART_DELIMITER)
            key = make_variant_key(genome_build, chrom, pos, ref, alt)
            # TODO: normalize this here or in form validation
            variant = db.variants.find_one({ '_id': key })
        else:
            clinvar_id = variant_string
            variant = get_variant_by_clinvar_id(db, clinvar_id)
            # Cannot subscribe to variant by clinvar id if it isn't in clinvar
            # Should have been validated upstream
            assert variant

        if variant:
            logger.debug('Found variant: {}'.format(variant['_id']))
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


def unsubscribe(user, form):
    db = mongo.db
    user_id = user.get('_id')
    assert user_id

    ignored_fields = ['csrf_token', 'remove']
    variant_ids = []
    for variant_id, should_unsubscribe in form.data.items():
        if variant_id in ignored_fields or not should_unsubscribe:
            continue
        variant_ids.append(variant_id)

    num_unsubscribed = unsubscribe_from_variants(db, user_id, variant_ids)
    return num_unsubscribed


def authenticate(token):
    """Given a token, return user data or None if not valid"""
    db = mongo.db
    user = db.users.find_one({ 'token': token })
    return user


def get_stats():
    db = mongo.db
    # Get number of variants with subscribers
    subscribed_variants = db.variants.count({ 'subscribers': { '$exists': True, '$ne': [] } })
    last_updated_doc = db.updates.find_one({}, sort=[('finished_at', DESCENDING)])
    last_updated = last_updated_doc.get('finished_at') if last_updated_doc else None
    return {
        'subscribed_variants': subscribed_variants,
        'last_updated': last_updated,
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


def get_user_subscribed_variants(user):
    db = mongo.db
    user_id = deep_get(user, '_id')
    logger.debug('Getting variants for user: {}'.format(user_id))
    if user_id:
        limit = 100
        results = db.variants.find({ 'subscribers': user_id }, limit=limit, sort=[('_id', ASCENDING)])
        return {
            'count': results.count(True),
            'total': results.count(False),
            'data': list(results),
        }


def merge_docs(old_doc, new_doc):
    merged_clinvar = {}
    had_clinvar_data = bool(old_doc['clinvar'])
    if had_clinvar_data:
        # Variant had existing clinvar, so we might notify
        old_data = old_doc['clinvar']['current']
        new_data = new_doc['clinvar']['current']
        # Append to history
        history = old_doc['clinvar']['history']
        history.append(old_data)
        # Set new annotation data
        merged_clinvar['current'] = new_data
        merged_clinvar['history'] = history
        merged_clinvar['variation_id'] = new_doc['clinvar']['variation_id']
    else:
        # Add clinvar data to existing subscribed variant
        merged_clinvar = new_doc['clinvar']

    merged_doc = deepcopy(old_doc)
    merged_doc.update({
        'variant': new_doc['variant'],
        'clinvar': merged_clinvar,
    })
    return merged_doc


def create_variant_task(db, doc):
    return {
        'old': None,
        'new': doc,
        'task': InsertOne(doc)
    }


def update_variant_task(db, existing_doc, updated_doc):
    doc_id = existing_doc['_id']
    merged_doc = merge_docs(existing_doc, updated_doc)
    logger.debug('Updating variant: {}, {} -> {}'.format(doc_id, get_variant_category(existing_doc), get_variant_category(merged_doc)))

    if existing_doc['subscribers']:
        logger.info('Will notify subscribers: {}'.format(updated_doc['subscribers']))

    return {
        'old': existing_doc,
        'new': merged_doc,
        'task': ReplaceOne({ '_id': doc_id }, merged_doc)
    }


def run_variant_tasks(db, tasks, notifier=None):
    db_update_queue = [task['task'] for task in tasks]
    counts = {
        'inserted': 0,
        'modified': 0,
        'notified': 0,
    }

    if db_update_queue:
        logger.info('Updating {} variants'.format(len(db_update_queue)))
        result = db.variants.bulk_write(db_update_queue, ordered=False)
        logger.info('Inserted {} variants and updated status of {}'.format(result.inserted_count, result.modified_count))
        counts['inserted'] = result.inserted_count
        counts['modified'] = result.modified_count

    if notifier:
        notification_queue = [(task['old'], task['new']) for task in tasks if task['old']]
        for old_doc, new_doc in notification_queue:
            notifier.notify_of_change(old_doc, new_doc)

        logger.info('Notifying of changes to {} variants'.format(len(notification_queue)))
        notifier.send_notifications()
        counts['notified'] = len(notification_queue)

    return counts
