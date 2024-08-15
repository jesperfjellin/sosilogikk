from setuptools import setup, find_packages

setup(
    name='sosilogikk',  
    version='1.0.0',
    license='GPLv3',
    author='Jesper Fjellin',
    author_email='jesperfjellin@gmail.com',
    description='Logikk for å bruke Python biblioteker som Geopandas, Shapely, Fiona etc på .SOS-filer. sosilogikk.py i mappen modules definerer en logikk for å bryte opp en .SOS-fil i objektsegmenter som kan lastes inn i en Geopandas dataframe.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/jesperfjellin/sosilogikk',  
    packages=find_packages(exclude=['exampleUse*', 'images*']),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)