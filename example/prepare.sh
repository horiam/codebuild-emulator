#!/usr/bin/env bash

git clone --depth 1 https://github.com/aws/aws-codebuild-docker-images.git
cd aws-codebuild-docker-images/ubuntu/java/openjdk-8/
docker build -t 'aws/codebuild/java:openjdk-8' .
cd -
cd aws-codebuild-docker-images/ubuntu/docker/1.12.1/
docker build -t 'aws/codebuild/docker:1.12.1' .
cd - 
git clone --depth 1 https://github.com/spring-guides/gs-spring-boot.git
