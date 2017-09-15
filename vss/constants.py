BENIGN = 'benign'
UNCERTAIN = 'uncertain'
UNKNOWN = 'unknown'
PATHOGENIC = 'pathogenic'

DEFAULT_GENOME_BUILD = 'b37'

DEFAULT_NOTIFICATION_PREFERENCES = {
    'unknown_to_benign': True,
    'vus_to_benign': True,
    'path_to_benign': True,

    'unknown_to_vus': True,
    'benign_to_vus': True,
    'path_to_vus': True,

    'unknown_to_path': True,
    'benign_to_path': True,
    'vus_to_path': True,

    'notify_emails': True,
    'notify_slack': True,
}
