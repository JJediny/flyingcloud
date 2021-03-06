#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Build an Application Bundle zipfile for Elastic Beanstalk deployment."""

from __future__ import print_function, absolute_import

import argparse
import datetime
import imp
import json
import os
import zipfile

from .vcs import find_vcs
from .archive import abspath, zip_add_directory, zip_write_directory, check_zipfile


VERSION = "0.2.1"


def parse_args(args=None, namespace=None):
    parser = argparse.ArgumentParser(
        description="Package a Cookbrite application "
                    "for deployment to Elastic Beanstalk.",
    )
    parser.add_argument(
        'package_path',
        nargs="?", default=".",
        help="Where the application lives"
    )

    parser.add_argument(
        '-V', '--version', action='version', version=VERSION,
        help="show program's version number and exit")

    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help="Be more verbose")

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true', default=False,
        help="Show what would be generated.")

    parser.add_argument(
        '--prefix', '-p',
        help="Prefix the zipfile_name with this string.  Default: %(default)r")

    parser.add_argument(
        '--emit-build-info-only', '-e',
        action='store_true', default=False,
        help="Emit the version.json file and exit")

    # TODO: get rid of --aux-package and --packages.
    # Bootstrap's --make-local-packages supersedes them.
    parser.add_argument(
        '--aux-package', '-a',
        nargs=2, metavar=('PACKAGE_PATH', 'PREFIX_DIR'),
        help="Auxiliary package")

    parser.add_argument(
        '--packages', '-P',
        nargs=3, metavar=('MODULE_PATH', 'FUNC', 'TARGET_DIR'),
        help="Additional third-party packages")

    parser.add_argument(
        '--build-number', '-b',
        default=12345, type=int,
        help="Build number to set (used in /version/ API response)")

    return parser.parse_args(args, namespace)


def initialize_namespace(namespace):
    namespace.package_path = abspath(namespace.package_path)
    namespace.vcs = find_vcs(namespace.package_path)
    namespace.build_time = datetime.datetime.utcnow()  # Bamboo and EB are on UTC
    namespace.build_time_str = namespace.build_time.strftime("%Y%m%dt%H%M")
    namespace.version_format = '{build_date}-{branch_name}-b{build_number:05d}-{sha}'
    namespace.version_data = build_version_data(namespace)
    namespace.version_label = namespace.version_format.format(**namespace.version_data)
    namespace.zipfile_name = '{prefix}-{version_label}.zip'.format(**namespace.__dict__)


def build_version_data(namespace):
    version_data = dict(
        build_date=namespace.build_time_str,
        branch_name=(namespace.vcs.current_branch() if namespace.vcs else os.getenv(
            "bamboo_repository_branch_name", "unknown")).replace('/', '-'),
        sha=(namespace.vcs.sha() if namespace.vcs else os.getenv("bamboo_repository_revision_number", "unknown"))[:7],
        build_number=namespace.build_number,
        )
    return version_data


def build_info(namespace):
    info = namespace.version_data.copy()
    info['version'] = namespace.version_label
    return info


def emit_build_info(namespace):
    info = build_info(namespace)
    json_info = json.dumps(info, indent=4)
    if not namespace.dry_run:
        with open(os.path.join(namespace.package_path, "version.json"), "w") as f:
            f.write(json_info)
            f.write('\n')
    if namespace.verbose:
        print(json_info)
    return info


def zip_package(namespace, exclude_dirs=None):
    exclude_dirs = exclude_dirs or ['.git', '.idea', '.main', '.env']
    exclude_extensions = ('.pyc', '.zip', '.log', '.dump', '.pb', '.sqlite', '.coverage', '.egg-info', '.o', '.dump.gz')
    exclude_filenames = ('TAGS', 'gusteaut')

    if not namespace.dry_run:
        with zipfile.ZipFile(
                namespace.zipfile_name, "w", zipfile.ZIP_DEFLATED) as zip_archive:
            logger = print if namespace.verbose else lambda x: None
            zip_add_directory(
                zip_archive, namespace.package_path,
                exclude_dirs, exclude_extensions, exclude_filenames,
                logger=logger)

            # TODO: get rid of --aux-package and --packages.
            # Bootstrap's --make-local-packages supersedes them.
            if namespace.aux_package:
                source_dir, prefix_dir = namespace.aux_package
                zip_add_directory(
                    zip_archive, source_dir,
                    exclude_dirs=exclude_dirs, exclude_extensions=exclude_extensions,
                    prefix_dir=prefix_dir, logger=logger)

            if namespace.packages:
                module_path, func, target_dir = namespace.packages
                module = imp.load_source("tmp_pkg", module_path)
                full_filenames = list(getattr(module, func)())

                dirpath = os.path.split(full_filenames[0])[0]
                filenames = []
                for f in full_filenames:
                    dir, filename = os.path.split(f)
                    assert dir == dirpath
                    filenames.append(filename)

                zip_write_directory(
                    zip_archive,
                    target_dir,
                    dirpath,
                    filenames,
                    logger=logger
                )

    check_zipfile(namespace.zipfile_name)

    return namespace.zipfile_name


def package_build(args=None, exclude_dirs=None):
    zipfile_name = None
    namespace = parse_args(args)
    initialize_namespace(namespace)
    emit_build_info(namespace)
    if not namespace.emit_build_info_only:
        zipfile_name = zip_package(namespace, exclude_dirs=exclude_dirs)
    return zipfile_name


if __name__ == '__main__':
    zipfile_name = package_build()
    print(zipfile_name)  # For capture by calling scripts
