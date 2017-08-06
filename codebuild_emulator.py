#!/usr/bin/env python

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
target = join(cwd, 'artifacts')
default_script_path = join(os.path.dirname(os.path.realpath(__file__)), 'codebuild_builder.py')

class CodebuildEmulator:

    def __init__(self, docker_version,
                 codebuild_client=boto3.client('codebuild'),
                 sts_client=boto3.client('sts')):
        self._docker_version = docker_version
        self._codebuild_client = codebuild_client
        self._sts_client = sts_client

    def _get_project(self, project_name):
        response = self._codebuild_client.batch_get_projects(names=[project_name])
        projects = response['projects']
        if projects:
            return projects[0]
        else:
            raise Exception("No project found")

    def run(self, configuration, input_src=cwd, target_dir=target):
        project = self._get_project(configuration['ProjectName'])
        work_dir = tempfile.mkdtemp()

        run = CodebuildRun(project, input_src, work_dir,
                           self._sts_client, self._docker_version)
        run.assume_role()
        run.prepare_dirs()

        exit_code = run.run_container()

        run.copy_artifacts(target_dir)
        shutil.rmtree(work_dir)
        return exit_code


class CodebuildRun:
    def __init__(self, project, input_src, work_dir,
                 sts_client=boto3.client('sts'), docker_version='1.24'):
        self._project = project
        self._input_src = input_src
        self._work_dir = work_dir
        self._sts_client = sts_client
        self._docker_version = docker_version

    def assume_role(self):
        service_role = self._project['serviceRole']
        assume = self._sts_client.assume_role(RoleArn=service_role,
                                              RoleSessionName='codebuild-emulator')
        self._access_key_id = assume['Credentials']['AccessKeyId']
        self._secret_access_key = assume['Credentials']['SecretAccessKey']
        self._session_token = assume['Credentials']['SessionToken']

    def prepare_dirs(self):
        readonly = join(self._work_dir, 'codebuild', 'readonly')
        os.makedirs(readonly)
        self._readonly_dir = readonly

        bin = join(readonly, 'bin')
        os.mkdir(bin)

        shutil.copy2(default_script_path, join(bin, 'executor'))
        src = join(readonly, 'src')

        shutil.copytree(self._input_src, src)

        with open(join(readonly, 'variables.json'), 'w') as varsfile:
            vars = self._get_env_vars()
            json.dump(vars, varsfile)

        buildspec = self._get_buildspec()
        buildspec_dest = join(readonly, 'buildspec.yml')

        if buildspec.startswith('version: '):
            with open(buildspec_dest, 'w') as buildspecfile:
                buildspecfile.write(buildspec)
        else:
            buildspec_src = join(src, buildspec)
            if os.path.exists(buildspec_src):
                shutil.copy2(buildspec_src, buildspec_dest)
            else:
                raise Exception("No buildspec provided")

        output_dir = join(self._work_dir, 'codebuild', 'output')
        os.mkdir(output_dir)
        self._output_dir = output_dir

    def run_container(self):
        image = self._project['environment']['image']
        volumes = {self._readonly_dir: {'bind': '/codebuild/readonly', 'mode': 'ro'},
                   self._output_dir: {'bind': '/codebuild/output', 'mode': 'rw'}}
        entrypoint = '/codebuild/readonly/bin/executor'
        environment = {'AWS_ACCESS_KEY_ID': self._access_key_id,
                       'AWS_SECRET_ACCESS_KEY': self._secret_access_key,
                       'AWS_SESSION_TOKEN': self._session_token}

        docker_client = docker.from_env(version=self._docker_version)
        docker_api = docker.APIClient(version=self._docker_version)
        container = docker_client.containers.run(image=image,
                                                       volumes=volumes,
                                                       entrypoint=entrypoint,
                                                       environment=environment,
                                                       user=os.getuid(),
                                                       tty=True,
                                                       detach=True)
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

        exit_code = docker_api.inspect_container(container.id)['State']['ExitCode']
        return exit_code

    def copy_artifacts(self, artifacts_target_dir):
        print("Artifacts are copied into " + artifacts_target_dir)
        shutil.rmtree(artifacts_target_dir, ignore_errors=True)
        shutil.copytree(join(self._output_dir, 'artifacts'), artifacts_target_dir)

    def _get_buildspec(self):
        if 'buildspec' in self._project['source']:
            buildspec_raw = self._project['source']['buildspec'].strip()
            return str(buildspec_raw)
        else:
            return 'buildspec.yml'

    def _get_env_vars(self):
        raw_environment = self._project['environment']['environmentVariables']
        environment = {}
        for tuple in raw_environment:
            key = tuple['name']
            value = tuple['value']
            environment[key] = value
        #TODO add all CODEBUILD envs
        environment['CODEBUILD_BUILD_ID'] = 'XXXX'
        return environment


@click.group()
def main():
    pass

@click.command()
@click.option('--provider', required=True)
@click.option('--docker-version', default='1.24')
def server(provider, docker_version):
    emulator = CodebuildEmulator(docker_version=docker_version)
    poller = JobPoller({'category': 'Build', 'owner': 'Custom', 'provider': provider, 'version': '1'}, emulator)
    poller.poll()

@click.command()
@click.option('--project', required=True)
@click.option('--input-dir', default=cwd)
@click.option('--target-dir', default=target)
@click.option('--docker-version', default='1.24')
def developer(project, input_dir, target_dir, docker_version):
    emulator = CodebuildEmulator(docker_version=docker_version)
    emulator.run({'ProjectName': project}, input_src=input_dir, target_dir=target_dir)


main.add_command(server)
main.add_command(developer)


if __name__ == '__main__':
    main()
