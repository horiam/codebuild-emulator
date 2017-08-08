import unittest
import os
from os.path import join
import json
import shutil
from codebuild_emulator import CodebuildEmulator
from codebuild_emulator import CodebuildRun


this_dir = os.path.dirname(os.path.realpath(__file__))
with open(join(this_dir, 'data', 'batch-get-projects.out'), 'r') as batchgetprojects:
    batch_get_projects_response = json.load(batchgetprojects)
test_project = batch_get_projects_response['projects'][0]
assume_role_response = {'Credentials': {'AccessKeyId': 'access_key_id',
                                        'SecretAccessKey': 'secret_access_key',
                                        'SessionToken': 'session_token'}}
class TestEmulator(unittest.TestCase):

    def _prepare_test(self, input_dir='good'):
        this_dir = os.path.dirname(os.path.realpath(__file__))
        input_src = join(this_dir, 'data', 'input', input_dir, 'src')
        artifacts_dir = join(this_dir, 'tmp', 'artifacts')
        shutil.rmtree(artifacts_dir, ignore_errors=True)
        os.makedirs(artifacts_dir)
        work_dir = join(this_dir, 'tmp', 'work')
        shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(work_dir)
        return input_src, work_dir, artifacts_dir

    def test_get_project(self):
        print 'test_get_project'
        emulator = CodebuildEmulator('1.24', codebuild_client=Boto3Mock(batch_get_projects_response))
        project = emulator._get_project('daily-terminal-report-app-pipeline-build-daily-terminal-report-java-app')
        self.assertEquals(project, test_project)

    def test_assume_role(self):
        print 'test_assume_role'
        run = CodebuildRun(test_project, None, None,
                           Boto3Mock(assume_role_response))
        run.assume_role()
        self.assertEquals(run._access_key_id, 'access_key_id')
        self.assertEquals(run._secret_access_key, 'secret_access_key')
        self.assertEquals(run._session_token, 'session_token')

    def test_prepare_dirs(self):
        print 'prepare_dirs'
        input_src, work_dir, artifacts_dir = self._prepare_test()
        run = CodebuildRun(test_project, input_src, work_dir)
        run.prepare_dirs()
        self.assertTrue(os.path.exists(join(work_dir, 'codebuild', 'output')))
        self.assertTrue(os.path.exists(join(work_dir, 'codebuild', 'readonly', 'bin', 'executor')))
        self.assertTrue(os.path.exists(join(work_dir, 'codebuild', 'readonly', 'src', 'source.foo')))
        with open(join(work_dir, 'codebuild', 'readonly', 'buildspec.yml'), 'r') as buildspec:
            first_line = buildspec.readlines()[0]
        self.assertEqual(first_line, 'version: 0.2\n')
        with open(join(work_dir, 'codebuild', 'readonly', 'variables.json'), 'r') as variables_file:
            variables = json.load(variables_file)
        self.assertDictEqual(variables, {"TEST_ENV_VAR_1": "foo", "CODEBUILD_BUILD_ID": "XXXX", "TEST_ENV_VAR_2": "bar"})

    # requires docker image codebuild-emulator-test built from the provided Dockerfile
    def test_run_container(self):
        print 'test_run_container'
        input_src, work_dir, artifacts_dir = self._prepare_test()
        run = CodebuildRun(test_project, input_src, work_dir, Boto3Mock(assume_role_response))
        run.assume_role()
        run.prepare_dirs()
        run.run_container()
        exit_code = run.wait_for_container()
        self.assertEquals(exit_code, 0)
        #the rest is tested in test_builder

    def test_run(self):
        print 'test_run'
        input_src, work_dir, artifacts_dir = self._prepare_test()
        emulator = CodebuildEmulator('1.24',
                                     codebuild_client=Boto3Mock(batch_get_projects_response),
                                     sts_client=Boto3Mock(assume_role_response))
        exit_code = emulator.run({'ProjectName': 'my-codebuild-project'},
                                 input_src, artifacts_dir)
        self.assertEquals(exit_code, 0)
        self.assertTrue(os.path.exists(join(artifacts_dir, 'source.foo')))
        self.assertTrue(os.path.exists(join(artifacts_dir, 'build')))
        self.assertTrue(os.path.exists(join(artifacts_dir, 'install')))
        self.assertTrue(os.path.exists(join(artifacts_dir, 'pre_build')))
        self.assertTrue(os.path.exists(join(artifacts_dir, 'post_build')))


class Boto3Mock:
    def __init__(self, what_to_return):
        self._what_to_return = what_to_return

    def batch_get_projects(self, names):
        return self._what_to_return

    def assume_role(self, RoleArn, RoleSessionName):
        return self._what_to_return
