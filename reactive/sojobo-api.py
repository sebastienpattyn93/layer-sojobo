#!/usr/bin/env python3
# Copyright (C) 2017  Qrama
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
# pylint: disable=c0111,c0103,c0301
from base64 import b64encode
from hashlib import sha256
import os
import shutil
import subprocess
from charmhelpers.core.templating import render
from charmhelpers.core.hookenv import status_set, log, config, open_port, unit_private_ip, application_version_set
from charmhelpers.core.host import service_restart, chownr, adduser
from charmhelpers.contrib.python.packages import pip_install
from charms.reactive import hook, when, when_not, set_state, remove_state


API_DIR = config()['api-dir']
USER = config()['api-user']
GROUP = config()['nginx-group']
HOST = config()['host'] if config()['host'] != '127.0.0.1' else unit_private_ip()
###############################################################################
# INSTALLATION AND UPGRADES
###############################################################################
@when('juju.installed')
@when_not('api.installed')
def install():
    log('Installing Sojobo API')
    os.mkdir(API_DIR)
    install_api()
    set_state('api.installed')


@hook('upgrade-charm')
def upgrade_charm():
    log('Updating Sojobo API')
    install_api()
    set_state('api.installed')


@when('api.installed', 'nginx.passenger.available')
@when_not('api.configured')
def configure_webapp():
    context = {'hostname': HOST, 'user': USER, 'rootdir': API_DIR}
    render('http.conf', '/etc/nginx/sites-enabled/sojobo.conf', context)
    open_port(80)
    restart_api()
    set_state('api.configured')
    status_set('blocked', 'Waiting for a connection with Redis')


@when('config.changed', 'api.running')
def config_changed():
    context = {'hostname': HOST, 'user': USER, 'rootdir': API_DIR}
    render('http.conf', '/etc/nginx/sites-enabled/sojobo.conf', context)
    restart_api()


@when('api.configured', 'redis.available')
@when_not('api.running')
def connect_to_redis(redis):
    redis_db = redis.redis_data()
    api_key = sha256(os.urandom(256)).hexdigest()
    password = b64encode(os.urandom(18)).decode('utf-8')
    render('settings.py', '{}/settings.py'.format(API_DIR), {
        'API_KEY': api_key,
        'JUJU_ADMIN_USER': 'admin',
        'JUJU_ADMIN_PASSWORD': password,
        'SOJOBO_API_DIR': API_DIR,
        'LOCAL_CHARM_DIR': config()['charm-dir'],
        'SOJOBO_IP': 'http://{}'.format(HOST),
        'SOJOBO_USER': USER,
        'REDIS_HOST': redis_db['host'],
        'REDIS_PORT': redis_db['port']
    })
    set_state('api.running')
    service_restart('nginx')
    status_set('active', 'admin-password: {} api-key: {}'.format(password, api_key))


@when('api.running')
@when_not('redis.available')
def redis_db_removed():
    remove_state('api.running')
    status_set('blocked', 'Waiting for a connection with redis')


@when('sojobo.available')
def configure(sojobo):
    with open("/{}/settings.py".format(API_DIR), "r") as settings:
        api_key = settings.readline().split(' = ')[1][1:-1]
    sojobo.configure('https://{}'.format(HOST), API_DIR, api_key, config()['api-user'])


@when('reverseproxy.available', 'api.running')
def configure_proxy(reverseproxy):
    reverseproxy.configure(80)
    set_state('api.reverseproxy-configured')
###############################################################################
# UTILS
###############################################################################
def mergecopytree(src, dst, symlinks=False, ignore=None):
    """"Recursive copy src to dst, mergecopy directory if dst exists.
    OVERWRITES EXISTING FILES!!"""
    if not os.path.exists(dst):
        os.makedirs(dst)
        shutil.copystat(src, dst)
    lst = os.listdir(src)
    if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]
    for item in lst:
        src_item = os.path.join(src, item)
        dst_item = os.path.join(dst, item)
        if symlinks and os.path.islink(src_item):
            if os.path.lexists(dst_item):
                os.remove(dst_item)
            os.symlink(os.readlink(src_item), dst_item)
        elif os.path.isdir(src_item):
            mergecopytree(src_item, dst_item, symlinks, ignore)
        else:
            shutil.copy2(src_item, dst_item)


def install_api():
    for pkg in ['Jinja2', 'Flask', 'pyyaml', 'click', 'pygments', 'apscheduler', 'gitpython', 'redis']:
        pip_install(pkg)
    subprocess.check_call(['pip', 'install', 'juju==0.3.0'])
    mergecopytree('files/sojobo_api', API_DIR)
    os.mkdir('{}/files'.format(API_DIR))
    os.mkdir('{}/bundle'.format(API_DIR))
    os.mkdir('{}/log'.format(API_DIR))
    os.mkdir('{}/backup'.format(API_DIR))
    adduser(USER)
    os.mkdir('/home/{}'.format(USER))
    chownr('/home/{}'.format(USER), USER, USER, chowntopdir=True)
    chownr(API_DIR, USER, GROUP, chowntopdir=True)
    from git import Repo
    Repo.clone_from('https://github.com/tengu-team/python-libjuju.git', '{}/libjuju'.format(API_DIR))
    mergecopytree('{}/libjuju/juju'.format(API_DIR), '/usr/local/lib/python3.5/dist-packages/juju/')
    shutil.copyfile('files/model.py', '/usr/local/lib/python3.5/dist-packages/juju/model.py')
    shutil.copyfile('files/controller.py', '/usr/local/lib/python3.5/dist-packages/juju/controller.py')
    service_restart('nginx')
    status_set('active', 'The Sojobo-api is installed')
    application_version_set('1.0.0')


def restart_api():
    service_restart('nginx')
    subprocess.check_call(['service', 'nginx', 'status'])
