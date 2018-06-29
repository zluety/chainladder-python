descr = "Chainladder Package - P&C actuarial package modeled after the R package of the same name"

#from distutils.core import setup
from setuptools import setup

setup(
    name='chainladder',
    version='0.1.7',
    maintainer='John Bogaardt',
    maintainer_email='jbogaardt@gmail.com',
    packages=['chainladder', 'chainladder.deterministic', 'chainladder.stochastic'],
    scripts=[],
    url='https://github.com/jbogaardt/chainladder-python',
    download_url='https://github.com/jbogaardt/chainladder-python/archive/v0.1.7.tar.gz',
    license= 'LICENSE',
    include_package_data=True,
    package_data = {'data':['/data/ABC',
                    '/data/M3IR5',
                    '/data/MCLincurred',
                    '/data/MCLpaid',
                    '/data/Mortgage',
                    '/data/MW2008',
                    '/data/MW2014',
                    '/data/qincurred',
                    '/data/qpaid',
                    '/data/RAA',
                    '/data/UKMotor',
                    '/data/USAAincurred',
                    '/data/USAApaid',
                    '/data/auto$CommercialAutoPaid',
                    '/data/auto$PersonalAutoIncurred',
                    '/data/auto$PersonalAutoPaid',
                    '/data/GenIns',
                    '/data/GenInsLong',
                    '/data/liab$AutoLiab',
                    '/data/liab$GeneralLiab']},
    description= descr,
    #long_description=open('README.md').read(),
    install_requires=[
        "pandas>=0.21.0",
        "numpy>=1.12.1",
        "matplotlib>=2.0.2",
        "seaborn>=0.7.1",
        "scipy>=0.19.0",
        "statsmodels>=0.8.0",
        "bokeh>=0.11.0"
    ],
)
