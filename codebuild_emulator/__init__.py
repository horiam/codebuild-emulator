import click
import os
from os.path import join
from jobpoller import JobPoller
from codebuild_emulator import CodebuildEmulator

cwd = os.getcwd()
target = join(cwd, 'artifacts')


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
