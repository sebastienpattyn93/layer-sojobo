# Introduction
<p>
This is the api for the Tengu platform. Besides providing all the necessary Tengu - commands, it also introduces
JuJu - wide users (instead of users on a controller-level) and the principle of an admin-user.
</p>

# Working
<p>
The entire api is modular: extra modules will be loaded automatically if placed in the api-folder, provided they
follow the naming rules and provide the required functions.
</p>

## API-modules
<p>
The api is written in Flask. This allows the use of blueprints to expand the api. API-modules file names must follow
this scheme: `api_<modulename>.py`. The modulename MAY NOT contain an underscore. The module itself must have the following
inside:
</p>
```python
<MODULENAME> = Blueprint(<modulename>, __name__)


def get():
    return <MODULENAME>
```

## Controller-modules
<p>
Controller modules name must follow this scheme: `controller_<controllername>.py`. The controllername MAY NOT contain
an underscore. The module itself must have the following inside:
</p>
```python
class Token(object):
    def __init__(self, url, auth):
        self.type = 'maas'
        self.url = url
        self.user = auth.username
        self.password = auth.password

    def get_credentials(self):
        return {'auth-type': 'oauth1', 'maas-oath': self.api_key}

    def get_cloud(self):
        return {'type': 'maas', 'auth-types': ['oauth1'], 'endpoint': self.url}


def create_controller(name, region, credentials):
    ...
    return check_output(['juju', 'bootstrap', cloudname, name])


def get_supported_series():
    return ['trusty', 'xenial']
```

* A Token object, which has the controllers type in lowercase, the url of the endpoint, the required information to log into the controller (username, password, api_key, etc.). The Token objects must have the `get_credentials` and `get_cloud`
functions, which return the required JuJu-styled data.
* A `create_controller(name, region, credentials)` function, which houses all the required code required to successfully bootstrap a controller of this type.
* A `get_supported_series()` function which returns a list of Ubuntu-versions this controller can deploy.

# Documentation
Documentation concerning the api or test-bench can be found in the api - and test-folder.

# Bugs
Report bugs on <a href="https://github.com/IBCNServices/tengu-charms/issues">Github</a>

# Author
Mathijs Moerman <a href="mailto:mathijs.moerman@qrama.io">mathijs.moerman@qrama.io</a>