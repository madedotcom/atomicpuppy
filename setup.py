from setuptools import setup, find_packages

install_requires = [
    "aiohttp",
    "chardet",
    "gevent",
    "pybreaker",
    "PyYAML",
    "redis",
    "retrying",
    "requests",
]

tests_require = [
    "Contexts",
    "fakeredis",
    "freezegun",
    "HTTPretty==0.8.10",
]

extras = {
    'test': tests_require,
}

setup(
    name="AtomicPuppy",
    version="1.2.1",
    packages=find_packages(),
    install_requires=install_requires,
    tests_require=tests_require,
    url='https://github.com/madedotcom/atomicpuppy',
    description='A service-activator component for eventstore',
    author='Bob Gregory',
    author_email='bob@made.com',
    keywords=['eventstore'],
    license='MIT',
)
