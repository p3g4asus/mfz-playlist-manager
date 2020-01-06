from pythonforandroid.recipe import CythonRecipe
class AioHTTPRecipe(CythonRecipe):
    version = '3.6.2'
    url = 'https://files.pythonhosted.org/packages/00/94/f9fa18e8d7124d7850a5715a0b9c0584f7b9375d331d35e157cee50f27cc/aiohttp-{version}.tar.gz'
    name = 'aiohttp'

    depends = ['python3', 'attrs', 'chardet', 'multidict', 'yarl', 'async-timeout', 'idna-ssl']

recipe = AioHTTPRecipe()
