# Copyright (C) 2016  Ghent University
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# pylint: disable=c0111,c0301,c0325
# !/usr/bin/env python3

import json
import os
# from os.path import expanduser
import socket
import yaml

from flask import Response, request

from pygments import highlight, lexers, formatters


def get_api_dir():
    # return os.environ.get('SOJOBO_API_DIR')
    return '/home/mathijs/Documents/repos/Sojobo-api/files/sojobo_api'


def get_user():
    # return os.environ.get('JUJU_ADMIN_USER')
    return 'tengu-ui'

def get_password():
    # return os.environ.get('JUJU_ADMIN_PASSWORD')
    return '4vQwtSKMNTyRtTfU'

def get_charm_dir():
    # return os.environ.get('LOCAL_CHARM_DIR')
    return '/tmp'


def write_yaml(path, content):
    with open(path, "w") as y_file:
        yaml.dump(content, y_file, default_flow_style=True)


def create_response(http_code, return_object):
    if request_wants_json():
        return Response(
            json.dumps(return_object),
            status=http_code,
            mimetype='application/json',
        )
    else:
        formatted_json = json.dumps(return_object, indent=4)
        formatter = formatters.HtmlFormatter( #pylint: disable=E1101
            full=True,
            title="{} returns:".format(socket.gethostname())
        )
        colorful_json = highlight(formatted_json, lexers.JsonLexer(), formatter) # pylint: disable=E1101
        return Response(
            colorful_json,
            status=http_code,
            mimetype='text/html',
        )


def request_wants_json():
    best = request.accept_mimetypes \
        .best_match(['application/json', 'text/html'])
    return best == 'application/json' and \
        request.accept_mimetypes[best] > \
        request.accept_mimetypes['text/html']


# def get_controllers(name):
#     with open(expanduser('~/.local/share/juju/controllers.yaml'))as c_file:
#         c_contents = yaml.safe_load(c_file)
#     return {
#         'controllers': {
#             name : c_contents['controllers'][name]
#         }
#     }