import gzip

from csv import DictReader
from pymongo import MongoClient

MONGO_DBNAME = 'vss'
CLINVAR_FILE = '/Users/buske/dat/clinvar/clinvar_alleles.single.b37.tsv.gz.old'

def get_key(row):
    # Hardcode the build for now, since it isn't in the file and we're only using grch37
    build = 'b37'
    return '-'.join([build, row['chrom'], row['pos'], row['ref'], row['alt']])

def get_doc(row):
    key = get_key(row)

    return {
        '_id': key,

        # Basic information
        'chrom': row['chrom'],
        'pos': row['pos'],
        'ref': row['ref'],
        'alt': row['alt'],

        # Current ClinGen classification
        'clinical_significance': row['clinical_significance'],
        'gold_stars': row['gold_stars'],
        'review_status': row['review_status'],
        'last_evaluated': row['last_evaluated'],

        # Array of historical clingen information
        'history': [
        ],

        # Subscribers to notify of changes
        'subscribers': [
        ],
    }

def iter_variants(filename):
    with gzip.open(filename, 'rt') as ifp:
        for row in DictReader(ifp, dialect='excel-tab'):
            yield row

if __name__ == '__main__':
    client = MongoClient('mongodb://localhost:27017')

    db = client[MONGO_DBNAME]

    for variant in iter_variants(CLINVAR_FILE):
        doc = get_doc(variant)

        doc_id = doc['_id']
        existing_doc = db.variants.find(doc_id)
        if existing_doc:
            # Variant is already known
            # If there is any existing clingen
            pass

        db.variants.insert_one(doc)
