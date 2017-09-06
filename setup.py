from setuptools import setup

setup(name='codebuild_emulator',
      version='0.1',
      description='To emulate AWS CodeBuild on premises',
      url='https://github.com/horiam/codebuild-emulator',
      author='Horia',
      author_email='horiam@gmail.com',
      license='Apache 2',
      install_requires=['boto3',
                        'click',
                        'docker'],
      scripts=['codebuild_emulator/codebuild_emulator.py',
               'codebuild_emulator/codebuild_builder.py',
               'codebuild_emulator/jobpoller.py'])
