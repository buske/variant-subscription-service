# Variant Subscription Service (VSS)
Subscribe to important updates on genomic variants of interest, such as changes in ClinVar classification

## Setup

### Prerequisites

* Python 3.3+
* mongodb

### Installation

```
git clone https://github.com/buske/variant-subscription-service.git
cd variant-subscription-service

mkvirtualenv -p python3 .virtualenv
source .virtualenv/bin/activate
pip install -r requirements.txt
```

## Run server

### Start mongodb

```
mongod --dbpath /path/to/db
```

### Start flask
```
export FLASK_APP=app.py
flask run
```
