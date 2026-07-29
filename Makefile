.PHONY: build

CONTAINER_MANAGER ?= podman
IMAGE_TAG ?= $(shell git rev-parse --short=8 HEAD)
RELEASE_TAG ?= latest

#if RELEASE_TAG is set to empty, make will set it to latest
ifeq ($(RELEASE_TAG),)
RELEASE_TAG := latest
endif

IMAGE_REPO ?= quay.io/aipcc-cicd/aipcc-product-management
IMAGE_NAME ?= $(IMAGE_REPO):$(IMAGE_TAG)

LABELS ?=

ARCH ?= $(shell if [ "$$(uname -m)" = "aarch64" ]; then echo "arm64"; elif [ "$$(uname -m)" = "x86_64" ]; then echo "amd64"; else uname -m; fi)

showarch:
	echo ${ARCH}

build:
	${CONTAINER_MANAGER} build --platform linux/$(ARCH) $(LABELS) -t $(IMAGE_NAME)-$(ARCH) .

push:
	${CONTAINER_MANAGER} push $(IMAGE_NAME)-$(ARCH)

manifest-delete:
	${CONTAINER_MANAGER} manifest rm $(IMAGE_NAME)

manifest-create:
	${CONTAINER_MANAGER} manifest create $(IMAGE_NAME)

manifest-build:
	${CONTAINER_MANAGER} manifest add $(IMAGE_NAME) $(IMAGE_REPO):$(IMAGE_TAG)-amd64
	${CONTAINER_MANAGER} manifest add $(IMAGE_NAME) $(IMAGE_REPO):$(IMAGE_TAG)-arm64

manifest-push:
	${CONTAINER_MANAGER} manifest push $(IMAGE_NAME)

tag:
	${CONTAINER_MANAGER} tag ${IMAGE_NAME} ${IMAGE_REPO}:${RELEASE_TAG} 

release:
	skopeo copy -a docker://$(IMAGE_NAME) docker://$(IMAGE_REPO):$(RELEASE_TAG)
