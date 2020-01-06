from pythonforandroid.recipe import PythonRecipe
class AioSqliteRecipe(PythonRecipe):
    version = '0.11.0'
    url = 'https://files.pythonhosted.org/packages/61/61/4082af155aa2d58971e94a8f5798a430c3b2c1b4fb8a977264c8a360f54a/aiosqlite-{version}.tar.gz'

    depends = ['python3', 'setuptools']

    name = 'aiosqlite'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = AioSqliteRecipe()
