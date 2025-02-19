pipeline {
    agent any
    parameters {
        string(name: 'FAILED_JOB_NAME', defaultValue: '', description: 'Name des fehlgeschlagenen Jobs')
        string(name: 'FAILED_BUILD_NUMBER', defaultValue: '', description: 'Buildnummer des fehlgeschlagenen Jobs')
    }
    stages {
        stage('Build Docker Image') {
            steps {
                sh 'docker build -t analyze-log-image .'
            }
        }
        stage('Analyze log') {
            steps {
                withCredentials([
                    string(credentialsId: 'jenkins-api-token', variable: 'JENKINS_API_TOKEN'),
                    string(credentialsId: 'openai-api-token', variable: 'OPENAI_API_TOKEN')
                ]) {
                    sh '''
                        docker run --rm \
                        -e LANG=C.UTF-8 \
                        -e LC_ALL=C.UTF-8 \
                        -e JENKINS_API_TOKEN=${JENKINS_API_TOKEN} \
                        -e OPENAI_API_TOKEN=${OPENAI_API_TOKEN} \
                        -e FAILED_JOB_NAME=${FAILED_JOB_NAME} \
                        -e FAILED_BUILD_NUMBER=${FAILED_BUILD_NUMBER} \
                        analyze-log-image > analysis_report.txt
                    '''
                }
            }
        }
    }
}
