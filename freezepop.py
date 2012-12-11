#!/usr/bin/env python
# Freeze Flask as static files & deploy to S3, which backs CloudFront.
#
# Author: semenko
#
""" Auto-deploy Frozen Flask sites to S3-backed CloudFront. """

import argparse
import gzip
import imp
import os
import StringIO
import subprocess
import sys
import time

from base64 import b64encode
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from flask_frozen import Freezer
from hashlib import md5


def main():
    """
    Freeze Aldine and resync S3 staging/prod stores.
    """

    parser = argparse.ArgumentParser(description='The Aldine S3/AWS management script.')

    parser.add_argument('--test', '-t', action='store_true', default=False,
                        dest='freeze_only',
                        help='Test the freeze results. Will NOT deploy.')

    parser.add_argument('--deploy', '-d', action='store_true', default=False,
                        dest='deploy',
                        help='Deploy staging and prod to S3. Will NOT test.')

    parser.add_argument('--no-delete', action='store_true', default=False,
                        dest='no_delete',
                        help='Don\'t delete orphan S3 files.')

    parser.add_argument('--overwrite-all', action='store_true', default=False,
                        dest='overwrite_all',
                        help='Overwrite everything. Useful if metadata changes.')

    parser.add_argument('--no-freeze', action='store_true', default=False,
                        dest='no_freeze',
                        help='Don\'t freeze Flask app first (assumes build/ is current)')

    args = parser.parse_args()

    # Special IAM user: aldine-deploy-bot
    with open('.awskey', 'r') as secret_key:
        os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAJNLD2X37HGDGTUEQ'
        os.environ['AWS_SECRET_ACCESS_KEY'] = secret_key.readline()

    if args.deploy or args.freeze_only:
        # Some flag constraints.
        assert((args.deploy and not args.freeze_only) or (args.freeze_only and not args.no_freeze))

        # Freeze Aldine
        # Per internal app configs, these make "frozen" static copies of these apps in:
        #    ./aldine_frozen/
        if not args.no_freeze:
            print("Freezing Aldine app ...")
            print("*** Look for errors here *** \n")
            aldine = imp.load_source('aldine', 'aldine.py')
            frozen_aldine = Freezer(aldine.app)
            frozen_aldine.freeze()
            print("")
        else:
            print('*** Skipping Flask freeze. Are you sure you wanted that?')

        print('*** Freeze complete!')
        time.sleep(1)

        # Push the frozen apps above to S3, if we want.
        if args.deploy:
            #### Connect to S3
            print('Connecting to AWS...\n')
            conn = S3Connection()

            # Deploy: (conn, frozen_path, remote_bucket)
            deploy_to_s3(conn, 'aldine_frozen', 'prod.aldinetravel.com', args.no_delete, args.overwrite_all)
            time.sleep(1)

        print('All done!')
    else:
        print('Doing nothing. Type -h for help.')

    return True


def deploy_to_s3(conn, frozen_path, bucket_name, no_delete, overwrite_all):
    """ Deploy a frozen app to S3, semi-intelligently. """

    print('*** Preparing to deploy in: %s' % bucket_name)
    time.sleep(1)

    # Get our bucket
    bucket = conn.lookup(bucket_name)
    if not bucket:
        # TODO: Standardize errors. Should we die always? Raise()? Return?
        sys.stderr.write('Cannot find bucket!\n')
        sys.exit(1)

    # Data structures
    cloud_set = set()
    cloud_hashes = {}
    local_set = set()
    local_hashes = {}

    print("Getting cloud file list ...")
    # Make a list of cloud objects & etag hashes
    # NOTE: Boto claims it provides a Content-MD5 value, but it totally lies.
    objects = bucket.list()
    for storage_object in objects:
        # WARN: This is a bit of a hack. Naming files .gz. will break the world.
        # if '.gz.' not in storage_object.name:
        cloud_set.add(storage_object.name)
        cloud_hashes[storage_object.name] = storage_object.etag

    print("Files in cloud: %s" % str(len(cloud_set)))

    # Build local files an a (more complex) hash list for Boto
    for dirname, dirnames, filenames in os.walk(frozen_path):
        # Filter out "~" files.
        for filename in filter(lambda x: not x.endswith("~"), filenames):
            full_path = os.path.join(dirname, filename)
            # TODO: Fix this hack.
            stripped_name = '/'.join(full_path.split('/', 2)[1:])
            local_set.add(stripped_name)
            # Add checksums on files
            cksum = md5()
            cksum.update(open(full_path).read())
            local_hashes[stripped_name] = (cksum.hexdigest(), b64encode(cksum.digest()))

    print("Files on disk: %s" % str(len(local_set)))
    time.sleep(1)

    # Completely missing files
    upload_pending = local_set.difference(cloud_set)
    delete_pending = cloud_set.difference(local_set)

    # Compare local and cloud hashes
    for filename, hashes in local_hashes.iteritems():
        hex_hash, b64hash = hashes
        if overwrite_all or cloud_hashes.get(filename) != '"' + hex_hash + '"':
            # NOTE: AWS overwrites uploads, so no need to delete first.
            upload_pending.add(filename)

    # TODO: Make these much higher when we have good versioning set up.
    cache_times = {'.png': '604800',  # 4 hours
                   '.jpg': '604800',
                   '.js': '14400',
                   '.css': '14400',
                   '.html': '14400',
                   '.ico': '604800',
                   '_DEFAULT_': '14400'
                   }
    def get_headers(extn):
        headers = {}
        exp_seconds = cache_times.get(extn, cache_times['_DEFAULT_'])

        headers['Cache-control'] = 'public, max-age=' + exp_seconds # TODO: fix whenever S3/CloudFront gzip doesn't suck

        # Security-related headers
        if extn in {'.html'}:
            headers['Content-Type'] = 'text/html; charset=UTF-8'
            headers['X-Content-Type-Options'] = 'nosniff'
            headers['X-Frame-Options'] = 'SAMEORIGIN'
            headers['X-XSS-Protection'] = '1; mode=block'
        return headers
        
    # Note: We don't need to setup permission here (e.g. k.make_public()), because there is
    # a bucket-wide AWS policy: http://docs.amazonwebservices.com/AmazonS3/latest/dev/WebsiteAccessPermissionsReqd.html
    # TODO: Do we need those bucket policies since we're using the S3 web hosting route? I don't think so.    
    if len(upload_pending) > 0:
        print("Uploading: %s" % str(len(upload_pending)))
        for upload_file in upload_pending:
            filename, extn = os.path.splitext(upload_file)

            k = Key(bucket)
            k.key = upload_file
            k.set_contents_from_filename(frozen_path + '/' + upload_file, headers=get_headers(extn), md5=local_hashes[upload_file])

            # Setup a gzip copy, too, maybe:
            if extn in {'.html', '.htm', '.css', '.js', '.txt'} and False:
                kgz = Key(bucket)
                kgz.key = filename + '.gz' + extn
                gz_buffer = StringIO.StringIO()
                gz_fh = gzip.GzipFile(mode='wb', compresslevel=9, fileobj=gz_buffer)
                gz_fh.write(open(frozen_path + '/' + upload_file).read())
                gz_fh.close()
                gz_buffer.seek(0)
                kgz.set_contents_from_file(gz_buffer, headers={'Content-Encoding': 'gzip', 'Content-Type': k.content_type})


    # Delete orphans, maybe.
    if len(delete_pending) > 0 and not no_delete:
        print("\nDeleting: %s" % str(len(delete_pending)))
        for delete_file in delete_pending:
            print("\t %s" % str(delete_file))
            bucket.delete_key(delete_file)
            # Try to delete .gz.ext files, too
            filename, extn = os.path.splitext(delete_file)
            bucket.delete_key(filename + '.gz' + extn)

    print('** Successfully deployed: %s!\n' % bucket_name)


if __name__ == '__main__':
    main()
