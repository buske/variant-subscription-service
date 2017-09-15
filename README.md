# Variant Facts

## (Formerly the Variant Subscription Service (VSS))

Subscribe to important updates on genomic variants of interest, such as changes in ClinVar classification


## Setup

### Prerequisites

* Python 3.3+
* mongodb

### Installation

```
git clone https://github.com/buske/variant-subscription-service.git
cd variant-subscription-service

virtualenv -p python3 .virtualenv
source .virtualenv/bin/activate
pip install -r requirements.txt
```


## Run server

### Start mongodb

```
mongod --dbpath /path/to/db
```

### Run in development mode
```
FLASK_APP=wsgi.py flask run --reload
```

### Run in production mode

*Instructions for Ubuntu 16.04*

- Install nginx
- Set up nginx
```
sudo cp deploy/vss.nginx /etc/nginx/sites-available/vss
sudo ln -s /etc/nginx/sites-available/vss /etc/nginx/sites-enabled/
systemctl restart nginx
```
- Set up uWSGI service
```
sudo cp deploy/vss.service /etc/systemd/system/vss.service
sudo systemctl start vss
sudo systemctl enable vss
```
- Override necessary environment variables in `production.cfg` (exclude from VCS)
```
cp config.py production.cfg
nano production.cfg
```
- Define environment variable `VSS_SETTINGS` with the FULL path to this cfg file, e.g. `VSS_SETTINGS=/path/to/production.cfg`


## Import ClinVar data

### Fetch source data
Soon, you will be able to fetch the latest source data with [vss-dat-import](https://github.com/david4096/vss-dat-import)

In the meantime, you must parse the ClinVar data yourself using the [Macarthur Lab parser](https://github.com/macarthur-lab/clinvar). As of 15 Sept 2017, you must use the unmerged [pr/33](https://github.com/macarthur-lab/clinvar/tree/pr/33). The `clinvar_alleles.single.b37.tsv.gz` file is what is required by the importer.

### Import parsed ClinVar data
You can then run the importer periodically (by hand or crontab) to notify users of changes to ClinVar classifications:
```
VSS_SETTINGS=/path/to/production.cfg python -m vss.scripts.import /path/to/clinvar_alleles.single.b37.tsv.gz
```
