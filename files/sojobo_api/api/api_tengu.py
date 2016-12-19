# !/usr/bin/env python3
# Copyright (C) 2016  Qrama
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
# pylint: disable=c0111,c0301,c0325,w0406,e0401
###############################################################################
# CONTROLLER FUNCTIONS
###############################################################################
import shutil

from flask import send_file, request, Blueprint
from api import w_errors as errors, w_juju as juju
from sojobo_api import create_response, get_api_dir


TENGU = Blueprint('tengu', __name__)


def get():
    return TENGU


@TENGU.route('/', methods=['GET'])
def get_all_info():
    try:
        token = juju.authenticate(request.args['api_key'], request.authorization)
        code, response = 200, juju.get_all_info(token)  # ToDo: write this function
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>', methods=['GET'])
def get_controller_info(controller):
    data = request.args
    try:
        juju.authenticate(data['api_key'], request.authorization)
        code, response = 200, juju.get_controller_info(controller)
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>', methods=['POST'])
def create_controller(controller):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization)
        if token.is_admin:
            if juju.controller_exists(controller):
                code, response = errors.already_exists('controller')
            elif 'file' in request.files:
                cfile = request.files['file']
                cfile.save('{}/files'.format(get_api_dir), '{}.json'.format(data['credentials']['project-id']))
                response = juju.create_controller(token, data['type'], controller, data['region'],
                                                  data['credentials'], cfile)
            else:
                response = juju.create_controller(token, data['type'], controller, data['region'], data['credentials'])
            code = 200
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>', methods=['DELETE'])
def delete_controller(controller):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller)
        if token.c_access == 'superuser':
            code, response = 200, juju.delete_controller(token)
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/backup', methods=['GET'])
def backup_controllers():
    try:
        token = juju.authenticate(request.args['api_key'], request.authorization)
        if token.is_admin:
            apidir = get_api_dir()
            homedir = '/home/ubuntu/.local/share/juju'
            shutil.copy2('{}/install_credentials.py'.format(apidir), '{}/backup/install_credentials.py'.format(apidir))
            shutil.copy2('{}/clouds.yaml'.format(homedir), '{}/backup/clouds.yaml'.format(apidir))
            shutil.copy2('{}/credentials.yaml'.format(homedir), '{}/backup/credentials.yaml'.format(apidir))
            shutil.copy2('{}/controllers.yaml'.format(homedir), '{}/backup/controllers.yaml'.format(apidir))
            shutil.make_archive('{}/backup'.format(apidir), 'zip', '{}/backup/'.format(apidir))
            return send_file('{}/backup.zip'.format(apidir))
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>', methods=['GET'])
def get_model_info(controller, model):
    data = request.args
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        code, response = 200, juju.get_model_info(token)
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>', methods=['PUT'])
def create_model(controller, model):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller)
        if juju.model_exists(controller, model):
            code, response = errors.already_exists('model')
        elif token.c_access == 'add-model' or token.c_access == 'superuser':
            juju.create_model(token, model, data.get('ssh_key', None))
            code, response = 200, {'model-name': token.m_name,
                                   'model-fullname': token.m_shared_name(),
                                   'gui-url': juju.get_gui_url(token)}
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>', methods=['DELETE'])
def delete():
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, data['controller'], data['model'])
        if token.m_access == 'admin':
            juju.delete_model(token)
            code, response = 200, 'The model has been destroyed'
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/sshkey', methods=['PUT'])
def add_ssh_key(controller, model):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if token.m_access == 'admin':
            juju.add_ssh_key(token, data['ssh_key'])
            code, response = 200, 'The ssh-key has been added'
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/sshkey', methods=['DELETE'])
def remove_ssh_key(controller, model):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if token.m_access == 'admin':
            juju.remove_ssh_key(token, data['ssh_key'])
            code, response = 200, 'The ssh-key has been removed'
        else:
            code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/applications/<application>', methods=['GET'])
def get_application_info(controller, model, application):
    try:
        token = juju.authenticate(request.args['api_key'], request.authorization, controller, model)
        if juju.app_exists(token, application):
            code = 200
            response = {'info': juju.get_app_info(token, application),
                        'config': juju.config(token, application)}
        else:
            code, response = errors.does_not_exist('application')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/applications/<application>', methods=['PUT'])
def add_application(controller, model, application):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.app_exists(token, application):
            code, response = errors.already_exists('application')
        else:
            if token.m_access == 'write' or token.m_access == 'admin':
                series = data.get('series', None)
                machine = data.get('target', None)
                if machine is None and series is None:
                    code, response = 200, juju.deploy_app(token, application)
                elif machine is None and juju.app_supports_series(application, series):
                    code, response = 200, juju.deploy_app(token, application, series)
                elif juju.machine_matches_series(token, machine, series) and series is None:
                    code, response = 200, juju.deploy_app(token, application, None, series)
                elif juju.machine_matches_series(token, machine, series) and juju.app_supports_series(application, series):
                    code, response = 200, juju.deploy_app(token, application, series, machine)
                elif juju.machine_matches_series(token, machine, series):
                    code, response = 400, 'The application does not support this version of Ubuntu'
                elif juju.app_supports_series(application, series):
                    code, response = 400, 'Target and application have a different version of Ubuntu'
                else:
                    code, response = 400, 'Target and application have a different Ubuntu version, the application is not available in this version'
            else:
                code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/applications/<application>', methods=['DELETE'])
def remove_app(controller, model, application):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.app_exists(token, application):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.remove_app(token, application)
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.does_not_exist('application')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/machines/<machine>', method=['GET'])
def get_machine_info(controller, model, machine):
    data = request.args
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.machine_exists(token, machine):
            code, response = 200, juju.get_machine_info(token, machine)  # ToDo: write function
        else:
            code, response = errors.does_not_exist('machine')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/machines/<machine>', methods=['PUT'])
def add_machine(controller, model, machine):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.machine_exists(token, machine):
            code, response = errors.already_exists('machine')
        else:
            if token.m_access == 'write' or token.m_access == 'admin':
                series = data.get('series', None)
                if series is None:
                    code, response = 200, juju.add_machine(token)
                elif juju.cloud_supports_series(token, series):
                    code, response = 200, juju.add_machine(token, series)
                else:
                    code, response = 400, 'This cloud does not support this version of Ubuntu'
            else:
                code, response = errors.no_permission()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/machines/<machine>', methods=['DELETE'])
def remove_machine(controller, model, machine):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.machine_exists(token, machine):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.remove_machine(token, machine)
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.does_not_exist('machine')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/<application>/unit', methods=['PUT'])
def add_unit(controller, model, application):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.app_exists(token, application):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.add_unit(token, application, data.get('target', None))
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.does_not_exist('application')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/<application>/<unitnumber>', methods=['DELETE'])
def remove_unit(controller, model, application, unitnumber):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        unit = '{}/{}'.format(application, unitnumber)
        if juju.unit_exists(token, unit):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.remove_unit(token, unit)
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.does_not_exist('unit')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/relation', methods=['POST'])
def add_relation(controller, model):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        app1, app2 = data['app1'], data['app2']
        if juju.app_exists(token, app1) and juju.app_exists(token, app2):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.add_relation(token, app1, app2)
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.does_not_exist('application')
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})


@TENGU.route('/<controller>/<model>/<app1>/<app2>', methods=['DELETE'])
def remove_relation(controller, model, app1, app2):
    data = request.json
    try:
        token = juju.authenticate(data['api_key'], request.authorization, controller, model)
        if juju.app_exists(token, app1) and juju.app_exists(token, app2):
            if token.m_access == 'write' or token.m_access == 'admin':
                code, response = 200, juju.remove_relation(token, app1, app2)
            else:
                code, response = errors.no_permission()
        else:
            code, response = errors.no_app()
    except KeyError:
        code, response = errors.invalid_data()
    return create_response(code, {'message': response})
