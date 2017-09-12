import sys
import gzip

from csv import DictReader
from pymongo import MongoClient

from . import BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC
from .notifier import Notifier

MONGO_DBNAME = 'vss'
CLINVAR_FILE = '/Users/buske/dat/clinvar/clinvar_alleles.single.b37.tsv.gz.new'

GENOME_BUILD = 'b37'

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

def get_key(row):
    # Hardcode the build for now, since it isn't in the file and we're only using grch37
    build = GENOME_BUILD
    return '-'.join([build, row['chrom'], row['pos'], row['ref'], row['alt']])

def parse_clinvar_category(significance):
    # Normalize significance (removing additional parts, like ", association")
    significance = significance.split(',')[0].strip().lower()
    if significance in CLINVAR_CATEGORY_MAPPING:
        category = CLINVAR_CATEGORY_MAPPING[significance]
    else:
        print('Unknown significance:', significance, file=sys.stderr)
        category = UNKNOWN

    return category

def get_doc(row):
    key = get_key(row)

    variant = {
        # Basic variant information
        'build': GENOME_BUILD,
        'chrom': row['chrom'],
        'pos': row['pos'],
        'ref': row['ref'],
        'alt': row['alt'],
    }

    clinvar = {
        'variation_id': row['variation_id'],
        # Current ClinVar annotation data
        'current': {
            'category': parse_clinvar_category(row['clinical_significance']),
            'clinical_significance': row['clinical_significance'],
            'gold_stars': row['gold_stars'],
            'review_status': row['review_status'],
            'last_evaluated': row['last_evaluated'],
        },
        # Array of historical ClinVar information
        'history': [],
    }

    return {
        '_id': key,
        'variant': variant,
        'clinvar': clinvar,
        'subscribers': [],
    }

def merge_docs(old_doc, new_doc, notifier):
    merged_clinvar = {}
    had_clinvar_data = bool(old_doc['clinvar'])
    if had_clinvar_data:
        # Variant had existing clinvar, so we might notify
        old_data = old_doc['clinvar']['current']
        new_data = new_doc['clinvar']['current']
        # Append to history
        history = old_doc['clinvar']['history']
        history.append(old_data)
        # Set new annotation data
        merged_clinvar['current'] = new_data
        merged_clinvar['history'] = history
        merged_clinvar['variation_id'] = old_doc['clinvar']['variation_id'] or new_doc['clinvar']['variation_id']
    else:
        # Add clinvar data to existing subscribed variant
        merged_clinvar = new_doc['clinvar']

    merged_doc = {
        '_id': old_doc['_id'],
        'variant': new_doc['variant'],
        'subscribers': old_doc['subscribers'] or ['orion.buske@gmail.com'],
        'clinvar': merged_clinvar,
    }
    if had_clinvar_data:
        if notifier.should_notify_of_clinvar_change(old_data, new_data):
            notifier.notify_of_change(merged_doc, old_data, new_data)
    else:
        # if subscribers and should_notify_of_clinvar_add(clinvar):
        if notifier.should_notify_of_clinvar_add(merged_clinvar['current']):
            notifier.notify_of_add(merged_doc, merged_clinvar['current'])

    return

def iter_variants(filename):
    with gzip.open(filename, 'rt') as ifp:
        for row in DictReader(ifp, dialect='excel-tab'):
            yield row

if __name__ == '__main__':
    client = MongoClient('mongodb://localhost:27017')
    db = client[MONGO_DBNAME]
    notifier = Notifier()

    for variant in iter_variants(CLINVAR_FILE):
        doc = get_doc(variant)

        doc_id = doc['_id']
        existing_doc = db.variants.find_one(doc_id)
        if existing_doc:
            # Variant is already known, either:
            # - someone subscribed before it was added to clinvar, or
            # - it was already in clinvar, and we might have new annotations
            merged_doc = merge_docs(existing_doc, doc, notifier)
            db.variants.find_one_and_replace(doc_id, merged_doc)
        else:
            # Add clinvar annotations with empty subscriber data
            db.variants.insert_one(doc)

    notifier.send_emails()
