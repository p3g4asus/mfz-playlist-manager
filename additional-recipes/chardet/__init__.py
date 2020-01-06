from pythonforandroid.recipe import PythonRecipe
class ChardetRecipe(PythonRecipe):
    version = '3.0.4'
    url = 'https://files.pythonhosted.org/packages/fc/bb/a5768c230f9ddb03acc9ef3f0d4a3cf93462473795d18e9535498c8f929d/chardet-{version}.tar.gz'

    depends = ['python3', 'setuptools']

    name = 'chardet'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = ChardetRecipe()
