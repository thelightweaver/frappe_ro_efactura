from setuptools import setup, find_packages

setup(
    name='frappe_ro_efactura',
    version='0.0.1',
    description='Integrare Frappe cu eFactura ANAF România',
    author='The Lightweaver',
    author_email='luis@lightweaver.uk',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'frappe'
    ]
)
