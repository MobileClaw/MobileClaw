# set up basic requirements for MobileClaw
from setuptools import setup, find_packages
import glob
import os

setup(
    name='mobileclaw',
    packages=find_packages(include=['mobileclaw']),
    # this must be the same as the name above
    version='0.0.1a1',
    description='Development framework and runtime system for mobile agents.',
    author='MobileClaw Team',
    license='CUSTOM',
    author_email='li.yuanchun@foxmail.com',
    url='https://github.com/MobileLLM/MobileClaw',  # use the URL to the github repo
    download_url='https://github.com/MobileLLM/MobileClaw/tarball/0.0.1a1',
    keywords=['AI', 'agent', 'mobile', 'framework', 'LLM'],  # arbitrary keywords
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python',
    ],
    entry_points={
        'console_scripts': [
            'mobileclaw=mobileclaw.main:main',
        ],
    },
    package_data={
        'mobileclaw': [os.path.relpath(x, 'mobileclaw') for x in glob.glob('mobileclaw/resources/**/*', recursive=True)]
    },
    install_requires=[
        'websocket-client',
        "structlog",
        "markitdown",
        'pyyaml',
        "Pillow",
        'zulip',
        'lark_oapi',
        'qq-botpy>=1.2.0',
        'python-telegram-bot>=20.0',
    ],
)
