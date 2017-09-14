from flask_wtf import FlaskForm
from wtforms.fields import *
from wtforms.validators import *

CHROMOSOMES = [str(x) for x in range(1, 23)]
CHROMOSOMES.extend(['X', 'Y', 'MT', 'M'])
CHROMOSOMES.extend(['chr{}'.format(x) for x in CHROMOSOMES])


class PreferencesForm(FlaskForm):

    unknown_to_benign = BooleanField('', default=True)
    benign_to_benign = BooleanField('', default=False)
    vus_to_benign = BooleanField('', default=True)
    path_to_benign = BooleanField('', default=True)

    unknown_to_vus = BooleanField('', default=True)
    benign_to_vus = BooleanField('', default=True)
    vus_to_vus = BooleanField('', default=False)
    path_to_vus = BooleanField('', default=True)

    unknown_to_path = BooleanField('', default=True)
    benign_to_path = BooleanField('', default=True)
    vus_to_path = BooleanField('', default=True)
    path_to_path = BooleanField('', default=False)

    notify_emails = BooleanField('Email', default=True)
    notify_slack = BooleanField('Slack', default=True)

    submit = SubmitField(u'Update preferences')


class RemoveSlackForm(FlaskForm):
    remove_slack = SubmitField(u'Remove Slack Integration')


class DeleteForm(FlaskForm):
    delete = SubmitField(u'Delete your account')


class SignupForm(FlaskForm):
    # TODO: normalize as part of validation process
    chr_pos_ref_alt = StringField(u'Chrom-Pos-Ref-Alt', validators=[DataRequired(), Regexp('([1[0-9]|2[0-2]|\d)-\d+-[ATCG]+-[ATCG]+')])
    tag = StringField(u'Tag this variant with a description (optional; please do not use patient information)')
    email = StringField(u'Email address', validators=[Email(), DataRequired()])

    # chromosome = StringField(u'Chromosome', validators=[DataRequired(), AnyOf(CHROMOSOMES)])
    # position = IntegerField(u'Position', validators=[DataRequired()])
    # reference = StringField(u'Reference allele', validators=[DataRequired()])
    # alternate = StringField(u'Alternate allele', validators=[DataRequired()])

    # eula = BooleanField(u'I did not read the <a data-toggle="modal" data-target="#tandc">terms and conditions</a>', validators=[DataRequired()])

    submit = SubmitField(u'Subscribe')


class LoginForm(FlaskForm):
    email = StringField(u'Email address to send login token', validators=[Email(), DataRequired()])

    submit = SubmitField(u'Send email')
