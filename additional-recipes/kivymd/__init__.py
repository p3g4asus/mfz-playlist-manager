from pythonforandroid.recipe import PythonRecipe
class KivyMDRecipe(PythonRecipe):
    # version = '6abb482b2ab4934e34e03b19b4a0b6dcd639b63a'
    # url = 'https://github.com/HeaTTheatR/KivyMD/archive/{version}.zip'
    version = '25b0b7f2df7dba463111543cf526b6cd6b672ace'
    url = 'https://github.com/p3g4asus/KivyMD/archive/{version}.zip'

    depends = ['python3', 'setuptools', 'pillow', 'requests', 'kivy']

    name = 'kivymd'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = KivyMDRecipe()
