#!/usr/bin/python

import boto3
import shutil
import zipfile
import os
import tempfile
import time
import threading
from os.path import join
from botocore.client import Config


class JobPoller:

    def __init__(self, action_type_id, builder):
        self._action_type_id = action_type_id
        self._codepipeline = boto3.client('codepipeline')
        self._builder = builder

    def poll(self):
        jobs = []
        while not jobs:
            time.sleep(2)
            response = self._codepipeline.poll_for_jobs(actionTypeId=self._action_type_id, maxBatchSize=1)
            jobs = response['jobs']

        job = jobs[0]

        job_id = job['id']
        print(job_id)
        nonce = job['nonce']
        self._codepipeline.acknowledge_job(jobId=job_id, nonce=nonce)

        threading.Thread(target=self._build, args=(job,)).start()
        self.poll()


    def _build(self, job):

        job_id = job['id']

        try:
           artifactCredentials = job['data']['artifactCredentials']
           s3session = boto3.Session(
               aws_access_key_id=artifactCredentials['accessKeyId'],
               aws_secret_access_key=artifactCredentials['secretAccessKey'],
               aws_session_token=artifactCredentials['sessionToken'])

           s3 = s3session.client('s3', config=Config(signature_version='s3v4'))
           bucketName = job['data']['inputArtifacts'][0]['location']['s3Location']['bucketName']
           objectKey = job['data']['inputArtifacts'][0]['location']['s3Location']['objectKey']

           tempdir = tempfile.mkdtemp()
           print('tempdir for job %s is %s' % (job_id, tempdir))

           input_src = join(tempdir, 'input')
           os.mkdir(input_src)
           target = join(tempdir, 'output')
           os.mkdir(target)

           print('Downloading artifact %s from bucket %s' % (objectKey, bucketName))
           s3.download_file(bucketName, objectKey, join(tempdir, 'input.zip'))

           with zipfile.ZipFile(join(tempdir, 'input.zip'), 'r') as zip:
               zip.extractall(target)

           configuration = job['data']['actionConfiguration']['configuration']
           print('Using configuration %s' % configuration)

           #Run build
           rc = self._builder.run(configuration=configuration, input_src=input_src, target_dir=target)

           shutil.make_archive(join(tempdir, 'output'), 'zip', target)

           uploadBucket = job['data']['outputArtifacts'][0]['location']['s3Location']['bucketName']
           uploadKey = job['data']['outputArtifacts'][0]['location']['s3Location']['objectKey']

           print('Uploading artifact %s to bucket %s' % (uploadKey, uploadBucket))
           s3.upload_file(join(tempdir, 'output.zip'), uploadBucket, uploadKey)

           if not rc == 0:
               print('job %s failed with return code %d' % (job_id, rc))
               self._codepipeline.put_job_failure_result(jobId=job_id, failureDetails={'type': 'JobFailed', 'message': 'Failed'})
           else:
               self._codepipeline.put_job_success_result(jobId=job_id, executionDetails={'summary': 'It worked'})
               print('job %s succeeded' % job_id)

           shutil.rmtree(tempdir)
           print("Done with " + job_id)

        except:
           self._codepipeline.put_job_failure_result(jobId=job_id, failureDetails={'type': 'JobFailed', 'message': 'Failed'})

