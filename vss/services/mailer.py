from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, Personalization, Content

class Mailer:
    def __init__(self, config):
        self.config = config
        self.client = SendGridAPIClient(apikey=self.config['SENDGRID_API_KEY'])

    def build(self, to_email, subject, body):
        mail = Mail()
        from_email = self.config['MAILER_FROM_EMAIL']
        from_name = self.config['MAILER_FROM_NAME']
        mail.from_email = Email(from_email, from_name)
        mail.subject = subject

        personalization = Personalization()
        personalization.add_to(Email(to_email))
        mail.add_personalization(personalization)

        mail.add_content(Content("text/plain", body))

        return mail.get()

    def send(self, mail):
        return self.client.client.mail.send.post(request_body=mail)
