#!/bin/bash

# GCloud Run deployment script for Physics Discovery System v3.0
# Author: RAP Corp Engineering Team
# Description: Production-quality deployment with health checks, rollback, and blue/green deployment
# Usage: ./deploy/deploy.sh [environment] [service_name] [image_tag]

set -euo pipefail

# Configuration variables
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
readonly CONFIG_DIR="$PROJECT_ROOT/config"
readonly LOGS_DIR="$PROJECT_ROOT/logs"

# Default values
DEFAULT_ENVIRONMENT="staging"
DEFAULT_SERVICE_NAME="physics-discovery-api"
DEFAULT_IMAGE_TAG="latest"
DEFAULT_REGION="us-central1"
DEFAULT_PROJECT_ID="rap-corp-physics"

# Parse command line arguments
ENVIRONMENT="${1:-$DEFAULT_ENVIRONMENT}"
SERVICE_NAME="${2:-$DEFAULT_SERVICE_NAME}"
IMAGE_TAG="${3:-$DEFAULT_IMAGE_TAG}"
REGION="${4:-$DEFAULT_REGION}"
PROJECT_ID="${5:-$DEFAULT_PROJECT_ID}"

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# Create logs directory if it doesn't exist
create_logs_directory() {
    mkdir -p "$LOGS_DIR"
}

# Validate prerequisites
validate_prerequisites() {
    log_info "Validating prerequisites..."
    
    # Check if gcloud CLI is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install Google Cloud SDK."
        exit 1
    fi
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker."
        exit 1
    fi
    
    # Check if required config files exist
    if [[ ! -f "$CONFIG_DIR/environments/$ENVIRONMENT.env" ]]; then
        log_error "Environment config file not found: $CONFIG_DIR/environments/$ENVIRONMENT.env"
        exit 1
    fi
    
    # Verify gcloud authentication
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 > /dev/null; then
        log_error "Not authenticated with gcloud. Run 'gcloud auth login'"
        exit 1
    fi
    
    log_success "Prerequisites validated"
}

# Load environment configuration
load_environment_config() {
    log_info "Loading environment configuration for: $ENVIRONMENT"
    
    local env_file="$CONFIG_DIR/environments/$ENVIRONMENT.env"
    
    if [[ -f "$env_file" ]]; then
        set -a
        source "$env_file"
        set +a
        log_success "Environment configuration loaded"
    else
        log_error "Environment configuration file not found: $env_file"
        exit 1
    fi
}

# Set gcloud project and region
configure_gcloud() {
    log_info "Configuring gcloud project and region..."
    
    gcloud config set project "$PROJECT_ID"
    gcloud config set run/region "$REGION"
    
    log_success "Gcloud configured for project: $PROJECT_ID, region: $REGION"
}

# Build and push Docker image
build_and_push_image() {
    local image_name="gcr.io/$PROJECT_ID/$SERVICE_NAME"
    local full_image_tag="$image_name:$IMAGE_TAG"
    
    log_info "Building Docker image: $full_image_tag"
    
    cd "$PROJECT_ROOT"
    
    # Build the Docker image
    docker build \
        --build-arg ENVIRONMENT="$ENVIRONMENT" \
        --build-arg BUILD_VERSION="$IMAGE_TAG" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        -t "$full_image_tag" \
        -f Dockerfile .
    
    if [[ $? -ne 0 ]]; then
        log_error "Docker build failed"
        exit 1
    fi
    
    log_success "Docker image built successfully"
    
    # Push the image to Google Container Registry
    log_info "Pushing image to GCR..."
    docker push "$full_image_tag"
    
    if [[ $? -ne 0 ]]; then
        log_error "Docker push failed"
        exit 1
    fi
    
    log_success "Image pushed to GCR: $full_image_tag"
    echo "$full_image_tag"
}

# Prepare environment variables for Cloud Run
prepare_environment_variables() {
    local env_vars=""
    local secrets=""
    
    # Standard environment variables
    env_vars+="ENVIRONMENT=$ENVIRONMENT,"
    env_vars+="SERVICE_NAME=$SERVICE_NAME,"
    env_vars+="VERSION=$IMAGE_TAG,"
    env_vars+="PROJECT_ID=$PROJECT_ID,"
    
    # Database configuration
    if [[ -n "${DATABASE_URL:-}" ]]; then
        env_vars