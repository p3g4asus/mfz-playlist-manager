from pythonforandroid.recipe import CythonRecipe
class MultidictRecipe(CythonRecipe):
    version = '4.7.3'
    url = 'https://files.pythonhosted.org/packages/84/96/5503ba866d8d216e49a6ce3bcb288df8a5fb3ac8a90b8fcff9ddcda32568/multidict-{version}.tar.gz'
    name = 'multidict'

    depends = ['python3', 'setuptools']

recipe = MultidictRecipe()
