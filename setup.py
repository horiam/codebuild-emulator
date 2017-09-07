from setuptools import setup, find_packages

setup(name='codebuild_emulator',
      packages=find_packages(),
      include_package_data=True,
      version='0.1',
      description='To emulate AWS CodeBuild on premises',
      url='https://github.com/horiam/codebuild-emulator',
      author='Horia',
      author_email='horiam@gmail.com',
      license='Apache 2',
      zip_safe=False,
      scripts=['bin/cbemu'],
      install_requires=['boto3',
                        'click',
                        'docker'])
