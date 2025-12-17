pipeline {
  agent any

  options {
    disableConcurrentBuilds()
  }

  environment {
    // Fixed to QA; defaults set to avoid unset-variable errors
    APP_ENV    = 'qa'
    APP_PORT   = '8510'
    IMAGE_NAME = 'ats-agent-job-agents1-service:qa'
    CONTAINER  = 'ats-agent-job-agents1-qa'
    LOG_PATH   = '/home/supriyo/ai_agents_qa/LOGS'
    NETWORK    = 'ats-qa-network'
  }

  stages {
    stage('Guard Branch') {
      when { expression { return env.BRANCH_NAME != null } }
      steps {
        script {
          if (env.BRANCH_NAME != 'qa') {
            echo "Skipping build: only qa branch is allowed (current: ${env.BRANCH_NAME})"
            currentBuild.result = 'NOT_BUILT'
            return
          }
        }
      }
    }

    stage('Init') {
      when { branch 'qa' }
      steps {
        script {
          // For now we deploy only QA. To re-enable branch-based mapping:
          // def branch = env.BRANCH_NAME ?: 'unknown'
          // def envMap = [
          //   'main'    : 'prod',
          //   'master'  : 'prod',
          //   'qa'      : 'qa',
          //   'release' : 'qa',
          //   'develop' : 'dev',
          //   'dev'     : 'dev'
          // ]
          // env.APP_ENV = envMap.get(branch, 'qa')
          env.APP_ENV = 'qa'    

          // Map env → port; adjust if you prefer different ports
          def portMap = [dev: '8410', qa: '8510', prod: '8610']
          def networkMap = [dev: 'ats-dev-network', qa: 'ats-qa-network', prod: 'ats-prod-network']
          env.APP_PORT   = portMap[env.APP_ENV]
          env.IMAGE_NAME = "ats-agent-job-agents1-service:${env.APP_ENV}"
          env.CONTAINER  = "ats-agent-job-agents1-${env.APP_ENV}"
          // Log path fixed per request; adjust map if enabling other envs
          env.LOG_PATH   = "/home/supriyo/ai_agents_qa/LOGS"
          env.FILE_PATH  = "/home/supriyo/ai_agents_qa/FILES"
          env.LOGO_PATH  = ''
          env.IMAGE_FILE_PATH  = "/home/supriyo/ai_agents_qa/IMAGES"
          env.NETWORK    = networkMap[env.APP_ENV]
          env.PDFKIT_PATH = ''
          env.BASE_URL = ''
          env.REDIS_DB = 0
          env.REDIS_PASSWORD = ''
          env.GEMINI_MODEL_NAME = 'gemini-2.5-flash'
          env.ACCESS_TOKEN_EXPIRE_HOURS = 24
        }
      }
    }

    stage('Checkout') {
      when { branch 'qa' }
      steps {
        checkout scm
      }
    }

    stage('Build Image') {
      when { branch 'qa' }
      steps {
        sh """
          docker build -t ${IMAGE_NAME} .
        """
      }
    }

    stage('Stop Old Container') {
      when { branch 'qa' }
      steps {
        sh """
          docker stop ${CONTAINER} 2>/dev/null || true
          docker rm -f ${CONTAINER} 2>/dev/null || true
        """
      }
    }

    stage('Run Container') {
      when { branch 'qa' }
      steps {
        script {
          // Expect per-env Jenkins credentials:
          // dbCreds-<env>      : usernamePassword (DB user/pass)
          // dbHost-<env>       : secret text (DB_HOST)
          // dbPort-<env>       : secret text (DB_PORT)
          // dbName-<env>       : secret text (DB_NAME)
          // jwtSecret-<env>    : secret text (JWT_SECRET_KEY)
          // docsCreds-<env>    : usernamePassword (DOCS_USERNAME/PASSWORD)
          // Credentials IDs are used as-is (no env suffix appended)
          def cred = { base -> base }

          withCredentials([
            // Google API
            string(credentialsId: cred('QA_GEMINI_API_KEY'), variable: 'GOOGLE_API_KEY'),
            // Application
            string(credentialsId: cred('QA-FILE-HANDLING-API'), variable: 'FILE_HANDLING_API_KEY'),
            string(credentialsId: cred('QA-AUTH-URL'), variable: 'AUTH_SERVICE_URL'),
            // JWT
            string(credentialsId: cred('AI-JWT-SECRET-KEY'), variable: 'JWT_SECRET_KEY'),
            
            // Database
            string(credentialsId: cred('AI-DB-HOST'), variable: 'DB_HOST'),
            string(credentialsId: cred('AI-DB-PORT'), variable: 'DB_PORT'),
            string(credentialsId: cred('AI-DB-NAME-QA'), variable: 'DB_NAME'),
            string(credentialsId: cred('AI-DB-QA-USER'), variable: 'DB_USER'),
            string(credentialsId: cred('AI-DB-QA-PASS'), variable: 'DB_PASSWORD'),
            
            // Redis
            string(credentialsId: cred('REDIS-HOST'), variable: 'REDIS_HOST'),
            string(credentialsId: cred('REDIS-PORT'), variable: 'REDIS_PORT'),
            
            // SMTP
            string(credentialsId: cred('QA-SMTP-EMAIL'), variable: 'SMTP_EMAIL'),
            string(credentialsId: cred('QA-SMTP-PASSWORD'), variable: 'SMTP_PASSWORD'),
            string(credentialsId: cred('QA-SMTP-SERVER'), variable: 'SMTP_SERVER'),
            string(credentialsId: cred('QA-SMTP-PORT'), variable: 'SMTP_PORT'),
            
          ]) {
            sh """
              docker run -d --name ${CONTAINER} --restart unless-stopped \\
                --add-host=host.docker.internal:host-gateway \\
                --network ${NETWORK} \\
                -p ${APP_PORT}:${APP_PORT} \\
                -e APP_ENV=${env.APP_ENV} \\
                -e APP_PORT=${APP_PORT} \\
                -e SERVICE_TYPE=api \\
                -e CELERY_LOGLEVEL=debug \\
                -e CELERY_CONCURRENCY=4 \\
                -e GOOGLE_API_KEY=$GOOGLE_API_KEY \\
                -e GOOGLE_MODEL_NAME=${GEMINI_MODEL_NAME} \\
                -e JOB_AGENT_LOG=${LOG_PATH} \\
                -e FILE_HANDLING_API_KEY=${FILE_HANDLING_API_KEY} \\
                -e AUTH_SERVICE_URL=$AUTH_SERVICE_URL \\
                -e ACCESS_TOKEN_EXPIRE_HOURS=${ACCESS_TOKEN_EXPIRE_HOURS} \\
                -e JWT_SECRET_KEY=$JWT_SECRET_KEY \\
                -e JWT_ALGORITHM=HS256 \\
                -e DB_HOST=$DB_HOST \\
                -e DB_PORT=$DB_PORT \\
                -e DB_NAME=$DB_NAME \\
                -e DB_USER=$DB_USER \\
                -e DB_PASSWORD=$DB_PASSWORD \\
                -e PDFKIT_PATH=${PDFKIT_PATH} \\
                -e IMAGE_PATH=${IMAGE_FILE_PATH} \\
                -e REDIS_HOST=$REDIS_HOST \\
                -e REDIS_PORT=$REDIS_PORT \\
                -e REDIS_DB=${REDIS_DB} \\
                -e REDIS_PASSWORD=${REDIS_PASSWORD} \\
                -e BASE_URL=${BASE_URL} \\
                -e SMTP_SERVER=$SMTP_SERVER \\
                -e SMTP_PORT=$SMTP_PORT \\
                -e SMTP_EMAIL=$SMTP_EMAIL \\
                -e SMTP_PASSWORD=$SMTP_PASSWORD \\
                -e LOGO_PATH=${LOGO_PATH} \\
                -v ${LOG_PATH}:${LOG_PATH} \\
                -v ${FILE_PATH}:${FILE_PATH} \\
                -v ${IMAGE_FILE_PATH}:${IMAGE_FILE_PATH} \\
                ${IMAGE_NAME}
            """
          }
        }
      }
    }
  }

  post {
    always {
      sh 'command -v docker >/dev/null 2>&1 && docker ps -a --filter "name=ats-agent-job-agents1-qa" || echo "docker not available on agent"'
    }
    failure {
      echo "Deployment failed for ${env.APP_ENV}"
    }
  }
}

