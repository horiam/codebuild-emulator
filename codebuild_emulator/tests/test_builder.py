import unittest
import shutil
import os
from codebuild_builder import CodebuildBuilder
from os.path import join
import threading
import time

class TestBuilder(unittest.TestCase):

    def _prepare_test(self, input_dir='good'):
        this_dir = os.path.dirname(os.path.realpath(__file__))
        output_dir = join(this_dir, 'tmp', 'output')
        readonly_dir = join(this_dir, 'data', 'input', input_dir)

        shutil.rmtree(output_dir, ignore_errors=True)
        os.makedirs(output_dir)
        return output_dir, readonly_dir

    def test_prepare_output(self):
        print 'test_prepare_output'
        output_dir, readonly_dir = self._prepare_test()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)
        builder._prepare_output()

        output_src = join(output_dir, 'src123456789')
        self.assertTrue(os.path.exists(join(output_src, 'source.foo')))

        pwd_txt = join(output_dir, 'tmp', 'pwd.txt')
        self.assertTrue(os.path.exists(pwd_txt))
        with open(pwd_txt, 'r') as pwd_txt_file:
            lines = pwd_txt_file.readlines()

        self.assertEqual(lines, [str(output_src)])

    def test_parse_buildspec(self):
        print 'test_parse_buildspec'
        output_dir, readonly_dir = self._prepare_test()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)
        builder._parse_buildspec()

        self.assertEqual(builder._version, 0.2)
        self.assertDictEqual(builder._envs, {'install': 'install', 'build': 'build'})

        self._verify_phase('install', builder._phases)
        self._verify_phase('pre_build', builder._phases)
        self._verify_phase('build', builder._phases)
        self._verify_phase('post_build', builder._phases)

        self.assertEqual(builder._artifacts['files'], ['**/*'])

    def _verify_phase(self, name, phases):
        self.assertTrue(name in phases)
        self.assertEqual(phases[name]['commands'], ['ls', "echo $%s > %s" % (name, name)])

    def test_run_phases(self):
        print 'test_run_phases'
        output_dir, readonly_dir = self._prepare_test()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)
        builder._prepare_output()
        builder._parse_buildspec()
        builder._run_phases()

        output_src = join(output_dir, 'src123456789')
        for expected_file_name in ['install', 'pre_build',
                                   'build', 'post_build']:
            expected_file_path = join(output_src, expected_file_name)
            print expected_file_path
            self.assertTrue(os.path.exists(expected_file_path))
            with open(expected_file_path, 'r') as expected_file:
                lines = expected_file.readlines()
            self.assertEqual(lines, [str(expected_file_name) + '\n'])

    def test_upload_artifacts(self):
        print 'test_upload_artifacts'
        output_dir, readonly_dir = self._prepare_test()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)
        builder._prepare_output()
        builder._parse_buildspec()
        builder._run_phases()
        builder._upload_artifacts()

        artifacts_dir = join(output_dir, 'artifacts')
        for expected_file_name in ['source.foo', 'install', 'pre_build',
                                   'build', 'post_build']:
            expected_file_path = join(artifacts_dir, expected_file_name)
            print expected_file_path
            self.assertTrue(os.path.exists(expected_file_path))

    def test_successful_run(self):
        print 'test_successful_run'
        output_dir, readonly_dir = self._prepare_test()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)
        builder.run()
        self.assertTrue(builder._succeeded)

    def test_failing_run(self):
        print 'test_failing_run'
        output_dir, readonly_dir = self._prepare_test('bad')
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)

        expected_exception_massage = ''
        try:
            builder.run()
        except Exception as e:
            expected_exception_massage = str(e)

        self.assertEqual(expected_exception_massage, 'Build failed')

        artifacts_dir = join(output_dir, 'artifacts')
        # needs to upload the files because build failed
        for expected_file_name in ['source.foo', 'install',
                                   'pre_build', 'post_build']:
            expected_file_path = join(artifacts_dir, expected_file_name)
            print expected_file_path
            self.assertTrue(os.path.exists(expected_file_path))

    def test_debug_run(self):
        print 'test_debug_run'
        output_dir, readonly_dir = self._prepare_test()
        open(join(output_dir, 'debug'), 'a').close()
        builder = CodebuildBuilder(input_dir=readonly_dir,
                                   output_dir=output_dir,
                                   debug=False)

        run_thread = threading.Thread(target=builder.run)
        run_thread.start()
        time.sleep(1)

        # continue 'ls' command in install phase
        os.unlink(join(output_dir, 'debug'))
        time.sleep(1)
        # skip 'touch' command in install phase
        open(join(output_dir, 'skip'), 'a').close()
        os.unlink(join(output_dir, 'debug'))
        time.sleep(1)
        # skip 'ls' command in pre_build phase
        open(join(output_dir, 'skip'), 'a').close()
        os.unlink(join(output_dir, 'debug'))
        time.sleep(1)
        # continue 'touch' command in install phase
        os.unlink(join(output_dir, 'debug'))
        time.sleep(1)
        # stop run
        open(join(output_dir, 'exit'), 'a').close()
        os.unlink(join(output_dir, 'debug'))

        run_thread.join(timeout=10)
        self.assertTrue(not run_thread.is_alive())

        artifacts_dir = join(output_dir, 'src123456789')
        # needs to upload the files because build failed
        for expected_file_name in ['source.foo', 'pre_build']:
            expected_file_path = join(artifacts_dir, expected_file_name)
            print expected_file_path
            self.assertTrue(os.path.exists(expected_file_path))

        self.assertEquals(len(os.listdir(artifacts_dir)), 2)

if __name__ == '__main__':
    unittest.main()
