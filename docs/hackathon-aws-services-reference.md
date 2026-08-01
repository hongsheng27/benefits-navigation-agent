# Hackathon AWS Services Reference

來源：Supported AWS Services List 20260722.xlsx
用途：快速查詢本次黑客松可用之 AWS 服務與限制。

## 與本專案相關的重點服務

以下列出本專案可能用到的 AWS 服務及其 IAM namespace。完整清單見原始附件。

### 資料庫與儲存

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| Amazon RDS | `rds` | ADR-0014 目標 (PostgreSQL) |
| Amazon RDS Data API | `rds-data` | Serverless 存取方式 |
| Amazon S3 | `s3` | 文件/附件儲存 |
| Amazon DynamoDB | `dynamodb` | 備選 |
| Amazon ElastiCache | `elasticache` | Cache 層備選 |

### AI/ML

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| Amazon Bedrock | `bedrock` | LLM 推論 (< 1 RPS) |
| Amazon Bedrock AgentCore | `bedrock-agentcore` | Agent 框架 |
| Amazon Comprehend | `comprehend` | NLP 備選 |
| Amazon Textract | `textract` | 文件 OCR 備選 |
| Amazon Kendra | `kendra` | RAG 備選 |
| Amazon OpenSearch Serverless | `aoss` | RAG 向量搜尋備選 |

### 運算與部署

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| Amazon EC2 | `ec2` | Standard 類型 256 vCPU 上限 |
| AWS Lambda | `lambda` | Serverless 運算 |
| Amazon ECS | `ecs` | Container 部署 |
| AWS Fargate (via ECS) | `ecs` | Serverless container |
| Amazon ECR | `ecr` | Container registry |
| AWS App Runner | — | 未在清單中確認 |

### API 與整合

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| Amazon API Gateway | `apigateway`, `execute-api` | HTTP API |
| AWS Step Functions | `states` | Workflow orchestration |
| Amazon EventBridge | `events` | Event-driven |
| Amazon SQS | `sqs` | Message queue |
| Amazon SNS | `sns` | Notification |

### 安全與身分

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| AWS IAM | `iam` | 身分管理 |
| AWS Secrets Manager | `secretsmanager` | 機密管理 |
| AWS KMS | `kms` | 加密金鑰 |
| Amazon Cognito | `cognito-idp`, `cognito-identity` | 使用者驗證備選 |

### 監控與日誌

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| Amazon CloudWatch | `cloudwatch` | 監控 |
| Amazon CloudWatch Logs | `logs` | 日誌 |
| AWS X-Ray | `xray` | Tracing |
| AWS CloudTrail | `cloudtrail` | 稽核 |

### 基礎設施

| 服務 | IAM Namespace | 備註 |
|------|---------------|------|
| AWS CloudFormation | `cloudformation` | IaC |
| AWS Systems Manager | `ssm` | 參數/設定管理 |
| Amazon Route 53 | `route53` | DNS |
| Amazon CloudFront | `cloudfront` | CDN |
| Elastic Load Balancing | `elasticloadbalancing` | 負載平衡 |

## EC2 vCPU 限額

| 執行個體類型 | vCPU |
|-------------|------|
| Standard (A, C, D, H, I, M, R, T, Z) | 256 |
| HPC | 192 |
| DL | 96 |
| F | 64 |
| Inf | 8 |
| Trn | 8 |
| G and VT | **0** (不可用) |
| P | **0** (不可用) |
| High Memory | **0** (不可用) |
| X | **0** (不可用) |

## SageMaker AI 重點限額

訓練與推論都有嚴格限制。詳見原始附件。重點：

- Endpoint: `ml.c5.large` 最多 8 個，GPU 類型大多為 0
- Training: 多數 GPU 類型限額為 0
- 不建議在平台上做大規模模型訓練

## 完整服務清單 (IAM Namespace)

以下為所有可用服務的 IAM namespace（依字母排序）：

```
a2c, access-analyzer, account, acm, acm-pca, aidevops, aiops, airflow,
airflow-serverless, amplify, amplifybackend, amplifyuibuilder, aoss,
apigateway, app-integrations, appconfig, appfabric, appflow,
application-autoscaling, application-signals, application-transformation,
applicationinsights, appmesh, appstream, appstudio, appsync, aps,
arc-region-switch, arc-zonal-shift, artifact, athena, autoscaling,
autoscaling-plans, aws-marketplace, b2bi, backup, backup-gateway,
backup-search, backup-storage, batch, bcm-data-exports, bedrock,
bedrock-agentcore, bedrock-mantle, billing, braket, budgets, cases,
cassandra, ce, chatbot, chime, cleanrooms, cleanrooms-ml, cloudformation,
cloudfront, cloudfront-keyvaluestore, cloudhsm, cloudshell, cloudtrail,
cloudwatch, codeartifact, codebuild, codecommit, codeconnections, codedeploy,
codeguru-profiler, codeguru-security, codepipeline, codestar-connections,
codestar-notifications, codewhisperer, cognito-identity, cognito-idp,
cognito-sync, comprehend, comprehendmedical, compute-optimizer, config,
connect, connect-campaigns, controlcatalog, cost-optimization-hub, cur,
databrew, dataexchange, datasync, datazone, deadline, detective, devicefarm,
devops-guru, directconnect, discovery, dlm, dms, drs, ds, ds-data, dsql,
dynamodb, ebs, ec2, ec2-instance-connect, ec2messages, ecr, ecr-public, ecs,
eks, eks-auth, elasticache, elasticbeanstalk, elasticfilesystem,
elasticloadbalancing, elasticmapreduce, emr-containers, emr-serverless,
entityresolution, es, events, execute-api, finspace, finspace-api, firehose,
fis, fms, fsx, gamelift, gameliftstreams, geo, geo-maps, geo-places,
geo-routes, glacier, globalaccelerator, glue, grafana, greengrass,
groundtruthlabeling, guardduty, health, healthlake, iam, identity-sync,
identitystore, imagebuilder, inspector-scan, inspector2, internetmonitor,
iot, iotdeviceadvisor, iotsitewise, iottwinmaker, iotwireless, ivs, ivschat,
kafka, kafka-cluster, kafkaconnect, kendra, kendra-ranking, kinesis,
kinesisanalytics, kinesisvideo, kms, lakeformation, lambda, launchwizard,
lex, license-manager, lightsail, logs, macie2, managedblockchain,
managedblockchain-query, mediaconnect, mediaconvert, mediaimport, medialive,
mediapackage, mediapackage-vod, mediapackagev2, mediatailor, medical-imaging,
memorydb, mgh, mgn, mq, neptune-db, neptune-graph, network-firewall,
networkflowmonitor, networkmanager, networkmonitor, notifications,
notifications-contacts, nova-act, observabilityadmin, omics, opensearch,
osis, outposts, payment-cryptography, pcs, personalize, pi, pipes, polly,
pricing, profile, q, qapps, qbusiness, qdeveloper, quicksight, ram, rds,
rds-data, rds-db, redshift, redshift-data, redshift-serverless, rekognition,
resiliencehub, resource-explorer, resource-explorer-2, resource-groups,
rolesanywhere, route53, route53-recovery-cluster,
route53-recovery-control-config, route53profiles, route53resolver, rum, s3,
s3-object-lambda, s3-outposts, s3express, s3files, s3tables, s3vectors,
sagemaker, scheduler, schemas, scn, secretsmanager, securityhub,
serverlessrepo, servicecatalog, servicediscovery, servicequotas, ses, shield,
signer, sns, social-messaging, sqs, ssm, ssm-guiconnect, ssm-quicksetup,
ssm-sap, ssmmessages, sso, sso-directory, sso-oauth, states,
storagegateway, sts, sustainability, synthetics, tag, textract,
timestream-influxdb, tiros, transcribe, transfer, translate, trustedadvisor,
user-subscriptions, verified-access, verifiedpermissions, vpc-lattice,
vpc-lattice-svcs, waf, waf-regional, wafv2, wellarchitected, wickr, wisdom,
workspaces, workspaces-instances, workspaces-web, xray
```

## 注意事項

- 上述限制可能依實際比賽情況調整，以競賽期間環境或公告為最終依據。
- 有疑問請於競賽期間向工作人員諮詢。
