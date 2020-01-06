from pythonforandroid.recipe import PythonRecipe
class PythonOscRecipe(PythonRecipe):
    version = '1.7.4'
    url = 'https://files.pythonhosted.org/packages/eb/76/ece85b5f35d13d684d52a251e5a676c80ff77164485266755f1b62bd92fe/python-osc-{version}.tar.gz'

    depends = ['python3', 'setuptools']

    name = 'python-osc'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = PythonOscRecipe()
