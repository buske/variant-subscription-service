#!/usr/bin/env python

from flask import render_template

from . import create_app
from .extensions import mongo

app = create_app()

@app.route('/v/<variant>')
def variant_detail(variant):
    variant = mongo.db.variants.find_one_or_404({'_id': variant})
    return render_template('variant.html', variant=variant)
