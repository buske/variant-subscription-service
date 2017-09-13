#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ..constants import BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC
from .mailer import build_mail, send_mail


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
    def __init__(self):
        self.change_notifications = {}  # dict: email -> list of notifications
        self.add_notifications = {}  # dict: email -> list of notifications

    # Notify if:
    # - benign -> uncertain, conflicting, pathogenic
    # - null, not provided, uncertain, conflicting -> benign, pathogenic
    # - pathogenic -> uncertain, conflicting, benign

    def should_notify_of_clinvar_change(self, old_clinvar, new_clinvar):
        # TODO: per-user preferences
        old_category = old_clinvar['category']
        new_category = new_clinvar['category']
        if old_category in (UNCERTAIN, UNKNOWN) and new_category in (BENIGN, UNCERTAIN):
            return False
        else:
            # Notify if the category changes
            return old_category != new_category

    def should_notify_of_clinvar_add(self, clinvar):
        # Notify of any classification being added to clinvar
        return clinvar['category'] != UNKNOWN

    def notify_of_change(self, doc, old_clinvar, new_clinvar):
        for to_email in doc['subscribers']:
            notifications = self.change_notifications.setdefault(to_email, [])
            notifications.append((doc, old_clinvar, new_clinvar))

    def notify_of_add(self, doc, clinvar):
        for to_email in doc['subscribers']:
            notifications = self.add_notifications.setdefault(to_email, [])
            notifications.append((doc, clinvar))

    def send_emails(self):
        all_emails = set(self.change_notifications).union(self.add_notifications)
        print('EMAILS:', all_emails)
        for to_email in all_emails:
            add_notifications = self.add_notifications.get(to_email, [])
            change_notifications = self.change_notifications.get(to_email, [])
            all_notifications = add_notifications + change_notifications
            notification_count = len(all_notifications)
            if notification_count == 1:
                # Custom subject for this case
                subject = "🎉  News for your variant: {}".format(all_notifications[0]['_id'])
            else:
                subject = "🎉  News for {} variants".format(notification_count)

            email_parts = []
            for add_notification in add_notifications:
                doc, clinvar = add_notification
                variant = doc['variant']
                email_parts.append("""
{}. new classification: {}:{} {}>{} ({})
- {} ({})
See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(len(email_parts) + 1, variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           clinvar['clinical_significance'], render_rating(clinvar['gold_stars']),
           doc['clinvar']['variation_id']))

            for change_notification in change_notifications:
                doc, old_clinvar, new_clinvar = change_notification
                variant = doc['variant']
                email_parts.append("""
{}. classification updated: {}:{} {}>{} ({})
- new classification: {} ({})
- previous classification: {} ({})
See ClinVar for more information: https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/
""".format(len(email_parts) + 1, variant['chrom'], variant['pos'], variant['ref'], variant['alt'], variant['build'],
           new_clinvar['clinical_significance'], render_rating(new_clinvar['gold_stars']),
           old_clinvar['clinical_significance'], render_rating(old_clinvar['gold_stars']),
           doc['clinvar']['variation_id']))

            body = '\n'.join(email_parts)

            mail = build_mail(to_email, subject, body)
            send_mail(mail)
            # sc = SlackClient(slack_token)
            # sc.api_call(
            #     "chat.postMessage",
            #     channel=channels,
            #     text=message,
            #     parse='full'
            # )
