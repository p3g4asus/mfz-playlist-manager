from pythonforandroid.recipe import CythonRecipe
class YarlRecipe(CythonRecipe):
    version = '1.4.2'
    url = 'https://files.pythonhosted.org/packages/d6/67/6e2507586eb1cfa6d55540845b0cd05b4b77c414f6bca8b00b45483b976e/yarl-{version}.tar.gz'
    name = 'yarl'

    depends = ['multidict', 'idna']

recipe = YarlRecipe()
