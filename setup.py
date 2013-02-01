from setuptools import setup, find_packages

def get_requirements()
    with open("requirements.txt") as f:
        return f.read()

setup(
    name = "BerryCAH",
    version = "0.1",
    packages = find_packages(exclude=['tests']),
    
    install_requires = get_requirements(),
    
    include_package_data = True,

)
