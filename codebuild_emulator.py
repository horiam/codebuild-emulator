#!/usr/bin/env python

import os
from os.path import join
import tempfile
import shutil
import json
import boto3
import docker
import click
import time
import threading
from jobpoller import JobPoller
import sys

cwd = os.getcwd()
target = join(cwd, 'artifacts')
default_script_path = join(os.path.dirname(os.path.realpath(__file__)), 'codebuild_builder.py')


class CodebuildEmulator:

    def __init__(self,
                 docker_version,
                 codebuild_client=boto3.client('codebuild'),
                 sts_client=boto3.client('sts'),
                 assume_role=True,
                 debug=False,
                 override={},
                 pull_image=False):

        self._docker_version = docker_version
        self._codebuild_client = codebuild_client
        self._sts_client = sts_client
        self._assume_role = assume_role
        self._debug = debug
        self._override = override
        self._pull_image = pull_image

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
                           self._sts_client, self._docker_version,
                           assume_role=self._assume_role,
                           debug=self._debug,
                           override=self._override,
                           pull_image=self._pull_image)
        run.assume_role()
        run.prepare_dirs()

        run.run_container()
        exit_code = run.wait_for_container()

        run.copy_artifacts(target_dir)

        shutil.rmtree(work_dir, ignore_errors=True)
        return exit_code


class CodebuildRun:
    def __init__(self,
                 project,
                 input_src,
                 work_dir,
                 sts_client=boto3.client('sts'),
                 docker_version='auto',
                 assume_role=True,
                 debug=False,
                 override={},
                 pull_image=False):

        self._project = project
        self._input_src = input_src
        self._work_dir = work_dir
        self._sts_client = sts_client
        self._docker_version = docker_version
        self._assume_role = assume_role
        self._debug = debug
        self._override = override
        self._pull_image = pull_image

    def assume_role(self):
        if self._assume_role:
            service_role = self._project['serviceRole']
            assume = self._sts_client.assume_role(RoleArn=service_role,
                                                  RoleSessionName='codebuild-emulator')
            self._access_key_id = assume['Credentials']['AccessKeyId']
            self._secret_access_key = assume['Credentials']['SecretAccessKey']
            self._session_token = assume['Credentials']['SessionToken']
        else:
            creds = boto3.Session().get_credentials()
            self._access_key_id = creds.access_key
            self._secret_access_key = creds.secret_key
            self._session_token = creds.token
        self._region_name = boto3.Session().region_name

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

        self._debug_file = join(output_dir, 'debug')
        if self._debug:
            open(self._debug_file, 'a').close()


    def run_container(self):
        image = self._project['environment']['image']
        volumes = {self._readonly_dir: {'bind': '/codebuild/readonly', 'mode': 'ro'},
                   self._output_dir: {'bind': '/codebuild/output', 'mode': 'rw'}}
        command = '/codebuild/readonly/bin/executor'
        environment = {'AWS_ACCESS_KEY_ID': self._access_key_id,
                       'AWS_SECRET_ACCESS_KEY': self._secret_access_key,
                       'AWS_SESSION_TOKEN': self._session_token,
                       'AWS_DEFAULT_REGION': self._region_name,
                       'CBEMU_UID': os.getuid(),
                       'CBEMU_GID': os.getgid()}

        privileged_mode = self._project['environment']['privilegedMode'] or image.startswith('aws/codebuild/docker')
        print('privileged_mode %r\n' % privileged_mode)

        docker_client = docker.from_env(version=self._docker_version)

        if self._pull_image:
            print('Pulling %s' % image)
            docker_client.images.pull(name=image)

        container = docker_client.containers.run(image=image,
                                                 volumes=volumes,
                                                 command=command,
                                                 environment=environment,
                                                 privileged=privileged_mode,
                                                 tty=True,
                                                 detach=True)
        self._container = container

    def wait_for_container(self):
        if self._debug:
            run_thread = threading.Thread(target=self._wait_for_input)
            run_thread.daemon = True
            run_thread.start()

        while True:
            stream = self._container.logs(stdout=True, stderr=True, stream=True, follow=True)
            try:
                for c in stream:
                    sys.stdout.write(c)
                    sys.stdout.flush()
                    if c == '\n':
                        sys.stdout.write('[Container] ')
                        sys.stdout.flush()
                break
            except Exception as e:
                print('\n' + '=' * 128)
                print(str(e))
                print('\n' + '=' * 128)


        if self._debug:
            run_thread.join(timeout=10)

        self._container.reload()

        while not self._container.status == 'exited':
            time.sleep(1)

        docker_api = docker.APIClient(version=self._docker_version)
        exit_code = docker_api.inspect_container(self._container.id)['State']['ExitCode']
        return exit_code

    def copy_artifacts(self, artifacts_target_dir):
        artifacts_source_dir = join(self._output_dir, 'artifacts')
        if os.path.exists(artifacts_source_dir):
            print("Artifacts are copied into " + artifacts_target_dir)
            shutil.rmtree(artifacts_target_dir, ignore_errors=True)
            shutil.copytree(artifacts_source_dir, artifacts_target_dir)

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
        for env,val in self._override.iteritems():
            print('Overriding %s with %s' % (env,val))
            environment[env] = val
        return environment

    def _wait_for_input(self):
        while True:
            while not os.path.exists(self._debug_file):
                time.sleep(1)
            time.sleep(1)
            value = raw_input('')

            if value == 'S':
                open(join(self._output_dir, 'skip'), 'a').close()
            elif value == 'Q':
                open(join(self._output_dir, 'exit'), 'a').close()
                os.unlink(self._debug_file)
                break
            os.unlink(self._debug_file)


@click.group()
def main():
    pass

@click.command()
@click.option('--provider', required=True)
@click.option('--docker-version', default='auto')
@click.option('--no-assume', is_flag=True)
@click.option('--debug', is_flag=True)
def server(provider, docker_version, no_assume, debug):
    emulator = CodebuildEmulator(docker_version=docker_version, assume_role=not no_assume, debug=debug)
    poller = JobPoller({'category': 'Build', 'owner': 'Custom', 'provider': provider, 'version': '1'}, emulator)
    poller.poll()

@click.command()
@click.option('--project', required=True)
@click.option('--input-dir', default=cwd)
@click.option('--target-dir', default=target)
@click.option('--docker-version', default='auto')
@click.option('--no-assume', is_flag=True)
@click.option('--debug', is_flag=True)
@click.option('--pull', is_flag=True)
@click.option('--override')
def developer(project, input_dir, target_dir, docker_version, no_assume, debug, override, pull):
    override_envs = {}
    if override:
        for envs in override.split(','):
            env,value = envs.split('=')
            override_envs[env] = value
    emulator = CodebuildEmulator(docker_version=docker_version, assume_role=not no_assume, debug=debug, override=override_envs, pull_image=pull)
    emulator.run({'ProjectName': project}, input_src=input_dir, target_dir=target_dir)


main.add_command(server)
main.add_command(developer)


if __name__ == '__main__':
    main()
