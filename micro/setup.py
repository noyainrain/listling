from setuptools import find_packages, setup

with open('README.md') as f:
    long_description = f.read()
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='noyainrain.micro',
    version='0.48.1',
    url='https://github.com/noyainrain/micro',
    maintainer='Sven James',
    maintainer_email='sven@inrain.org',
    description='Toolkit for social micro web apps.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Operating System :: POSIX',
        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)'
    ],
    packages=find_packages(),
    package_data={'micro': ['doc/*']},
    install_requires=requirements
)
