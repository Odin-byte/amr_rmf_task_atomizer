import os
from setuptools import setup
from glob import glob

package_name = 'amr_rmf_task_atomizer'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Include launch files
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),
        # Include scripts for installation
        (os.path.join('lib', package_name), glob('scripts/*')),
        # Include config files for installation
        (os.path.join('share', package_name, 'config'), glob('config/*'))
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='',
    maintainer_email='',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'amr_task_state_pub = amr_rmf_task_atomizer.rmf_task_state_pub:main',
            'task_atomizer = amr_rmf_task_atomizer.amr_rmf_task_atomizer:main',
        ],
    },
)
