from setuptools import setup, find_packages

install_requires = [
    "aiohttp>=3.6,<3.7",
    "chardet==3.0.4",
    "gevent==1.4.0",
    "greenlet==0.4.15",
    "pybreaker==0.5.0",
    "PyYAML==5.1.2",
    "redis==3.3.6",
    "retrying==1.3.3",
    "requests==2.22.0",
]

tests_require = [
    "Contexts",
    "fakeredis==1.0.4",
    "freezegun==0.3.12",
    "HTTPretty==0.8.10",
]

extras = {
    'test': tests_require,
}

setup(
    name="AtomicPuppy",
    version="1.0",
    packages=find_packages(),
    dependency_links=[
        "git+https://github.com/madedotcom/Contexts.git@15d1649d5768188443bdd37920a6181982682e0a#egg=Contexts",
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
