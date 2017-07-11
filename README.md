# codebuild-emulator

Allows you to run your AWS CodeBuild projects on premisses.

Has 2 modes:

Developer in which you can run your CodeBuild project with a local directory as input artifact. The output artifact will be copied locally after the build finishes.

For example running ``codebuild-emulator.py developer --project my-cb-project --docker-version 1.27`` is going to fetch the CodeBuild project my-cb-project from AWS and get the required information to start the docker container, run the buildspec assuming the role defined in the CodeBuild project.


The server mode is there to work in coordination with a custom action in CodePipeline. It will poll for CodePipeline builds and run them locally.
For example ``codebuild-emulator.py server --provider my-provider --docker-version 1.27``
is going to poll for CodePipeline job id ``{'category': 'Build', 'owner': 'Custom', 'provider': 'my-provider', 'version': '1'}`` it expects a CodePipeline  actionConfiguration with a CodeBuild project name. 

So the CloudFormation step for this example CodePipeline action is going to look like this:
```yaml         
- Name: BuildStuff
  Actions:
  - InputArtifacts:
    - Name: InputArtifact
    Name: BuildStuff
    ActionTypeId:
      Category: Build
      Owner: Custom
      Version: '1'
      Provider: 'my-cb-project'
    Configuration:
      ProjectName: !Ref 'my-cb-project'
    OutputArtifacts:
    - Name: OutputArtifact
    RunOrder: 1
```

Requirements:
- Docker 
- Python
- A machine with aws credentials configured or an EC2 instance with an InstanceProfile
- Using custom CodeBuild docker images in your CodeBuild project
- The role/user that starts codebuild-emulator has to be able to access CodePipeline, CodeBuild and ECR (only if you host you custom CodeBuild images there)
- A CodeBuild project
- The CodeBuild service role has to be assumable by the role you are running codebuild-emulator with 

Known limitations:
- Does not support Docker in docker builds yet

Future:
- Debug mode
