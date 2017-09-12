from flask_wtf import FlaskForm
from wtforms.fields import *
from wtforms.validators import *

CHROMOSOMES = [str(x) for x in range(1, 23)]
CHROMOSOMES.extend(['X', 'Y', 'MT', 'M'])
CHROMOSOMES.extend(['chr{}'.format(x) for x in CHROMOSOMES])


class SignupForm(FlaskForm):
    email = StringField(u'Your email address', validators=[Email(), DataRequired()])
    chr_pos_ref_alt = StringField(u'Chrom-Pos-Ref-Alt', validators=[DataRequired(), Regexp('([1[0-9]|2[0-2]|\d)-\d+-[ATCG]+-[ATCG]+')])
    # chromosome = StringField(u'Chromosome', validators=[DataRequired(), AnyOf(CHROMOSOMES)])
    # position = IntegerField(u'Position', validators=[DataRequired()])
    # reference = StringField(u'Reference allele', validators=[DataRequired()])
    # alternate = StringField(u'Alternate allele', validators=[DataRequired()])

    eula = StringField(u'I did not read the terms and conditions')

    submit = SubmitField(u'Signup')


class LoginForm(FlaskForm):
    email = StringField(u'Your email address', validators=[Email(), DataRequired()])

    submit = SubmitField(u'Signup')
