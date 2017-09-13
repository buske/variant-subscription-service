import logging

from .constants import BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CLINVAR_CATEGORY_MAPPING = {
    'pathogenic': PATHOGENIC,
    'pathogenic/likely pathogenic': PATHOGENIC,
    'likely pathogenic': PATHOGENIC,
    'conflicting interpretations of pathogenicity': UNCERTAIN,
    'not provided': UNKNOWN,
    'uncertain significance': UNCERTAIN,
    'likely benign': BENIGN,
    'benign/likely benign': BENIGN,
    'benign': BENIGN,
}

def parse_clinvar_category(significance):
    # Normalize significance (removing additional parts, like ", association")
    significance = significance.split(',')[0].strip().lower()
    if significance in CLINVAR_CATEGORY_MAPPING:
        category = CLINVAR_CATEGORY_MAPPING[significance]
    else:
        logger.warning('Unknown significance: {}'.format(significance))
        category = UNKNOWN

    return category
