from pythonforandroid.recipe import PythonRecipe
class AttrsRecipe(PythonRecipe):
    version = '19.3.0'
    url = 'https://files.pythonhosted.org/packages/98/c3/2c227e66b5e896e15ccdae2e00bbc69aa46e9a8ce8869cc5fa96310bf612/attrs-{version}.tar.gz'

    depends = ['python3', 'setuptools']

    name = 'attrs'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = AttrsRecipe()
