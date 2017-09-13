import sys
import gzip
import logging

from csv import DictReader

from . import connect_db
from ..constants import DEFAULT_GENOME_BUILD, BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC
from ..backend import build_variant_doc, get_variant_category
from ..services.notifier import Notifier

CLINVAR_FILE = '/Users/buske/dat/clinvar/clinvar_alleles.single.b37.tsv.gz.old'

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        merged_clinvar['variation_id'] = new_doc['clinvar']['variation_id']
    else:
        # Add clinvar data to existing subscribed variant
        merged_clinvar = new_doc['clinvar']

    return {
        '_id': old_doc['_id'],
        'variant': new_doc['variant'],
        'subscribers': old_doc['subscribers'],
        'clinvar': merged_clinvar,
    }


def update_variant(existing_doc, updated_doc):
    doc_id = existing_doc['_id']
    merged_doc = merge_docs(existing_doc, updated_doc, notifier)
    logger.debug('Updating variant: {}'.format(existing_doc))
    db.variants.find_one_and_replace({ '_id': doc_id }, merged_doc)
    return merged_doc


def create_variant(doc):
    result = db.variants.insert_one(doc)
    logger.debug('Creating variant, result: {}'.format(result.inserted_id))
    return doc


def iter_variants(filename):
    with gzip.open(filename, 'rt') as ifp:
        for row in DictReader(ifp, dialect='excel-tab'):
            yield row


def did_variant_category_change(old_doc, new_doc):
    old_category = get_variant_category(old_doc)
    new_category = get_variant_category(new_doc)
    return old_category != new_category


if __name__ == '__main__':
    db = connect_db()
    notifier = Notifier(db)

    for variant in iter_variants(CLINVAR_FILE):
        doc = build_variant_doc(DEFAULT_GENOME_BUILD, **variant)

        doc_id = doc['_id']
        existing_doc = db.variants.find_one({ '_id': doc_id })
        if did_variant_category_change(existing_doc, doc):
            logger.debug('Variant changed: {} -> {}'.format(existing_doc, doc))

            if existing_doc:
                # Variant is already known, either:
                # - someone subscribed before it was added to clinvar, or
                # - it was already in clinvar, and we might have new annotations
                new_doc = update_variant(existing_doc, doc)
            else:
                # Add clinvar annotations with empty subscriber data
                create_variant(doc)
                new_doc = doc

            if new_doc['subscribers']:
                logger.debug('Notifying subscribers: {}'.format(new_doc['subscribers']))
                notifier.notify_of_change(existing_doc, new_doc)


    notifier.send_notifications()
