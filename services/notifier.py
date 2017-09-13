#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import requests

from ..constants import BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC, DEFAULT_NOTIFICATION_PREFERENCES
from ..backend import get_variant_category
from .mailer import build_mail, send_mail

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# dict: FROM -> TO -> FIELD_NAME
NOTIFICATION_PREFERENCE_MAP = {
    UNKNOWN: {
        BENIGN: 'unknown_to_benign',
        UNCERTAIN: 'unknown_to_vus',
        PATHOGENIC: 'unknown_to_path',
    },
    BENIGN: {
        UNCERTAIN: 'benign_to_vus',
        PATHOGENIC: 'unknown_to_path',
    },
    UNCERTAIN: {
        BENIGN: 'vus_to_benign',
        PATHOGENIC: 'vus_to_path',
    },
    PATHOGENIC: {
        BENIGN: 'path_to_benign',
        UNCERTAIN: 'path_to_vus',
    },
}

def render_rating(gold_stars):
    try:
        stars = int(gold_stars)
    except TypeError:
        stars = 0

    if stars == 1:
        return '1 star'
    else:
        return '{} stars'.format(stars)


class Notifier:
    def __init__(self, db):
        self.notifications = {}  # dict: user_id -> list of notifications
        self.users = {}  # dict: user_id -> user data (memoization)
        self.db = db

    def _get_user(self, user_id):
        # Get user data, memoized with self.users
        user = self.users.get(user_id)
        if not user:
            user = self.db.users.find_one(user_id)
            self.users[user_id] = user
        return user

    def _get_preference_name(self, old_category, new_category):
        return NOTIFICATION_PREFERENCE_MAP[old_category][new_category]

    def should_notify_user(self, user, old_category, new_category):
        preference_field = self._get_preference_name(old_category, new_category)
        should_notify = user.get('notification_preferences', DEFAULT_NOTIFICATION_PREFERENCES).get(preference_field)

        if should_notify is None:
            logger.error('Missing user notification preference for {} -> {}'.format(old_category, new_category))
        else:
            return bool(should_notify)

    def notify_of_change(self, old_doc, new_doc):
        old_category = get_variant_category(old_doc)
        new_category = get_variant_category(new_doc)
        logger.debug('Notifying of change: {}'.format(old_doc['subscribers']))
        for user_id in old_doc['subscribers']:
            user = self._get_user(user_id)
            if self.should_notify_user(user, old_category, new_category):
                logger.debug('Notifying user ({}) of change to variant: {}'.format(user['email'], new_doc['_id']))
                # Add to user's notification queue
                user_notifications = self.notifications.setdefault(user_id, [])
                user_notifications.append({
                    'old_category': old_category,
                    'new_category': new_category,
                    'old_doc': old_doc,
                    'new_doc': new_doc,
                })

    def make_notification(self, notification):
        variant = notification['new_doc']['variant']
        clinvar = notification['new_doc']['clinvar']['current']
        old_clinvar = notification['old_doc']['clinvar']['current']
        variation_id = notification['new_doc']['clinvar']['variation_id']
        if notification['old_category']:
            # New classification
            return """new classification: {}:{} {}>{} ({})
- {} ({})
See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           clinvar['clinical_significance'], render_rating(clinvar['gold_stars']),
           variation_id)
        else:
            # Re-classification
            return """classification updated: {}:{} {}>{} ({})
- new classification: {} ({})
- previous classification: {} ({})
See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           clinvar['clinical_significance'], render_rating(clinvar['gold_stars']),
           old_clinvar['clinical_significance'], render_rating(old_clinvar['gold_stars']),
           variation_id)

    def send_notifications(self):
        logger.debug('Sending notifications to {} users'.format(len(self.notifications)))
        for user_id, user_notifications in self.notifications.items():
            user = self.users[user_id]
            email = user.get('email')
            slack_url = user.get('slack', {}).get('incoming_webhook', {}).get('url')
            logger.debug('Sending {} notifications to {}'.format(len(user_notifications), email))
            notification_count = len(user_notifications)
            if notification_count == 1:
                # Custom subject for this case
                subject = "🎉  News for your variant: {}".format(user_notifications[0]['new_doc']['_id'])
            else:
                subject = "🎉  News for {} variants".format(notification_count)

            text_parts = []
            for notification in user_notifications:
                part = '{}. {}'.format(len(text_parts) + 1, self.make_notification(notification))
                text_parts.append(part)

            text = '\n'.join(text_parts)

            if email:
                mail = build_mail(email, subject, text)
                send_mail(mail)

            if slack_url:
                response = requests.post(slack_url, json={"text": text})
                if response.status_code != 200:
                    logger.error('Slack posting failed: {}'.format(response))
                else:
                    logger.debug('Slack post: {}'.format(response))

