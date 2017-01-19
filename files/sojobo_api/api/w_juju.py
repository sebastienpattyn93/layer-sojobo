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
# pylint: disable=c0111,c0301,c0325,c0103,r0204,r0913,r0902,e0401
import base64
import hashlib
from importlib import import_module
import json
import os
from subprocess import check_call, check_output, STDOUT, CalledProcessError
import requests
import yaml
from sojobo_api import get_api_dir
from flask import abort
from api import w_errors as errors
################################################################################
# TENGU FUNCTIONS
################################################################################
def get_user():
    return os.environ.get('JUJU_ADMIN_USER')


def get_password():
    return os.environ.get('JUJU_ADMIN_PASSWORD')


def get_charm_dir():
    return os.environ.get('LOCAL_CHARM_DIR')


def get_controller_types():
    c_list = {}
    for f_path in os.listdir('{}/controllers'.format(get_api_dir())):
        if 'controller_' in f_path and '.pyc' not in f_path:
            name = f_path.split('.')[0]
            c_list[name.split('_')[1]] = import_module('controllers.{}'.format(name))
    return c_list


def app_supports_series(app_name, series):
    if 'local:' in app_name:
        with open('{}/{}/metadata.yaml'.format(get_charm_dir(), app_name.split(':')[1])) as data:
            supports = series in yaml.load(data)['series']
    else:
        supports = False
        data = requests.get('https://api.jujucharms.com/v4/{}/expand-id'.format(app_name))
        for value in json.loads(data.text):
            if series in value['Id']:
                supports = True
                break
    return supports


def cloud_supports_series(token, series):
    return series in get_controller_types()[token.c_token.type].get_supported_series()


def output_pass(commands, controller=None, model=None):
    if controller is not None and model is not None:
        commands.extend(['-m', '{}:{}'.format(controller, model)])
    elif controller is not None:
        commands.extend(['-c', controller])
    try:
        result = check_output(commands, input=bytes('{}\n'.format(get_password()), 'utf-8'), stderr=STDOUT).decode('utf-8')
    except CalledProcessError as e:
        msg = e.output.decode('utf-8')
        if 'no credentials provided' in msg:
            check_output(['juju', 'login', get_user()], input=bytes('{}\n'.format(get_password()), 'utf-8'))
            result = output_pass(commands)
        else:
            error = errors.cmd_error(msg)
            abort(error[0], error[1])
    return result


def check_login(auth):
    if auth.username == get_user():
        result = auth.password == get_password()
    else:
        try:
            check_output(['juju', 'logout'], stderr=STDOUT)
            check_output(['juju', 'login', auth.username, '-c', get_all_controllers()[0]],
                         input=bytes('{}\n'.format(auth.password), 'utf-8'), stderr=STDOUT)
            result = True
            check_call(['juju', 'logout'])
        except CalledProcessError as e:
            result = 'invalid entity name or password (unauthorized access)' in e.output.decode('utf-8')
        except (TypeError, IndexError):
            result = False
    return result


class JuJu_Token(object):
    def __init__(self, auth):
        self.username = auth.username
        self.password = auth.password
        self.is_admin = self.set_admin()
        self.c_name = None
        self.c_access = None
        self.c_token = None
        self.m_name = None
        self.m_access = None

    def set_controller(self, c_name):
        c_type, c_endpoint = controller_info(c_name)
        self.c_name = c_name
        self.c_access = get_controller_access(self, self.username)
        self.c_token = getattr(get_controller_types()[c_type], 'Token')(c_endpoint, self.username, self.password)
        return self

    def set_model(self, modelname):
        self.m_name = modelname
        if self.c_access == 'superuser':
            self.m_access = 'admin'
        else:
            self.m_access = get_model_access(self, self.username)
        return self

    def m_shared_name(self):
        return "{}/{}".format(get_user(), self.m_name)

    def set_admin(self):
        return self.username == get_user() and self.password == get_password()


def authenticate(api_key, auth, controller=None, modelname=None):
    with open('{}/api-key'.format(get_api_dir()), 'r') as key:
        apikey = key.readlines()[0]
    if api_key != apikey or not check_login(auth):
        error = errors.unauthorized()
        abort(error[0], error[1])
    token = JuJu_Token(auth)
    if controller is not None and controller_exists(controller):
        if token.set_controller(controller).c_access is None:
            error = errors.no_access('controller')
            abort(error[0], error[1])
        if modelname is not None and model_exists(controller, modelname):
            if token.set_model(modelname).m_access:
                error = errors.no_access('model')
                abort(error[0], error[1])
        elif modelname is not None and not model_exists(controller, modelname):
            error = errors.does_not_exist('model')
            abort(error[0], error[1])
    elif not controller_exists(controller) and controller is not None:
        error = errors.does_not_exist('controller')
        abort(error[0], error[1])
    return token
###############################################################################
# CONTROLLER FUNCTIONS
###############################################################################
def create_controller(c_type, name, region, credentials):
    exists = False
    for key, value in get_controller_types().items():
        if c_type == key:
            value.create_controller(name, region, credentials)
            pswd = os.environ.get('JUJU_ADMIN_PASSWORD')
            check_output(['juju', 'change-user-password', get_user(), '-c', name], input=bytes('{}\n{}\n'.format(pswd, pswd), 'utf-8'))
            exists = True
            break
    if not exists:
        output = 'Incorrect controller type. Supported options are: {}'.format(get_controller_types().keys())
    return output


def controller_info(c_name):
    with open('/home/ubuntu/.local/share/juju/controllers.yaml') as data:
        controller = yaml.load(data)['controllers'][c_name]
    return controller['cloud'], controller['api-endpoints'][-1].split(':')[0]


def delete_controller(token):
    check_call(['juju', 'destroy-controller', token.c_name, '-y'])
    check_call(['juju', 'remove-credential', token.c_token.type, token.c_name])
    return get_controllers_info(token)


def get_all_controllers():
    controllers = json.loads(output_pass(['juju', 'controllers', '--format', 'json']))
    try:
        result = list(controllers['controllers'].keys())
    except AttributeError:
        result = []
    return result


def controller_exists(c_name):
    return c_name in get_all_controllers()


def get_controller_access(token, username):
    users = json.loads(output_pass(['juju', 'users', '--format', 'json'], token.c_name))
    result = None
    for user in users:
        if user['user-name'] == username:
            access = user['access']
            if c_access_exists(access):
                result = access
    return result


def get_controllers_info(token):
    return [get_controller_info(token) for c in get_all_controllers() if token.set_controller(c).c_access is not None]


def get_controller_info(token):
    if token.c_access is not None:
        result = {'name': token.c_name, 'type': token.c_token.type, 'models': get_models_info(token),
                  'users': get_users_controller(token)}
    else:
        result = None
    return result


def c_access_exists(access):
    return access in ['login', 'add-model', 'superuser']
###############################################################################
# MODEL FUNCTIONS
###############################################################################
def get_all_models(controller):
    data = json.loads(output_pass(['juju', 'list-models', '--format', 'json'], controller))
    return [model['name'] for model in data['models']]


def model_exists(controller, model):
    return model in get_all_models(controller)


def get_model_access(token, username):
    check_call(['juju', 'switch', '{}:{}'.format(token.c_name, token.m_name)])
    model_info = json.loads(check_output(['juju', 'show-model', '--format', 'json']).decode('utf-8'))
    try:
        access = model_info[token.m_name]['users'][username]['access']
    except KeyError:
        access = None
    return access


def m_access_exists(access):
    return access in ['read', 'write', 'admin']


def get_models_info(token):
    return [get_model_info(token) for m in get_all_models(token.c_name) if token.set_model(m).m_access is not None]


def get_model_info(token):
    if token.m_access is not None:
        result = {'name': token.m_name, 'users': get_users_model(token), 'ssh-keys': get_ssh_keys(token),
                  'applications': get_applications_info(token), 'machines': get_machines_info(token),
                  'juju-gui-url': get_gui_url(token)}
    else:
        result = None
    return result


def get_ssh_keys(token):
    return output_pass(['juju', 'ssh-keys', '--full'], token.c_name, token.m_name).split('\n')[1:-1]


def get_applications_info(token):
    data = json.loads(output_pass(['juju', 'status', '--format', 'json'], token.c_name, token.m_name))
    result = []
    for name, info in data['applications'].items():
        res1 = {'name': name, 'relations': info['relations']}
        try:
            units = info['units'].items()
            res1['units'] = []
            for unit, uinfo in units:
                res1['units'].append({'name': unit, 'machine': uinfo['machine'], 'ip': uinfo['public-address'],
                                      'ports': uinfo.get('open-ports', None)})
        except KeyError:
            pass
        result.append(res1)
    return result


def get_units_info(token, application):
    data = json.loads(output_pass(['juju', 'machines', '--format', 'json'], token.c_name, token.m_name))[application]['units']
    return [{'name': u, 'machine': ui['machine'], 'ip': ui['public-address'],
             'ports': ui['open-ports']} for u, ui in data.items()]


def get_machines_info(token):
    data = json.loads(output_pass(['juju', 'machines', '--format', 'json'], token.c_name, token.m_name))['machines'].keys()
    return [get_machine_info(token, m) for m in data]


def get_machine_info(token, machine):
    data = json.loads(output_pass(['juju', 'machines', '--format', 'json'], token.c_name, token.m_name))['machines'][machine]
    try:
        containers = None
        if 'containers' in data.keys():
            containers = [{'name': c, 'ip': ci['dns-name'], 'series': ci['series']} for c, ci in data['containers'].items()]
        result = {'name': machine, 'instance-id': data['instance-id'], 'ip': data['dns-name'], 'series': data['series'], 'containers': containers}
    except KeyError:
        result = {'name': machine, 'instance-id': 'Unknown', 'ip': 'Unknown', 'series': 'Unknown', 'containers': 'Unknown'}
    return result


def get_gui_url(token):
    data = output_pass(['juju', 'gui', '--no-browser'], token.c_name, token.m_name).rstrip().split(':')[2]
    url = json.loads(output_pass(['juju', 'machines', '--format', 'json'], token.c_name, 'controller'))['machines']['0']['dns-name']
    return 'https://{}:{}'.format(url, data)


def create_model(token, model, ssh_key=None):
    output_pass(['juju', 'add-model', model], token.c_name)
    if ssh_key is not None:
        add_ssh_key(token, ssh_key)
    output_pass(['juju', 'grant', token.username, 'admin', model], token.c_name)
    return get_model_info(token)


def delete_model(token):
    output_pass(['juju', 'destroy-model', '-y', '{}:{}'.format(token.c_name, token.m_name)])
    return get_controller_info(token)


def add_ssh_key(token, ssh_key):
    output_pass(['juju', 'add-ssh-key', '"{}"'.format(ssh_key)], token.c_name, token.m_name)
    return get_ssh_keys(token)


def remove_ssh_key(token, ssh_key):
    key = base64.b64decode(bytes(ssh_key.strip().split()[1].encode('ascii')))
    fp_plain = hashlib.md5(key).hexdigest()
    fingerprint = ':'.join(a+b for a, b in zip(fp_plain[::2], fp_plain[1::2]))
    return output_pass(['juju', 'remove-ssh-key', fingerprint], token.c_name, token.m_name)
###############################################################################
# USER FUNCTIONS
###############################################################################
def create_user(username, password):
    for controller in get_all_controllers():
        output_pass(['juju', 'add-user', username], controller)
        output_pass(['juju', 'revoke', username, 'login'], controller)
    change_user_password(username, password)
    return get_user_info(username)


def delete_user(username):
    for controller in get_all_controllers():
        output_pass(['juju', 'remove-user', username, '-y'], controller)
    return 'The user {} has been removed'.format(username)


def change_user_password(username, password):
    for controller in get_all_controllers():
        check_output(['juju', 'change-user-password', username, '-c', controller],
                     input=bytes('{}\n{}\n'.format(password, password), 'utf-8'))
    return get_user_info(username)


def get_users(controller):
    data = json.loads(output_pass(['juju', 'users', '--format', 'json'], controller))
    return {u['user-name']: u['access'] for u in data}


def get_users_controller(token):
    if token.c_access == 'superuser':
        data = json.loads(output_pass(['juju', 'list-users', '--format', 'json'], token.c_name))
        users = [{'name': u['user-name'], 'access': u['access']} for u in data]
    elif token.c_access is not None:
        users = [{'name': token.username, 'access': token.c_access}]
    else:
        users = None
    return users


def get_users_model(token):
    if token.m_access == 'admin' or token.m_access == 'write':
        check_call(['juju', 'switch', '{}:{}'.format(token.c_name, token.m_name)])
        users_info = json.loads(check_output(['juju', 'show-model', '--format', 'json']).decode('utf-8'))[token.m_name]['users']
        users = [{'name': k, 'access': v['access']} for k, v in users_info.items()]
    elif token.m_access is not None:
        users = [{'name': token.username, 'access': token.m_access}]
    else:
        users = None
    return users


def add_to_controller(token, username, access):
    current_access = get_controller_access(token, username)
    if current_access == 'superuser':
        if access == 'add-model':
            output_pass(['juju', 'revoke', username, 'superuser'], token.c_name)
        elif access == 'login':
            output_pass(['juju', 'revoke', username, 'superuser'], token.c_name)
            output_pass(['juju', 'revoke', username, 'add-model'], token.c_name)
    elif current_access == 'add-model':
        if access == 'superuser':
            output_pass(['juju', 'grant', username, 'superuser'], token.c_name)
        elif access == 'login':
            output_pass(['juju', 'revoke', username, 'add-model'], token.c_name)
    elif current_access == 'login':
        if access != 'login':
            output_pass(['juju', 'grant', username, access], token.c_name)
    elif current_access is None:
        output_pass(['juju', 'grant', username, access], token.c_name)
    return get_user_info(username)


def remove_from_controller(token, username):
    current_access = get_controller_access(token, username)
    if current_access == 'superuser':
        output_pass(['juju', 'revoke', username, 'superuser'], token.c_name)
        output_pass(['juju', 'revoke', username, 'add-model'], token.c_name)
        output_pass(['juju', 'revoke', username, 'login'], token.c_name)
    elif current_access == 'add-model':
        output_pass(['juju', 'revoke', username, 'add-model'], token.c_name)
        output_pass(['juju', 'revoke', username, 'login'], token.c_name)
    elif current_access == 'login':
        output_pass(['juju', 'revoke', username, 'login'], token.c_name)
    return get_user_info(username)


def add_to_model(token, username, access):
    if not c_access_exists(get_controller_access(token, username)):
        add_to_controller(token, username, 'login')
    current_access = get_model_access(token, username)
    if current_access == 'admin':
        if access == 'write':
            output_pass(['juju', 'revoke', username, 'admin', token.m_name])
        elif access == 'read':
            output_pass(['juju', 'revoke', username, 'admin', token.m_name])
            output_pass(['juju', 'revoke', username, 'write', token.m_name])
    elif current_access == 'write':
        if access == 'admin':
            output_pass(['juju', 'grant', username, 'admin', token.m_name])
        elif access == 'read':
            output_pass(['juju', 'revoke', username, 'write', token.m_name])
    elif current_access == 'login':
        if access != 'login':
            output_pass(['juju', 'grant', username, access, token.m_name])
    elif current_access is None:
        output_pass(['juju', 'grant', username, access, token.m_name])
    return get_user_info(username)


def remove_from_model(token, username):
    current_access = get_model_access(token, username)
    if current_access == 'admin':
        output_pass(['juju', 'revoke', username, 'admin', token.m_name], token.c_name)
        output_pass(['juju', 'revoke', username, 'write', token.m_name], token.c_name)
        output_pass(['juju', 'revoke', username, 'read', token.m_name], token.c_name)
    elif current_access == 'write':
        output_pass(['juju', 'revoke', username, 'write', token.m_name], token.c_name)
        output_pass(['juju', 'revoke', username, 'read', token.m_name], token.c_name)
    elif current_access == 'read':
        output_pass(['juju', 'revoke', username, 'read', token.m_name], token.c_name)
    return get_user_info(username)


def user_exists(username):
    return username == get_user() or username in get_all_users()


def get_all_users():
    try:
        users = json.loads(output_pass(['juju', 'users', '--all', '--format', 'json'], get_all_controllers()[0]))
        result = [user['user-name'] for user in users]
    except IndexError:
        result = {get_user(): 'superuser'}
    return result


def get_users_info():
    controllers = {}
    for controller in get_all_controllers():
        users = json.loads(output_pass(['juju', 'users', '--format', 'json'], controller))
        controllers[controller] = {u['user-name']: u['access'] for u in users if u['access'] != ''}
    all_users = {}
    for controller, users in controllers.items():
        for user, access in users.items():
            if user in all_users.keys():
                all_users[user].append({'name': controller, 'access': access})
            else:
                all_users[user] = [{'name': controller, 'access': access}]
    users = [{'name': u, 'controllers': c} for u, c in all_users.items()]
    for user in users:
        for controller in user['controllers']:
            models = json.loads(output_pass(['juju', 'models', '--format', 'json'], controller['name']))['models']
            for m in models:
                try:
                    controller['models'] = {'name': m['name'], 'access': m['users'][user['name']]['access']}
                except KeyError:
                    pass
    return users


def get_user_info(username):
    for user in get_users_info():
        if user['name'] == username:
            return user
#####################################################################################
# APPLICATION FUNCTIONS
#####################################################################################
def config(token, app_name):
    return json.loads(output_pass(['juju', 'config', app_name, '--format', 'json'], token.c_name, token.m_name))


def app_exists(token, app_name):
    data = json.loads(output_pass(['juju', 'status', '--format', 'json'], token.c_name, token.m_name))
    return app_name in data['applications'].keys()


def deploy_app(token, app_name, series=None, target=None):
    if target is None and series is None:
        result = output_pass(['juju', 'deploy', app_name], token.c_name, token.m_name)
    elif target is None:
        result = output_pass(['juju', 'deploy', app_name, '--series', series], token.c_name, token.m_name)
    else:
        if not token.c_token.supportlxd and 'lxd' in target:
            result = '{} doesn\'t support lxd-containers'.format(token.c_token.c_type.upper())
        else:
            if 'local:' in app_name:
                app_name = app_name.replace('local:', '{}/'.format(get_charm_dir()))
            result = output_pass(['juju', 'deploy', app_name, '--series', series, '--to', target], token.c_name, token.m_name)
    return result


def remove_app(token, app_name):
    return output_pass(['juju', 'remove-application', app_name], token.c_name, token.m_name)


def add_machine(token, series=None):
    if series is None:
        result = output_pass(['juju', 'add-machine'], token.c_name, token.m_name)
    else:
        result = output_pass(['juju', 'add-machine', '--series', series], token.c_name, token.m_name)
    return result


def machine_exists(token, machine):
    data = json.loads(output_pass(['juju', 'status', '--format', 'json'], token.c_name, token.m_name))
    if 'lxd' in machine:
        return machine in data['machines'][machine.split('/')[0]]['containers'].keys()
    else:
        return machine in data['machines'].keys()


def get_machine_series(token, machine):
    data = json.loads(output_pass(['juju', 'list-machines', '--format', 'json'], token.c_name, token.m_name))
    if 'lxd' in machine:
        return data['machines'][machine.split('/')[0]]['containers'][machine]['series']
    else:
        return data['machines'][machine]['series']


def machine_matches_series(token, machine, series):
    return series == get_machine_series(token, machine)


def remove_machine(token, machine):
    return output_pass(['juju', 'remove-machine', '--force', machine], token.c_name, token.m_name)


def get_application_info(token, application):
    data = json.loads(output_pass(['juju', 'status', '--format', 'json'], token.c_name, token.m_name))
    result = {'name': application, 'relations': data['applications'][application]['relations'], 'units': []}
    for u, ui in data['applications'][application]['units'].items():
        try:
            unit = {'name': u, 'machine': ui['machine'], 'instance-id': data['machines'][ui['machine']]['instance-id'], 'ip': ui['public-address'], 'ports': ui['open-ports']}
        except KeyError:
            unit = {'name': u, 'machine': 'Waiting', 'instance-id': 'Unknown', 'ip': 'Unknown', 'ports': 'Unknown'}
        result['units'].append(unit)
    return result


def get_unit_info(token, application, unitnumber):
    data = get_application_info(token, application)
    for u in data['units']:
        if u['name'] == '{}/{}'.format(application, unitnumber):
            return u


def unit_exists(token, application, unitnumber):
    data = json.loads(output_pass(['juju', 'status', '--format', 'json'], token.c_name, token.m_name))['applications'][application]
    return '{}/{}'.format(application, unitnumber) in data['units'].keys()


def add_unit(token, app_name, target=None):
    if target is None:
        return output_pass(['juju', 'add-unit', app_name], token.c_name, token.m_name)
    else:
        return output_pass(['juju', 'add-unit', app_name, '--to', target])


def remove_unit(token, application, unit_number):
    return output_pass(['juju', 'remove-unit', '{}/{}'.format(application, unit_number)], token.c_name, token.m_name)


def add_relation(token, app1, app2):
    return output_pass(['juju', 'add-relation', app1, app2], token.c_name, token.m_name)


def remove_relation(token, app1, app2):
    return output_pass(['juju', 'remove-relation', app1, app2], token.c_name, token.m_name)


def get_app_info(token, app_name):
    return json.loads(output_pass(['juju', 'status'], token.c_name, token.m_name))['applications'][app_name]
