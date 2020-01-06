from pythonforandroid.recipe import PythonRecipe
class AioHTTPSecurityRecipe(PythonRecipe):
    version = '0.4.0'
    url = 'https://files.pythonhosted.org/packages/36/01/d85be376b7c1773b3cb7849cd56dc7d38165664df7de2d3e20af507ef5bb/aiohttp-security-{version}.tar.gz'

    depends = ['python3', 'aiohttp']

    name = 'aiohttp-security'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = AioHTTPSecurityRecipe()
