from pythonforandroid.recipe import PythonRecipe
class TypingExtensionsRecipe(PythonRecipe):
    version = '3.7.4.1'
    url = 'https://files.pythonhosted.org/packages/e7/dd/f1713bc6638cc3a6a23735eff6ee09393b44b96176d3296693ada272a80b/typing_extensions-{version}.tar.gz'

    depends = ['python3']

    name = 'typing-extensions'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = TypingExtensionsRecipe()
