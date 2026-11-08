SATOOSHI_FIRMWARE_DIR ?= $(abspath $(BR2_EXTERNAL_SATOOSHI_PATH)/../..)
SATOOSHI_CARGO_VENDOR ?= $(SATOOSHI_FIRMWARE_DIR)/build-minimal/cargo-vendor
include $(sort $(wildcard $(BR2_EXTERNAL_SATOOSHI_PATH)/package/*/*.mk))
include $(BR2_EXTERNAL_SATOOSHI_PATH)/linux/early-logo.mk
