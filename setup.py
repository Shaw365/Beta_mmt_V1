"""
Barra风格因子择时策略

基于Barra CNE6模型的风格因子择时策略
"""

from setuptools import setup, find_packages

setup(
    name='barra_factor_timing',
    version='1.0.0',
    description='Barra风格因子择时策略',
    author='AI量化团队',
    author_email='quant@example.com',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    python_requires='>=3.7',
    install_requires=[
        'pandas>=1.3.0',
        'numpy>=1.20.0',
        'scipy>=1.7.0',
        'statsmodels>=0.12.0',
        'matplotlib>=3.3.0',
        'seaborn>=0.11.0',
        'sqlalchemy>=1.4.0',
        'pymysql>=1.0.0',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Financial and Insurance Industry',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
)
