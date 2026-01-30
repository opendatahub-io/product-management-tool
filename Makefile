.PHONY: build

CONTAINER_MANAGER ?= podman
IMAGE_TAG ?= $(shell git rev-parse --short=8 HEAD)
RELEASE_TAG ?= latest

#if RELEASE_TAG is set to empty, make will set it to latest
ifeq ($(RELEASE_TAG),)
RELEASE_TAG := latest
endif

GITLAB_IMAGE_REPO ?= registry.gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management
QUAY_IMAGE_REPO ?= quay.io/aipcc-cicd/aipcc-product-management
QUAY_IMAGE_NAME ?= $(QUAY_IMAGE_REPO):$(RELEASE_TAG)
GITLAB_IMAGE_NAME ?= $(GITLAB_IMAGE_REPO):$(IMAGE_TAG)

ARCH ?= $(shell if [ "$$(uname -m)" = "aarch64" ]; then echo "arm64"; elif [ "$$(uname -m)" = "x86_64" ]; then echo "amd64"; else uname -m; fi)

showarch:
	echo ${ARCH}

build:
	${CONTAINER_MANAGER} build --platform linux/$(ARCH) -t $(GITLAB_IMAGE_NAME)-$(ARCH) .

push:
	${CONTAINER_MANAGER} push $(GITLAB_IMAGE_NAME)-$(ARCH)

manifest-delete:
	${CONTAINER_MANAGER} manifest rm $(GITLAB_IMAGE_NAME)

manifest-create:
	${CONTAINER_MANAGER} manifest create $(GITLAB_IMAGE_NAME)

manifest-build:
	${CONTAINER_MANAGER} manifest add $(GITLAB_IMAGE_NAME) $(GITLAB_IMAGE_REPO):$(IMAGE_TAG)-amd64
	${CONTAINER_MANAGER} manifest add $(GITLAB_IMAGE_NAME) $(GITLAB_IMAGE_REPO):$(IMAGE_TAG)-arm64

manifest-push:
	${CONTAINER_MANAGER} manifest push $(GITLAB_IMAGE_NAME)

tag:
	${CONTAINER_MANAGER} tag ${GITLAB_IMAGE_NAME} ${GITLAB_IMAGE_REPO}:${RELEASE_TAG} 

release:
	skopeo copy -a docker://$(GITLAB_IMAGE_NAME) docker://$(QUAY_IMAGE_NAME)
