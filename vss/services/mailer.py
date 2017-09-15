import sendgrid
import os

from sendgrid.helpers.mail import *

sg = sendgrid.SendGridAPIClient(apikey=os.environ.get('SENDGRID_API_KEY'))


def build_mail(to_email, subject, body):
    mail = Mail()
    mail.from_email = Email("support@variantfacts.com", "Variant Facts")
    mail.subject = subject

    personalization = Personalization()
    personalization.add_to(Email(to_email))
    mail.add_personalization(personalization)

    mail.add_content(Content("text/plain", body))

    return mail.get()


def send_mail(mail):
    return sg.client.mail.send.post(request_body=mail)
