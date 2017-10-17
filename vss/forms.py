from flask_wtf import FlaskForm
from wtforms.fields import *
from wtforms.validators import *
from wtforms.validators import ValidationError

CHROMOSOMES = [str(x) for x in range(1, 23)]
CHROMOSOMES.extend(['X', 'Y', 'MT', 'M'])
CHROMOSOMES.extend(['chr{}'.format(x) for x in CHROMOSOMES])

from .extensions import mongo
from .backend import VARIANT_PART_DELIMITER, get_variant_by_clinvar_id

def ValidClinvarVariant():
    message = 'Unknown Clinvar identifier.'

    def _validate(form, field):
        variant_string = field.data
        if variant_string and variant_string.count(VARIANT_PART_DELIMITER) == 3:
            chrom, pos, ref, alt = variant_string.split(VARIANT_PART_DELIMITER)
        else:
            # Keep as string to match what's in db
            clinvar_id = variant_string
            variant = get_variant_by_clinvar_id(mongo.db, clinvar_id)
            if not variant:
                raise ValidationError(message)

    return _validate

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


class SilenceForm(FlaskForm):
    silence = SubmitField(u'Silence all notifications')


class VariantForm(FlaskForm):
    remove = SubmitField(u'Remove selected variants')


class SignupForm(FlaskForm):
    # TODO: normalize as part of validation process
    variant = StringField(u'Variant (chrom-pos-ref-alt on b37 reference or ClinVar Variation identifier)\ne.g., "1-55518071-G-A", "230224"', validators=[DataRequired(), Regexp('(1[0-9]|2[0-2]|\d|[MXY])-\d+-[ATCG]+-[ATCG]+|\d+'), ValidClinvarVariant()])
    tag = StringField(u'Give this variant a name (optional; please do not use patient information)')
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


class LogoutForm(FlaskForm):
    submit = SubmitField(u'Log out')
