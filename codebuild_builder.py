#!/usr/bin/env python

import shutil
import os
from os.path import join
import subprocess
import yaml
import glob
import json
import time

class CodebuildBuilder:

    def __init__(self, input_dir, output_dir, debug):
       self._input_dir = input_dir
       self._output_dir = output_dir
       self._debug = debug or os.path.exists(join(output_dir, 'debug'))
       self._returncodes = {}
       self._succeeded = True

    def _parse_buildspec(self):
        buildspec = self._get_buiildspec()
        self._version = buildspec['version']
        self._envs = buildspec['env']['variables'] if 'env' in buildspec else []
        self._phases = buildspec['phases']
        self._artifacts = buildspec['artifacts']

    def _run_phase(self, phase_name):
        if not phase_name in self._phases:
            self._returncodes[phase_name] = 0
            return True

        tmp = join(self._output_dir, 'tmp')
        envsh = join(tmp, 'env.sh')

        if not os.path.exists(envsh):
           with open(envsh, 'w') as envshfile:
               with open(join(self._input_dir, 'variables.json'), 'r') as variablesfile:
                   variables = json.load(variablesfile)
               for key in variables:
                   envshfile.write("export %s=%s\n" % (key, variables[key]))
               for key in self._envs:
                   envshfile.write("export %s=%s\n" % (key, self._envs[key]))
           os.chmod(envsh, 500)

        shell = join(tmp, 'shell.sh')
        pwd = join(tmp, 'pwd.txt')

        rc = 0
        for command in self._phases[phase_name]['commands']:
            with open(shell, 'w') as shellfile:
                shellfile.write("cd $(cat %s)\n" % pwd)
                shellfile.write(". %s\n" % envsh)
                shellfile.write("set -ae\n")
                shellfile.write(command + '\n')
                shellfile.write("export -p > %s\n" % envsh)
                shellfile.write("pwd > %s\n" % pwd)
            os.chmod(shell, 500)
            # debug mode
            if self._debug:
                print(command)
                print('Do you want to run this command ? [Enter/S/X] ')
                skip = self._wait_for_debug()
                if skip:
                   continue

            rc = subprocess.call(shell, shell=True)

            if not rc == 0:
                self._succeeded = False
                if not self._debug:
                    break

        self._returncodes[phase_name] = rc
        return rc == 0

    def _upload_artifacts(self):
        base_directory = self._artifacts['base-directory'] + '/' if 'base-directory' in self._artifacts else ''
        discard_paths = self._artifacts['discard-paths']

        artifact_dir = join(self._output_dir, 'artifacts')

        print("Uploading artifacts")

        if '**/*' in self._artifacts['files']:
            shutil.copytree(join(self._src, base_directory), artifact_dir)
        else:
            os.mkdir(artifact_dir)
            for element in self._artifacts['files']:
                for artifact in glob.glob(join(self._src, base_directory, element)):
                    if os.path.isdir(artifact):
                        continue
                    if discard_paths:
                        shutil.copy2(artifact, artifact_dir)
                    else:
                        subprocess.Popen(['cp','--parents',artifact,artifact_dir], cwd=self._src).wait()

    def _process_buildspec_phase(self, phases, phase_name):
        if phase_name in phases:
            commands = phases[phase_name]['commands']
            return commands
        return []

    def _get_buiildspec(self):
        buildspec_path = join(self._input_dir, 'buildspec.yml')
        with open(buildspec_path, 'r') as stream:
            buildspec = yaml.load(stream)
            return buildspec

    def _prepare_output(self):
        self._src = join(self._output_dir, 'src123456789')
        shutil.copytree(join(self._input_dir, 'src'),
                        self._src)
        tmp = join(self._output_dir, 'tmp')
        os.mkdir(tmp)

        with open(join(tmp, 'pwd.txt'), 'w') as pwdfile:
            pwdfile.write(self._src)

    def _run_phases(self):
        if self._run_phase('install') and self._run_phase('pre_build'):
            self._run_phase('build')
            self._run_phase('post_build')
            return True
        else:
            return False

    def run(self):
        try:
            self._prepare_output()
            self._parse_buildspec()

            if self._run_phases():
                self._upload_artifacts()

            if not self._succeeded:
                raise Exception('Build failed')
        except:
            raise

    def _wait_for_debug(self):
        skip = False
        debug_flag = join(self._output_dir, 'debug')
        while os.path.exists(debug_flag):
            time.sleep(1)

        skip_flag = join(self._output_dir, 'skip')
        if os.path.exists(skip_flag):
            skip = True
            os.unlink(skip_flag)
        elif os.path.exists(join(self._output_dir, 'exit')):
            exit()

        open(debug_flag, 'a').close()
        return skip

if __name__ == '__main__':
    builder = CodebuildBuilder(input_dir='/codebuild/readonly',
                               output_dir='/codebuild/output',
                               debug=False)
    builder.run()
