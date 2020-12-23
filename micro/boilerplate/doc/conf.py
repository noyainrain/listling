import os
import sys
sys.path.insert(0, os.path.abspath('..'))

import micro

extensions = ['sphinx.ext.autodoc', 'sphinxcontrib.httpdomain']
source_suffix = ['.rst', '.md']
source_parsers = {'.md': 'recommonmark.parser.CommonMarkParser'}

project = '{name}'
copyright = '{year} {name} contributors'
version = release = '{version}'

html_theme_options = {
    'logo': '{logo-file}',
    'logo_name': True,
    'description': '{slogan}'
}
html_favicon = '{favicon-path}'
html_static_path = ['{logo-path}']
html_sidebars = {'**': ['about.html', 'navigation.html', 'searchbox.html']}
html_show_sourcelink = False

autodoc_member_order = 'bysource'

# Make micro documentation snippets available
try:
    os.symlink(micro.DOC_PATH, 'micro')
except FileExistsError:
    pass
