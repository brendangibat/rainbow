#!/usr/bin/env python
#
# Copyright 2014 DoAT. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY DoAT ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL DoAT OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are
# those of the authors and should not be interpreted as representing official
# policies, either expressed or implied, of DoAT

import argparse
import pprint
import sys
import yaml
import logging
from rainbow.datasources import DataSourceCollection
from rainbow.preprocessor import Preprocessor
from rainbow.templates import TemplateLoader
from rainbow.cloudformation import Cloudformation, StackFailStatus, StackSuccessStatus


def main():  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('rainbow')

    parser = argparse.ArgumentParser(description='Load cloudformation templates with cool data sources as arguments')
    parser.add_argument('-d', '--data-source', metavar='DATASOURCE', dest='datasources', action='append', default=[],
                        help='Data source. Format is data_sourcetype:data_sourceargument. For example, ' +
                             'cfn_outputs:[region:]stackname, cfn_resources:[region:]stackname, or ' +
                             'yaml:yamlfile. First match is used')
    parser.add_argument('-r', '--region', default='us-east-1', help='AWS region')
    parser.add_argument('-n', '--noop', action='store_true',
                        help="Don't actually call aws; just show what would be done.")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--dump-datasources', action='store_true',
                        help='Simply output all datasources and their values')
    parser.add_argument('--update-stack', action='store_true',
                        help='Update a pre-existing stack rather than create a new one')
    parser.add_argument('--block', action='store_true',
                        help='Track stack creation, if the stack creation failed, exits with a non-zero exit code')

    parser.add_argument('-b', '--bucket', help='The bucket to store Cloudformation template within S3.')
    parser.add_argument('-f', '--filename', help='The filename to store the Cloudformation template as within S3.')
    parser.add_argument('-t', '--timeout', help='The timeout for s3 communication.')

    parser.add_argument('stack_name')
    parser.add_argument('templates', metavar='template', type=str, nargs='+')

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    Cloudformation.default_region = args.region
    datasource_collection = DataSourceCollection(args.datasources, args.bucket)

    # load and merge templates
    template = TemplateLoader.load_templates(args.templates)

    # preprocess computed values
    preprocessor = Preprocessor(datasource_collection=datasource_collection, region=args.region)
    template = preprocessor.process(template)

    # build list of parameters for stack creation/update from datasources
    parameters = Cloudformation.resolve_template_parameters(template, datasource_collection)

    if args.dump_datasources:
        pprint.pprint(datasource_collection)
        return

    logger.debug('Will create stack "%s" with parameters: %r', args.stack_name, parameters)
    logger.debug('Template:\n%s', yaml.dump(template))

    if args.noop:
        logger.info('NOOP mode. exiting')
        return

    cloudformation = Cloudformation(args.region)

    if args.block:
        # set the iterator prior to updating the stack, so it'll begin from the current bottom
        stack_events_iterator = cloudformation.tail_stack_events(args.stack_name, None if args.update_stack else 0)

    if args.update_stack:
        cloudformation.update_stack(args.stack_name, template, parameters, args.bucket, args.filename, args.timeout)
    else:
        cloudformation.create_stack(args.stack_name, template, parameters, args.bucket, args.filename, args.timeout)

    if args.block:
        for event in stack_events_iterator:
            if isinstance(event, StackFailStatus):
                logger.warn('Stack creation failed: %s', event)
                sys.exit(1)
            elif isinstance(event, StackSuccessStatus):
                logger.info('Stack creation succeeded: %s', event)
            else:
                logger.info('%(resource_type)s %(logical_resource_id)s %(physical_resource_id)s %(resource_status)s '
                            '%(resource_status_reason)s', event)

if __name__ == '__main__':  # pragma: no cover
    main()
