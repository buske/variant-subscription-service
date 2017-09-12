#!/usr/bin/env python

from flask import render_template

from . import create_app

app = create_app()

@app.route('/')
def hello_world():
    return render_template('hello.html')
