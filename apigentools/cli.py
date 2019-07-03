# (C) Datadog, Inc. 2019
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)

import argparse
import logging
import os
import sys

from apigentools.config import Config
from apigentools.constants import CONFIG_FILE, OPENAPI_GENERATOR_GIT
from apigentools.commands import all_commands
from apigentools.utils import change_cwd, env_or_val, get_current_commit, set_log, set_log_level

log = logging.getLogger(__name__)


def get_cli_parser():
    p = argparse.ArgumentParser(
        description="Script for manipulating Datadog's OpenAPI spec and generating client code from it",
    )
    p.add_argument(
        "-r", "--spec-repo-dir",
        default=env_or_val("APIGENTOOLS_SPEC_REPO_DIR", "."),
        help="Switch to this directory before doing anything else",
    )
    p.add_argument(
        "-c", "--config-dir",
        default=env_or_val("APIGENTOOLS_CONFIG_DIR", "config"),
        help="Path to config directory (default: 'config')",
    )
    p.add_argument(
        "-v", "--verbose",
        default=env_or_val("APIGENTOOLS_VERBOSE", False),
        action='store_true',
        help="Whether or not to log the generation in verbose mode",
    )
    sp = p.add_subparsers(dest="action", required=True)

    generate_parser = sp.add_parser(
        "generate",
        help="Generate client code"
    )
    generate_parser.add_argument(
        "-s", "--spec-dir",
        default=env_or_val("APIGENTOOLS_SPEC_DIR", "spec"),
        help="Path to directory with OpenAPI specs (default: 'spec')",
    )
    generate_parser.add_argument(
        "-f", "--full-spec-file",
        default=env_or_val("APIGENTOOLS_FULL_SPEC_FILE", "full_spec.yaml"),
        help="Name of the OpenAPI full spec file to write (default: 'full_spec.yaml')",
    )
    generate_parser.add_argument(
        "-g", "--generated-code-dir",
        default=env_or_val("APIGENTOOLS_GENERATED_CODE_DIR", "generated"),
        help="Path to directory where to save the generated code (default: 'generated')",
    )
    generate_parser.add_argument(
        "--additional-stamp",
        nargs="*",
        help="Additional components to add to the 'apigentoolsStamp' variable passed to templates",
        default=[],
    )
    generate_parser.add_argument(
        "-i", "--generated-with-image",
        default=env_or_val("APIGENTOOLS_IMAGE", "NO IMAGE!"),
        help="Override the tag of the image with which the client code was generated",
    )
    generate_parser.add_argument(
        "-d", "--downstream-templates-dir",
        default=env_or_val("APIGENTOOLS_DOWNSTREAM_TEMPLATES_DIR", "downstream-templates"),
        help="Path to directory with downstream templates (default: 'downstream-templates')",
    )

    template_group = generate_parser.add_mutually_exclusive_group()
    template_group.add_argument(
        "-t", "--template-dir",
        default=env_or_val("APIGENTOOLS_TEMPLATES_DIR", "templates"),
        help="Path to directory with processed upstream templates (default: 'templates')",
    )
    template_group.add_argument(
        "--builtin-templates",
        action="store_true",
        default=False,
        help="Use unpatched upstream templates",
    )

    templates_parser = sp.add_parser(
        "templates",
        help="Get upstream templates and apply downstream patches",
    )
    templates_parser.add_argument(
        "-o", "--output-dir",
        default=env_or_val("APIGENTOOLS_TEMPLATES_DIR", "templates"),
        help="Path to directory where to put processed upstream templates (default: 'templates')",
    )
    templates_parser.add_argument(
        "-p", "--template-patches-dir",
        default=env_or_val("APIGENTOOLS_TEMPLATE_PATCHES_DIR", "template-patches"),
        help="Directory with patches for upstream templates (default: 'template-patches')",
    )
    templates_source = templates_parser.add_subparsers(
        dest="templates_source",
        required=True,
        help="Source of upstream templates"
    )
    jar_parser = templates_source.add_parser(
        "openapi-jar",
        help="Obtain upstream templates from openapi-generator jar",
    )
    jar_parser.add_argument(
        "jar_path",
        help="Path to openapi-generator jar file",
    )
    local_parser = templates_source.add_parser(
        "local-dir",
        help="Obtain upstream templates from a local directory",
    )
    local_parser.add_argument(
        "local_path",
        help="Path to directory with upstream templates",
    )
    git_parser = templates_source.add_parser(
        "openapi-git",
        help="Obtain upstream templates from openapi-generator git repository",
    )
    git_parser.add_argument(
        "-u", "--repo_url",
        default=OPENAPI_GENERATOR_GIT,
        help="URL of the openapi-generator repo (default: '{}')".format(OPENAPI_GENERATOR_GIT),
    )
    git_parser.add_argument(
        "git_committish",
        default="master",
        nargs="?",
        help="Git 'committish' to check out before obtaining templates (default: 'master')"
    )

    validate_parser = sp.add_parser(
        "validate",
        help="Validate OpenAPI spec",
    )
    # these are duplicated with generate_parser, we should deduplicate
    validate_parser.add_argument(
        "-s", "--spec-dir",
        default=env_or_val("APIGENTOOLS_SPEC_DIR", "spec"),
        help="Path to directory with OpenAPI specs (default: 'spec')",
    )
    validate_parser.add_argument(
        "-f", "--full-spec-file",
        default=env_or_val("APIGENTOOLS_FULL_SPEC_FILE", "full_spec.yaml"),
        help="Name of the OpenAPI full spec file to write (default: 'full_spec.yaml')",
    )

    test_parser = sp.add_parser(
        "test",
        help="Run tests for generated code"
    )
    test_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=env_or_val("APIGENTOOLS_TEST_BUILD_NO_CACHE", False),
        help="Build test image with --no-cache option",
    )
    test_parser.add_argument(
        "-g", "--generated-code-dir",
        default=env_or_val("APIGENTOOLS_GENERATED_CODE_DIR", "generated"),
        help="Path to directory where to save the generated code (default: 'generated')",
    )

    split_parser = sp.add_parser(
        "split",
        help="Split single OpenAPI spec file into multiple files"
    )
    split_parser.add_argument(
        "-i", "--input-file",
        required=True,
        help="Path to the OpenAPI full spec file to split",
    )
    split_parser.add_argument(
        "-s", "--spec-dir",
        default=env_or_val("APIGENTOOLS_SPEC_DIR", "spec"),
        help="Path to directory with OpenAPI specs (default: 'spec')",
    )
    split_parser.add_argument(
        "-v", "--api-version",
        default=env_or_val("APIGENTOOLS_SPLIT_SPEC_VERSION", "v1"),
        help="Version of API that the input spec describes (default: 'v1')",
    )
    return p


def cli():
    toplog = logging.getLogger(__name__.split(".")[0])
    set_log(toplog)
    args = get_cli_parser().parse_args()
    if args.verbose:
        set_log_level(toplog, logging.DEBUG)

    with change_cwd(args.spec_repo_dir):
        config = Config.from_file(os.path.join(args.config_dir, CONFIG_FILE))
        command_class = all_commands[args.action]
        command = command_class(config, args)
        sys.exit(command.run())