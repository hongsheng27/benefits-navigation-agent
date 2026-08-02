# Infrastructure

The backend runs as a single ECS Fargate task behind an ALB, with CloudFront in
front of both the static frontend and the API. Everything here was created with
the AWS CLI rather than SAM or CDK; these files are the reproducible parts.

```
infra/
├── deploy.sh                  build → push → roll the service
└── ecs/
    ├── task-definition.json   envsubst template
    ├── trust-policy.json      assume-role policy for both roles
    └── task-role-policy.json  Bedrock invoke, one model only
```

## Shape

```
CloudFront (HTTPS, one distribution)
├── default             → S3 bucket (frontend/dist)
└── /sessions*, /health → ALB :80 → Fargate task :8000
```

One distribution serves both, so the frontend and API are same-origin and CORS
is not needed at all.

## Why desired count is 1, and must stay 1

Three pieces of state live inside the process, and each one breaks if a second
task or worker appears:

1. `InMemorySessionStore` keeps sessions on the FastAPI application instance.
2. `app/llm/bedrock.py` rate-limits Bedrock with a module-level global, and the
   competition quota is under one request per second per account.
3. `app/adapters/postgresql/connection.py` opens a pool of up to 10 RDS
   connections per process.

Scaling out means moving all three out of process first. Until then: one task,
one uvicorn worker, no autoscaling. The same reasoning rules out Lambda, whose
concurrency model is "one process per concurrent request".

## Why there is an ALB for a single task

Not for load balancing. CloudFront origins must be a domain name, and a Fargate
task gets a new public address every time it restarts — so a CloudFront origin
pointed straight at the task breaks silently on the next deployment. The ALB is
bought purely for a stable name. This is not hypothetical: it happened on
2026-08-02, and the symptom was a frontend that loaded fine with every API call
failing.

## Deploying

```bash
./infra/deploy.sh
```

It prints the caller identity before doing anything, because more than one set of
AWS credentials usually exists on a developer machine, and tags the image with
the commit SHA so "which code is running?" always has an answer.

Rolling the service replaces the task and **destroys every in-flight session**.
Freeze deployments before a demo.

## Creating the resources from scratch

The account already has these; this is the order to rebuild them in.

```bash
export AWS_ACCOUNT_ID=... AWS_REGION=us-west-2
export BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
export BEDROCK_FOUNDATION_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0

# 1. Roles. The execution role pulls the image and writes logs; the task role is
#    what the application itself uses. Keeping them apart means the application
#    never holds permission to pull images.
aws iam create-role --role-name jiezhu-ecs-execution \
  --assume-role-policy-document file://infra/ecs/trust-policy.json
aws iam attach-role-policy --role-name jiezhu-ecs-execution \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam create-role --role-name jiezhu-ecs-task \
  --assume-role-policy-document file://infra/ecs/trust-policy.json
envsubst < infra/ecs/task-role-policy.json > /tmp/task-role-policy.json
aws iam put-role-policy --role-name jiezhu-ecs-task \
  --policy-name bedrock-invoke --policy-document file:///tmp/task-role-policy.json

# 2. Logs. A retention policy is required by ADR-0007, not optional.
aws logs create-log-group --log-group-name /ecs/jiezhu-backend
aws logs put-retention-policy --log-group-name /ecs/jiezhu-backend --retention-in-days 7

# 3. Cluster, security groups, ALB, target group, listener, then the service.
#    Both security groups reference the CloudFront managed prefix list
#    (com.amazonaws.global.cloudfront.origin-facing) so nothing but CloudFront
#    reaches the ALB, and nothing but the ALB reaches the task.
```

## Things that cost time to rediscover

**The image must be ARM64.** It is built on Apple Silicon and the task
definition pins `cpuArchitecture: ARM64`. A mismatch fails with `exec format
error`, which names neither the architecture nor the image.

**The base image comes from `public.ecr.aws`.** Docker Hub and ghcr.io both reset
the connection from the venue network on 2026-08-02. It also avoids Docker Hub
pull-rate limits when ECS pulls the image.

**The API cache behaviours use `CachingDisabled`.** Caching a session snapshot
would hand one user's state to the next. They also have to allow POST and DELETE
— the default behaviour only allows GET and HEAD — and use
`AllViewerExceptHostHeader` so `X-Session-Id` and `Content-Type` reach the
backend.

**`VITE_API_BASE_URL` is baked in at build time.** Build the frontend with it
empty so the bundle uses relative paths; changing the variable after deploying
does nothing. Vite reads the repository-root `.env`, not `frontend/.env`.

**Both hops behind CloudFront are plain HTTP.** Viewer traffic is HTTPS;
CloudFront → ALB → task is not encrypted. Do not describe the system as
end-to-end encrypted.

## Not done yet

- RDS is not wired up. That needs a security-group rule from the task's group,
  the password in Secrets Manager injected through the task definition `secrets`
  field, an actual `benefits_navigation` database (the instance was created
  without one), and `scripts/migrate_sqlite_to_postgresql.py`. Switch
  `DATA_STORE_BACKEND` only after the container is known good, because the pool
  opens eagerly and an unreachable RDS becomes a container restart loop.
- No custom domain; the CloudFront default certificate is in use.
- No IaC. If this outlives the Hackathon, port it to SAM or CDK.
