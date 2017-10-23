import sys
import gzip
import logging

from csv import DictReader
from datetime import datetime

from . import app, connect_db
from ..constants import DEFAULT_GENOME_BUILD, BENIGN, UNCERTAIN, UNKNOWN, PATHOGENIC
from ..extensions import mongo
from ..backend import build_variant_doc, get_variant_category, update_variant_task, create_variant_task, run_variant_tasks
from ..services.notifier import UpdateNotifier

logging.basicConfig(format="%(levelname)s (%(name)s %(lineno)s): %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

    task_list = []
    variant_iterator = iter_variants(clinvar_filename)
    for i, (old_doc, new_doc) in enumerate(iter_variant_updates(db, variant_iterator)):
        if i % 10000 == 0:
            logger.debug('Processed {} variants'.format(i))

        if old_doc:
            # Variant is already known, either:
            # - someone subscribed before it was added to clinvar, or
            # - it was already in clinvar, and we might have new annotations
            task = update_variant_task(db, old_doc, new_doc)

        else:
            # Add clinvar annotations with empty subscriber data
            task = create_variant_task(db, new_doc)

        task_list.append(task)

    results = run_variant_tasks(db, task_list, notifier=notifier)
    logger.debug('Variants updated. Results: {}'.format(results))

    db.updates.insert_one({
        'started_at': started_at,
        'finished_at': datetime.utcnow(),
        'inserted_count': results['inserted'],
        'modified_count': results['modified'],
        'notified_count': results['notified'],
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
