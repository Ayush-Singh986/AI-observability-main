pipeline {
    agent {
        label 'aws-jenkins'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 45, unit: 'MINUTES')
    }

    parameters {
        string(name: 'AWS_REGION', defaultValue: 'us-east-1', description: 'AWS region containing EKS and ECR')
        string(name: 'EKS_CLUSTER_NAME', defaultValue: 'blame-the-deploy', description: 'EKS cluster to deploy into')
    }

    environment {
        KUBERNETES_NAMESPACE = 'online-boutique'
        RENDERED_MANIFEST = 'build/kubernetes-manifests.yaml'
        DEPLOYMENT_ATTEMPTED = 'false'
    }

    stages {
        stage('Validate tools and source files') {
            steps {
                sh '''
                    set -eu
                    command -v aws
                    command -v docker
                    command -v kubectl
                    command -v python3
                    test -f release/kubernetes-manifests.yaml
                    test -f release/image-sources.txt
                    python3 -m py_compile scripts/mirror-images-to-ecr.py scripts/index-deployment.py
                '''
            }
        }

        stage('Authenticate to AWS and ECR') {
            when {
                branch 'main'
            }
            steps {
                script {
                    env.AWS_ACCOUNT_ID = sh(
                        returnStdout: true,
                        script: 'aws sts get-caller-identity --query Account --output text'
                    ).trim()
                    env.ECR_REGISTRY = "${env.AWS_ACCOUNT_ID}.dkr.ecr.${params.AWS_REGION}.amazonaws.com"
                }
                sh '''
                    set -eu
                    aws ecr get-login-password --region "$AWS_REGION" \
                      | docker login --username AWS --password-stdin "$ECR_REGISTRY"
                '''
            }
        }

        stage('Mirror public images to ECR') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    set -eu
                    python3 scripts/mirror-images-to-ecr.py \
                      release/kubernetes-manifests.yaml "$RENDERED_MANIFEST"
                '''
            }
        }

        stage('Deploy to Amazon EKS') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    set -eu
                    aws eks update-kubeconfig \
                      --region "$AWS_REGION" \
                      --name "$EKS_CLUSTER_NAME"
                    kubectl apply --dry-run=client \
                      --namespace "$KUBERNETES_NAMESPACE" \
                      --filename "$RENDERED_MANIFEST"
                '''
                script {
                    env.DEPLOYMENT_ATTEMPTED = 'true'
                }
                sh '''
                    set -eu
                    kubectl apply \
                      --namespace "$KUBERNETES_NAMESPACE" \
                      --filename "$RENDERED_MANIFEST"

                    deployments=$(kubectl get deployments \
                      --namespace "$KUBERNETES_NAMESPACE" \
                      --output 'jsonpath={.items[*].metadata.name}')
                    test -n "$deployments"
                    for deployment in $deployments; do
                      kubectl rollout status "deployment/$deployment" \
                        --namespace "$KUBERNETES_NAMESPACE" \
                        --timeout=10m
                    done
                '''
            }
        }

    }

    post {
        success {
            echo 'The Online Boutique deployment completed successfully.'
        }
        failure {
            echo 'The pipeline failed. Check the stage logs and Kubernetes rollout status.'
        }
        always {
            script {
                if (env.BRANCH_NAME == 'main' && env.DEPLOYMENT_ATTEMPTED == 'true') {
                    withCredentials([
                        string(credentialsId: 'elastic-endpoint', variable: 'ES_ENDPOINT'),
                        string(credentialsId: 'elastic-api-key', variable: 'ES_API_KEY')
                    ]) {
                        sh """
                            set -eu
                            export AWS_REGION EKS_CLUSTER_NAME BUILD_URL GIT_COMMIT
                            DEPLOYMENT_RESULT='${currentBuild.currentResult}' \
                              python3 scripts/index-deployment.py
                        """
                    }
                }
            }
        }
    }
}
