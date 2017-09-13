import sys
import gzip

from csv import DictReader

from . import get_db
from ..constants import DEFAULT_GENOME_BUILD
from ..backend import build_variant_doc
from ..services.notifier import Notifier

CLINVAR_FILE = '/Users/buske/dat/clinvar/clinvar_alleles.single.b37.tsv.gz.new'

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
    db = get_db()
    notifier = Notifier()

    for variant in iter_variants(CLINVAR_FILE):
        doc = build_variant_doc(DEFAULT_GENOME_BUILD, **variant)

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
