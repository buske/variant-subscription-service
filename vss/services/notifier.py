#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import requests

from ..constants import BASE_URL, BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC, DEFAULT_NOTIFICATION_PREFERENCES
from ..backend import get_variant_category
from ..utils import deep_get
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


def render_rating(gold_stars, unicode_emoji=False, max_stars=4):
    try:
        stars = int(gold_stars)
    except TypeError:
        stars = 0

    if unicode_emoji:
        return ('★' * stars) + '☆' * (max_stars - stars)
    else:
        if stars == 1:
            return '1 star'
        else:
            return '{} stars'.format(stars)


def render_rating_slack(gold_stars):
    try:
        stars = int(gold_stars)
    except TypeError:
        stars = 0



class Notifier:
    def notify(self, user, subject, body, force_email=True):
        # force_email is used for overriding the user preferences to receive email
        email = user.get('email')

        # Take into account user notification preferences
        can_email_user = email and (force_email or deep_get(user, 'notification_preferences.notify_emails', DEFAULT_NOTIFICATION_PREFERENCES['notify_emails']))
        logger.debug('Notifications for user {}: email={}'.format(email, can_email_user))

        if can_email_user:
            logger.debug('Sending notification to email: {}'.format(email))
            mail = build_mail(email, subject, body)
            response = send_mail(mail)
            if response.status_code != 202:
                logger.error('Error sending email ({}): {}'.format(response.status_code, response.body))
            else:
                logger.debug('Sent email:\n  to: {}\n  subject: {!r}\n  body: {!r}\n  response: {}'.format(email, subject, body, response.body))

    def slack_notify(self, user, data):
        email = user.get('email')
        slack_url = deep_get(user, 'slack.incoming_webhook.url')

        json = {
            "attachments": [
                {
                    "fallback": "Summary of your variants",
                    "color": "#36a64f",
                    "pretext": "You have {} updates for your variants".format(len(data)),
                    "author_name": "Variant Facts",
                    "author_link": "http://127.0.0.1:5000",
                    "author_icon": "http://flickr.com/icons/bobby.jpg",
                    # "title": "New classification for your variants",
                    "fields": data,
                    "image_url": "http://my-website.com/path/to/image.jpg",
                    "thumb_url": "http://example.com/path/to/thumb.png",
                    "footer": "Variant Facts",
                    "footer_icon": "https://platform.slack-edge.com/img/default_application_icon.png"
                }
            ]
        }
        # Take into account user notification preferences
        can_slack_user = slack_url and deep_get(user, 'notification_preferences.notify_slack', DEFAULT_NOTIFICATION_PREFERENCES['notify_slack'])
        logger.debug('Notifications for user {}: slack={}'.format(email, can_slack_user))

        if can_slack_user:
            logger.debug('Posting notification to slack')
            response = requests.post(slack_url, json=json)
            if response.status_code != 200:
                logger.error('Error posting to Slack ({}): {}'.format(response.status_code, response.text))
            else:
                logger.debug('Posted to Slack: {}'.format(response.text))


class ResendTokenNotifier(Notifier):
    def __init__(self, db):
        self.db = db

    def resend_token(self, email):
        user = None
        if email:
            user = self.db.users.find_one({ 'email': email })

        if user:
            logger.debug('Resending token to: {}'.format(email))
            token = user['token']

            account_url = '{}/account/?t={}'.format(BASE_URL, token)

            subject = '🚀  Your login link for Variant Facts'
            body = """
Here is a link to manage your account: {}

This link gives full access to your account, so keep it private.
""".format(account_url)

            self.notify(user, subject, body, force_email=True)
            return True


class SubscriptionNotifier(Notifier):
    def __init__(self, db):
        self.db = db

    def notify_of_subscription(self, user_id, new_subscription_count):
        user = self.db.users.find_one({ '_id': user_id })
        token = user['token']
        email = user.get('email')

        total_subscription_count = self.db.variants.count({ 'subscribers': user_id })

        account_url = '{}/account/?t={}'.format(BASE_URL, token)

        s_new = 's' if new_subscription_count > 1 else ''
        s_total = 's' if total_subscription_count > 1 else ''
        # send welcome email
        subject = "🙌  Subscribed to {} variant{}".format(new_subscription_count, s_new)

        text = """You subscribed to Variant Facts!

You've added {} variant{} for a total of {} variant{}.

Manage your account here: {}
    """.format(new_subscription_count, s_new, total_subscription_count, s_total, account_url)

        self.notify(user, subject, text)


class UpdateNotifier(Notifier):
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
        should_notify = deep_get(user, 'notification_preferences.{}'.format(preference_field, DEFAULT_NOTIFICATION_PREFERENCES[preference_field]))

        if should_notify is None:
            logger.error('Missing user notification preference for {} -> {}'.format(old_category, new_category))
        else:
            return bool(should_notify)

    def notify_of_change(self, old_doc, new_doc):
        old_category = get_variant_category(old_doc)
        new_category = get_variant_category(new_doc)
        logger.debug('Will notify of change: {}'.format(old_doc['subscribers']))
        for user_id in old_doc['subscribers']:
            user = self._get_user(user_id)
            if self.should_notify_user(user, old_category, new_category):
                logger.info('Will notify user ({}) of change to variant: {}'.format(user['email'], new_doc['_id']))
                # Add to user's notification queue
                user_notifications = self.notifications.setdefault(user_id, [])
                user_notifications.append({
                    'old_category': old_category,
                    'new_category': new_category,
                    'old_doc': old_doc,
                    'new_doc': new_doc,
                })
            else:
                logger.info('Skipping notification of user ({}) of change to variant ({}) due to user preferences'.format(user['email'], new_doc['_id']))

    def make_notification(self, notification):
        variant = deep_get(notification, 'new_doc.variant')
        clinvar = deep_get(notification, 'new_doc.clinvar.current')
        old_clinvar = deep_get(notification, 'old_doc.clinvar.current')
        variation_id = deep_get(notification, 'new_doc.clinvar.variation_id')
        if old_clinvar:
            # Re-classification
            return """classification updated: {}:{} {}>{} ({})
  - new classification: {} ({})
  - previous classification: {} ({})
  - See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           clinvar['clinical_significance'], render_rating(clinvar['gold_stars']),
           old_clinvar['clinical_significance'], render_rating(old_clinvar['gold_stars']),
           variation_id)
        else:
            # New classification
            return """new classification: {}:{} {}>{} ({})
  - {} ({})
  - See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           clinvar['clinical_significance'], render_rating(clinvar['gold_stars']),
           variation_id)

    def make_slack_notification(self, notification):
        variant = deep_get(notification, 'new_doc.variant')
        clinvar = deep_get(notification, 'new_doc.clinvar.current')
        old_clinvar = deep_get(notification, 'old_doc.clinvar.current')
        variation_id = deep_get(notification, 'new_doc.clinvar.variation_id')
        data = []
        if old_clinvar:
            # Re-classification
            data.append({
                'title': 'Classification updated',
                'value': '{}:{} {}>{} ({})\n{} {} → {} {}\n'
                         'See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/'.format(
                    variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
                    old_clinvar['clinical_significance'], render_rating(old_clinvar['gold_stars'], True),
                    clinvar['clinical_significance'], render_rating(clinvar['gold_stars'], True), variation_id),
                'short': False
            })
        else:
            data.append({
                'title': 'New classification',
                'value': '{}:{} {}>{} ({})\n{} {}\n'
                         'See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/'.format(
                    variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
                    clinvar['clinical_significance'], render_rating(clinvar['gold_stars'], True), variation_id),
                'short': False
            })
        logger.debug('DATA: {}'.format(data))
        return data

    def send_notifications(self):
        logger.debug('Sending notifications to {} users'.format(len(self.notifications)))
        for user_id, user_notifications in self.notifications.items():
            user = self.users[user_id]
            logger.debug('Sending {} notifications to {}'.format(len(user_notifications), user))
            notification_count = len(user_notifications)
            if notification_count == 1:
                # Custom subject for this case
                subject = "🎉  News for your variant: {}".format(deep_get(user_notifications[0], 'new_doc._id'))
            else:
                subject = "🎉  News for {} variants".format(notification_count)

            text_parts = []
            slack_text_parts = []
            for i, notification in enumerate(user_notifications):
                part = '{}. {}'.format(i + 1, self.make_notification(notification))
                text_parts.append(part)
                slack_text_parts.extend(self.make_slack_notification(notification))

            text = '\n'.join(text_parts)
            logger.debug('Email text below\n%s', text)
            self.notify(user, subject, text)
            self.slack_notify(user, slack_text_parts)
