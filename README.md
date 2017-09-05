# codebuild-emulator

## What is it ?
codebuild-emulator is a tool for [AWS CodeBuild](https://aws.amazon.com/codebuild/) (CB) [projects](http://docs.aws.amazon.com/codebuild/latest/userguide/build-projects-working.html) users or maintainers to help test their CB projects on premises.

## How does it work ?
codebuild-emulator can run in two modes:
* developer: to run CB projects manually with a local input artifact
* server: to run CB projects from a AWS CodePipeline as a [custom action](http://docs.aws.amazon.com/codepipeline/latest/userguide/actions-create-custom-action.html)

## Developer mode
Will run the CB project locally and by passing it local input artifact as the content of directory. The output artifact will be put in a directory as well. 
Usecase: Let's say that you want to run locally one of your CB projects (my-codebuild-project) that builds a jar form a java source code. You will run codebuild-emulator with the local java source code:  
```sh
cd my-java-sourcecode/
codebuild_emulator.py developer --project my-codebuild-project
```  
After running the codebuild-emulator will write what you specified in the CB project as an output artifcat (the JAR) in the local artifact/ directory.

Under the hood codebuild-emulator is:
1. Fetching the CB project from AWS
2. Assuming the service IAM role of the CB project
3. Pulling the CB docker image 
4. Starting the docker container from this image 
5. Runing a process in this container that will run all buildspec phases

### Command line arguments
```--project <project-name>```  
CB project name to use

```--debug```  
codebuild-emulator can pause before runnig each individual command from the buildspec and ask if you want to skip it or run it. Unlike the normal CB behaviour, the debug mode will continue after a failed command. 
It allows you to avoid running commands line that you don't want or give you the opportunity to go into the container before or after a command for debug purposes.

```--pull```  
Force pull of the docker image specified in the CB project.

```--no-assume```  
Skip the assume of the CB project service IAM role specified in the CB project. It will pass the actual user credentials to the container through environment variables. Useful if you can not assume the CB service role with your user. 

```--override```  
Override or pass an extra environment variable to the container. eg ``--override MY_ENV=foo,MY_OTHER_ENV=bar``

### Running docker in CodeBuild
For codebuild-emulator and underlying docker to be able to run docker in docker you need to configure your local docker daemon to overlay [storage driver](https://docs.docker.com/engine/userguide/storagedriver/overlayfs-driver/).

## Server mode
The server mode is there to work in coordination with a custom action in CodePipeline. It will poll for CodePipeline builds and run them locally.
For example:  ```codebuild_emulator.py server --provider my-provider```
is going to poll for CodePipeline job id ``{'category': 'Build', 'owner': 'Custom', 'provider': 'my-provider', 'version': '1'}`` it expects a CodePipeline actionConfiguration with a CodeBuild project name. 

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

### Requirements:
- Docker 
- Python and all codebuild-emulator dependencies installed
- A machine with aws credentials configured or an EC2 instance with an InstanceProfile
- Having the CB docker images locally or being able to pull them from where you run
- The IAM role/user that starts codebuild-emulator has to be able to access:
  * CodeBuild
  * CodePipeline (in server mode)
  * ECR (only if your custom CB docker images are in ECR)
- A CodeBuild project

### Future:
- A Vgrantfile to run codebuild-emulator
