#!/usr/bin/python

import os
from os.path import join
import tempfile
import shutil
import json
import time
import boto3
import docker
import click
from jobpoller import JobPoller

cwd = os.getcwd()
target = join(cwd, 'target', 'artifacts')

class CodebuildEmulator:

    def _get_project(self):
        codebuild = boto3.client('codebuild')
        response = codebuild.batch_get_projects(names=[self._project_name])
        projects = response['projects']
        if projects:
            return projects[0]
        else:
            raise Exception("No project found")


    def _get_buildspec(self, project):
        if 'buildspec' in project['source']:
            buildspec_raw = project['source']['buildspec'].strip()
            return str(buildspec_raw)
        else:
            return 'buildspec.yml'


    def _get_env_vars(self, project):
        raw_environment = project['environment']['environmentVariables']
        environment = {}
        for tuple in raw_environment:
            key = tuple['name']
            value = tuple['value']
            environment[key] = value
        #TODO add all CODEBUILD envs
        environment['CODEBUILD_BUILD_ID'] = 'XXXX'
        return environment


    def _get_image(self, project):
        return project['environment']['image']


    def run(self, configuration, input_src=cwd, target_dir=target, pid1_path='codebuild-builder.py'):

        self._project_name = configuration['ProjectName']

        project = self._get_project()

        tempdir = tempfile.mkdtemp()

        service_role = project['serviceRole']

        assume = boto3.client('sts').assume_role(RoleArn=service_role, RoleSessionName='codebuild-emulator')

        access_key_id = assume['Credentials']['AccessKeyId']
        secret_access_key = assume['Credentials']['SecretAccessKey']
        session_token = assume['Credentials']['SessionToken']

        readonly = join(tempdir, 'codebuild', 'readonly')
        os.makedirs(readonly)

        bin = join(readonly, 'bin')
        os.mkdir(bin)

        shutil.copy2(pid1_path, join(bin, 'execute'))
        src = join(readonly, 'src')

        shutil.copytree(input_src, src)

        with open(join(readonly, 'variables.json'), 'w') as varsfile:
            vars = self._get_env_vars(project)
            json.dump(vars, varsfile)

        buildspec = self._get_buildspec(project)
        buildspec_dest = join(readonly, 'buildspec.yml')

        if buildspec.startswith('version: ') :
            with open(buildspec_dest, 'w') as buildspecfile:
                buildspecfile.write(buildspec)
        else:
            buildspec_src = join(src, buildspec)
            if os.path.exists(buildspec_src):
               shutil.copy2(buildspec_src, buildspec_dest)
            else:
               raise Exception("No buildspec provided")


        output_dir = join(tempdir, 'codebuild/output')
        os.mkdir(output_dir)

        image = self._get_image(project)

        docker_client = docker.from_env(version='auto')

        container = docker_client.containers.run(image=image,
                                                 volumes={readonly: {'bind': '/codebuild/readonly', 'mode': 'ro'},
                                                          output_dir: {'bind': '/codebuild/output', 'mode': 'rw'}},
                                                 entrypoint='/codebuild/readonly/bin/execute',
                                                 environment={'AWS_ACCESS_KEY_ID': access_key_id,
                                                              'AWS_SECRET_ACCESS_KEY': secret_access_key,
                                                              'AWS_SESSION_TOKEN': session_token},
                                                 user=os.getuid(),
                                                 tty=True,
                                                 detach=True)

        print("Artifacts are copied into " + target_dir)

        stream = container.logs(stream=True)
        str = ''

        for c in stream:
            if c == '\n':
                print(str)
                str = ''
            else:
                str = str + c

        container.reload()

        while not container.status == 'exited':
            time.sleep(1)

        docker_api = docker.APIClient(version='1.24')
        exit_code = docker_api.inspect_container(container.id)['State']['ExitCode']

        shutil.rmtree(target_dir)
        shutil.copytree(join(output_dir, 'artifacts'), target_dir)
        shutil.rmtree(tempdir)

        print(exit_code)
        return exit_code


@click.group()
def main():
    pass


@click.command()
@click.option('--provider')
def server(provider):
    emulator = CodebuildEmulator()
    poller = JobPoller({'category': 'Build', 'owner': 'Custom', 'provider': provider, 'version': '1'}, emulator)
    poller.poll()


@click.command()
@click.option('--project')
@click.option('--input-dir')
@click.option('--target-dir')
def developer(project, input_dir, target_dir):
    emulator = CodebuildEmulator()
    emulator.run({'ProjectName': project}, input_src=input_dir, target_dir=target_dir)


main.add_command(server)
main.add_command(developer)


if __name__ == '__main__':
    main()
