#!/usr/bin/env python

from flask import render_template
from flask_pymongo import PyMongo

from . import create_app

app = create_app()
mongo = PyMongo(app)

@app.route('/')
def hello_world():
    return render_template('home.html')

@app.route('/v/<variant>')
def variant_detail(variant):
    variant = mongo.db.variants.find_one_or_404({'_id': variant})
    return render_template('variant.html', variant=variant)
