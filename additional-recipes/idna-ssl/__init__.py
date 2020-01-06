from pythonforandroid.recipe import PythonRecipe


class IdnaSSLRecipe(PythonRecipe):
    name = 'idna-ssl'
    version = '1.1.0'
    url = 'https://files.pythonhosted.org/packages/46/03/07c4894aae38b0de52b52586b24bf189bb83e4ddabfe2e2c8f2419eec6f4/idna-ssl-{version}.tar.gz'

    depends = ['setuptools', 'idna']

    call_hostpython_via_targetpython = False


recipe = IdnaSSLRecipe()
