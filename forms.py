from flask_wtf import FlaskForm
from wtforms.fields import *
from wtforms.validators import *

CHROMOSOMES = [str(x) for x in range(1, 23)]
CHROMOSOMES.extend(['X', 'Y', 'MT', 'M'])
CHROMOSOMES.extend(['chr{}'.format(x) for x in CHROMOSOMES])


class PreferencesForm(FlaskForm):

    unknown_to_benign = BooleanField('')
    benign_to_benign = BooleanField('')
    vus_to_benign = BooleanField('')
    path_to_benign = BooleanField('')

    unknown_to_vus = BooleanField('')
    benign_to_vus = BooleanField('')
    vus_to_vus = BooleanField('')
    path_to_vus = BooleanField('')

    unknown_to_path = BooleanField('')
    benign_to_path = BooleanField('')
    vus_to_path = BooleanField('')
    path_to_path = BooleanField('')

    delete = SubmitField(u'As HRC said to DJT, delete your account')
    submit = SubmitField(u'Update preferences')


class SignupForm(FlaskForm):
    chr_pos_ref_alt = StringField(u'Chrom-Pos-Ref-Alt', validators=[DataRequired(), Regexp('([1[0-9]|2[0-2]|\d)-\d+-[ATCG]+-[ATCG]+')])
    tag = StringField(u'Tag this variant with a name (optional)')
    email = StringField(u'Email address', validators=[Email(), DataRequired()])

    # chromosome = StringField(u'Chromosome', validators=[DataRequired(), AnyOf(CHROMOSOMES)])
    # position = IntegerField(u'Position', validators=[DataRequired()])
    # reference = StringField(u'Reference allele', validators=[DataRequired()])
    # alternate = StringField(u'Alternate allele', validators=[DataRequired()])

    eula = BooleanField(u'I did not read the <a data-toggle="modal" data-target="#tandc">terms and conditions</a>', validators=[DataRequired()])

    submit = SubmitField(u'Signup')


class LoginForm(FlaskForm):
    email = StringField(u'Email address', validators=[Email(), DataRequired()])
    # password = PasswordField(u'Password', validators=[DataRequired()])

    submit = SubmitField(u'Login')
