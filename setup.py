from setuptools import setup, find_packages

install_requires = [
    "aiohttp==2.3.10",
    "chardet==3.0.4", # latest
    "gevent==1.4.0", # latest
    "greenlet==0.4.15", # latest
    "pybreaker==0.5.0", # latest
    "PyYAML==5.1.2",  # latest
    "redis==3.3.6", # latest
    "retrying==1.3.3", # latest
    "requests==2.22.0", # latest
]

tests_require = [
    "Contexts",
    "fakeredis",
    "freezegun==0.3.12", # latest
    "HTTPretty"
]

extras = {
    'test': tests_require,
}

setup(
    name="AtomicPuppy",
    version="0.7.0",
    packages=find_packages(),
    dependency_links=[
        "git+https://github.com/OddBloke/HTTPretty.git@f899d1bda8234658c2cec5aab027cb5b7c42203c#egg=HTTPretty"
        "git+https://github.com/damiansoriano/Contexts.git@4ad390aa4f514eff94b8ef43f6da0b404e42e1a7#egg=Contexts",
        "git+https://github.com/jamesls/fakeredis.git@d675ee1d6c4ac7a3bb0129f916232c0f2c6e9dd5#egg=fakeredis"
    ],
    install_requires=install_requires,
    tests_require=tests_require,
    url='https://github.com/madedotcom/atomicpuppy',
    description='A service-activator component for eventstore',
    author='Bob Gregory',
    author_email='bob@made.com',
    keywords=['eventstore'],
    license='MIT',
)
