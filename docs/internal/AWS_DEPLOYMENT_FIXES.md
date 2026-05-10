# AWS Deployment Fixes & Configuration

## 🚨 Critical Issues for AWS Deployment

### 1. **WebRTC TURN Server (CRITICAL)**

**Problem:** WebRTC won't work on AWS without a TURN server because:
- AWS instances are behind NAT
- Direct peer-to-peer connections fail
- Browser can't reach the server's local IP

**Solution:** Configure TURN server in `audio_capture_robust.py`

```python
def get_webrtc_config_for_saas() -> Dict[str, Any]:
    """Complete WebRTC configuration for AWS deployment."""
    return {
        "rtc_configuration": {
            "iceServers": [
                # Google STUN servers
                {"urls": ["stun:stun.l.google.com:19302"]},
                {"urls": ["stun:stun1.l.google.com:19302"]},
                {"urls": ["stun:stun2.l.google.com:19302"]},
                
                # CRITICAL: TURN server for AWS (required!)
                {
                    "urls": [
                        "turn:openrelay.metered.ca:80",
                        "turn:openrelay.metered.ca:443",
                        "turn:openrelay.metered.ca:443?transport=tcp"
                    ],
                    "username": "openrelayproject",
                    "credential": "openrelayproject",
                },
                
                # Backup TURN server
                {
                    "urls": ["turn:numb.viagenie.ca"],
                    "username": "webrtc@live.com",
                    "credential": "muazkh",
                },
            ],
        },
        "media_stream_constraints": {
            "video": {
                "width": {"ideal": 640, "max": 1280},
                "height": {"ideal": 480, "max": 720},
                "frameRate": {"ideal": 15, "max": 30},
            },
            "audio": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl": True,
            },
        },
        "sendback_audio": True,
    }
```

### 2. **Database Configuration**

**Problem:** SQLite doesn't work well on AWS (file locking, no scaling)

**Solution:** Use PostgreSQL on AWS RDS

**Update `database.py`:**

```python
import os
from sqlalchemy import create_engine

# AWS: Use environment variable for database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://username:password@your-rds-endpoint:5432/psysense"
)

# For local development, fallback to SQLite
if not os.getenv("AWS_EXECUTION_ENV"):
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./psysense.db")

engine = create_engine(
    DATABASE_URL,
    # Remove SQLite-specific args for PostgreSQL
    connect_args={} if DATABASE_URL.startswith("postgresql") else {"check_same_thread": False}
)
```

**AWS Environment Variables:**
```bash
DATABASE_URL=postgresql://admin:password@psysense-db.xxxxx.us-east-1.rds.amazonaws.com:5432/psysense
```

### 3. **File Storage (Audio/Video)**

**Problem:** Temporary files on EC2 are lost on restart

**Solution:** Use AWS S3 for file storage

**Create `aws_storage.py`:**

```python
import boto3
import os
from botocore.exceptions import ClientError

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'psysense-audio-files')

def upload_audio_to_s3(file_path: str, object_name: str = None) -> str:
    """Upload audio file to S3 and return URL."""
    if object_name is None:
        object_name = os.path.basename(file_path)
    
    try:
        s3_client.upload_file(file_path, BUCKET_NAME, object_name)
        url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{object_name}"
        return url
    except ClientError as e:
        print(f"S3 upload error: {e}")
        return None

def download_audio_from_s3(object_name: str, file_path: str) -> bool:
    """Download audio file from S3."""
    try:
        s3_client.download_file(BUCKET_NAME, object_name, file_path)
        return True
    except ClientError as e:
        print(f"S3 download error: {e}")
        return False

def delete_audio_from_s3(object_name: str) -> bool:
    """Delete audio file from S3."""
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=object_name)
        return True
    except ClientError as e:
        print(f"S3 delete error: {e}")
        return False
```

### 4. **Environment Variables**

**Problem:** `.env` file won't work on AWS

**Solution:** Use AWS Systems Manager Parameter Store or Secrets Manager

**Update code to read from AWS:**

```python
import boto3
import os

def get_secret(secret_name: str) -> str:
    """Get secret from AWS Secrets Manager."""
    if os.getenv('AWS_EXECUTION_ENV'):
        # Running on AWS
        client = boto3.client('secretsmanager', region_name='us-east-1')
        try:
            response = client.get_secret_value(SecretId=secret_name)
            return response['SecretString']
        except Exception as e:
            print(f"Error getting secret {secret_name}: {e}")
            return None
    else:
        # Local development
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv(secret_name)

# Usage
GROQ_API_KEY = get_secret('GROQ_API_KEY_2') or get_secret('GROQ_API_KEY')
```

### 5. **HTTPS/SSL Configuration**

**Problem:** WebRTC requires HTTPS in production

**Solution:** Use AWS Certificate Manager + Application Load Balancer

**Streamlit config for HTTPS:**

Create `.streamlit/config.toml`:

```toml
[server]
port = 8501
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 200

[browser]
serverAddress = "your-domain.com"
serverPort = 443
```

### 6. **Microservices Architecture**

**Problem:** Running all services on one EC2 instance doesn't scale

**Solution:** Use AWS ECS/Fargate or separate EC2 instances

**Docker Compose for AWS:**

```yaml
version: '3.8'

services:
  main-app:
    build: .
    ports:
      - "8501:8501"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - GROQ_API_KEY=${GROQ_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
    depends_on:
      - answer-service
      - fusion-service
      - emotion-service
      - insight-service
      - engagement-service

  answer-service:
    build: ./answer_service
    ports:
      - "8000:8000"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}

  fusion-service:
    build: ./fusion_service
    ports:
      - "8001:8001"

  emotion-service:
    build: ./emotion_service
    ports:
      - "8002:8002"

  insight-service:
    build: ./insight_service
    ports:
      - "8003:8003"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}

  engagement-service:
    build: ./engagement_service
    ports:
      - "8004:8004"
```

### 7. **Dockerfile Updates**

**Current Dockerfile issues:**
- Missing system dependencies
- No health checks
- Not optimized for production

**Fixed Dockerfile:**

```dockerfile
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run application
CMD ["streamlit", "run", "demo_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### 8. **Load Balancer Configuration**

**AWS Application Load Balancer settings:**

```yaml
# Target Group Health Check
HealthCheckPath: /_stcore/health
HealthCheckIntervalSeconds: 30
HealthCheckTimeoutSeconds: 5
HealthyThresholdCount: 2
UnhealthyThresholdCount: 3

# Sticky Sessions (required for WebRTC)
Stickiness:
  Enabled: true
  Type: lb_cookie
  DurationSeconds: 3600

# WebSocket Support
ProtocolVersion: HTTP1
```

### 9. **Security Group Configuration**

**Required inbound rules:**

```
Port 443 (HTTPS) - 0.0.0.0/0
Port 80 (HTTP) - 0.0.0.0/0 (redirect to 443)
Port 8501 (Streamlit) - Load Balancer only
Port 8000-8004 (Microservices) - VPC only
Port 3478 (TURN/STUN) - 0.0.0.0/0
Port 5349 (TURN/STUN TLS) - 0.0.0.0/0
```

### 10. **CloudFront CDN (Optional but Recommended)**

**Benefits:**
- Faster global access
- DDoS protection
- SSL/TLS termination

**CloudFront configuration:**

```yaml
Origins:
  - DomainName: your-alb.us-east-1.elb.amazonaws.com
    CustomOriginConfig:
      HTTPPort: 80
      HTTPSPort: 443
      OriginProtocolPolicy: https-only
      OriginSSLProtocols: [TLSv1.2]

DefaultCacheBehavior:
  ViewerProtocolPolicy: redirect-to-https
  AllowedMethods: [GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE]
  CachedMethods: [GET, HEAD, OPTIONS]
  Compress: true
  
  # WebSocket support
  ForwardedValues:
    QueryString: true
    Headers:
      - Host
      - Origin
      - Upgrade
      - Connection
```

## 📋 AWS Deployment Checklist

### Pre-Deployment

- [ ] Set up AWS RDS PostgreSQL database
- [ ] Create S3 bucket for file storage
- [ ] Configure AWS Secrets Manager for API keys
- [ ] Set up VPC with public/private subnets
- [ ] Configure security groups
- [ ] Register domain name (Route 53)
- [ ] Request SSL certificate (ACM)

### Deployment Steps

1. **Database Setup:**
   ```bash
   # Create RDS PostgreSQL instance
   aws rds create-db-instance \
     --db-instance-identifier psysense-db \
     --db-instance-class db.t3.micro \
     --engine postgres \
     --master-username admin \
     --master-user-password YourPassword123 \
     --allocated-storage 20
   ```

2. **S3 Bucket:**
   ```bash
   # Create S3 bucket
   aws s3 mb s3://psysense-audio-files
   
   # Set lifecycle policy (delete files after 7 days)
   aws s3api put-bucket-lifecycle-configuration \
     --bucket psysense-audio-files \
     --lifecycle-configuration file://lifecycle.json
   ```

3. **Secrets Manager:**
   ```bash
   # Store Groq API key
   aws secretsmanager create-secret \
     --name GROQ_API_KEY_2 \
     --secret-string "gsk_your_key_here"
   ```

4. **EC2 Instance:**
   ```bash
   # Launch EC2 instance (t3.medium recommended)
   # Install Docker
   sudo yum update -y
   sudo yum install -y docker
   sudo service docker start
   sudo usermod -a -G docker ec2-user
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

5. **Deploy Application:**
   ```bash
   # Clone repository
   git clone your-repo-url
   cd psysense
   
   # Set environment variables
   export DATABASE_URL="postgresql://admin:password@your-rds-endpoint:5432/psysense"
   export GROQ_API_KEY="your-key"
   export AWS_ACCESS_KEY_ID="your-key"
   export AWS_SECRET_ACCESS_KEY="your-secret"
   
   # Build and run
   docker-compose up -d
   ```

6. **Load Balancer:**
   ```bash
   # Create Application Load Balancer
   aws elbv2 create-load-balancer \
     --name psysense-alb \
     --subnets subnet-xxx subnet-yyy \
     --security-groups sg-xxx
   
   # Create target group
   aws elbv2 create-target-group \
     --name psysense-targets \
     --protocol HTTP \
     --port 8501 \
     --vpc-id vpc-xxx \
     --health-check-path /_stcore/health
   ```

7. **SSL Certificate:**
   ```bash
   # Request certificate
   aws acm request-certificate \
     --domain-name your-domain.com \
     --validation-method DNS
   
   # Add HTTPS listener to ALB
   aws elbv2 create-listener \
     --load-balancer-arn arn:aws:elasticloadbalancing:... \
     --protocol HTTPS \
     --port 443 \
     --certificates CertificateArn=arn:aws:acm:... \
     --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...
   ```

### Post-Deployment

- [ ] Test WebRTC connection from external network
- [ ] Verify database connectivity
- [ ] Test file upload/download to S3
- [ ] Check all microservices are running
- [ ] Monitor CloudWatch logs
- [ ] Set up CloudWatch alarms
- [ ] Configure auto-scaling (optional)
- [ ] Set up backup strategy

## 🔧 Configuration Files for AWS

### 1. `aws_config.py`

```python
import os
import boto3

# AWS Configuration
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'psysense-audio-files')
RDS_ENDPOINT = os.getenv('RDS_ENDPOINT')

# Database URL for AWS
if os.getenv('AWS_EXECUTION_ENV'):
    DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{RDS_ENDPOINT}:5432/{os.getenv('DB_NAME')}"
else:
    DATABASE_URL = "sqlite:///./psysense.db"

# Secrets Manager
def get_secret(secret_name):
    if os.getenv('AWS_EXECUTION_ENV'):
        client = boto3.client('secretsmanager', region_name=AWS_REGION)
        try:
            response = client.get_secret_value(SecretId=secret_name)
            return response['SecretString']
        except Exception as e:
            print(f"Error: {e}")
            return None
    else:
        return os.getenv(secret_name)

# API Keys
GROQ_API_KEY = get_secret('GROQ_API_KEY_2') or get_secret('GROQ_API_KEY')
```

### 2. `lifecycle.json` (S3 Lifecycle Policy)

```json
{
  "Rules": [
    {
      "Id": "DeleteOldAudioFiles",
      "Status": "Enabled",
      "Prefix": "audio/",
      "Expiration": {
        "Days": 7
      }
    }
  ]
}
```

### 3. `.ebextensions/01_packages.config` (Elastic Beanstalk)

```yaml
packages:
  yum:
    postgresql-devel: []
    gcc: []
    python3-devel: []
    libGL: []
    libglib2.0-0: []

option_settings:
  aws:elasticbeanstalk:application:environment:
    PYTHONPATH: "/var/app/current:$PYTHONPATH"
  aws:elasticbeanstalk:container:python:
    WSGIPath: "application:application"
```

## 🚨 Critical AWS-Specific Issues

### Issue 1: WebRTC Behind NAT

**Symptom:** Camera works locally but not on AWS

**Fix:** TURN server configuration (see above)

### Issue 2: File Permissions

**Symptom:** Can't write temporary files

**Fix:**
```python
import tempfile
import os

# Use /tmp on AWS Lambda/ECS
TEMP_DIR = os.getenv('TEMP_DIR', '/tmp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Create temp file
temp_file = tempfile.NamedTemporaryFile(
    suffix=".wav",
    dir=TEMP_DIR,
    delete=False
)
```

### Issue 3: Cold Start

**Symptom:** First request is very slow

**Fix:** Keep-alive Lambda or use ECS with minimum task count

### Issue 4: Memory Limits

**Symptom:** Out of memory errors

**Fix:** Use larger instance type (t3.medium minimum)

## 📊 AWS Cost Estimation

**Monthly costs (approximate):**

- EC2 t3.medium (24/7): $30
- RDS db.t3.micro: $15
- S3 storage (100GB): $2.30
- Data transfer (100GB): $9
- ALB: $16
- CloudFront (optional): $10
- **Total: ~$82/month**

**Cost optimization:**
- Use Reserved Instances (save 40%)
- Auto-scaling (scale down at night)
- S3 lifecycle policies
- CloudFront caching

## 🔐 Security Best Practices

1. **Use IAM roles** instead of access keys
2. **Enable VPC Flow Logs** for monitoring
3. **Use AWS WAF** for DDoS protection
4. **Enable CloudTrail** for audit logs
5. **Encrypt data at rest** (RDS, S3)
6. **Use Secrets Manager** for all credentials
7. **Enable MFA** for AWS console access
8. **Regular security audits** with AWS Inspector

## 📈 Monitoring & Logging

**CloudWatch Metrics to monitor:**
- CPU utilization
- Memory utilization
- Network in/out
- Request count
- Error rate
- Response time

**CloudWatch Logs:**
```python
import logging
import watchtower

# Configure CloudWatch logging
logger = logging.getLogger(__name__)
logger.addHandler(watchtower.CloudWatchLogHandler(
    log_group='/aws/psysense/application',
    stream_name='main-app'
))
```

## ✅ Final AWS Deployment Checklist

- [ ] TURN server configured
- [ ] PostgreSQL RDS set up
- [ ] S3 bucket created
- [ ] Secrets Manager configured
- [ ] HTTPS/SSL enabled
- [ ] Load balancer configured
- [ ] Security groups set up
- [ ] CloudWatch monitoring enabled
- [ ] Backup strategy in place
- [ ] Auto-scaling configured (optional)
- [ ] Domain name configured
- [ ] WebRTC tested from external network

---

**Ready for AWS deployment after applying these fixes!**
