from pythonforandroid.recipe import PythonRecipe
class AsyncTimeoutRecipe(PythonRecipe):
    version = '3.0.1'
    url = 'https://files.pythonhosted.org/packages/a1/78/aae1545aba6e87e23ecab8d212b58bb70e72164b67eb090b81bb17ad38e3/async-timeout-{version}.tar.gz'

    depends = ['typing-extensions']

    name = 'async-timeout'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = AsyncTimeoutRecipe()
