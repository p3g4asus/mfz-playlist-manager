from pythonforandroid.recipe import PythonRecipe
class AioHTTPSessionRecipe(PythonRecipe):
    version = '2.9.0'
    url = 'https://files.pythonhosted.org/packages/f8/fe/53dfd35f5c7fcc7f2d0866cb29e722303e3fae7f749c1f3d4d11d361dc38/aiohttp-session-{version}.tar.gz'

    depends = ['python3', 'aiohttp']

    name = 'aiohttp-session'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = AioHTTPSessionRecipe()
