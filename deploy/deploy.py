"""Direct AWS API deployment. No CloudFormation/CDK. Reuses .deploy/state.json."""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
REGION = 'us-east-1'
NAME = 'c2g-demo'


def main():
    os.chdir(ROOT)
    folder = ROOT / '.deploy'
    folder.mkdir(mode=0o700, exist_ok=True)
    state_path = folder / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    session = boto3.Session(region_name=REGION)
    clients = {n: session.client(n, config=Config(retries={'mode': 'standard', 'max_attempts': 5}))
               for n in ['sts', 'ec2', 'elbv2', 'ecs', 'ecr', 'iam', 'logs', 's3', 'cloudfront', 'ssm']}
    ec2, elb, ecs, iam, cf, s3 = [clients[n] for n in ['ec2', 'elbv2', 'ecs', 'iam', 'cloudfront', 's3']]
    account = clients['sts'].get_caller_identity()['Account']
    if state.get('account', account) != account:
        raise ValueError('Deployment state belongs to a different AWS account')
    state['account'] = account

    def save():
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2, default=str))
        temporary.chmod(0o600)
        temporary.replace(state_path)

    def once(key, create):
        if key not in state:
            state[key] = create()
            save()
        return state[key]

    def tags(kind, label):
        return [{'ResourceType': kind, 'Tags': [{'Key': 'Name', 'Value': label}, {'Key': 'Project', 'Value': NAME}]}]

    print('Creating dedicated VPC and security groups', flush=True)
    vpc = once('vpc', lambda: ec2.create_vpc(CidrBlock='10.82.0.0/16', TagSpecifications=tags('vpc', NAME))['Vpc']['VpcId'])
    ec2.modify_vpc_attribute(VpcId=vpc, EnableDnsHostnames={'Value': True})
    igw = once('igw', lambda: ec2.create_internet_gateway(TagSpecifications=tags('internet-gateway', NAME))['InternetGateway']['InternetGatewayId'])
    once('igw_attached', lambda: (ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc), True)[1])
    route = once('route', lambda: ec2.create_route_table(VpcId=vpc, TagSpecifications=tags('route-table', NAME))['RouteTable']['RouteTableId'])
    once('default_route', lambda: (ec2.create_route(RouteTableId=route, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw), True)[1])
    for i, az in enumerate(['us-east-1a', 'us-east-1b']):
        for kind, octet in [('public', i + 1), ('private', i + 11)]:
            key = f'{kind}_{i}'
            subnet = once(key, lambda: ec2.create_subnet(VpcId=vpc, CidrBlock=f'10.82.{octet}.0/24', AvailabilityZone=az, TagSpecifications=tags('subnet', f'{NAME}-{key}'))['Subnet']['SubnetId'])
            if kind == 'public':
                once(f'association_{i}', lambda: ec2.associate_route_table(RouteTableId=route, SubnetId=subnet)['AssociationId'])
    alb_sg = once('alb_sg', lambda: ec2.create_security_group(GroupName=f'{NAME}-alb', Description='CloudFront VPC origin to ALB', VpcId=vpc)['GroupId'])
    task_sg = once('task_sg', lambda: ec2.create_security_group(GroupName=f'{NAME}-task', Description='ALB to ECS only', VpcId=vpc)['GroupId'])
    # VPC origin creates a service-managed SG; prefix list admits CloudFront while it provisions.
    prefix = ec2.describe_managed_prefix_lists(Filters=[{'Name': 'prefix-list-name', 'Values': ['com.amazonaws.global.cloudfront.origin-facing']}])['PrefixLists'][0]['PrefixListId']
    once('alb_ingress', lambda: (ec2.authorize_security_group_ingress(GroupId=alb_sg, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'PrefixListIds': [{'PrefixListId': prefix}]}]), True)[1])
    once('task_ingress', lambda: (ec2.authorize_security_group_ingress(GroupId=task_sg, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 8090, 'ToPort': 8090, 'UserIdGroupPairs': [{'GroupId': alb_sg}]}]), True)[1])

    print('Preparing scoped ECS roles and encrypted login password', flush=True)
    token_path = folder / 'login-password.txt'
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32))
        token_path.chmod(0o600)
    parameter = f'/{NAME}/login-password'
    clients['ssm'].put_parameter(Name=parameter, Type='SecureString', Value=token_path.read_text().strip(), Overwrite=True)
    param_arn = f'arn:aws:ssm:{REGION}:{account}:parameter{parameter}'
    trust = json.dumps({'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'ecs-tasks.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]})
    execution = once('execution_role', lambda: iam.create_role(RoleName=f'{NAME}-execution', AssumeRolePolicyDocument=trust)['Role']['Arn'])
    task_role = once('task_role', lambda: iam.create_role(RoleName=f'{NAME}-task', AssumeRolePolicyDocument=trust)['Role']['Arn'])
    def policy(role, statements):
        iam.put_role_policy(RoleName=role, PolicyName=NAME, PolicyDocument=json.dumps({'Version': '2012-10-17', 'Statement': statements}))
    repo = once('repository', lambda: clients['ecr'].create_repository(repositoryName=NAME, imageScanningConfiguration={'scanOnPush': True})['repository']['repositoryUri'])
    clients['ecr'].put_lifecycle_policy(repositoryName=NAME, lifecyclePolicyText=json.dumps({'rules': [{'rulePriority': 1, 'description': 'Keep 10 images', 'selection': {'tagStatus': 'any', 'countType': 'imageCountMoreThan', 'countNumber': 10}, 'action': {'type': 'expire'}}]}))
    log_group = f'/ecs/{NAME}'
    once('logs', lambda: (clients['logs'].create_log_group(logGroupName=log_group), log_group)[1])
    clients['logs'].put_retention_policy(logGroupName=log_group, retentionInDays=7)
    policy(f'{NAME}-execution', [
        {'Effect': 'Allow', 'Action': 'ecr:GetAuthorizationToken', 'Resource': '*'},
        {'Effect': 'Allow', 'Action': ['ecr:BatchCheckLayerAvailability', 'ecr:GetDownloadUrlForLayer', 'ecr:BatchGetImage'], 'Resource': f'arn:aws:ecr:{REGION}:{account}:repository/{NAME}'},
        {'Effect': 'Allow', 'Action': ['logs:CreateLogStream', 'logs:PutLogEvents'], 'Resource': f'arn:aws:logs:{REGION}:{account}:log-group:{log_group}:*'},
        {'Effect': 'Allow', 'Action': 'ssm:GetParameters', 'Resource': param_arn}])
    resources = [f'arn:aws:bedrock:{r}::foundation-model/{p}*' for r in ['us-east-1', 'us-east-2', 'us-west-2'] for p in ['anthropic.claude-', 'openai.gpt-']]
    resources += [f'arn:aws:bedrock:{REGION}:{account}:inference-profile/us.{p}*' for p in ['anthropic.', 'openai.']]
    resources += [f'arn:aws:bedrock:{REGION}:{account}:project/default']
    policy(f'{NAME}-task', [
        {'Effect': 'Allow', 'Action': ['bedrock:ListFoundationModels', 'bedrock:ListInferenceProfiles'], 'Resource': '*'},
        {'Effect': 'Allow', 'Action': ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'], 'Resource': resources}])

    print('Building and pushing backend container', flush=True)
    image = f'{repo}:{int(time.time())}'
    subprocess.run(['docker', 'build', '-t', image, '.'], check=True)
    auth = clients['ecr'].get_authorization_token()['authorizationData'][0]
    username, password = base64.b64decode(auth['authorizationToken']).decode().split(':', 1)
    subprocess.run(['docker', 'login', '--username', username, '--password-stdin', auth['proxyEndpoint']], input=password.encode(), check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'push', image], check=True)
    state['image'] = image
    save()

    print('Creating internal ALB and Fargate service', flush=True)
    alb = once('alb', lambda: elb.create_load_balancer(Name=NAME, Scheme='internal', Type='application', Subnets=[state['private_0'], state['private_1']], SecurityGroups=[alb_sg])['LoadBalancers'][0])
    target = once('target', lambda: elb.create_target_group(Name=NAME, Protocol='HTTP', Port=8090, VpcId=vpc, TargetType='ip', HealthCheckPath='/api/health', HealthCheckIntervalSeconds=15, HealthyThresholdCount=2)['TargetGroups'][0]['TargetGroupArn'])
    elb.modify_target_group_attributes(TargetGroupArn=target, Attributes=[{'Key': 'deregistration_delay.timeout_seconds', 'Value': '30'}])
    once('listener', lambda: elb.create_listener(LoadBalancerArn=alb['LoadBalancerArn'], Protocol='HTTP', Port=80, DefaultActions=[{'Type': 'forward', 'TargetGroupArn': target}])['Listeners'][0]['ListenerArn'])
    cluster = once('cluster', lambda: ecs.create_cluster(clusterName=NAME)['cluster']['clusterArn'])
    task = ecs.register_task_definition(family=NAME, executionRoleArn=execution, taskRoleArn=task_role, networkMode='awsvpc', requiresCompatibilities=['FARGATE'], cpu='256', memory='512', runtimePlatform={'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'}, containerDefinitions=[{
        'name': 'api', 'image': image, 'essential': True, 'portMappings': [{'containerPort': 8090, 'protocol': 'tcp'}],
        'environment': [{'name': 'AWS_REGION', 'value': REGION}, {'name': 'DEMO_USERNAME', 'value': 'admin'}], 'secrets': [{'name': 'DEMO_PASSWORD', 'valueFrom': param_arn}],
        'readonlyRootFilesystem': True,
        'logConfiguration': {'logDriver': 'awslogs', 'options': {'awslogs-group': log_group, 'awslogs-region': REGION, 'awslogs-stream-prefix': 'api'}},
        'healthCheck': {'command': ['CMD', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8090/api/health')"], 'interval': 30, 'timeout': 5, 'retries': 3, 'startPeriod': 15}
    }])['taskDefinition']['taskDefinitionArn']
    state['task_definition'] = task
    save()
    if 'service' not in state:
        once('service', lambda: ecs.create_service(cluster=cluster, serviceName=NAME, taskDefinition=task, desiredCount=1, launchType='FARGATE', platformVersion='LATEST', networkConfiguration={'awsvpcConfiguration': {'subnets': [state['public_0'], state['public_1']], 'securityGroups': [task_sg], 'assignPublicIp': 'ENABLED'}}, loadBalancers=[{'targetGroupArn': target, 'containerName': 'api', 'containerPort': 8090}], deploymentConfiguration={'maximumPercent': 200, 'minimumHealthyPercent': 100, 'deploymentCircuitBreaker': {'enable': True, 'rollback': True}}, healthCheckGracePeriodSeconds=60)['service']['serviceArn'])
    else:
        ecs.update_service(cluster=cluster, service=NAME, taskDefinition=task)

    print('Creating private S3 origin and CloudFront VPC origin', flush=True)
    bucket = once('bucket', lambda: (s3.create_bucket(Bucket=f'{NAME}-{account}-{REGION}'), f'{NAME}-{account}-{REGION}')[1])
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={k: True for k in ['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets']})
    s3.put_bucket_ownership_controls(Bucket=bucket, OwnershipControls={'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
    s3.upload_file(str(ROOT / 'frontend/index.html'), bucket, 'index.html', ExtraArgs={'ContentType': 'text/html; charset=utf-8', 'CacheControl': 'no-cache'})
    oac = once('oac', lambda: cf.create_origin_access_control(OriginAccessControlConfig={'Name': NAME, 'SigningProtocol': 'sigv4', 'SigningBehavior': 'always', 'OriginAccessControlOriginType': 's3'})['OriginAccessControl']['Id'])
    elb.get_waiter('load_balancer_available').wait(LoadBalancerArns=[alb['LoadBalancerArn']])
    origin = once('vpc_origin', lambda: cf.create_vpc_origin(VpcOriginEndpointConfig={'Name': NAME, 'Arn': alb['LoadBalancerArn'], 'HTTPPort': 80, 'HTTPSPort': 443, 'OriginProtocolPolicy': 'http-only', 'OriginSslProtocols': {'Quantity': 1, 'Items': ['TLSv1.2']}})['VpcOrigin']['Id'])
    for attempt in range(80):
        status = cf.get_vpc_origin(Id=origin)['VpcOrigin']['Status']
        print('VPC origin:', status, flush=True)
        if status == 'Deployed':
            break
        if status not in ['Deploying', 'InProgress']:
            raise RuntimeError(f'Unexpected VPC origin status: {status}')
        time.sleep(15)
    else:
        raise TimeoutError('VPC origin not ready; rerun to resume')
    managed_groups = ec2.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc]}, {'Name': 'group-name', 'Values': ['CloudFront-VPCOrigins-Service-SG']}])['SecurityGroups']
    if managed_groups:
        once('origin_sg_ingress', lambda: (ec2.authorize_security_group_ingress(GroupId=alb_sg, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'UserIdGroupPairs': [{'GroupId': managed_groups[0]['GroupId']}]}]), True)[1])
        once('prefix_removed', lambda: (ec2.revoke_security_group_ingress(GroupId=alb_sg, IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'PrefixListIds': [{'PrefixListId': prefix}]}]), True)[1])
    static_behavior = {'TargetOriginId': 's3', 'ViewerProtocolPolicy': 'redirect-to-https', 'TrustedSigners': {'Enabled': False, 'Quantity': 0}, 'Compress': True, 'CachePolicyId': '658327ea-f89d-4fab-a63d-7e88639e58f6', 'ResponseHeadersPolicyId': '67f7725c-6f97-4210-82d7-5512b31e9d03'}
    api_behavior = {'PathPattern': '/api/*', 'TargetOriginId': 'api', 'ViewerProtocolPolicy': 'https-only', 'TrustedSigners': {'Enabled': False, 'Quantity': 0}, 'Compress': True, 'AllowedMethods': {'Quantity': 7, 'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'], 'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']}}, 'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad', 'OriginRequestPolicyId': 'b689b0a8-53d0-40ab-baf2-68738e2966ac', 'ResponseHeadersPolicyId': '67f7725c-6f97-4210-82d7-5512b31e9d03'}
    dist = once('distribution', lambda: cf.create_distribution(DistributionConfig={
        'CallerReference': f'{NAME}-{time.time_ns()}', 'Comment': NAME, 'Enabled': True, 'DefaultRootObject': 'index.html', 'PriceClass': 'PriceClass_100', 'HttpVersion': 'http2', 'IsIPV6Enabled': True,
        'Origins': {'Quantity': 2, 'Items': [
            {'Id': 's3', 'DomainName': f'{bucket}.s3.{REGION}.amazonaws.com', 'OriginAccessControlId': oac, 'S3OriginConfig': {'OriginAccessIdentity': ''}},
            {'Id': 'api', 'DomainName': alb['DNSName'], 'VpcOriginConfig': {'VpcOriginId': origin, 'OriginReadTimeout': 60, 'OriginKeepaliveTimeout': 5}}]},
        'DefaultCacheBehavior': static_behavior, 'CacheBehaviors': {'Quantity': 1, 'Items': [api_behavior]}, 'ViewerCertificate': {'CloudFrontDefaultCertificate': True}
    })['Distribution'])
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({'Version': '2012-10-17', 'Statement': [{'Sid': 'CloudFrontOACOnly', 'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'}, 'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{bucket}/*', 'Condition': {'StringEquals': {'AWS:SourceArn': dist['ARN']}}}]}))
    cf.create_invalidation(DistributionId=dist['Id'], InvalidationBatch={'Paths': {'Quantity': 1, 'Items': ['/*']}, 'CallerReference': str(time.time_ns())})
    print('Waiting for ECS and CloudFront readiness', flush=True)
    ecs.get_waiter('services_stable').wait(cluster=cluster, services=[NAME], WaiterConfig={'Delay': 15, 'MaxAttempts': 80})
    services = ecs.describe_services(cluster=cluster, services=[NAME])['services']
    if services[0]['taskDefinition'] != task or services[0]['runningCount'] != 1:
        raise RuntimeError('ECS rolled back or task is not running')
    cf.get_waiter('distribution_deployed').wait(Id=dist['Id'], WaiterConfig={'Delay': 15, 'MaxAttempts': 80})
    state['url'] = f'https://{dist["DomainName"]}'
    save()
    print('Ready:', state['url'], flush=True)
    print('Username: admin. Password is in .deploy/login-password.txt (not printed)', flush=True)


if __name__ == '__main__':
    main()
