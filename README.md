# codebuild-emulator

## What is it ?
codebuild-emulator is a tool for [AWS CodeBuild](https://aws.amazon.com/codebuild/) (CB) [projects](http://docs.aws.amazon.com/codebuild/latest/userguide/build-projects-working.html) users or maintainers to help test their CB projects on premises.

## How does it work ?
codebuild-emulator can run in two modes:
* developer: to run CB projects manually with a local input artifact
* server: to run CB projects from a AWS CodePipeline as a [custom action](http://docs.aws.amazon.com/codepipeline/latest/userguide/actions-create-custom-action.html)

## Developer mode
Will run the CB project locally and by passing it local input artifact as the content of directory. The output artifact will be put in a directory as well. 

Under the hood codebuild-emulator is:
1. Fetching the CB project from AWS
2. Assuming the service IAM role of the CB project
3. Pulling the CB docker image 
4. Starting the docker container from this image 
5. Runing a process in this container that will run all buildspec phases

### Example Usecase: 
*You can find all the files mentioned here in the example directory of this project.*

Let's say that you need a to build your java artefact and put in a docker container ready to be used. You can use AWS CodePipeline and CodeBuuild to that for you.  
The [CloudFormation template](example/pipeline.yaml) contains the definition of a CodePipeline with two CodeBuild stages that is going to build the [Spring Boot app example](https://spring.io/guides/gs/spring-boot/) then put in a docker image.   

To create the pipeline you need:
 * [GitHub OAthToken](https://help.github.com/articles/git-automation-with-oauth-tokens/)  
 * A docker registry where CodeBuild can push the docker image (AWS ECR for example)
 * The ARN of your IAM user or role - so that later you can assume the CodeBuild service IAM role
```bash
cd example/
aws cloudformation create-stack --stack-name example-pipeline \
--template-body file://pipeline.yaml \
--capabilities CAPABILITY_IAM \
--parameters \
ParameterKey=GitHubOAuthToken,ParameterValue=<Your GitHub OAthToken> \
ParameterKey=ImageTag,ParameterValue=<Name of you docker image> \
ParameterKey=MyIamRole,ParameterValue=<arn of your IAM user/role>
```

Run the prepare script that will clone the Spring Boot project and build the two docker images that the CB projects from the pipeline use (this can take some time).
```bash
./prepare.sh
```
Run the first CB project with codebuild-emulator - this will run the buildspec of the CB project to build the jar and put in the artifact directory:
```bash
cd gs-spring-boot/
cbemu developer --project example-pipeline-app-build
```

Now let's build the docker image and push it to the registry by running codebuild-emulator with the second CB project:
```bash
cd artifact/
cbemu developer --project example-pipeline-container-build 
```  
If you don't want to push the docker image use the ``--debug`` mode and skip the push step. Or you can change the docker image name by overriding the CB project's environment varible with ``--override IMAGE_TAG=my-other-test-registry.com/my-image`` for example.  


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
For example:  ```cbemu server --provider my-provider```
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
### Install
```pip install git+https://github.com/horiam/codebuild-emulator.git```
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

