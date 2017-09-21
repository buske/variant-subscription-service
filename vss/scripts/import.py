import sys
import gzip
import logging

from csv import DictReader
from pymongo import InsertOne, ReplaceOne
from datetime import datetime

from . import app, connect_db
from ..constants import DEFAULT_GENOME_BUILD, BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC
from ..extensions import mongo
from ..backend import build_variant_doc, get_variant_category
from ..services.notifier import UpdateNotifier

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def merge_docs(old_doc, new_doc):
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


def update_variant(db, existing_doc, updated_doc):
    doc_id = existing_doc['_id']
    merged_doc = merge_docs(existing_doc, updated_doc)
    logger.debug('Updating variant: {}, {} -> {}'.format(doc_id, get_variant_category(existing_doc), get_variant_category(merged_doc)))
    return merged_doc, ReplaceOne({ '_id': doc_id }, merged_doc)


def create_variant(db, doc):
    return InsertOne(doc)


def iter_variants(filename):
    with gzip.open(filename, 'rt') as ifp:
        for row in DictReader(ifp, dialect='excel-tab'):
            yield row


def did_variant_category_change(old_doc, new_doc):
    old_category = get_variant_category(old_doc)
    new_category = get_variant_category(new_doc)
    return old_category != new_category


def iter_variant_updates(db, variants):
    for variant in variants:
        new_doc = build_variant_doc(DEFAULT_GENOME_BUILD, **variant)

        doc_id = new_doc['_id']
        old_doc = db.variants.find_one({ '_id': doc_id })
        if did_variant_category_change(old_doc, new_doc):
            yield (old_doc, new_doc)


def main(clinvar_filename):
    db = connect_db()
    notifier = UpdateNotifier(db, app.config)
    started_at = datetime.utcnow()

    db_update_queue = []
    notification_queue = []
    variant_iterator = iter_variants(clinvar_filename)
    for i, (old_doc, new_doc) in enumerate(iter_variant_updates(db, variant_iterator)):
        if i % 10000 == 0:
            logger.debug('Processed {} variants'.format(i))

        if old_doc:
            # Variant is already known, either:
            # - someone subscribed before it was added to clinvar, or
            # - it was already in clinvar, and we might have new annotations
            updated_doc, db_update = update_variant(db, old_doc, new_doc)
            if old_doc['subscribers']:
                logger.info('Will notify subscribers: {}'.format(updated_doc['subscribers']))
                notification_queue.append((old_doc, updated_doc))

        else:
            # Add clinvar annotations with empty subscriber data
            db_update = create_variant(db, new_doc)

        db_update_queue.append(db_update)

    if db_update_queue:
        logger.info('Updating {} variants'.format(len(db_update_queue)))
        result = db.variants.bulk_write(db_update_queue, ordered=False)
        logger.info('Inserted {} variants and updated status of {}'.format(result.inserted_count, result.modified_count))

    if notification_queue:
        for old_doc, new_doc in notification_queue:
            notifier.notify_of_change(old_doc, new_doc)

        logger.info('Notifying of changes to {} variants'.format(len(notification_queue)))
        notifier.send_notifications()

    db.updates.insert_one({
        'started_at': started_at,
        'finished_at': datetime.utcnow(),
        'inserted_count': result.inserted_count,
        'modified_count': result.modified_count,
        'notified_count': len(notification_queue),
    })


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description='Update ClinVar data')
    parser.add_argument('clinvar_filename', metavar='CLINVAR_ALLELES_TSV_GZ', type=str,
                        help='clinvar_alleles.single.b*.tsv.gz from github.com/macarthur-lab/clinvar pipeline')

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    main(args.clinvar_filename)
