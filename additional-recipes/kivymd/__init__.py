from pythonforandroid.recipe import PythonRecipe
class KivyMDRecipe(PythonRecipe):
    # version = 'master'
    # url = 'https://github.com/HeaTTheatR/KivyMD/archive/{version}.zip'
    version = '27e7e35576ec14d1fa11973a86d85ed8657eb7ae'
    url = 'https://github.com/p3g4asus/KivyMD/archive/{version}.zip'

    depends = ['python3', 'setuptools', 'pillow', 'requests', 'kivy']

    name = 'kivymd'
    call_hostpython_via_targetpython = False
    install_in_hostpython = True

recipe = KivyMDRecipe()
