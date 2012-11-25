# Aldine Travel

This repository backs [Aldine Travel](http://www.aldinetravel.com/) (a [Flask](http://flask.pocoo.org/) app).

## Overview

This site is frozen via [Frozen-Flask](http://packages.python.org/Frozen-Flask/) then pushed to S3 which backs a CloudFront endpoint.

## Directories

* (Site)/s/
  * Static files. Usually loaded via static.DOMAIN.com via CloudFront
* (Site)/templates/
  * [Jinja2](http://jinja.pocoo.org/) templates for Flask.

## Copyright

Some shared libraries are available via an Apache License v2.0 (e.g. BootStrap)

All other work is Copyright 2012, Aldine Travel, Inc. All rights reserved.
