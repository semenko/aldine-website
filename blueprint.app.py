#!/usr/bin/env python

import jinja2
import logging
import os
import re
import subprocess
import urlparse
from flask import abort, Blueprint, Flask, make_response, redirect, render_template, send_from_directory, url_for
app = Flask(import_name=__name__, static_folder='s')
app.url_generators = []  # Hold URL generator functions.


###
# Create a static() handler for templates.
# This serves static content from either:
#   /s/ or static.aldinetravel.com
###
def static(path):
    root = app.config.get('STATIC_ROOT', None)
    if root is None:  # Just use /s/ instead of CDN
        return url_for('static', filename=path)
    return urlparse.urljoin(root, path)


@app.context_processor
def inject_static():
    return dict(static=static)


#################################
# Blocks for URL Control
#################################


template_page = Blueprint('template_page', __name__,
                          template_folder='templates')

@template_page.route('/', defaults={'page': 'index'})
@template_page.route('/<page>.html')
def show(page):
    try:
        return render_template('pages/%s.html' % page)
    except jinja2.TemplateNotFound:
        abort(404)

app.register_blueprint(template_page)



######
# *** Odd URLs and support functions
######

# Return favicon from the root path
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 's'),
                               'favicon.ico', mimetype='image/x-icon')

# Return robotos from the root path
@app.route('/robots.txt')
def robots():
    return send_from_directory(os.path.join(app.root_path, 's'),
                               'robots.txt', mimetype='text/plain')

@app.route('/openid')
def openid():
    return send_from_directory(os.path.join(app.root_path, 's'),
                               'openid', mimetype='application/xrds+xml')

@app.route('/.well-known/host-meta')
def host_meta():
    return send_from_directory(os.path.join(app.root_path, 's'),
                               'host-meta', mimetype='text/plain')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5002, debug=True)
else:
    # We're probably being Frozen. Cool.
    app.config['FREEZER_DESTINATION'] = './.app_frozen/'

    app.config['prod'] = True
    # We don't really support SSL given Cloudfront, but ...
    app.config['STATIC_ROOT'] = '//d1tse6dhitxps4.cloudfront.net/s/'
