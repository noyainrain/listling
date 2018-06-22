import os
import sys
sys.path.insert(0, os.path.abspath('..'))

import micro

extensions = ['sphinx.ext.autodoc', 'sphinxcontrib.httpdomain']
source_suffix = ['.rst', '.md']
source_parsers = {'.md': 'recommonmark.parser.CommonMarkParser'}
master_doc = 'index'

project = 'Open Listling'
copyright = '2018 Open Listling contributors'
version = release = '0.5.2'

html_theme_options = {
    'logo': 'listling.svg',
    'logo_name': True,
    'description': 'Collaborative lists',
    'github_user': 'noyainrain',
    'github_repo': 'listling',
    'github_button': True,
    'github_type': 'star'
}
html_favicon = '../client/images/icon-small.png'
html_static_path = ['../client/images/listling.svg']
html_sidebars = {'**': ['about.html', 'navigation.html', 'searchbox.html']}
html_show_sourcelink = False

autodoc_member_order = 'bysource'

# Make micro documentation snippets available
try:
    os.symlink(micro.DOC_PATH, 'micro')
except FileExistsError:
    pass
